"use client";

/**
 * /me/print — a printable, personalized checklist built from the student's
 * live dashboard data. Opened from the Checklist panel's Print button:
 *
 *   ?scope=unit&unit=3   one sheet for one unit (the default: "this unit")
 *   ?scope=remaining     one sheet per unit that still has open work
 *   ?scope=missing       one sheet of past-due work
 *
 * Re-fetches the dashboard so a printout is never stale, then opens the
 * browser's print dialog (print to paper or Save as PDF).
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { fmtDate } from "@/components/dashboard/DashboardView";
import { getStudentDashboard, retryUnlessAuth } from "@/lib/api/client";
import type { DashChecklistRow, StudentDashboard } from "@/lib/api/types";
import { DASHBOARD_QR_SVG, DASHBOARD_URL_SHORT } from "@/lib/dashboardQr";
import { loadSession } from "@/lib/studentSession";
import "./print.css";

const TYPE_NAME = { video: "Video", scenario: "Scenario", frq: "FRQ" } as const;

interface Sheet {
  title: string;
  subtitle: string;
  rows: DashChecklistRow[];
  /** Group rows under chapter headings (unit sheets) or by unit (past-due). */
  groupBy: "chapter" | "unit";
}

function displayName(name: string): string {
  if (!name.includes(",")) return name;
  const [last, first] = name.split(",", 2);
  return `${first.trim()} ${last.trim()}`;
}

function rowNote(r: DashChecklistRow): { text: string; cls: string } | null {
  if (r.score != null) return { text: `${Number.isInteger(r.score) ? r.score : r.score.toFixed(1)}%`, cls: "ok" };
  if (r.status === "pending_grade") return { text: "turned in, awaiting grade", cls: "ok" };
  if (r.almost_label) return { text: r.almost_label, cls: r.status === "missing" ? "bad" : "" };
  if (r.status === "missing") return { text: r.state === "in_progress" ? "started, past due" : "past due", cls: "bad" };
  if (r.state === "in_progress") return { text: "in progress", cls: "" };
  return null;
}

function verb(r: DashChecklistRow): string {
  if (r.type === "video") return "Watch";
  if (r.type === "scenario") return "Play + submit the reflection for";
  return "Write and submit";
}

function buildSheets(d: StudentDashboard, scope: string, unitParam: number | null): Sheet[] {
  const unitSheet = (u: StudentDashboard["units"][number]): Sheet => ({
    title: `Unit ${u.unit} Checklist`,
    subtitle: `Unit ${u.unit} · ${u.name} · target dates ${fmtDate(u.start)} – ${fmtDate(u.end)}`,
    rows: d.checklist.filter((r) => r.unit === u.unit),
    groupBy: "chapter",
  });
  if (scope === "missing") {
    return [{
      title: "Past-Due Checklist",
      subtitle: `Everything past its target date and not yet turned in. ${d.late_policy}`,
      rows: d.checklist.filter((r) => r.status === "missing"),
      groupBy: "unit",
    }];
  }
  if (scope === "remaining") {
    const open = d.units.filter((u) => u.done < u.total);
    return (open.length ? open : d.units.slice(-1)).map(unitSheet);
  }
  const current = d.units.find((u) => u.state === "current") ?? d.units.find((u) => u.done < u.total) ?? d.units[0];
  const u = d.units.find((x) => x.unit === unitParam) ?? current;
  return u ? [unitSheet(u)] : [];
}

function groups(sheet: Sheet, d: StudentDashboard): { label: string; when: string; rows: DashChecklistRow[] }[] {
  const out: { label: string; when: string; rows: DashChecklistRow[] }[] = [];
  for (const r of sheet.rows) {
    const label =
      sheet.groupBy === "unit"
        ? `Unit ${r.unit} · ${d.units.find((u) => u.unit === r.unit)?.name ?? ""}`
        : r.chapter
          ? `Chapter ${r.chapter}`
          : `Unit ${r.unit} FRQ`;
    let g = out.find((x) => x.label === label);
    if (!g) {
      g = { label, when: "", rows: [] };
      out.push(g);
    }
    g.rows.push(r);
  }
  for (const g of out) {
    const dates = g.rows.map((r) => r.target).sort();
    g.when = dates[0] === dates[dates.length - 1] ? `target ${fmtDate(dates[0])}` : `targets ${fmtDate(dates[0])} – ${fmtDate(dates[dates.length - 1])}`;
  }
  return out;
}

