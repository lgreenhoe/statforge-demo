from __future__ import annotations

from typing import Any


STAT_TRAINING_MAP: dict[str, dict[str, Any]] = {
    "AVG": {
        "title": "AVG",
        "description": "Batting average tracks hit frequency per at-bat.",
        "target_range": ".300+",
        "focus_areas": ["Barrel accuracy", "Bat path consistency", "2-strike contact quality"],
        "drills": [
            {"name": "Short Bat Contact Series", "why": "Improves barrel control through the zone.", "sets": "3 x 12 swings"},
            {"name": "Front Toss Oppo Rounds", "why": "Builds late contact and line-drive consistency.", "sets": "4 x 10 swings"},
            {"name": "2-Strike Battle BP", "why": "Trains contact-first approach under pressure.", "sets": "3 rounds of 8 pitches"},
        ],
    },
    "OBP": {
        "title": "OBP",
        "description": "On-base percentage reflects reaching base via hits and walks.",
        "target_range": ".360+",
        "focus_areas": ["Zone control", "Pitch recognition", "At-bat quality"],
        "drills": [
            {"name": "Take-Till-Strike Rounds", "why": "Improves patience and strike-zone command.", "sets": "4 rounds of 6 pitches"},
            {"name": "Ball/Strike Callout Toss", "why": "Sharpens visual pitch tracking.", "sets": "3 x 15 pitches"},
            {"name": "Intentional Count Hitting", "why": "Improves plan by count and swing decisions.", "sets": "3 rounds (0-0, 1-1, 2-2)"},
        ],
    },
    "SLG": {
        "title": "SLG",
        "description": "Slugging percentage measures total bases per at-bat (power output).",
        "target_range": ".450+",
        "focus_areas": ["Hip-shoulder separation", "Line-drive carry", "Gap authority"],
        "drills": [
            {"name": "Gap Line-Drive Tee", "why": "Builds repeatable extra-base contact path.", "sets": "4 x 10 swings"},
            {"name": "Med Ball Rotation Throws", "why": "Develops rotational power transfer.", "sets": "3 x 8 each side"},
            {"name": "High-Velo Front Toss", "why": "Improves power timing at game speed.", "sets": "4 x 8 swings"},
        ],
    },
    "OPS": {
        "title": "OPS",
        "description": "OPS combines on-base skill and power in one offensive metric.",
        "target_range": ".800+",
        "focus_areas": ["Contact quality", "Discipline", "Damage in hitter's counts"],
        "drills": [
            {"name": "Count Advantage BP", "why": "Trains aggressive swings in plus counts.", "sets": "5 rounds of 6 pitches"},
            {"name": "Decision Ladder", "why": "Links recognition to selective aggression.", "sets": "3 x 12 pitch calls"},
            {"name": "Middle-In Fastball Rounds", "why": "Improves damage on mistake pitches.", "sets": "4 x 8 swings"},
        ],
    },
    "K_RATE": {
        "title": "K Rate",
        "description": "Strikeout rate measures strikeouts per plate appearance.",
        "target_range": "< 20%",
        "focus_areas": ["2-strike approach", "Contact priority", "Early pitch recognition"],
        "drills": [
            {"name": "2-Strike Choke-Up Rounds", "why": "Shortens swing for more contact.", "sets": "4 x 8 swings"},
            {"name": "Machine Mix Recognition", "why": "Improves swing/no-swing decisions.", "sets": "3 x 12 pitches"},
            {"name": "Foul-Off Compete Drill", "why": "Builds survival in deep counts.", "sets": "5 competitive ABs"},
        ],
    },
    "BB_RATE": {
        "title": "BB Rate",
        "description": "Walk rate tracks how often a hitter earns walks per plate appearance.",
        "target_range": "8-12%",
        "focus_areas": ["Strike-zone discipline", "Pitch tracking", "Pre-pitch plan"],
        "drills": [
            {"name": "No-Swing Tracking", "why": "Improves zone recognition without swing noise.", "sets": "3 x 20 pitches"},
            {"name": "Borderline Take Drill", "why": "Builds confidence laying off edge pitches.", "sets": "4 rounds of 8"},
            {"name": "Pitch Type Calling", "why": "Improves early identification and timing.", "sets": "3 rounds of 15"},
        ],
    },
    "CS_PCT": {
        "title": "CS%",
        "description": "Caught-stealing percentage reflects throwing and transfer effectiveness.",
        "target_range": "30%+",
        "focus_areas": ["Transfer speed", "Footwork efficiency", "Throw accuracy"],
        "drills": [
            {"name": "Transfer Quick Hands", "why": "Reduces exchange time glove-to-hand.", "sets": "5 x 10 reps"},
            {"name": "Knee-Down to Throw", "why": "Improves throw quality from game setups.", "sets": "4 x 8 reps"},
            {"name": "Ladder + Throw Burst", "why": "Links foot speed to throwing rhythm.", "sets": "4 x 6 reps"},
        ],
    },
    "PB_RATE": {
        "title": "PB Rate",
        "description": "Passed-ball rate tracks blocking consistency over innings caught.",
        "target_range": "< 0.03",
        "focus_areas": ["Low-ball receive posture", "Lateral block mechanics", "Recovery speed"],
        "drills": [
            {"name": "Rapid Tennis Ball Blocks", "why": "Builds clean chest angle and soft hands.", "sets": "4 x 15 reps"},
            {"name": "Lateral Dirt-Ball Series", "why": "Improves side-to-side block movement.", "sets": "3 x 10 each side"},
            {"name": "Recover-and-Throw", "why": "Trains quick recovery after blocks.", "sets": "4 x 6 reps"},
        ],
    },
    "POP_TIME": {
        "title": "Pop Time",
        "description": "Pop time measures total catch-to-target speed for throws to bases.",
        "target_range": "1.95-2.10s",
        "focus_areas": ["Explosive transfer", "Efficient foot replacement", "Throw carry"],
        "drills": [
            {"name": "Timed Transfer Ladder", "why": "Directly reduces transfer split times.", "sets": "6 sets x 5 reps"},
            {"name": "Foot Replace to Line Throw", "why": "Improves straight-line energy transfer.", "sets": "5 x 6 reps"},
            {"name": "Pocket to Pop Repeaters", "why": "Creates repeatable quick-release pattern.", "sets": "4 x 8 reps"},
        ],
    },
    "TRANSFER_TIME": {
        "title": "Transfer Time",
        "description": "Transfer time isolates catch-to-release quickness and efficiency.",
        "target_range": "0.65-0.80s",
        "focus_areas": ["Exchange speed", "Compact arm path", "Footwork timing"],
        "drills": [
            {"name": "Rapid Exchange Series", "why": "Builds faster glove-to-hand transitions.", "sets": "5 x 12 reps"},
            {"name": "Short-Clock Transfer Drill", "why": "Trains release under timed pressure.", "sets": "6 x 5 reps"},
            {"name": "Foot-Replace Quick Throws", "why": "Syncs lower half with fast release.", "sets": "4 x 8 reps"},
        ],
    },
}


def get_stat_training(stat_key: str) -> dict[str, Any] | None:
    return STAT_TRAINING_MAP.get(stat_key)
