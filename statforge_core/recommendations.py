from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass
class Drill:
    name: str
    setup: str
    reps_sets: str
    coaching_cues: str
    progression: str


@dataclass
class Recommendation:
    title: str
    why_this_triggered: str
    drills: list[Drill]
    priority: str
    category: str


_PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}


@lru_cache(maxsize=4)
def load_recommendation_rules(rules_path: str | None = None) -> dict[str, Any]:
    if rules_path:
        path = Path(rules_path)
    else:
        path = Path(__file__).resolve().with_name("recommendation_rules.json")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _evaluate_rule(metric_value: float, operator: str, threshold: float) -> tuple[bool, float]:
    if operator == "gt":
        delta = metric_value - threshold
        return delta > 0, delta
    if operator == "lt":
        delta = threshold - metric_value
        return delta > 0, delta
    if operator == "gte":
        delta = metric_value - threshold
        return delta >= 0, delta
    if operator == "lte":
        delta = threshold - metric_value
        return delta >= 0, delta
    return False, 0.0


def _rule_threshold(rule: dict[str, Any], thresholds: dict[str, float] | None) -> float:
    default = float(rule.get("threshold", 0.0))
    if not thresholds:
        return default
    rule_id = str(rule.get("id", ""))
    metric = str(rule.get("metric", ""))
    if rule_id and rule_id in thresholds:
        return float(thresholds[rule_id])
    if metric and metric in thresholds:
        return float(thresholds[metric])
    return default


def generate_recommendations(
    metrics: dict[str, Any],
    thresholds: dict[str, float] | None = None,
    rules_path: str | None = None,
    max_items: int = 3,
) -> list[Recommendation]:
    rules_blob = load_recommendation_rules(rules_path=rules_path)
    rule_items = list(rules_blob.get("rules", []))
    scored: list[tuple[int, float, Recommendation]] = []

    for rule in rule_items:
        metric_key = str(rule.get("metric", ""))
        operator = str(rule.get("operator", "gt"))
        metric_value = _safe_float(metrics.get(metric_key))
        if metric_value is None:
            continue

        threshold = _rule_threshold(rule, thresholds)
        matched, raw_delta = _evaluate_rule(metric_value, operator, threshold)
        if not matched:
            continue

        severity = raw_delta / (abs(threshold) if threshold not in (0.0, -0.0) else 1.0)
        drill_rows = list(rule.get("drills", []))
        drills = [
            Drill(
                name=str(d.get("name", "")),
                setup=str(d.get("setup", "")),
                reps_sets=str(d.get("reps_sets", "")),
                coaching_cues=str(d.get("coaching_cues", "")),
                progression=str(d.get("progression", "")),
            )
            for d in drill_rows
        ]
        why_template = str(rule.get("why_template", "Rule triggered for this metric."))
        why_text = why_template.format(value=metric_value, threshold=threshold)
        rec = Recommendation(
            title=str(rule.get("title", "Development Focus")),
            why_this_triggered=why_text,
            drills=drills,
            priority=str(rule.get("priority", "Medium")),
            category=str(rule.get("category", "General")),
        )
        priority_rank = _PRIORITY_RANK.get(rec.priority, 99)
        scored.append((priority_rank, -severity, rec))

    scored.sort(key=lambda row: (row[0], row[1], row[2].title))
    unique: list[Recommendation] = []
    seen_titles: set[str] = set()
    for _, _, rec in scored:
        if rec.title in seen_titles:
            continue
        seen_titles.add(rec.title)
        unique.append(rec)
        if len(unique) >= max_items:
            break
    return unique


def recommendation_to_dict(rec: Recommendation) -> dict[str, Any]:
    return asdict(rec)
