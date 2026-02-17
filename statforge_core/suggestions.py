from __future__ import annotations

from typing import Any


def _f(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def get_suggestions(player_stats: dict[str, Any]) -> list[dict[str, Any]]:
    ops = _f(player_stats.get("ops"))
    k_rate = _f(player_stats.get("k_rate"))
    cs_pct = _f(player_stats.get("cs_pct"))
    pop_time = _f(player_stats.get("pop_time"))
    exchange = _f(player_stats.get("exchange"))
    pb_rate = _f(player_stats.get("pb_rate"))

    suggestions: list[dict[str, Any]] = []

    if k_rate is not None and k_rate > 0.24:
        suggestions.append(
            {
                "title": "Contact and Plate Discipline",
                "why": f"K-rate is elevated ({k_rate:.1%}); reduce empty swings in leverage counts.",
                "drills": [
                    "Two-Strike Contact Ladder (4x8)",
                    "Take/Track Recognition Rounds (3x10)",
                    "Short-path Opposite Gap Series (3x8)",
                ],
            }
        )

    if ops is not None and ops < 0.740:
        suggestions.append(
            {
                "title": "Approach and Timing",
                "why": f"OPS is below target ({ops:.3f}); improve quality contact and on-base approach.",
                "drills": [
                    "Gap-to-Gap Sequencing (3x10)",
                    "Early Timing Cue Rounds (4x6)",
                ],
            }
        )

    if pop_time is not None and pop_time > 2.18:
        suggestions.append(
            {
                "title": "Pop Time Efficiency",
                "why": f"Pop time trend is high ({pop_time:.2f}s); tighten transfer-to-throw sequence.",
                "drills": [
                    "Knee-Down to Throw Progression (5x5)",
                    "Foot Replacement Timing (4x6)",
                    "Quick Exchange Challenge (3x10)",
                ],
            }
        )

    if exchange is not None and exchange > 0.82:
        suggestions.append(
            {
                "title": "Exchange Mechanics",
                "why": f"Exchange time is slower than benchmark ({exchange:.2f}s).",
                "drills": [
                    "Pocket-to-Release Reps (6x6)",
                    "Rapid Transfer Ladder (4x8)",
                ],
            }
        )

    if cs_pct is not None and cs_pct < 0.30:
        suggestions.append(
            {
                "title": "Run Game Control",
                "why": f"CS% is low ({cs_pct:.1%}); improve throw line and decision timing.",
                "drills": [
                    "Target-Line Throw Series (5x4)",
                    "Transfer + One-Hop Accuracy (4x6)",
                ],
            }
        )

    if pb_rate is not None and pb_rate > 0.03:
        suggestions.append(
            {
                "title": "Blocking Consistency",
                "why": f"Passed-ball rate is elevated ({pb_rate:.1%}).",
                "drills": [
                    "Tennis Ball Block Sequence (4x8)",
                    "Lateral Block + Recover Throws (3x6)",
                ],
            }
        )

    if suggestions:
        return suggestions[:3]

    return [
        {
            "title": "Maintain Balanced Development",
            "why": "No major risk flags in current sample; reinforce repeatable fundamentals.",
            "drills": [
                "Mixed Skill Circuit: receiving, transfer, swing decisions",
                "Pressure Rep Finisher (2x5)",
            ],
        }
    ]
