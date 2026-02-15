from __future__ import annotations

from typing import Any


def calculate_pop_metrics(
    catch_time: float,
    release_time: float,
    target_time: float | None = None,
    metric_mode: str = "transfer",
    estimated_flight: float | None = None,
) -> dict[str, Any]:
    if release_time <= catch_time:
        raise ValueError("release_time must be greater than catch_time")

    transfer = release_time - catch_time
    throw_time: float | None = None

    if metric_mode == "full_pop":
        if target_time is None:
            raise ValueError("target_time is required for full_pop mode")
        if target_time <= release_time:
            raise ValueError("target_time must be greater than release_time")
        throw_time = target_time - release_time
        pop_total = target_time - catch_time
    elif metric_mode == "estimated_pop":
        if estimated_flight is None:
            raise ValueError("estimated_flight is required for estimated_pop mode")
        if estimated_flight < 0:
            raise ValueError("estimated_flight must be non-negative")
        throw_time = estimated_flight
        pop_total = transfer + estimated_flight
    else:
        pop_total = transfer

    return {
        "metric_mode": metric_mode,
        "transfer": transfer,
        "throw_time": throw_time,
        "pop_total": pop_total,
        "estimated_flight": estimated_flight if metric_mode == "estimated_pop" else None,
    }
