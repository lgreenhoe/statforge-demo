from __future__ import annotations

from typing import Any

Suggestion = dict[str, Any]

TRAINING_MAP: dict[str, Suggestion] = {
    "plate_discipline": {
        "what_were_seeing": "Swing decisions are creating too many strikeouts relative to walks.",
        "what_to_do_this_week": "Prioritize pitch recognition and count leverage in early batting blocks.",
        "drills": [
            "Color-ball recognition rounds (track, no swing)",
            "2-strike battle cage rounds (shorten path, opposite-field focus)",
            "Take/attack decision ladder with coach callouts",
        ],
    },
    "contact_quality": {
        "what_were_seeing": "OPS is below target, indicating inconsistent quality of contact.",
        "what_to_do_this_week": "Rebuild barrel consistency and directional intent before adding intensity.",
        "drills": [
            "Front-toss line-drive ladder (middle-to-oppo)",
            "Top-hand / bottom-hand path control series",
            "Launch-window constraint rounds (hard line drives only)",
        ],
    },
    "exchange_speed": {
        "what_were_seeing": "Exchange time is slower than target for current level.",
        "what_to_do_this_week": "Reduce transfer variance with quick, repeatable footwork and glove-to-hand paths.",
        "drills": [
            "Knee-down quick transfer reps with stopwatch",
            "Four-corner footwork and transfer rhythm sequence",
            "Rapid-fire receive-to-release progression (accuracy first)",
        ],
    },
    "pop_efficiency": {
        "what_were_seeing": "Pop time trend is above benchmark despite stable receiving reps.",
        "what_to_do_this_week": "Tighten transfer-to-throw timing while preserving throwing-line accuracy.",
        "drills": [
            "One-knee to power-position pop progression",
            "Short-box target throws emphasizing arm path",
            "Timed 5-rep pop clusters with reset cues",
        ],
    },
    "run_game_control": {
        "what_were_seeing": "Caught-stealing rate is low versus attempts allowed.",
        "what_to_do_this_week": "Sync exchange and throw decisions with game-speed runner pressure.",
        "drills": [
            "Live steal-read scenarios with variable runner jumps",
            "Receive-and-throw lane alignment reps",
            "Tag-window timing with middle-infield partner",
        ],
    },
    "blocking": {
        "what_were_seeing": "Passed-ball rate suggests blocking consistency can improve.",
        "what_to_do_this_week": "Emphasize chest angle, centerline control, and recovery speed.",
        "drills": [
            "Tennis-ball short-hop block sequence",
            "Lateral block and recover to throw",
            "Reaction-machine dirt-ball reps",
        ],
    },
}


def _is_triggered(flag: str, metrics: dict[str, float | None]) -> bool:
    k_rate = metrics.get("k_rate_season")
    bb_rate = metrics.get("bb_rate_season")
    ops = metrics.get("ops_season")
    transfer = metrics.get("transfer_avg")
    pop_time = metrics.get("pop_time_avg")
    cs_pct = metrics.get("cs_pct_season")
    pb_rate = metrics.get("pb_rate_season")

    if flag == "plate_discipline":
        return (k_rate is not None and k_rate > 0.24) or (bb_rate is not None and bb_rate < 0.08)
    if flag == "contact_quality":
        return ops is not None and ops < 0.72
    if flag == "exchange_speed":
        return transfer is not None and transfer > 0.80
    if flag == "pop_efficiency":
        return pop_time is not None and pop_time > 2.18
    if flag == "run_game_control":
        return cs_pct is not None and cs_pct < 0.30
    if flag == "blocking":
        return pb_rate is not None and pb_rate > 0.03
    return False


def build_training_suggestions(metrics: dict[str, float | None], max_items: int = 3) -> list[Suggestion]:
    ordered_flags = [
        "plate_discipline",
        "contact_quality",
        "exchange_speed",
        "pop_efficiency",
        "run_game_control",
        "blocking",
    ]

    suggestions: list[Suggestion] = []
    for flag in ordered_flags:
        if _is_triggered(flag, metrics):
            suggestions.append(TRAINING_MAP[flag])
        if len(suggestions) >= max_items:
            return suggestions

    if suggestions:
        return suggestions

    return [
        {
            "what_were_seeing": "Current demo profile is stable across major trend flags.",
            "what_to_do_this_week": "Use a maintenance microcycle focused on consistency and readiness.",
            "drills": [
                "Mixed-skill circuit (receiving, transfer, swing decisions)",
                "Pressure rep finishers with target outcomes",
            ],
        }
    ]
