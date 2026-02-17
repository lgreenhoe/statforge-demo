from __future__ import annotations

from statforge_core.brand import APP_NAME, DISCLAIMER, TAGLINE

APP_TITLE = APP_NAME
APP_SUBTITLE = TAGLINE
APP_SIGNATURE = "by Anchor & Honor"
APP_DISCLAIMER = DISCLAIMER

SECTION_GAP_MD = '<div style="margin-top:0.45rem;"></div>'

HELP_TEXT = {
    "dashboard": "Read-only dashboard built from the current player and season filters.",
    "development_plan": "Deterministic recommendations only. No external services or generated content.",
    "games_empty": "No games in the current scope. Adjust filters in the sidebar to view stats.",
    "practice_empty": "No practice sessions in the current scope. Drill Library is still available below.",
    "trends_empty": "No trend data available for the selected filters.",
    "demo_readonly": "Demo Mode (Read-only)",
}

METRIC_HELP = {
    "avg": "Batting average: hits divided by at-bats.",
    "ops": "OPS: on-base percentage plus slugging percentage.",
    "k_rate": "K-rate: strikeouts divided by plate appearances; lower is better.",
    "cs_pct": "CS%: runners caught stealing divided by steal attempts allowed.",
    "exchange": "Exchange time: glove-to-hand transfer speed in seconds.",
    "pop_time": "Pop time: total catcher throw time to target in seconds.",
}
