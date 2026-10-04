"use client";

/**
 * Presentational half of the student dashboard (/me). Everything here is
 * derived from one GET /student/dashboard response; the page owns the
 * session, loading, and sign-in gate.
 */

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  DashBadge,
  DashChecklistRow,
  DashMove,
  DashStatus,
  StudentDashboard,
  StudentDashboardResponse,
} from "@/lib/api/types";
import { burstConfetti } from "./confetti";
import { Icon } from "./icons";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-08" → "Oct 8" without timezone drift. */
export function fmtDate(iso: string): string {
  const [, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}`;
}

const TYPE_NAME = { video: "Video", scenario: "Scenario", frq: "FRQ" } as const;

function fmtPct(v: number | null | undefined): string {
  return v == null ? "—" : `${Number.isInteger(v) ? v : v.toFixed(1)}%`;
}

function useAnimatedNumber(target: number, ms = 1100): number {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setV(target);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      setV(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

function ActionLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
}) {
  if (href.startsWith("/")) {
    return (
      <Link href={href} className={className}>
        {children}
      </Link>
    );
  }
  return (
    <a href={href} className={className} rel="noopener">
      {children}
    </a>
  );
}

function AltLink({ href }: { href: string | null }) {
  if (!href) return null;
  return (
    <span className="dsh-alt">
      Link blocked on this wifi? <a href={href} rel="noopener">Try the backup link</a>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function GradeRing({ grade }: { grade: number | null }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(grade ?? 0));
    return () => cancelAnimationFrame(id);
  }, [grade]);
  const color = grade == null ? "#6f8780" : grade >= 80 ? "#3fb37f" : grade >= 70 ? "#e0a429" : "#ef6b6b";
  return (
    <svg className="dsh-ring" width="128" height="128" viewBox="0 0 128 128" aria-hidden>
      <defs>
        <linearGradient id="dshRing" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={color} />
          <stop offset="1" stopColor="#d8ad5b" />
        </linearGradient>
      </defs>
      <circle cx="64" cy="64" r={r} fill="none" stroke="rgba(0,0,0,.3)" strokeWidth="12" />
      <circle
        cx="64"
        cy="64"
        r={r}
        fill="none"
        stroke="url(#dshRing)"
        strokeWidth="12"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - Math.min(100, shown) / 100)}
        transform="rotate(-90 64 64)"
      />
    </svg>
  );
}

function Hero({ d }: { d: StudentDashboard }) {
  const s = d.summary;
  const g = useAnimatedNumber(s.grade ?? 0);
  const lvl = d.game.level;
  const xp = useAnimatedNumber(d.game.xp);
  return (
    <div className="dsh-grid dsh-hero">
      <section className="dsh-panel" aria-label="Current grade">
        <div className="dsh-k">Current grade</div>
        <div className="dsh-ringwrap" style={{ marginTop: 10 }}>
          <GradeRing grade={s.grade} />
          <div>
            <div className="dsh-big">
              {s.grade == null ? "—" : `${g.toFixed(0)}%`}
              {s.letter && <small>{s.letter}</small>}
            </div>
            <div className="dsh-note">
              Counts past-due missing work as 0.
              {s.grade_submitted != null && (
                <>
                  <br />
                  On work you&apos;ve turned in: <b>{fmtPct(s.grade_submitted)}</b>
                </>
              )}
            </div>
          </div>
        </div>
        {s.catch_up && s.catch_up.grade_after != null && (
          <div className="dsh-note" style={{ marginTop: 12 }}>
            <Icon name="bolt" className="st-inline" />Catch up on {s.catch_up.items} item
            {s.catch_up.items === 1 ? "" : "s"} → about{" "}
            <b style={{ color: "#d8ad5b" }}>
              {s.catch_up.grade_after.toFixed(0)}% {s.catch_up.letter_after}
            </b>
          </div>
        )}
      </section>

      <section className="dsh-panel" aria-label="Pace">
        <div className="dsh-k">Pace vs. the schedule</div>
        <div className={`dsh-pace pace-${s.pace}`}>
          <i style={{ background: "currentColor" }} />
          {s.pace_label}
        </div>
        <div className="dsh-note">
          {s.missing_count > 0
            ? `${s.missing_count} past-due item${s.missing_count === 1 ? "" : "s"} still open`
            : s.early_count > 0
              ? `Nothing past due · ${s.early_count} finished early`
              : "Nothing past due — nice."}
        </div>
        <div className="dsh-mini">
          <div>
            <b>
              {s.done_count}
              <span style={{ fontSize: 12 }}>/{s.total_count}</span>
            </b>
            <span>completed</span>
          </div>
          <div>
            <b>{s.due_count}</b>
            <span>due so far</span>
          </div>
          <div>
            <b style={{ color: s.missing_count ? "#ef6b6b" : "#3fb37f" }}>{s.missing_count}</b>
            <span>missing</span>
          </div>
        </div>
      </section>

      <section className="dsh-panel" aria-label="Level and streak">
        <div className="dsh-k">Level {lvl.number}</div>
        <div className="dsh-level">
          <b>{lvl.name}</b>
          <span>{Math.round(xp).toLocaleString()} XP</span>
        </div>
        <div className="dsh-xpbar" role="progressbar" aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={Math.round(lvl.progress * 100)} aria-label="Progress to next level">
          <div style={{ width: `${Math.max(3, lvl.progress * 100)}%` }} />
        </div>
        <div className="dsh-note">
          {lvl.next_at != null
            ? `${(lvl.next_at - d.game.xp).toLocaleString()} XP to ${lvl.next_name}`
            : "Max level reached"}
        </div>
        <div className="dsh-chips">
          <span className="dsh-chip" title="Weeks in a row where every pacing-guide target was done on time">
            <Icon name="flame" /> {d.game.streak.current_weeks}-week streak
          </span>
          <span className="dsh-chip">
            <Icon name="bolt" /> {d.game.activity.last_7_days} done this week
          </span>
          <span className="dsh-chip">
            <Icon name="flag" /> {d.game.badges.filter((b) => b.earned).length} badges
          </span>
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Next moves
// ---------------------------------------------------------------------------

function verb(m: DashMove): string {
  if (m.kind === "finish") return m.type === "scenario" ? "Submit reflection" : "Finish";
  if (m.kind === "resume") return "Resume";
  if (m.kind === "revise") return "Revise";
  return m.type === "video" ? "Watch" : m.type === "scenario" ? "Play" : "Write";
}

function why(m: DashMove): React.ReactNode {
  const gain = m.grade_delta >= 0.1 ? (
    <>
      worth <span className="dsh-gain">+{m.grade_delta.toFixed(1)} pts</span> to your grade
    </>
  ) : null;
  const time = `~${m.effort_minutes} min`;
  if (m.kind === "revise") {
    return (
      <>
        Your best attempt is the one that counts{m.label ? ` · ${m.label}` : ""} · {time}
        {gain && <> · up to {gain}</>}
      </>
    );
  }
  if (m.past_due) {
    return (
      <>
        Past due since {fmtDate(m.target)} · {time}
        {gain && <> · {gain}</>}
      </>
    );
  }
  const days = m.days_until_due;
  return (
    <>
      Due {fmtDate(m.target)} ({days === 0 ? "today" : days === 1 ? "tomorrow" : `in ${days} days`}) · {time} ·{" "}
      {m.grade_delta >= 0.1 ? (
        <>
          on time it&apos;s worth <span className="dsh-gain">+{m.grade_delta.toFixed(1)} pts</span>
        </>
      ) : (
        "keeps you on pace"
      )}
    </>
  );
}

function NextMoves({ moves }: { moves: DashMove[] }) {
  if (!moves.length) {
    return (
      <div className="dsh-panel">
        <div className="dsh-k">Your next move</div>
        <h3 style={{ margin: "8px 0 4px" }}>You&apos;re all caught up 🎉</h3>
        <div className="dsh-why">Nothing is due in the next 10 days. Get a head start on the next unit below.</div>
      </div>
    );
  }
  const [top, ...rest] = moves;
  return (
    <>
      <div className="dsh-spot">
        <div className="dsh-spot-in">
          <div>
            <div className="dsh-k" style={{ color: "#d8ad5b" }}>
              Your highest-impact move{top.kind === "finish" ? " · quick win" : ""}
            </div>
            <h3>
              {verb(top)}: {top.title}
            </h3>
            <div className="dsh-why">{why(top)}</div>
          </div>
          <div>
            <ActionLink href={top.link} className="dsh-go">
              {verb(top)} →
            </ActionLink>
            <AltLink href={top.alt_link} />
          </div>
        </div>
      </div>
      {rest.length > 0 && (
        <div className="dsh-moves">
          {rest.map((m) => (
            <ActionLink key={m.key + m.kind} href={m.link} className="dsh-move">
              <div className="dsh-k" style={{ color: m.past_due ? "#ef6b6b" : undefined }}>
                {verb(m)} · {TYPE_NAME[m.type]}
              </div>
              <div className="t">{m.title}</div>
              <div className="m">{why(m)}</div>
            </ActionLink>
          ))}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Unit trail + checklist
// ---------------------------------------------------------------------------

function Trail({ d }: { d: StudentDashboard }) {
  return (
    <div className="dsh-panel">
      <div className="dsh-trail">
        {d.units.map((u) => {
          const r = 24;
          const c = 2 * Math.PI * r;
          const p = u.total ? u.done / u.total : 0;
          const stroke = u.state === "cleared" ? "#d8ad5b" : u.missing ? "#ef6b6b" : "#3987e5";
          return (
            <div key={u.unit} className={`dsh-node ${u.state}`}>
              <svg width="62" height="62" viewBox="0 0 62 62" aria-hidden>
                <circle cx="31" cy="31" r="29" fill="#0f2725" />
                <circle cx="31" cy="31" r={r} fill="none" stroke="rgba(0,0,0,.35)" strokeWidth="6" />
                <circle cx="31" cy="31" r={r} fill="none" stroke={stroke} strokeWidth="6" strokeLinecap="round"
                  strokeDasharray={c} strokeDashoffset={c * (1 - p)} transform="rotate(-90 31 31)" />
                {u.state === "cleared" ? (
                  <path d="M22 31.5l6 6 12-12" fill="none" stroke="#d8ad5b" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
                ) : (
                  <text x="31" y="36" textAnchor="middle" fontSize="15" fontWeight="800" fill="#f3eee2">{u.unit}</text>
                )}
              </svg>
              <div>
                <div className="n">Unit {u.unit}{u.state === "current" ? " · now" : ""}</div>
                <div className="s">{u.name}</div>
                <div className="s">
                  {u.done}/{u.total} done{u.missing ? ` · ${u.missing} missing` : ""}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const STATUS: Record<DashStatus, { icon: string; color: string; label: string }> = {
  done_on_time: { icon: "check", color: "#3fb37f", label: "Done on time" },
  done: { icon: "check", color: "#3fb37f", label: "Done" },
  done_late: { icon: "check", color: "#a9bab4", label: "Done (late)" },
  pending_grade: { icon: "hourglass", color: "#d8ad5b", label: "Waiting for a grade" },
  missing: { icon: "alert", color: "#ef6b6b", label: "Past due" },
  in_progress: { icon: "half", color: "#3987e5", label: "In progress" },
  upcoming: { icon: "dot", color: "#6f8780", label: "Upcoming" },
};

function rowAction(r: DashChecklistRow): { text: string; href: string | null } {
  if (!r.available || !r.link) {
    return { text: r.score != null ? "" : "Not open yet", href: null };
  }
  if (r.score != null) return r.can_revise ? { text: "Revise", href: r.link } : { text: "", href: null };
  if (r.status === "pending_grade") return { text: "", href: null };
  if (r.almost_label) return { text: r.type === "scenario" ? "Submit reflection" : "Finish", href: r.link };
  if (r.state === "in_progress") return { text: "Resume", href: r.link };
  return { text: r.type === "video" ? "Watch" : r.type === "scenario" ? "Play" : "Write", href: r.link };
}

/** Split button: one click prints this unit; the caret offers the rest. */
function PrintMenu({ d, current }: { d: StudentDashboard; current: number }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const remaining = d.units.filter((u) => u.done < u.total).length;
  const go = (qs: string) => {
    setOpen(false);
    window.open(`/me/print?${qs}`, "_blank", "noopener");
  };
  return (
    <div className="dsh-print" ref={ref}>
      <button className="dsh-print-main" onClick={() => go(`scope=unit&unit=${current}`)}
        title={`Print a personalized Unit ${current} checklist`}>
        <Icon name="printer" className="st-inline" />Print Unit {current} checklist
      </button>
      <button className="dsh-print-caret" aria-label="More print options" aria-expanded={open}
        aria-haspopup="menu" onClick={() => setOpen((v) => !v)}>
        ▾
      </button>
      {open && (
        <div className="dsh-print-menu" role="menu">
          <button role="menuitem" onClick={() => go(`scope=unit&unit=${current}`)}>
            This unit <span>Unit {current} · 1 page</span>
          </button>
          <button role="menuitem" onClick={() => go("scope=remaining")}>
            All remaining units <span>{remaining} page{remaining === 1 ? "" : "s"}</span>
          </button>
          {d.summary.missing_count > 0 && (
            <button role="menuitem" onClick={() => go("scope=missing")}>
              Past-due only <span>{d.summary.missing_count} item{d.summary.missing_count === 1 ? "" : "s"}</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Checklist({ d }: { d: StudentDashboard }) {
  const current = d.units.find((u) => u.state === "current")?.unit ?? d.units[0]?.unit ?? 1;
  const [unit, setUnit] = useState<number | "missing">(d.summary.missing_count > 0 ? "missing" : current);
  const week = useMemo(() => new Set(d.this_week.keys), [d.this_week.keys]);
  const rows =
    unit === "missing" ? d.checklist.filter((r) => r.status === "missing") : d.checklist.filter((r) => r.unit === unit);
  return (
    <div className="dsh-panel">
      <PrintMenu d={d} current={current} />
      <div className="dsh-tabs" role="tablist" aria-label="Checklist filter">
        {d.summary.missing_count > 0 && (
          <button className="dsh-tab" role="tab" aria-selected={unit === "missing"} onClick={() => setUnit("missing")}>
            Past due ({d.summary.missing_count})
          </button>
        )}
        {d.units.map((u) => (
          <button key={u.unit} className="dsh-tab" role="tab" aria-selected={unit === u.unit} onClick={() => setUnit(u.unit)}>
            Unit {u.unit} · {u.done}/{u.total}
          </button>
        ))}
      </div>
      <ul className="dsh-list">
        {rows.map((r) => {
          const st = STATUS[r.status];
          const act = rowAction(r);
          return (
            <li key={r.key} className={`dsh-row${week.has(r.key) ? " week" : ""}`}>
              <span style={{ color: st.color }}>
                <Icon name={st.icon} className="st" title={st.label} />
              </span>
              <div>
                <span className="ti">{r.title}</span>
                <span className="ty">{TYPE_NAME[r.type]}</span>
                <div className="meta">
                  {r.flexible ? "By " : "Target "}
                  {fmtDate(r.target)}
                  {week.has(r.key) && " · this week"} · {st.label}
                  {r.almost_label && r.score == null ? ` · ${r.almost_label}` : ""}
                </div>
              </div>
              <span className="sc" style={{ color: r.score == null ? "#6f8780" : undefined }}>
                {r.score != null ? fmtPct(r.score) : r.status === "missing" ? "0" : "—"}
              </span>
              {act.href ? (
                <ActionLink href={act.href} className="act">
                  {act.text} →
                </ActionLink>
              ) : (
                <span className="act muted">{act.text}</span>
              )}
            </li>
          );
        })}
        {rows.length === 0 && <li className="dsh-row"><span /><span className="meta">Nothing here.</span></li>}
      </ul>
      <div className="dsh-legend">Highlighted rows are this week&apos;s pacing-guide targets.</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

const LEVEL_ORDER = ["low_effort", "minimal", "developing", "solid", "full"];

function Stats({ d }: { d: StudentDashboard }) {
  const maxWeek = Math.max(1, ...d.game.activity.weeks.map((w) => w.completed));
  return (
    <div className="dsh-panel">
      <div className="dsh-k" style={{ marginBottom: 6 }}>Progress by type</div>
      {d.by_type.map((t) => (
        <div key={t.type} className="dsh-typerow">
          <div className="lbl">
            {t.label}
            <span>
              {Math.round(t.weight * 100)}% of grade · {t.done}/{t.total} done
            </span>
          </div>
          <div className="bar" role="img" aria-label={`${t.done} of ${t.total} done; ${t.due} due so far`}>
            <div className="fill" style={{ width: `${(100 * t.done) / t.total}%` }} />
            <div className="mark" style={{ left: `calc(${(100 * t.due) / t.total}% - 1px)` }} />
          </div>
          <div className="v" title="Average on submitted work">{fmtPct(t.avg_submitted)}</div>
        </div>
      ))}
      <div className="dsh-legend">
        Blue = completed · <i />marker = where the pacing guide has you today · % = your average on submitted work
      </div>

      <div className="dsh-k" style={{ margin: "18px 0 4px" }}>Items finished per week</div>
      <div className="dsh-bars">
        {d.game.activity.weeks.map((w, i, arr) => (
          <div key={w.start} className={`col${i === arr.length - 1 ? " now" : ""}`} tabIndex={0}
            aria-label={`Week of ${fmtDate(w.start)}: ${w.completed} completed`}>
            <span className="tip">Week of {fmtDate(w.start)}: {w.completed}</span>
            <div className="b" style={{ height: `${(78 * w.completed) / maxWeek}%` }} />
            <span>{i === arr.length - 1 ? "now" : fmtDate(w.start)}</span>
          </div>
        ))}
      </div>

      {d.stats.video_first_try_pct != null && (
        <>
          <div className="dsh-k" style={{ margin: "18px 0 4px" }}>Video checkpoints</div>
          <div className="dsh-note" style={{ marginTop: 0 }}>
            <b style={{ fontSize: 22, color: "#f3eee2" }}>{fmtPct(d.stats.video_first_try_pct)}</b> right on the first try
            across {d.stats.video_questions} questions in {d.stats.videos_completed} videos
          </div>
        </>
      )}

      {d.stats.reflection_dimensions.length > 0 && (
        <>
          <div className="dsh-k" style={{ margin: "18px 0 4px" }}>Scenario reflections · typical level</div>
          {d.stats.reflection_dimensions.map((dim) => {
            const rank = Math.round(dim.avg_rank);
            return (
              <div key={dim.key} className="dsh-dim">
                <span style={{ textTransform: "capitalize" }}>{dim.key}</span>
                <div className="dsh-meter" aria-hidden>
                  {LEVEL_ORDER.slice(1).map((_, i) => (
                    <span key={i} className={i < rank ? "on" : ""} />
                  ))}
                </div>
                <span className="lv">{dim.typical_level.replace("_", " ")}</span>
              </div>
            );
          })}
        </>
      )}

      {d.stats.frq_dimensions.length > 0 && (
        <>
          <div className="dsh-k" style={{ margin: "18px 0 4px" }}>FRQ rubric</div>
          {d.stats.frq_dimensions.map((dim) => (
            <div key={dim.key} className="dsh-dim">
              <span>{dim.title}</span>
              <div className="bar" style={{ height: 8 }}>
                <div className="fill" style={{ width: `${dim.pct ?? 0}%` }} />
              </div>
              <span className="lv">{fmtPct(dim.pct)}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tips + badges
// ---------------------------------------------------------------------------

function Tips({ d }: { d: StudentDashboard }) {
  return (
    <div className="dsh-panel">
      {d.tips.map((t, i) => (
        <div key={i} className="dsh-tip" style={t.kind === "praise" ? { borderColor: "#3fb37f" } : undefined}>
          <h3>{t.title}</h3>
          <p>{t.body}</p>
          {t.quote && <blockquote>&ldquo;{t.quote}&rdquo;<br /><span style={{ fontStyle: "normal", fontSize: 11, color: "#6f8780" }}>— feedback on your most recent work</span></blockquote>}
          {t.review && (
            <ul>
              {t.review.map((q, j) => (
                <li key={j}>
                  {q.prompt} <span>({q.video})</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function useNewBadges(student: string, badges: DashBadge[]): Set<string> {
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    const key = `dash-badges-seen.v1:${student}`;
    let seen: string[] = [];
    try {
      seen = JSON.parse(window.localStorage.getItem(key) ?? "[]");
    } catch {
      seen = [];
    }
    const earned = badges.filter((b) => b.earned).map((b) => b.id);
    const isNew = earned.filter((id) => !seen.includes(id));
    if (isNew.length) {
      setFresh(new Set(isNew));
      burstConfetti();
      try {
        window.localStorage.setItem(key, JSON.stringify(Array.from(new Set([...seen, ...earned]))));
      } catch {
        // storage blocked: confetti may repeat next visit — harmless
      }
    }
  }, [student, badges]);
  return fresh;
}

function Badges({ d, student }: { d: StudentDashboard; student: string }) {
  const fresh = useNewBadges(student, d.game.badges);
  const sorted = [...d.game.badges].sort((a, b) => Number(b.earned) - Number(a.earned));
  return (
    <div className="dsh-badges">
      {sorted.map((b) => (
        <div key={b.id} className={`dsh-badge ${b.earned ? "on" : "off"}${fresh.has(b.id) ? " new" : ""}`}>
          <Icon name={b.icon} />
          <div className="bn">{b.name}{fresh.has(b.id) ? " · new!" : ""}</div>
          <div className="bd">{b.description}</div>
          {!b.earned && b.goal != null && (
            <div className="bp">
              {b.progress ?? 0} / {b.goal}
            </div>
          )}
          {!b.earned && b.goal == null && <div className="bp">Locked</div>}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------

export default function DashboardView({ data }: { data: StudentDashboardResponse }) {
  const d = data.dashboard!;
  const first = data.student.name.includes(",")
    ? data.student.name.split(",")[1].trim().split(" ")[0]
    : data.student.name.split(" ")[0];
  const down = Object.entries(data.sources).filter(([, v]) => v === "unavailable").map(([k]) => k);
  return (
    <>
      <h1 className="dsh-hello">Hey {first} 👋</h1>
      <p className="dsh-sub">
        {d.course} · {d.term} · live as of {fmtDate(d.as_of)}
      </p>
      {down.length > 0 && (
        <div className="dsh-warn" role="status">
          Couldn&apos;t reach the {down.join(" and ")} app right now, so those items may show as not done. Refresh in a minute.
        </div>
      )}

      <Hero d={d} />

      <div className="dsh-section">
        <h2>Next best moves <span>ranked by how much they help your grade, how soon they&apos;re due, and how long they take</span></h2>
        <NextMoves moves={d.next_moves} />
      </div>

      <div className="dsh-section">
        <h2>Course trail</h2>
        <Trail d={d} />
      </div>

      <div className="dsh-section dsh-grid dsh-two">
        <div>
          <h2 style={{ fontSize: 13, letterSpacing: ".14em", textTransform: "uppercase", color: "#a9bab4", margin: "0 0 12px" }}>
            Checklist
          </h2>
          <Checklist d={d} />
        </div>
        <div>
          <h2 style={{ fontSize: 13, letterSpacing: ".14em", textTransform: "uppercase", color: "#a9bab4", margin: "0 0 12px" }}>
            Tips for you
          </h2>
          <Tips d={d} />
        </div>
      </div>

      <div className="dsh-section">
        <h2>Your stats</h2>
        <Stats d={d} />
      </div>

      <div className="dsh-section">
        <h2>Badges <span>{d.game.badges.filter((b) => b.earned).length} of {d.game.badges.length} earned</span></h2>
        <Badges d={d} student={data.student.name} />
      </div>

      <div className="dsh-foot">
        <b>How this is calculated.</b> Your grade uses the syllabus weights (videos 20% · scenarios 35% · FRQ exams 45%).
        Every item past its pacing-guide date with no grade counts as 0 until you turn it in. Scenario and FRQ scores are
        your best attempt. Video score = 75 for finishing + up to 25 for first-try answers. {d.late_policy} XP and badges
        are just for fun and never affect your grade. This page is tied to your personal access code — keep it to yourself.
      </div>
    </>
  );
}
