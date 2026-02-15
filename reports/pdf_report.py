from __future__ import annotations

from pathlib import Path
from typing import Any


def _fmt(value: float | None, decimals: int = 3) -> str:
    if value is None:
        return "—"
    txt = f"{value:.{decimals}f}"
    if txt.startswith("0."):
        return "." + txt[2:]
    if txt.startswith("-0."):
        return "-." + txt[3:]
    return txt


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.3f}"


def generate_player_report_pdf(
    filepath: str,
    player: dict[str, Any],
    filters: dict[str, Any],
    metrics: dict[str, Any],
    trends: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    practice_summary: dict[str, Any],
    recent_notes: list[dict[str, Any]],
) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "ReportLab is required for PDF export. Install with: pip install reportlab"
        ) from exc

    path = Path(filepath)
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter

    left = 42
    y = height - 40

    def line(text: str, size: int = 10, bold: bool = False, color=colors.black, gap: int = 14) -> None:
        nonlocal y
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(left, y, text)
        y -= gap

    line("StatForge", size=18, bold=True)
    line("by Anchor & Honor", size=10, color=colors.HexColor("#6B7785"), gap=16)

    player_line = (
        f"{player.get('name', '-') } | {player.get('position', '-') } | {player.get('level', '-') or '-'} | "
        f"{filters.get('scope_label', 'All') }"
    )
    line(f"Player: {player_line}", size=10, gap=18)

    line("Performance Summary", size=12, bold=True)
    perf = metrics.get("performance", {})
    line(
        "AVG {0}   OBP {1}   SLG {2}   OPS {3}   K Rate {4}   BB Rate {5}".format(
            _fmt(perf.get("AVG")),
            _fmt(perf.get("OBP")),
            _fmt(perf.get("SLG")),
            _fmt(perf.get("OPS")),
            _fmt(perf.get("K_RATE")),
            _fmt(perf.get("BB_RATE")),
        ),
        size=9,
    )
    line(
        "CS% {0}   PB Rate {1}".format(_fmt(perf.get("CS_PCT")), _fmt(perf.get("PB_RATE"))),
        size=9,
        gap=18,
    )

    line("Trends", size=12, bold=True)
    header = "Metric   Season   Last5   Δ   Trend   Last10   Δ   Trend"
    line(header, size=9, bold=True)
    for row in trends:
        delta5 = _fmt_delta(row.get("delta5"))
        delta10 = _fmt_delta(row.get("delta10"))
        line(
            f"{row.get('metric', '—'):<8} {_fmt(row.get('season')):<6} {_fmt(row.get('last5')):<6} {delta5:<7} {row.get('trend5', '—'):<5} "
            f"{_fmt(row.get('last10')):<6} {delta10:<7} {row.get('trend10', '—')}",
            size=8,
            gap=12,
        )
    y -= 4

    line("Focus This Week", size=12, bold=True)
    if recommendations:
        for rec in recommendations[:3]:
            line(f"• {rec.get('title', '-')}", size=10, bold=True, gap=12)
            line(f"  {rec.get('reason', '-')}", size=9, color=colors.HexColor("#4B5663"), gap=11)
            for drill in rec.get("drills", [])[:4]:
                line(f"  - {drill}", size=9, gap=11)
            y -= 2
    else:
        line("No recommendations in current scope.", size=9)

    line("Practice This Week", size=12, bold=True)
    top_focuses = practice_summary.get("top_focuses", [])
    top_focus = top_focuses[0][0] if top_focuses else "—"
    line(
        f"Sessions: {practice_summary.get('session_count', 0)}   Total Minutes: {practice_summary.get('total_minutes', 0)}   Top Focus: {top_focus}",
        size=9,
        gap=16,
    )

    line("Recent Notes", size=12, bold=True)
    if recent_notes:
        for item in recent_notes[:3]:
            note = (item.get("notes") or "—").strip() or "—"
            if len(note) > 80:
                note = note[:80].rstrip() + "..."
            line(f"{item.get('date', '-') } vs {item.get('opponent', 'Unknown Opponent')}: {note}", size=8, gap=11)
    else:
        line("No recent notes.", size=9)

    c.showPage()
    c.save()