function SheetView({ sheet, d, student }: { sheet: Sheet; d: StudentDashboard; student: string }) {
  const week = new Set(d.this_week.keys);
  const done = sheet.rows.filter((r) => r.score != null || r.status === "pending_grade").length;
  const pastDue = sheet.rows.filter((r) => r.status === "missing").length;
  const s = d.summary;
  return (
    <section className="ckp-sheet">
      <div className="ckp-head">
        <div>
          <h1>
            {displayName(student)} — {sheet.title}
          </h1>
          <div className="sub">
            {d.course} · {sheet.subtitle}
          </div>
        </div>
        <div className="meta">
          Printed <b>{fmtDate(d.as_of)}</b>
          <br />
          Live version: {DASHBOARD_URL_SHORT}
        </div>
      </div>

      <div className="ckp-stats">
        <div>
          <span>Done on this sheet</span>
          <b>
            {done} / {sheet.rows.length}
          </b>
        </div>
        <div>
          <span>Past due here</span>
          <b style={{ color: pastDue ? "#b42318" : "#1a7a2e" }}>{pastDue}</b>
        </div>
        <div>
          <span>Current grade</span>
          <b>
            {s.grade != null ? `${s.grade.toFixed(0)}% ${s.letter}` : "—"}
          </b>
        </div>
        <div>
          <span>Pace</span>
          <b>{s.pace_label}</b>
        </div>
      </div>

      {sheet.rows.length === 0 && <div className="ckp-empty">Nothing here. You&apos;re all caught up!</div>}
      {groups(sheet, d).map((g) => (
        <div key={g.label}>
          <h2>
            {g.label} <span>{g.when}</span>
          </h2>
          {g.rows.map((r) => {
            const checked = r.score != null || r.status === "pending_grade";
            const note = rowNote(r);
            return (
              <div key={r.key} className={`ckp-item${checked ? " done" : ""}${week.has(r.key) ? " week" : ""}`}>
                <span className="box">{checked ? "✓" : " "}</span>
                <span className="label">
                  <span className="ty">{TYPE_NAME[r.type]}</span>
                  {verb(r)} <b>{r.title}</b>
                  {note && <span className={`note ${note.cls}`}>{note.text}</span>}
                </span>
                <span className="due">
                  {r.flexible ? "by " : ""}
                  {fmtDate(r.target)}
                  {week.has(r.key) ? " · this week" : ""}
                </span>
              </div>
            );
          })}
        </div>
      ))}

      <div className="ckp-foot">
        <div className="ckp-progress">
          <span>
            <b>
              {done} of {sheet.rows.length}
            </b>{" "}
            done
          </span>
          <span className="bar">
            <div style={{ width: `${sheet.rows.length ? (100 * done) / sheet.rows.length : 0}%` }} />
          </span>
          <span>{d.late_policy}</span>
        </div>
        <div className="ckp-dash">
          {/* Static, build-time constant SVG (lib/dashboardQr.ts) — not user content. */}
          <div className="qr" dangerouslySetInnerHTML={{ __html: DASHBOARD_QR_SVG }} />
          <div>
            This sheet is a snapshot from {fmtDate(d.as_of)}. Your <b>live dashboard</b> updates the moment you finish
            something: scan the code or go to <b>{DASHBOARD_URL_SHORT}</b> and enter your access code. Bold dates are
            this week&apos;s targets.
          </div>
        </div>
      </div>
    </section>
  );
}

function PrintContent() {
  const params = useSearchParams();
  const scope = params.get("scope") ?? "unit";
  const unitParam = params.get("unit") ? Number(params.get("unit")) : null;
  const [hasSession, setHasSession] = useState<boolean | null>(null);
  useEffect(() => setHasSession(!!loadSession()), []);

  const q = useQuery({
    queryKey: ["student-dashboard-print"],
    queryFn: getStudentDashboard,
    enabled: hasSession === true,
    retry: retryUnlessAuth,
  });

  const printed = useRef(false);
  useEffect(() => {
    // ?autoprint=0 previews the sheets without opening the dialog.
    if (!q.data?.dashboard || printed.current || params.get("autoprint") === "0") return;
    printed.current = true;
    // Let layout and the QR settle before the dialog snapshots the page.
    const t = window.setTimeout(() => window.print(), 400);
    return () => window.clearTimeout(t);
  }, [q.data, params]);

  if (hasSession === null) return null;
  if (!hasSession || q.error) {
    return (
      <div className="ckp-bar" style={{ marginTop: 40 }}>
        <p>Open your dashboard and enter your access code first, then use its Print button.</p>
        <Link href="/me">Go to my dashboard</Link>
      </div>
    );
  }
  if (!q.data) return <div className="ckp-bar"><p>Building your checklist…</p></div>;
  const d = q.data.dashboard;
  if (!d) {
    return (
      <div className="ckp-bar" style={{ marginTop: 40 }}>
        <p>Your class isn&apos;t set up for the dashboard yet.</p>
        <Link href="/me">Back</Link>
      </div>
    );
  }
  const sheets = buildSheets(d, scope, unitParam);
  return (
    <>
      <div className="ckp-bar">
        <p>
          {sheets.length} page{sheets.length === 1 ? "" : "s"} · print it, or choose “Save as PDF” in the print dialog.
        </p>
        <span style={{ display: "flex", gap: 8 }}>
          <Link href="/me">← Dashboard</Link>
          <button className="primary" onClick={() => window.print()}>
            Print
          </button>
        </span>
      </div>
      {sheets.map((sh) => (
        <SheetView key={sh.title} sheet={sh} d={d} student={q.data!.student.name} />
      ))}
    </>
  );
}

export default function PrintChecklistPage() {
  return (
    <main className="ckp">
      <Suspense fallback={null}>
        <PrintContent />
      </Suspense>
    </main>
  );
}
