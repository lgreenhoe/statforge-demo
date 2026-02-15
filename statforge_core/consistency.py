from __future__ import annotations

import math
from typing import Any


def compute_consistency(samples: list[float]) -> dict[str, Any]:
    n = len(samples)
    if n == 0:
        return {
            "n": 0,
            "mean": 0.0,
            "sd": 0.0,
            "cv": None,
            "grade": "—",
            "label": "Not enough data",
            "provisional": False,
        }

    mean = sum(samples) / n
    if n > 1:
        variance = sum((x - mean) ** 2 for x in samples) / (n - 1)
        sd = math.sqrt(max(0.0, variance))
    else:
        sd = 0.0
    cv = (sd / mean) if mean > 0 else None

    if cv is None:
        grade = "—"
        label = "Not enough data"
    elif cv <= 0.05:
        grade, label = "A", "Consistent"
    elif cv <= 0.10:
        grade, label = "B", "Consistent"
    elif cv <= 0.15:
        grade, label = "C", "Moderate"
    elif cv <= 0.20:
        grade, label = "D", "Inconsistent"
    else:
        grade, label = "F", "Inconsistent"

    provisional = n < 5
    if provisional and label != "Not enough data":
        label = f"{label} (provisional)"
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "cv": cv,
        "grade": grade,
        "label": label,
        "provisional": provisional,
    }
