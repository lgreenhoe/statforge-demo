from __future__ import annotations

import re
from typing import Any


KEY_ALIASES: dict[str, str] = {
    "games": "games",
    "g": "games",
    "pa": "pa",
    "ab": "ab",
    "h": "h",
    "1b": "1b",
    "2b": "2b",
    "doubles": "2b",
    "3b": "3b",
    "triples": "3b",
    "hr": "hr",
    "rbi": "rbi",
    "r": "r",
    "bb": "bb",
    "so": "so",
    "k": "so",
    "hbp": "hbp",
    "sf": "sf",
    "sb": "sb",
    "cs": "cs",
    "sb_allowed": "sb_allowed",
    "sba": "sb_allowed",
    "innings_caught": "innings_caught",
    "inn": "innings_caught",
    "ip": "innings_caught",
    "pb": "pb",
    "avg": "avg",
    "obp": "obp",
    "slg": "slg",
    "ops": "ops",
    "transfer_time": "transfer_time",
    "transfer": "transfer_time",
    "pop_time": "pop_time",
    "pop": "pop_time",
}

INT_FIELDS = {
    "games", "pa", "ab", "h", "1b", "2b", "3b", "hr", "rbi", "r", "bb", "so", "hbp", "sf", "sb", "cs", "sb_allowed", "pb",
}
FLOAT_FIELDS = {"innings_caught", "avg", "obp", "slg", "ops", "transfer_time", "pop_time"}


def _to_number(raw: str) -> float | int | None:
    token = raw.strip().rstrip("%")
    if token.startswith("."):
        token = "0" + token
    try:
        if "." in token:
            return float(token)
        return int(token)
    except ValueError:
        return None


def _normalize_key(raw: str) -> str | None:
    raw_key = raw.strip().lower()
    if "%" in raw_key:
        alias = KEY_ALIASES.get(raw_key.replace("-", "_").replace(" ", "_"))
        return alias
    key = raw_key.replace("-", "_").replace(" ", "_")
    return KEY_ALIASES.get(key)


def parse_season_summary(text: str) -> dict[str, Any]:
    stats: dict[str, float | int] = {}
    unknown_lines: list[str] = []
    parsed_pairs: list[tuple[str, float | int]] = []

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in lines:
        tokens = [t.strip() for t in re.split(r"[|,;]+", line) if t.strip()]
        line_parsed = False
        for token in tokens:
            multi_pairs = re.findall(r"(?i)\b([A-Za-z0-9_%\-]+)\s*[:=]\s*([0-9.]+%?)", token)
            if len(multi_pairs) >= 2:
                for raw_key, raw_val in multi_pairs:
                    norm_key = _normalize_key(raw_key)
                    value = _to_number(raw_val)
                    if norm_key is None or value is None:
                        continue
                    if norm_key in INT_FIELDS:
                        value = int(round(float(value)))
                    elif norm_key in FLOAT_FIELDS:
                        value = float(value)
                    stats[norm_key] = value
                    parsed_pairs.append((norm_key, value))
                    line_parsed = True
                continue

            m = re.match(r"(?i)^\s*([A-Za-z0-9_%\-\s]+)\s*[:=]\s*([0-9.]+%?)\s*$", token)
            if not m:
                m = re.match(r"(?i)^\s*([A-Za-z0-9_%\-\s]+)\s+([0-9.]+%?)\s*$", token)
            if not m:
                continue
            norm_key = _normalize_key(m.group(1))
            value = _to_number(m.group(2))
            if norm_key is None or value is None:
                continue
            if norm_key in INT_FIELDS:
                value = int(round(float(value)))
            elif norm_key in FLOAT_FIELDS:
                value = float(value)
            stats[norm_key] = value
            parsed_pairs.append((norm_key, value))
            line_parsed = True
        if not line_parsed:
            unknown_lines.append(line)
    return {"stats": stats, "unknown_lines": unknown_lines, "parsed_pairs": parsed_pairs}


def compute_season_summary_metrics(stats: dict[str, Any]) -> dict[str, float]:
    def getf(key: str) -> float:
        try:
            return float(stats.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    ab = getf("ab")
    h = getf("h")
    bb = getf("bb")
    hbp = getf("hbp")
    sf = getf("sf")
    so = getf("so")
    innings = getf("innings_caught")
    pb = getf("pb")
    games = getf("games")
    sba = getf("sb_allowed")
    cs = getf("cs")
    doubles = getf("2b")
    triples = getf("3b")
    hr = getf("hr")
    singles = getf("1b") if "1b" in stats else max(0.0, h - doubles - triples - hr)
    tb = singles + (2 * doubles) + (3 * triples) + (4 * hr)
    pa = ab + bb + hbp + sf

    metrics: dict[str, float] = {}
    if ab > 0:
        metrics["avg"] = h / ab
        metrics["slg"] = tb / ab
    if (ab + bb + hbp + sf) > 0:
        metrics["obp"] = (h + bb + hbp) / (ab + bb + hbp + sf)
    if "obp" in metrics and "slg" in metrics:
        metrics["ops"] = metrics["obp"] + metrics["slg"]
    if pa > 0:
        metrics["k_pct"] = so / pa
        metrics["bb_pct"] = bb / pa
    if games > 0:
        metrics["pb_per_game"] = pb / games
    if innings > 0:
        metrics["pb_per_inning"] = pb / innings
    if sba > 0:
        metrics["cs_rate"] = cs / sba
    for key in ("avg", "obp", "slg", "ops", "transfer_time", "pop_time"):
        if key in stats and key not in metrics:
            try:
                metrics[key] = float(stats[key])
            except (TypeError, ValueError):
                pass
    return metrics
