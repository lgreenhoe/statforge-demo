from __future__ import annotations

from statforge_core.video_protocols import compute_protocol_result


def run_protocol_smoke_tests() -> None:
    catcher = compute_protocol_result(
        "Catcher Pop Time",
        {"catch": 0.50, "release": 1.25, "target": 2.05},
    )
    assert round(float(catcher["duration_seconds"] or 0.0), 3) == 1.55

    pitcher = compute_protocol_result(
        "Pitcher Time To Plate",
        {"start": 0.10, "plate": 1.55},
    )
    assert round(float(pitcher["duration_seconds"] or 0.0), 3) == 1.45

    infield = compute_protocol_result(
        "Infield Transfer",
        {"glove": 0.20, "release": 0.92},
    )
    assert round(float(infield["duration_seconds"] or 0.0), 3) == 0.72

    outfield = compute_protocol_result(
        "Outfield Glove To Release",
        {"glove": 0.40, "release": 1.52},
    )
    assert round(float(outfield["duration_seconds"] or 0.0), 3) == 1.12

    hitting = compute_protocol_result(
        "Hitting Load To Contact",
        {"load": 0.33, "contact": 0.67},
    )
    assert round(float(hitting["duration_seconds"] or 0.0), 3) == 0.34


if __name__ == "__main__":
    run_protocol_smoke_tests()
    print("video_protocols smoke tests passed")
