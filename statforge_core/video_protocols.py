from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .pop_time import calculate_pop_metrics


@dataclass(frozen=True)
class VideoProtocol:
    analysis_type: str
    allowed_positions: tuple[str, ...]
    event_markers: tuple[str, ...]
    description: str
    compute: Callable[[dict[str, float], dict[str, Any] | None], dict[str, float | None]]


def _validate_marker_sequence(markers: dict[str, float], required: tuple[str, ...]) -> None:
    for marker in required:
        if marker not in markers:
            raise ValueError(f"Missing marker: {marker}")
    for left, right in zip(required, required[1:]):
        if float(markers[right]) <= float(markers[left]):
            raise ValueError(f"Invalid marker order: '{right}' must be after '{left}'")


def _compute_catcher_pop_time(markers: dict[str, float], options: dict[str, Any] | None = None) -> dict[str, float | None]:
    opts = options or {}
    has_target = "target" in markers
    metric_mode = "full_pop" if has_target else "estimated_pop"
    estimated_flight = None
    if not has_target:
        estimated_flight = float(opts.get("estimated_flight", 0.8))
    pop = calculate_pop_metrics(
        catch_time=float(markers["catch"]),
        release_time=float(markers["release"]),
        target_time=float(markers["target"]) if has_target else None,
        metric_mode=metric_mode,
        estimated_flight=estimated_flight,
    )
    throw_time = pop.get("throw_time")
    return {
        "duration_seconds": float(pop["pop_total"]),
        "transfer_seconds": float(pop["transfer"]),
        "throw_seconds": float(throw_time) if throw_time is not None else None,
    }


def _compute_duration_between(markers: dict[str, float], start_key: str, end_key: str) -> dict[str, float | None]:
    start = float(markers[start_key])
    end = float(markers[end_key])
    if end <= start:
        raise ValueError(f"Invalid marker order: '{end_key}' must be after '{start_key}'")
    return {"duration_seconds": end - start}


def _compute_pitcher_time_to_plate(markers: dict[str, float], options: dict[str, Any] | None = None) -> dict[str, float | None]:
    _ = options
    _validate_marker_sequence(markers, ("start", "plate"))
    return _compute_duration_between(markers, "start", "plate")


def _compute_infield_transfer(markers: dict[str, float], options: dict[str, Any] | None = None) -> dict[str, float | None]:
    _ = options
    _validate_marker_sequence(markers, ("glove", "release"))
    return _compute_duration_between(markers, "glove", "release")


def _compute_outfield_release(markers: dict[str, float], options: dict[str, Any] | None = None) -> dict[str, float | None]:
    _ = options
    _validate_marker_sequence(markers, ("glove", "release"))
    return _compute_duration_between(markers, "glove", "release")


def _compute_hitting_load_to_contact(markers: dict[str, float], options: dict[str, Any] | None = None) -> dict[str, float | None]:
    _ = options
    _validate_marker_sequence(markers, ("load", "contact"))
    return _compute_duration_between(markers, "load", "contact")


PROTOCOLS: tuple[VideoProtocol, ...] = (
    VideoProtocol(
        analysis_type="Catcher Pop Time",
        allowed_positions=("Catcher",),
        event_markers=("catch", "release", "target"),
        description="Catch-to-release plus throw time when target marker is provided.",
        compute=_compute_catcher_pop_time,
    ),
    VideoProtocol(
        analysis_type="Pitcher Time To Plate",
        allowed_positions=("Pitcher",),
        event_markers=("start", "plate"),
        description="First movement to plate crossing.",
        compute=_compute_pitcher_time_to_plate,
    ),
    VideoProtocol(
        analysis_type="Infield Transfer",
        allowed_positions=("Infield", "FirstBase", "1B"),
        event_markers=("glove", "release"),
        description="Ball-in-glove to release time.",
        compute=_compute_infield_transfer,
    ),
    VideoProtocol(
        analysis_type="Outfield Glove To Release",
        allowed_positions=("Outfield",),
        event_markers=("glove", "release"),
        description="Outfield transfer timing from glove to release.",
        compute=_compute_outfield_release,
    ),
    VideoProtocol(
        analysis_type="Hitting Load To Contact",
        allowed_positions=("Hitter",),
        event_markers=("load", "contact"),
        description="Load to contact timing for swing sequencing.",
        compute=_compute_hitting_load_to_contact,
    ),
)

PROTOCOL_REGISTRY: dict[str, VideoProtocol] = {protocol.analysis_type: protocol for protocol in PROTOCOLS}


def normalize_position(position: str | None) -> str:
    value = str(position or "").strip().lower()
    if value in {"1b", "first", "first base", "firstbase"}:
        return "FirstBase"
    if value in {"c", "catcher"}:
        return "Catcher"
    if value in {"p", "pitcher"}:
        return "Pitcher"
    if value in {"if", "infield", "infielder", "2b", "3b", "ss"}:
        return "Infield"
    if value in {"of", "outfield", "outfielder", "lf", "cf", "rf"}:
        return "Outfield"
    if value in {"hitter", "hit", "bat", "batter", "dh"}:
        return "Hitter"
    return (str(position or "").strip() or "Catcher")


def list_protocols_for_position(position: str | None) -> list[VideoProtocol]:
    normalized = normalize_position(position)
    return [protocol for protocol in PROTOCOLS if normalized in protocol.allowed_positions]


def get_protocol(analysis_type: str) -> VideoProtocol:
    protocol = PROTOCOL_REGISTRY.get(str(analysis_type))
    if protocol is None:
        raise KeyError(f"Unknown analysis type: {analysis_type}")
    return protocol


def compute_protocol_result(
    analysis_type: str,
    markers: dict[str, float],
    options: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    protocol = get_protocol(analysis_type)
    return protocol.compute(markers, options or {})
