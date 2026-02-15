from __future__ import annotations

import re
from typing import Any


STAT_BENCHMARKS: dict[str, dict[str, dict[str, float]]] = {
    "12U": {
        "transfer_time": {"elite": 0.70, "good": 0.85, "developing": 1.05},
        "pop_time": {"elite": 2.05, "good": 2.25, "developing": 2.45},
    },
    "13U": {
        "transfer_time": {"elite": 0.65, "good": 0.80, "developing": 1.00},
        "pop_time": {"elite": 1.95, "good": 2.10, "developing": 2.35},
    },
}


STAT_DIRECTIONS: dict[str, str] = {
    "transfer_time": "lower_better",
    "pop_time": "lower_better",
}


def _normalize_age_level(level_raw: str | None) -> str | None:
    if not level_raw:
        return None
    normalized = str(level_raw).strip().upper().replace(" ", "")
    if normalized in STAT_BENCHMARKS:
        return normalized
    for key in STAT_BENCHMARKS.keys():
        if key in normalized:
            return key
    return None


def classify_stat(stat_key: str, value: float | None, age_level: str) -> str:
    if value is None:
        return "neutral"
    level_key = _normalize_age_level(age_level)
    if not level_key or level_key not in STAT_BENCHMARKS:
        return "neutral"
    bench = STAT_BENCHMARKS[level_key].get(stat_key)
    if not bench:
        return "neutral"

    direction = STAT_DIRECTIONS.get(stat_key, "lower_better")
    elite = float(bench.get("elite", 0.0))
    good = float(bench.get("good", elite))

    if direction == "higher_better":
        if value >= elite:
            return "strength"
        if value >= good:
            return "neutral"
        return "growth"

    if value <= elite:
        return "strength"
    if value <= good:
        return "neutral"
    return "growth"


def score_stat(stat_key: str, player_value: float | None, benchmark: dict[str, float] | None) -> int:
    if player_value is None or not benchmark:
        return 0
    direction = STAT_DIRECTIONS.get(stat_key, "lower_better")
    elite = float(benchmark.get("elite", 0.0))
    good = float(benchmark.get("good", elite))
    developing = float(benchmark.get("developing", good))

    if direction == "higher_better":
        if player_value >= elite:
            return 3
        if player_value >= good:
            return 2
        if player_value >= developing:
            return 1
        return 0

    if player_value <= elite:
        return 3
    if player_value <= good:
        return 2
    if player_value <= developing:
        return 1
    return 0


def _parse_transfer_from_notes(notes: str) -> float | None:
    match = re.search(r"best_transfer=([0-9]+(?:\.[0-9]+)?)s", notes)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _profile_metric_values(db: Any, player_id: int) -> dict[str, float | None]:
    rows = db.get_recent_practice_sessions(player_id, limit=50)
    transfer_values: list[float] = []
    pop_values: list[float] = []
    for row in rows:
        notes = str(row["notes"] or "")
        transfer = _parse_transfer_from_notes(notes)
        if transfer is not None:
            transfer_values.append(transfer)
        pop_avg = row["pop_time_avg"]
        if pop_avg is not None:
            try:
                pop_values.append(float(pop_avg))
            except (TypeError, ValueError):
                pass

    transfer_value = (sum(transfer_values) / len(transfer_values)) if transfer_values else None
    pop_value = (sum(pop_values) / len(pop_values)) if pop_values else None
    return {"transfer_time": transfer_value, "pop_time": pop_value}


def build_player_development_profile(db: Any, player_id: int) -> dict[str, Any]:
    player = db.get_player(player_id)
    level = _normalize_age_level(player["level"] if player else None)
    values = _profile_metric_values(db, player_id)

    strengths: list[str] = []
    growth: list[str] = []
    neutral: list[str] = []
    evaluations: dict[str, dict[str, Any]] = {}

    for stat_key, stat_value in values.items():
        classification = classify_stat(stat_key, stat_value, level or "")
        evaluations[stat_key] = {"value": stat_value, "classification": classification}
        if classification == "strength":
            strengths.append(stat_key)
        elif classification == "growth":
            growth.append(stat_key)
        else:
            neutral.append(stat_key)

    return {
        "age_level": level,
        "strengths": strengths,
        "growth": growth,
        "neutral": neutral,
        "evaluations": evaluations,
    }


def get_player_focus_stats(db: Any, player_id: int, age_level: str | None) -> list[dict[str, Any]]:
    level = _normalize_age_level(age_level)
    if not level or level not in STAT_BENCHMARKS:
        return []
    values = _profile_metric_values(db, player_id)
    scored: list[dict[str, Any]] = []
    for stat_key, value in values.items():
        benchmark = STAT_BENCHMARKS[level].get(stat_key)
        score = score_stat(stat_key, value, benchmark)
        if benchmark:
            if STAT_DIRECTIONS.get(stat_key, "lower_better") == "lower_better":
                benchmark_range = (
                    f"Elite <= {benchmark['elite']:.2f}s | Good <= {benchmark['good']:.2f}s | "
                    f"Developing <= {benchmark['developing']:.2f}s"
                )
            else:
                benchmark_range = (
                    f"Elite >= {benchmark['elite']:.2f} | Good >= {benchmark['good']:.2f} | "
                    f"Developing >= {benchmark['developing']:.2f}"
                )
        else:
            benchmark_range = "—"
        scored.append(
            {
                "stat_key": stat_key,
                "value": value,
                "benchmark": benchmark,
                "benchmark_range": benchmark_range,
                "score": score,
                "priority": "High" if score <= 0 else "Medium",
            }
        )

    scored.sort(key=lambda row: (int(row["score"]), str(row["stat_key"])))
    return scored[:2]
