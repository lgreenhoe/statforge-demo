from __future__ import annotations

from typing import Any

DrillItem = dict[str, Any]

DRILL_LIBRARY: list[DrillItem] = [
    {
        "id": "hit_two_strike_ladder",
        "name": "Two-Strike Contact Ladder",
        "category": "Hitting",
        "goal": "Reduce strikeout rate with short, controlled bat path decisions.",
        "setup": "Front toss, middle-away lanes, two-strike count simulation.",
        "reps_volume": "4 rounds x 8 swings",
        "coaching_cues": "Short path, quiet head, stay through the center line.",
        "progression": "Shrink lane width each round and add mixed pace.",
        "equipment": "Bat, balls, cones, L-screen",
        "duration_minutes": 10,
    },
    {
        "id": "hit_take_track",
        "name": "Take/Track Round",
        "category": "Hitting",
        "goal": "Improve pitch recognition and chase decisions.",
        "setup": "Coach toss from short distance; hitter tracks only.",
        "reps_volume": "3 rounds x 10 pitches",
        "coaching_cues": "Call ball/strike early and hold boundaries.",
        "progression": "Mix speed and edge location each round.",
        "equipment": "Balls, plate markers",
        "duration_minutes": 10,
    },
    {
        "id": "catch_kneedown_throw",
        "name": "Knee-Down to Throw Series",
        "category": "Catching",
        "goal": "Improve transfer rhythm and lower pop time.",
        "setup": "Receive from knee-down stance and transition immediately to throw.",
        "reps_volume": "5 sets x 5 reps",
        "coaching_cues": "Direct hand path and eliminate extra gather.",
        "progression": "Add stopwatch benchmark by set.",
        "equipment": "Catcher gear, stopwatch, target net",
        "duration_minutes": 10,
    },
    {
        "id": "catch_foot_replace",
        "name": "Foot Replacement Timing",
        "category": "Catching",
        "goal": "Clean lower-half timing during exchange and release.",
        "setup": "Dry reps then short throws to second-base target net.",
        "reps_volume": "4 sets x 6 reps",
        "coaching_cues": "Right-left replacement rhythm, shoulders level.",
        "progression": "Move from dry reps to live short-hop feeds.",
        "equipment": "Catcher gear, target net",
        "duration_minutes": 10,
    },
    {
        "id": "catch_quick_exchange",
        "name": "Quick Exchange Challenge",
        "category": "Throwing",
        "goal": "Speed up glove-to-hand transfer under pressure.",
        "setup": "Rapid-fire coach feeds with immediate exchange.",
        "reps_volume": "3 rounds x 10 feeds",
        "coaching_cues": "One-move transfer; keep hands compact.",
        "progression": "Score only clean exchanges and raise benchmark.",
        "equipment": "Balls, stopwatch",
        "duration_minutes": 10,
    },
    {
        "id": "arm_target_line",
        "name": "Target-Line Throw Series",
        "category": "Throwing",
        "goal": "Improve throw-line accuracy and reduce arm-side misses.",
        "setup": "Second-base line target with taped lane.",
        "reps_volume": "5 sets x 4 throws",
        "coaching_cues": "Finish over front side and stay through lane.",
        "progression": "Track lane-hit percentage by set.",
        "equipment": "Tape lane, net, baseballs",
        "duration_minutes": 10,
    },
    {
        "id": "arm_one_hop_accuracy",
        "name": "Transfer + One-Hop Accuracy",
        "category": "Throwing",
        "goal": "Build consistent release slot and one-hop accuracy.",
        "setup": "Coach feeds and throw to chest-high net marker.",
        "reps_volume": "4 rounds x 6 throws",
        "coaching_cues": "Stable release slot; avoid arm drag.",
        "progression": "Randomize feed location and timing.",
        "equipment": "Net marker, baseballs",
        "duration_minutes": 10,
    },
    {
        "id": "hit_gap_sequence",
        "name": "Gap-to-Gap Sequencing",
        "category": "Hitting",
        "goal": "Restore timing and directional contact quality.",
        "setup": "Alternate opposite-gap and pull-gap intent swings.",
        "reps_volume": "3 sets x 10 swings",
        "coaching_cues": "Match barrel path to pitch plane.",
        "progression": "Add offspeed recognition callout.",
        "equipment": "Bat, balls, front toss screen",
        "duration_minutes": 10,
    },
]


def _norm(text: str) -> str:
    return text.strip().lower()


def filter_drill_library(category: str = "All", search_text: str = "") -> list[DrillItem]:
    query = _norm(search_text)
    rows = DRILL_LIBRARY
    if category != "All":
        rows = [row for row in rows if row["category"] == category]
    if not query:
        return rows
    return [
        row
        for row in rows
        if query in _norm(row["name"])
        or query in _norm(row["goal"])
        or query in _norm(row["coaching_cues"])
        or query in _norm(row["setup"])
        or query in _norm(row["equipment"])
    ]


def match_library_drills(text: str, category: str | None = None, limit: int = 3) -> list[DrillItem]:
    words = [w for w in _norm(text).split() if len(w) >= 4]
    matches: list[tuple[int, DrillItem]] = []
    for row in DRILL_LIBRARY:
        if category and row["category"].lower() != category.lower():
            continue
        corpus = " ".join([row["name"], row["goal"], row["setup"], row["coaching_cues"]]).lower()
        score = sum(1 for word in words if word in corpus)
        if score > 0:
            matches.append((score, row))
    matches.sort(key=lambda x: (-x[0], x[1]["name"]))
    if matches:
        return [row for _, row in matches[:limit]]
    if category:
        fallback = [row for row in DRILL_LIBRARY if row["category"].lower() == category.lower()]
        return fallback[:limit]
    return DRILL_LIBRARY[:limit]
