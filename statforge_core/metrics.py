from typing import Iterable


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def compute_hitting_metrics(totals: dict[str, float]) -> dict[str, float]:
    ab = totals.get("ab", 0)
    h = totals.get("h", 0)
    doubles = totals.get("doubles", 0)
    triples = totals.get("triples", 0)
    hr = totals.get("hr", 0)
    bb = totals.get("bb", 0)

    singles = h - doubles - triples - hr
    tb = singles + (2 * doubles) + (3 * triples) + (4 * hr)

    avg = safe_div(h, ab)
    obp = safe_div(h + bb, ab + bb)
    slg = safe_div(tb, ab)
    ops = obp + slg
    return {"AVG": avg, "OBP": obp, "SLG": slg, "OPS": ops}


def compute_catching_metrics(totals: dict[str, float]) -> dict[str, float]:
    cs_caught = totals.get("cs_caught", 0)
    sb_allowed = totals.get("sb_allowed", 0)
    passed_balls = totals.get("passed_balls", 0)
    innings_caught = totals.get("innings_caught", 0)

    cs_pct = safe_div(cs_caught, sb_allowed)
    pb_rate = safe_div(passed_balls, innings_caught)
    return {"CS%": cs_pct, "PB Rate": pb_rate}


def per_game_ops(row: dict[str, float]) -> float:
    stats = {
        "ab": row.get("ab", 0),
        "h": row.get("h", 0),
        "doubles": row.get("doubles", 0),
        "triples": row.get("triples", 0),
        "hr": row.get("hr", 0),
        "bb": row.get("bb", 0),
    }
    return compute_hitting_metrics(stats)["OPS"]


def per_game_so_rate(row: dict[str, float]) -> float:
    ab = row.get("ab", 0)
    bb = row.get("bb", 0)
    so = row.get("so", 0)
    pa = ab + bb
    return safe_div(so, pa)


def per_game_cs_pct(row: dict[str, float]) -> float:
    return safe_div(row.get("cs_caught", 0), row.get("sb_allowed", 0))


def per_game_pb_rate(row: dict[str, float]) -> float:
    return safe_div(row.get("passed_balls", 0), row.get("innings_caught", 0))


def average(values: Iterable[float]) -> float:
    values_list = list(values)
    return sum(values_list) / len(values_list) if values_list else 0.0


def trend_arrow(last5: float, prev5: float, inverse_better: bool = False) -> str:
    if abs(last5 - prev5) < 1e-9:
        return "→"
    if inverse_better:
        return "↑" if last5 < prev5 else "↓"
    return "↑" if last5 > prev5 else "↓"


def compute_last5_trend(
    game_rows: list[dict[str, float]],
    extractor,
    inverse_better: bool = False,
) -> str:
    if len(game_rows) < 10:
        return "—"

    last5 = [extractor(r) for r in game_rows[:5]]
    prev5 = [extractor(r) for r in game_rows[5:10]]
    last5_avg = average(last5)
    prev5_avg = average(prev5)
    return trend_arrow(last5_avg, prev5_avg, inverse_better=inverse_better)


def compare_window_to_season(window_value: float | None, season_value: float | None) -> dict[str, float | str]:
    if window_value is None or season_value is None:
        return {"delta": 0.0, "trend": "FLAT"}
    delta = window_value - season_value
    if abs(delta) < 0.005:
        trend = "FLAT"
    elif delta > 0:
        trend = "UP"
    else:
        trend = "DOWN"
    return {"delta": delta, "trend": trend}
