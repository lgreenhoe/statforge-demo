from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Recommendation:
    title: str
    reason: str
    drills: list[str]
    priority: int  # lower = higher priority


def _value(metrics: dict, window: str, key: str) -> float | None:
    return metrics.get(window, {}).get(key)


def _delta(metrics: dict, key: str) -> float | None:
    season_val = _value(metrics, "season", key)
    last5_val = _value(metrics, "last5", key)
    if season_val is None or last5_val is None:
        return None
    return last5_val - season_val


def _severity_to_priority(severity: float, base: int = 10) -> int:
    scaled = int(round(severity * 100))
    return max(1, base - scaled)


def generate_recommendations(metrics: dict) -> list[Recommendation]:
    recs: list[Recommendation] = []

    season_k = _value(metrics, "season", "K_RATE")
    last5_k = _value(metrics, "last5", "K_RATE")
    if season_k is not None and last5_k is not None and last5_k > season_k + 0.05:
        severity = last5_k - season_k
        recs.append(
            Recommendation(
                title="Contact & Timing",
                reason="Strikeout rate trending up last 5 games",
                drills=[
                    "Short bat / choke-up rounds off tee",
                    "Front toss: 20 swings focusing contact",
                    "2-strike approach: middle/oppo rounds",
                ],
                priority=_severity_to_priority(severity, base=7),
            )
        )

    season_obp = _value(metrics, "season", "OBP")
    last5_obp = _value(metrics, "last5", "OBP")
    if season_obp is not None and last5_obp is not None and last5_obp < season_obp - 0.02:
        severity = season_obp - last5_obp
        recs.append(
            Recommendation(
                title="Plate Discipline",
                reason="On-base performance dipped over the last 5 games",
                drills=[
                    "Take until strike (tracking rounds)",
                    "Zone awareness: call ball/strike on toss",
                ],
                priority=_severity_to_priority(severity, base=8),
            )
        )

    season_slg = _value(metrics, "season", "SLG")
    last5_slg = _value(metrics, "last5", "SLG")
    season_avg = _value(metrics, "season", "AVG")
    last5_avg = _value(metrics, "last5", "AVG")
    avg_stable = (
        season_avg is not None
        and last5_avg is not None
        and abs(last5_avg - season_avg) < 0.01
    )
    if season_slg is not None and last5_slg is not None and last5_slg < season_slg - 0.05 and avg_stable:
        severity = season_slg - last5_slg
        recs.append(
            Recommendation(
                title="Gap Power",
                reason="Slugging is down while batting average is stable",
                drills=[
                    "Med ball rotational throws",
                    "Launch angle tee: line drives to gaps",
                ],
                priority=_severity_to_priority(severity, base=9),
            )
        )

    season_cs = _value(metrics, "season", "CS_PCT")
    last5_cs = _value(metrics, "last5", "CS_PCT")
    cs_trigger = False
    cs_severity = 0.0
    if season_cs is not None and season_cs < 0.25:
        cs_trigger = True
        cs_severity = max(cs_severity, 0.25 - season_cs)
    if season_cs is not None and last5_cs is not None and last5_cs < season_cs - 0.10:
        cs_trigger = True
        cs_severity = max(cs_severity, (season_cs - last5_cs))
    if cs_trigger:
        recs.append(
            Recommendation(
                title="Pop Time / Transfer",
                reason="Caught-stealing performance is below target trend",
                drills=[
                    "Glove-to-hand transfer reps (50/day)",
                    "Knee-down to throw transitions",
                    "Quick feet ladder + throw (short)",
                ],
                priority=_severity_to_priority(cs_severity, base=6),
            )
        )

    season_pb = _value(metrics, "season", "PB_RATE")
    last5_pb = _value(metrics, "last5", "PB_RATE")
    pb_trigger = False
    pb_severity = 0.0
    if season_pb is not None and season_pb > 0.05:
        pb_trigger = True
        pb_severity = max(pb_severity, season_pb - 0.05)
    if season_pb is not None and last5_pb is not None and last5_pb > season_pb + 0.02:
        pb_trigger = True
        pb_severity = max(pb_severity, last5_pb - season_pb)
    if pb_trigger:
        recs.append(
            Recommendation(
                title="Blocking Consistency",
                reason="Blocking/passed ball trend needs attention",
                drills=[
                    "Tennis ball rapid blocks",
                    "Lateral block steps (10 each side x 3)",
                    "Coach toss dirt balls: 20 reps",
                ],
                priority=_severity_to_priority(pb_severity, base=7),
            )
        )

    recs.sort(key=lambda r: r.priority)
    return recs[:3]
