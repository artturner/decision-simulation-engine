"""Convert docs/chapter-summaries/*.md to briefing-kit overview HTML pages.

Structure mirrors docs/d2l-templates/chapter1-overview.html exactly.
"""
import html
import re
import sys
from pathlib import Path

REPO = Path(r"C:\Users\arttu\decision-simulation-engine")
SRC = REPO / "docs" / "chapter-summaries"
DST = REPO / "docs" / "d2l-templates"

HEAD_COMMENT = """<!-- Chapter {n} overview page \u2014 styled to match the weekly briefing kit.
  Two ways to use it:
    1. Standalone D2L page (paste whole file via the </> source view), or
    2. Lift everything below the h2 into the briefing page's collapsible
       "Chapter overview & objectives" block.
-->
"""


def clean(text: str, keep_bold: bool) -> str:
    """Escape HTML, convert markdown bold, normalize ' - ' to em dashes."""
    text = html.escape(text.strip(), quote=False)
    if keep_bold:
        text = re.sub(
            r"\*\*(.+?)\*\*",
            r'<strong style="color: #111827;">\1</strong>',
            text,
        )
    else:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = text.replace(" - ", " &mdash; ")
    return text


def parse(md: str) -> dict:
    m = re.match(r"#\s*Chapter\s+(\d+):\s*(.+)", md.strip())
    if not m:
        raise ValueError("missing '# Chapter N: Title' heading")
    number, title = int(m.group(1)), m.group(2).strip()

    sections: dict[str, list[str]] = {}
    current = None
    for line in md.splitlines()[1:]:
        h = re.match(r"##\s*(.+)", line)
        if h:
            current = h.group(1).strip().lower()
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line.strip())

    def paras(key: str) -> list[str]:
        return [ln for ln in sections.get(key, []) if not re.match(r"\d+\.\s", ln)]

    def items(key: str) -> list[str]:
        out = []
        for ln in sections.get(key, []):
            m2 = re.match(r"\d+\.\s+(.+)", ln)
            if m2:
                out.append(m2.group(1).strip())
        return out

    return {
        "number": number,
        "title": title,
        "overview": paras("chapter overview"),
        "goals": items("learning goals"),
        "glance": items("goals at a glance"),
        "why": paras("why this matters"),
    }


def render(d: dict) -> str:
    n = d["number"]
    out = [HEAD_COMMENT.format(n=n)]
    out.append(
        '<div style="max-width: 720px; margin: 0 auto; font-family: -apple-system, '
        "'Segoe UI', Lato, Arial, sans-serif; color: #111827; line-height: 1.6;\">\n\n"
    )
    out.append(
        f'  <p style="margin: 0 0 4px; font-size: 12px; letter-spacing: 0.12em; '
        f'text-transform: uppercase; color: #6b7280;">Chapter {n}</p>\n\n'
    )
    out.append(
        f'  <h2 style="margin: 0 0 18px; font-size: 26px; line-height: 1.25; '
        f'color: #111827;">{clean(d["title"], keep_bold=False)}</h2>\n\n'
    )
    out.append(
        '  <p style="margin: 0 0 6px; font-size: 12px; letter-spacing: 0.12em; '
        'text-transform: uppercase; color: #6b7280;">Overview</p>\n'
    )
    for p in d["overview"]:
        out.append(
            f'  <p style="margin: 0 0 22px; font-size: 15px; color: #4b5563;">'
            f"{clean(p, keep_bold=False)}</p>\n"
        )
    out.append("\n")
    out.append(
        '  <p style="margin: 0 0 8px; font-size: 12px; letter-spacing: 0.12em; '
        'text-transform: uppercase; color: #6b7280;">Learning goals</p>\n\n'
    )
    last = len(d["goals"]) - 1
    for i, goal in enumerate(d["goals"]):
        pad = "10px 0 14px" if i == last else "10px 0"
        out.append(
            f'  <div style="display: flex; align-items: flex-start; gap: 14px; '
            f'padding: {pad}; border-top: 1px solid #f3f4f6;">\n'
            f'    <span style="font-size: 13px; font-weight: 700; color: #9ca3af;">{i + 1:02d}</span>\n'
            f'    <p style="margin: 0; font-size: 14.5px; color: #374151;">'
            f"{clean(goal, keep_bold=True)}</p>\n"
            "  </div>\n"
        )
    out.append(
        '\n  <p style="margin: 8px 0 8px; font-size: 12px; letter-spacing: 0.12em; '
        'text-transform: uppercase; color: #6b7280;">Goals at a glance</p>\n'
    )
    out.append('  <p style="margin: 0 0 22px;">\n')
    for i, chip in enumerate(d["glance"]):
        text = clean(chip, keep_bold=False).rstrip(".")
        out.append(
            f'    <span style="display: inline-block; font-size: 12.5px; font-weight: 700; '
            f"color: #374151; border: 1px solid #e5e7eb; border-radius: 999px; "
            f'padding: 4px 12px; margin: 0 6px 6px 0;">{i + 1:02d} &middot; {text}</span>\n'
        )
    out.append("  </p>\n\n")
    out.append(
        '  <div style="background: #f9fafb; border: 1px solid #e5e7eb; '
        'border-radius: 10px; padding: 14px 16px;">\n'
        '    <p style="margin: 0 0 4px; font-size: 12px; letter-spacing: 0.12em; '
        'text-transform: uppercase; color: #6b7280;">Why this matters</p>\n'
    )
    for p in d["why"]:
        out.append(
            f'    <p style="margin: 0; font-size: 14.5px; color: #374151;">'
            f"{clean(p, keep_bold=False)}</p>\n"
        )
    out.append("  </div>\n\n</div>\n")
    return "".join(out)


def main() -> int:
    only_chapter = int(sys.argv[1]) if len(sys.argv) > 1 else None
    dest_override = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    count = 0
    for md_path in sorted(SRC.glob("chapter_*.md")):
        d = parse(md_path.read_text(encoding="utf-8"))
        if only_chapter is not None and d["number"] != only_chapter:
            continue
        if not (d["overview"] and d["goals"] and d["glance"] and d["why"]):
            print(f"SKIP {md_path.name}: missing section(s)", file=sys.stderr)
            continue
        dest = dest_override or DST / f"chapter{d['number']}-overview.html"
        dest.write_text(render(d), encoding="utf-8", newline="\n")
        print(f"{md_path.name} -> {dest.name} (goals={len(d['goals'])}, glance={len(d['glance'])})")
        count += 1
    print(f"wrote {count} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
