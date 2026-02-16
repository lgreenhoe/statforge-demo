from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

try:
    import altair as alt
except Exception:  # pragma: no cover - fallback when altair is unavailable
    alt = None  # type: ignore[assignment]

from statforge_core.consistency import compute_consistency
from statforge_core.metrics import compute_catching_metrics, compute_hitting_metrics
from statforge_core.pop_time import calculate_pop_metrics
from statforge_core.recommendations import generate_recommendations
from statforge_core.season_summary import compute_season_summary_metrics
from statforge_web.drill_library import DRILL_LIBRARY, filter_drill_library, match_library_drills
from statforge_web.drills import build_training_suggestions
from statforge_web.ui_constants import APP_SIGNATURE, APP_SUBTITLE, APP_TITLE, HELP_TEXT, METRIC_HELP, SECTION_GAP_MD
from statforge_web.ui_styles import get_app_css

DATA_DIR = Path(__file__).resolve().parent / "demo_data"
NAV_SCREENS = [
    "Player",
    "Teams",
    "Add Game + Stats",
    "Practice",
    "Season Summary",
    "Team Dashboard",
    "Video Analysis",
    "Dashboard",
    "Trends",
]
NAV_ICONS = {
    "Player": "👤",
    "Teams": "👥",
    "Add Game + Stats": "🗂️",
    "Practice": "🏋️",
    "Season Summary": "🧾",
    "Team Dashboard": "📋",
    "Video Analysis": "🎬",
    "Dashboard": "📊",
    "Trends": "📈",
}
WEB_SECTIONS = ["Dashboard", "Development Plan ⭐", "Games", "Practice", "Trends", "Pop Time", "Export"]
METRIC_LABELS = {
    "avg": "AVG",
    "obp": "OBP",
    "slg": "SLG",
    "ops": "OPS",
    "k_rate": "K Rate",
    "bb_rate": "BB Rate",
    "cs_pct": "CS%",
    "pb_rate": "PB Rate",
}
DATE_COLUMNS = ("date", "game_date", "session_date", "event_date")
PLAYER_FILTER_KEY = "sidebar_player"
SEASON_FILTER_KEY = "sidebar_season"
GAME_FILTER_KEY = "sidebar_game"
NAV_FILTER_KEY = "sidebar_nav"
RESET_FILTERS_KEY = "sidebar_reset_filters"
COACH_NOTES_KEY = "coach_notes"


def _query_param_value(name: str) -> str | None:
    try:
        raw = st.query_params.get(name)
    except Exception:
        return None
    if raw is None:
        return None
    if isinstance(raw, list):
        return str(raw[0]) if raw else None
    return str(raw)


def _safe_default_from_query(
    key: str, options: list[str], default: str, query_name: str | None = None
) -> str:
    current = st.session_state.get(key)
    if current in options:
        return str(current)
    query_val = _query_param_value(query_name or key)
    if query_val in options:
        st.session_state[key] = query_val
        return query_val
    st.session_state[key] = default
    return default


def _inject_noindex() -> None:
    st.markdown(
        '<meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">',
        unsafe_allow_html=True,
    )


def _inject_styles() -> None:
    st.markdown(get_app_css(), unsafe_allow_html=True)


def _expected_password() -> str | None:
    secret_val: str | None = None
    try:
        secret_val = st.secrets.get("APP_PASSWORD")
    except StreamlitSecretNotFoundError:
        secret_val = None
    if secret_val:
        return str(secret_val)
    return os.getenv("STATFORGE_WEB_PASSWORD")


def _password_gate() -> bool:
    expected = _expected_password()
    if not expected:
        st.error("Demo password is not configured. Set APP_PASSWORD or STATFORGE_WEB_PASSWORD.")
        return False

    if st.session_state.get("authed"):
        return True

    st.subheader("Private Demo Access")
    with st.form("demo_access_form", clear_on_submit=False):
        provided = st.text_input("Password", type="password")
        remember_session = st.checkbox(
            "Remember me this session",
            value=bool(st.session_state.get("remember_me", True)),
            help="Keep the demo unlocked for this browser session.",
        )
        submitted = st.form_submit_button("Enter Demo")

    if submitted:
        if provided == expected:
            st.session_state["remember_me"] = remember_session
            st.session_state["auth_error"] = ""
            if remember_session:
                st.session_state["authed"] = True
                st.rerun()
            return True
        st.session_state["auth_error"] = (
            "Incorrect password. Please try again. "
            "If this is a shared demo, verify APP_PASSWORD or STATFORGE_WEB_PASSWORD is set correctly."
        )

    auth_error = st.session_state.get("auth_error")
    if auth_error:
        st.error(str(auth_error))
    return False


@st.cache_data(show_spinner=False)
def _load_demo_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    players = pd.read_csv(DATA_DIR / "players.csv")
    games = pd.read_csv(DATA_DIR / "games.csv")
    practice = pd.read_csv(DATA_DIR / "practice.csv")
    season_summaries = pd.read_csv(DATA_DIR / "season_summaries.csv")
    return players, games, practice, season_summaries


def _fmt_rate(value: float | None, places: int = 3) -> str:
    if value is None:
        return "—"
    return f"{value:.{places}f}".lstrip("0")


def _fmt_float(value: float | None, places: int = 3) -> str:
    if value is None:
        return "—"
    return f"{value:.{places}f}"


def _fmt_seconds(value: float | None, places: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{places}f}s"


def _fmt_percent(value: float | None, places: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.{places}f}%"


def _fmt_signed(value: float | None, places: int = 3) -> str:
    if value is None:
        return "—"
    return f"{value:+.{places}f}"


def _trend_arrow(delta: float, inverse_better: bool = False) -> str:
    if abs(delta) < 0.005:
        return "→"
    if inverse_better:
        return "▲" if delta < 0 else "▼"
    return "▲" if delta > 0 else "▼"


def _reset_filters_state() -> None:
    reset_keys = [
        PLAYER_FILTER_KEY,
        SEASON_FILTER_KEY,
        GAME_FILTER_KEY,
        NAV_FILTER_KEY,
        COACH_NOTES_KEY,
        "trend_inseason_season",
        "drill_category_filter",
    ]
    for key in reset_keys:
        if key in st.session_state:
            del st.session_state[key]
    try:
        st.query_params.clear()
    except Exception:
        pass


def _render_empty_state(message: str, hint: str, button_key: str) -> None:
    st.info(message)
    st.caption(hint)
    if st.button("Reset Filters", key=button_key):
        _reset_filters_state()
        st.rerun()


def _fmt_metric_for_table(metric_key: str, value: float | None) -> str:
    if metric_key in {"k_rate", "bb_rate", "cs_pct", "pb_rate"}:
        return _fmt_percent(value)
    return _fmt_rate(value)


def _window_metrics(window_games: pd.DataFrame) -> dict[str, float | None]:
    if window_games.empty:
        return {
            "avg": None,
            "obp": None,
            "slg": None,
            "ops": None,
            "k_rate": None,
            "bb_rate": None,
            "cs_pct": None,
            "pb_rate": None,
        }

    totals = {
        "ab": float(window_games["ab"].sum()),
        "h": float(window_games["h"].sum()),
        "doubles": float(window_games["doubles"].sum()),
        "triples": float(window_games["triples"].sum()),
        "hr": float(window_games["hr"].sum()),
        "bb": float(window_games["bb"].sum()),
        "so": float(window_games["so"].sum()),
        "rbi": float(window_games["rbi"].sum()),
        "sb": float(window_games["sb"].sum()),
        "cs": float(window_games["cs"].sum()),
        "innings_caught": float(window_games["innings_caught"].sum()),
        "passed_balls": float(window_games["passed_balls"].sum()),
        "sb_allowed": float(window_games["sb_allowed"].sum()),
        "cs_caught": float(window_games["cs_caught"].sum()),
    }

    hitting = compute_hitting_metrics(totals)
    catching = compute_catching_metrics(totals)
    pa = totals["ab"] + totals["bb"]

    return {
        "avg": hitting["AVG"],
        "obp": hitting["OBP"],
        "slg": hitting["SLG"],
        "ops": hitting["OPS"],
        "k_rate": (totals["so"] / pa) if pa else 0.0,
        "bb_rate": (totals["bb"] / pa) if pa else 0.0,
        "cs_pct": catching["CS%"],
        "pb_rate": catching["PB Rate"],
    }


def _build_recommendation_metrics(
    games_sorted: pd.DataFrame,
    practice_df: pd.DataFrame,
) -> dict[str, float | None]:
    season_metrics = _window_metrics(games_sorted)
    last5_metrics = _window_metrics(games_sorted.head(5))
    last10_metrics = _window_metrics(games_sorted.head(10))

    practice_sorted = practice_df.sort_values(["season_label", "session_no"], ascending=[False, False])
    transfer_avg = practice_sorted["transfer_time"].astype(float).mean() if not practice_sorted.empty else None
    pop_avg = practice_sorted["pop_time"].astype(float).mean() if not practice_sorted.empty else None
    transfer_last5 = practice_sorted.head(5)["transfer_time"].astype(float).mean() if not practice_sorted.empty else None
    pop_last5 = practice_sorted.head(5)["pop_time"].astype(float).mean() if not practice_sorted.empty else None

    transfer_samples = practice_sorted["transfer_time"].dropna().astype(float).tolist() if not practice_sorted.empty else []
    obp_samples: list[float] = []
    for _, row in games_sorted.iterrows():
        ab = float(row["ab"])
        bb = float(row["bb"])
        h = float(row["h"])
        denom = ab + bb
        if denom > 0:
            obp_samples.append((h + bb) / denom)

    transfer_cons = compute_consistency(transfer_samples) if len(transfer_samples) >= 2 else None
    obp_cons = compute_consistency(obp_samples) if len(obp_samples) >= 2 else None

    return {
        "avg_season": season_metrics["avg"],
        "obp_season": season_metrics["obp"],
        "slg_season": season_metrics["slg"],
        "ops_season": season_metrics["ops"],
        "k_rate_season": season_metrics["k_rate"],
        "bb_rate_season": season_metrics["bb_rate"],
        "cs_pct_season": season_metrics["cs_pct"],
        "pb_rate_season": season_metrics["pb_rate"],
        "avg_last5": last5_metrics["avg"],
        "obp_last5": last5_metrics["obp"],
        "slg_last5": last5_metrics["slg"],
        "ops_last5": last5_metrics["ops"],
        "k_rate_last5": last5_metrics["k_rate"],
        "bb_rate_last5": last5_metrics["bb_rate"],
        "cs_pct_last5": last5_metrics["cs_pct"],
        "pb_rate_last5": last5_metrics["pb_rate"],
        "avg_last10": last10_metrics["avg"],
        "obp_last10": last10_metrics["obp"],
        "slg_last10": last10_metrics["slg"],
        "ops_last10": last10_metrics["ops"],
        "k_rate_last10": last10_metrics["k_rate"],
        "bb_rate_last10": last10_metrics["bb_rate"],
        "cs_pct_last10": last10_metrics["cs_pct"],
        "pb_rate_last10": last10_metrics["pb_rate"],
        "ops_delta_last5_vs_season": None
        if last5_metrics["ops"] is None or season_metrics["ops"] is None
        else float(last5_metrics["ops"]) - float(season_metrics["ops"]),
        "k_rate_delta_last5_vs_season": None
        if last5_metrics["k_rate"] is None or season_metrics["k_rate"] is None
        else float(last5_metrics["k_rate"]) - float(season_metrics["k_rate"]),
        "transfer_avg": transfer_avg,
        "transfer_last5": transfer_last5,
        "transfer_delta_last5_vs_season": None
        if transfer_last5 is None or transfer_avg is None
        else float(transfer_last5) - float(transfer_avg),
        "pop_time_avg": pop_avg,
        "pop_time_last5": pop_last5,
        "pop_delta_last5_vs_season": None
        if pop_last5 is None or pop_avg is None
        else float(pop_last5) - float(pop_avg),
        "transfer_consistency_cv": None if transfer_cons is None else transfer_cons.get("cv"),
        "obp_consistency_cv": None if obp_cons is None else obp_cons.get("cv"),
    }


def _delta_label(delta: float | None, inverse_better: bool = False, suffix: str = "") -> str:
    if delta is None:
        return "stable"
    if abs(delta) < 0.005:
        return "stable"
    if inverse_better:
        direction = "improving" if delta < 0 else "declining"
    else:
        direction = "up" if delta > 0 else "down"
    return f"{direction}{suffix}"


def _build_filtered_export_frame(
    ctx: dict[str, Any], games_df: pd.DataFrame, practice_df: pd.DataFrame, summaries_df: pd.DataFrame
) -> pd.DataFrame:
    filter_meta = {
        "player_name": str(ctx["player"]["player_name"]),
        "season_filter": str(ctx["season"]),
        "game_filter": str(ctx["selected_game_label"]),
        "date_range": (
            "All"
            if not ctx.get("date_range")
            else f"{ctx['date_range'][0].date().isoformat()} to {ctx['date_range'][1].date().isoformat()}"
        ),
        "coach_notes": str(ctx.get("coach_notes", "")),
    }
    frames: list[pd.DataFrame] = []
    for source, df in [
        ("games", games_df.copy()),
        ("practice", practice_df.copy()),
        ("season_summaries", summaries_df.copy()),
    ]:
        if df.empty:
            continue
        enriched = df.copy()
        enriched.insert(0, "source", source)
        for k, v in filter_meta.items():
            enriched[k] = v
        frames.append(enriched)
    if not frames:
        return pd.DataFrame([{"source": "empty", **filter_meta}])
    return pd.concat(frames, ignore_index=True, sort=False)


def _build_export_csv(ctx: dict[str, Any], games_df: pd.DataFrame, practice_df: pd.DataFrame, summaries_df: pd.DataFrame) -> str:
    export_df = _build_filtered_export_frame(ctx, games_df, practice_df, summaries_df)
    timestamp = datetime.now(timezone.utc).isoformat()
    date_range = ctx.get("date_range")
    date_txt = "All" if not date_range else f"{date_range[0].date().isoformat()} to {date_range[1].date().isoformat()}"
    header_lines = [
        f"# Export generated_at_utc: {timestamp}",
        f"# Filter player: {ctx['player']['player_name']}",
        f"# Filter season: {ctx['season']}",
        f"# Filter game: {ctx['selected_game_label']}",
        f"# Filter date_range: {date_txt}",
        f"# Coach notes: {str(ctx.get('coach_notes', '')).strip() or '(none)'}",
    ]
    buffer = StringIO()
    export_df.to_csv(buffer, index=False)
    return "\n".join(header_lines) + "\n" + buffer.getvalue()


def _render_sidebar_filters_summary(ctx: dict[str, Any], games_df: pd.DataFrame) -> None:
    date_range = ctx.get("date_range")
    date_txt = "All dates"
    if date_range:
        date_txt = f"{date_range[0].date().isoformat()} to {date_range[1].date().isoformat()}"
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### Current View")
    st.sidebar.caption(
        f"Player: {ctx['player']['player_name']}\n"
        f"Season: {ctx['season']}\n"
        f"Game: {ctx['selected_game_label']}\n"
        f"Date Range: {date_txt}\n"
        f"Games in Scope: {len(games_df)}"
    )
    if st.sidebar.button("Reset filters", key=RESET_FILTERS_KEY, use_container_width=True):
        _reset_filters_state()
        st.session_state[PLAYER_FILTER_KEY] = str(ctx.get("default_player", ""))
        st.session_state[SEASON_FILTER_KEY] = "All"
        st.session_state[GAME_FILTER_KEY] = "All"
        st.session_state[NAV_FILTER_KEY] = str(ctx.get("default_nav", "📊 Dashboard"))
        st.rerun()


def _render_share_view(ctx: dict[str, Any]) -> None:
    params = {
        "player": str(ctx["player"]["player_name"]),
        "season": str(ctx["season"]),
        "game": str(ctx["selected_game_label"]),
        "section": str(ctx["section"]),
    }
    query_string = urlencode(params)
    st.sidebar.markdown("#### Share this view")
    st.sidebar.caption("Copy this query string and append it to the app URL:")
    st.sidebar.code(f"?{query_string}", language="text")
    st.sidebar.caption(
        f"Current filters: {ctx['player']['player_name']} | {ctx['season']} | {ctx['selected_game_label']}"
    )
    if st.sidebar.button("Apply filters to URL", use_container_width=True):
        try:
            st.query_params.clear()
            for key, value in params.items():
                st.query_params[key] = value
            st.sidebar.success("URL updated with current filters.")
        except Exception:
            st.sidebar.info("Query parameters are not supported in this environment.")


def _render_sidebar_export(ctx: dict[str, Any], games_df: pd.DataFrame, practice_df: pd.DataFrame, summaries_df: pd.DataFrame) -> None:
    st.sidebar.markdown("#### Coach Notes")
    st.sidebar.text_area(
        "Session-only notes",
        key=COACH_NOTES_KEY,
        height=110,
        placeholder="Add temporary coaching notes for this filtered view...",
        help="Stored in browser session only; never written to disk.",
    )
    ctx["coach_notes"] = str(st.session_state.get(COACH_NOTES_KEY, "")).strip()
    st.sidebar.markdown("#### Export")
    st.sidebar.download_button(
        label="Export current view to CSV",
        data=_build_export_csv(ctx, games_df, practice_df, summaries_df),
        file_name="statforge_current_view.csv",
        mime="text/csv",
        use_container_width=True,
    )


def _render_drill_library_matches(query: str, category: str | None = None, max_items: int = 2) -> None:
    matches = match_library_drills(query, category=category, limit=max_items)
    for drill in matches:
        with st.expander(f"Drill Library: {drill['name']} [{drill['id']}]", expanded=False):
            st.write(f"**Category:** {drill['category']}  |  **Duration:** {drill['duration_minutes']} min")
            st.write(f"**Goal:** {drill['goal']}")
            st.write(f"**Setup:** {drill['setup']}")
            st.write(f"**Volume:** {drill['reps_volume']}")
            st.write(f"**Coaching cues:** {drill['coaching_cues']}")
            st.write(f"**Progression:** {drill['progression']}")
            st.write(f"**Equipment:** {drill['equipment']}")


def _build_sidebar(players: pd.DataFrame, games: pd.DataFrame) -> dict[str, Any]:
    st.sidebar.markdown("### StatForge Demo")
    st.sidebar.caption("Executive coaching workspace")
    st.sidebar.success(HELP_TEXT["demo_readonly"])

    player_options = players["player_name"].tolist()
    default_player = player_options[0] if player_options else ""
    _safe_default_from_query(PLAYER_FILTER_KEY, player_options, default_player, query_name="player")
    player_name = st.sidebar.selectbox("Player", options=player_options, key=PLAYER_FILTER_KEY)
    player_row = players.loc[players["player_name"] == player_name].iloc[0]
    player_id = int(player_row["player_id"])

    player_games = games.loc[games["player_id"] == player_id].copy()
    seasons = sorted(player_games["season_label"].dropna().astype(str).unique().tolist())
    season_options = ["All"] + seasons
    _safe_default_from_query(SEASON_FILTER_KEY, season_options, "All", query_name="season")
    season = st.sidebar.selectbox("Season", options=season_options, key=SEASON_FILTER_KEY)

    if season != "All":
        scoped_games = player_games.loc[player_games["season_label"].astype(str) == season].copy()
    else:
        scoped_games = player_games.copy()

    date_col = next((col for col in DATE_COLUMNS if col in scoped_games.columns), None)
    date_range: tuple[pd.Timestamp, pd.Timestamp] | None = None
    if date_col:
        parsed_dates = pd.to_datetime(scoped_games[date_col], errors="coerce").dropna()
        if not parsed_dates.empty:
            min_date = parsed_dates.min().date()
            max_date = parsed_dates.max().date()
            selected_dates = st.sidebar.date_input(
                "Date Range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
            )
            if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
                start, end = selected_dates
                date_range = (pd.Timestamp(start), pd.Timestamp(end))
                scoped_games = scoped_games.assign(
                    _parsed_date=pd.to_datetime(scoped_games[date_col], errors="coerce")
                )
                scoped_games = scoped_games.loc[
                    scoped_games["_parsed_date"].between(date_range[0], date_range[1], inclusive="both")
                ].drop(columns=["_parsed_date"])
        else:
            st.sidebar.caption("Date range selector unavailable for this dataset.")
    else:
        st.sidebar.caption("Date range selector unavailable for this dataset.")

    scoped_games = scoped_games.sort_values(["season_label", "game_no"], ascending=[False, False])
    game_options = ["All"] + [
        f"{row['season_label']} • Game {int(row['game_no'])}" for _, row in scoped_games.iterrows()
    ]
    _safe_default_from_query(GAME_FILTER_KEY, game_options, "All", query_name="game")
    selected_game_label = st.sidebar.selectbox("Game", options=game_options, key=GAME_FILTER_KEY)

    nav_options = [f"{NAV_ICONS.get(screen, '')} {screen}" for screen in NAV_SCREENS]
    default_nav = f"{NAV_ICONS.get('Dashboard', '')} Dashboard"
    section_from_query = _query_param_value("section")
    if section_from_query:
        section_candidate = f"{NAV_ICONS.get(section_from_query, '')} {section_from_query}"
        if section_candidate in nav_options:
            st.session_state[NAV_FILTER_KEY] = section_candidate
    _safe_default_from_query(NAV_FILTER_KEY, nav_options, default_nav, query_name="section")
    tk_screen_with_icon = st.sidebar.selectbox(
        "Navigation",
        options=nav_options,
        key=NAV_FILTER_KEY,
    )
    tk_screen = tk_screen_with_icon.split(" ", 1)[1] if " " in tk_screen_with_icon else tk_screen_with_icon

    nav_map = {
        "Player": "Dashboard",
        "Teams": "Dashboard",
        "Add Game + Stats": "Games",
        "Practice": "Practice",
        "Season Summary": "Dashboard",
        "Team Dashboard": "Trends",
        "Video Analysis": "Pop Time",
        "Dashboard": "Dashboard",
        "Trends": "Trends",
    }
    section = nav_map.get(tk_screen, "Dashboard")

    st.sidebar.markdown("---")
    st.sidebar.caption("Read-only preview. Desktop app handles all editing and saves.")

    return {
        "player": player_row,
        "player_id": player_id,
        "player_games": player_games,
        "scoped_games": scoped_games,
        "date_range": date_range,
        "season": season,
        "selected_game_label": selected_game_label,
        "tk_screen": tk_screen,
        "section": section,
        "default_player": default_player,
        "default_nav": default_nav,
    }


def _render_top_header(ctx: dict[str, Any]) -> None:
    player = ctx["player"]
    season = ctx["season"]
    game = ctx["selected_game_label"]
    st.markdown(
        (
            '<div class="sf-header"><div class="sf-header-top">'
            f'<div class="sf-brand"><div class="sf-wordmark">{APP_TITLE}</div>'
            f'<div class="sf-tagline">{APP_SUBTITLE}</div>'
            '<div class="sf-tagline-secondary">Demo • Read-only • Anonymized</div>'
            f'<div class="sf-subtitle">{APP_SIGNATURE}</div></div>'
            '<div class="sf-badge-row">'
            '<span class="sf-badge">Demo</span>'
            '<span class="sf-badge">Read-only</span>'
            '<span class="sf-badge">Anonymized</span>'
            '</div>'
            '</div>'
            '<div class="sf-context">'
            f'<span class="sf-chip">Player: {player["player_name"]}</span>'
            f'<span class="sf-chip">Position: {player["position"]}</span>'
            f'<span class="sf-chip">Level: {player["level"]}</span>'
            f'<span class="sf-chip">Season: {season}</span>'
            f'<span class="sf-chip">Game: {game}</span>'
            '</div>'
            '<div class="sf-trust-row">'
            '<span>Demo Dataset Snapshot • Feb 2026</span>'
            '<span>Logic Version • v0.9 (Preview)</span>'
            '</div></div>'
        ),
        unsafe_allow_html=True,
    )


def _render_kpi_cards(
    season_metrics: dict[str, float | None],
    last5_metrics: dict[str, float | None],
    last10_metrics: dict[str, float | None],
    practice_df: pd.DataFrame,
) -> None:
    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Key KPIs</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-card-subtitle">Season baseline with recent movement against last 5 and last 10 samples.</div>',
        unsafe_allow_html=True,
    )
    practice_sorted = practice_df.sort_values(["season_label", "session_no"], ascending=[False, False])
    transfer_avg = practice_sorted["transfer_time"].astype(float).mean() if not practice_sorted.empty else None
    pop_avg = practice_sorted["pop_time"].astype(float).mean() if not practice_sorted.empty else None
    transfer_last5 = practice_sorted.head(5)["transfer_time"].astype(float).mean() if not practice_sorted.empty else None
    transfer_last10 = practice_sorted.head(10)["transfer_time"].astype(float).mean() if not practice_sorted.empty else None
    pop_last5 = practice_sorted.head(5)["pop_time"].astype(float).mean() if not practice_sorted.empty else None
    pop_last10 = practice_sorted.head(10)["pop_time"].astype(float).mean() if not practice_sorted.empty else None

    cards = [
        {
            "label": "AVG",
            "help": METRIC_HELP["avg"],
            "value": _fmt_rate(season_metrics["avg"]),
            "delta5": None
            if last5_metrics["avg"] is None or season_metrics["avg"] is None
            else float(last5_metrics["avg"]) - float(season_metrics["avg"]),
            "delta10": None
            if last10_metrics["avg"] is None or season_metrics["avg"] is None
            else float(last10_metrics["avg"]) - float(season_metrics["avg"]),
        },
        {
            "label": "OPS",
            "help": METRIC_HELP["ops"],
            "value": _fmt_rate(season_metrics["ops"]),
            "delta5": None
            if last5_metrics["ops"] is None or season_metrics["ops"] is None
            else float(last5_metrics["ops"]) - float(season_metrics["ops"]),
            "delta10": None
            if last10_metrics["ops"] is None or season_metrics["ops"] is None
            else float(last10_metrics["ops"]) - float(season_metrics["ops"]),
        },
        {
            "label": "Exchange (s)",
            "help": METRIC_HELP["exchange"],
            "value": _fmt_float(transfer_avg),
            "delta5": None if transfer_last5 is None or transfer_avg is None else float(transfer_last5) - float(transfer_avg),
            "delta10": None if transfer_last10 is None or transfer_avg is None else float(transfer_last10) - float(transfer_avg),
        },
        {
            "label": "Pop Time (s)",
            "help": METRIC_HELP["pop_time"],
            "value": _fmt_float(pop_avg),
            "delta5": None if pop_last5 is None or pop_avg is None else float(pop_last5) - float(pop_avg),
            "delta10": None if pop_last10 is None or pop_avg is None else float(pop_last10) - float(pop_avg),
        },
    ]
    row_a = st.columns(2, gap="small")
    row_b = st.columns(2, gap="small")
    all_cols = [row_a[0], row_a[1], row_b[0], row_b[1]]
    for col, card in zip(all_cols, cards):
        with col:
            st.markdown('<div class="sf-kpi-card">', unsafe_allow_html=True)
            st.metric(
                label=card["label"],
                value=card["value"],
                delta=_fmt_signed(card["delta5"], places=3) if card["delta5"] is not None else "—",
                help=card["help"],
            )
            st.caption(
                f"What changed recently? Last 5: {_fmt_signed(card['delta5'], places=3)} | Last 10: {_fmt_signed(card['delta10'], places=3)}"
            )
            st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_training_suggestions(metric_pack: dict[str, float | None]) -> None:
    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Training Suggestions</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-card-subtitle">Deterministic mapping from stat flags to weekly drill plans.</div>',
        unsafe_allow_html=True,
    )

    suggestions = build_training_suggestions(metric_pack)
    for idx, item in enumerate(suggestions, start=1):
        st.markdown(f"**{idx}. What we're seeing**")
        st.write(item["what_were_seeing"])
        st.markdown("**What to do this week**")
        st.write(item["what_to_do_this_week"])
        st.markdown("**Drills (10 min, 2x/week)**")
        for drill in item["drills"]:
            st.markdown(f"- {drill}")
            _render_drill_library_matches(drill, max_items=1)
        if idx < len(suggestions):
            st.markdown("---")
    st.markdown("</div>", unsafe_allow_html=True)


def _render_dashboard_coach_summary(metric_pack: dict[str, float | None]) -> None:
    st.markdown('<div class="sf-card sf-standout">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Coach Summary</div>', unsafe_allow_html=True)
    st.caption("Quick interpretation from the currently filtered sample.")
    st.markdown(
        f"- OPS trend: **{_delta_label(metric_pack.get('ops_delta_last5_vs_season'))}**\n"
        f"- K-rate trend: **{_delta_label(metric_pack.get('k_rate_delta_last5_vs_season'), inverse_better=True)}**\n"
        f"- Pop time: **{_delta_label(metric_pack.get('pop_delta_last5_vs_season'), inverse_better=True)}**\n"
        f"- Exchange time: **{_delta_label(metric_pack.get('transfer_delta_last5_vs_season'), inverse_better=True)}**"
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_executive_summary(metric_pack: dict[str, float | None]) -> None:
    good_signals: list[str] = []
    needs_work: list[str] = []

    ops_delta = metric_pack.get("ops_delta_last5_vs_season")
    k_delta = metric_pack.get("k_rate_delta_last5_vs_season")
    pop_delta = metric_pack.get("pop_delta_last5_vs_season")
    cs_pct = metric_pack.get("cs_pct_season")

    if ops_delta is not None and ops_delta > 0:
        good_signals.append(f"OPS is improving ({_fmt_signed(ops_delta, 3)} vs season baseline).")
    if k_delta is not None and k_delta < 0:
        good_signals.append(f"K-rate is trending down ({_fmt_signed(k_delta, 3)} vs season baseline).")
    if pop_delta is not None and pop_delta < 0:
        good_signals.append(f"Pop time is improving ({_fmt_signed(pop_delta, 3)}s vs season baseline).")
    if not good_signals:
        good_signals.append("Performance trend is stable with no major negative movement.")

    if ops_delta is not None and ops_delta < 0:
        needs_work.append(f"OPS is below recent baseline ({_fmt_signed(ops_delta, 3)}).")
    if k_delta is not None and k_delta > 0:
        needs_work.append(f"K-rate has increased ({_fmt_signed(k_delta, 3)}).")
    if cs_pct is not None and cs_pct < 0.30:
        needs_work.append(f"CS% is low for this sample ({_fmt_percent(cs_pct)}).")
    if not needs_work:
        needs_work.append("No urgent red flags detected in this filter scope.")

    next_action = (
        "Run a focused 2x/week catching + plate-discipline block and monitor Last 5 deltas on OPS, K-rate, and Pop time."
    )

    st.markdown('<div class="sf-card sf-standout">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Executive Summary</div>', unsafe_allow_html=True)
    st.markdown(
        f"- **What’s good:** {good_signals[0]}\n"
        f"- **What needs work:** {needs_work[0]}\n"
        f"- **What to do next:** {next_action}"
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_key_metric_help_row(season_metrics: dict[str, float | None], metric_pack: dict[str, float | None]) -> None:
    c1, c2, c3 = st.columns(3, gap="small")
    c4, c5 = st.columns(2, gap="small")
    c1.metric("OPS", _fmt_rate(season_metrics.get("ops")), help=METRIC_HELP["ops"])
    c2.metric("K-rate", _fmt_percent(season_metrics.get("k_rate")), help=METRIC_HELP["k_rate"])
    c3.metric("CS%", _fmt_percent(season_metrics.get("cs_pct")), help=METRIC_HELP["cs_pct"])
    c4.metric("Pop time", _fmt_seconds(metric_pack.get("pop_time_avg"), 2), help=METRIC_HELP["pop_time"])
    c5.metric("Exchange", _fmt_seconds(metric_pack.get("transfer_avg"), 2), help=METRIC_HELP["exchange"])


def _build_recent_trend_insight(perf_df: pd.DataFrame) -> str:
    if perf_df.empty or len(perf_df) < 3:
        return "Insight: Not enough recent data to summarize trends."

    lookback = min(5, len(perf_df))
    recent = perf_df.tail(lookback)
    if len(recent) < 3:
        return "Insight: Not enough recent data to summarize trends."

    ops_start = float(recent["OPS"].iloc[0])
    ops_end = float(recent["OPS"].iloc[-1])
    k_start = float(recent["K Rate"].iloc[0])
    k_end = float(recent["K Rate"].iloc[-1])
    ops_delta = ops_end - ops_start
    k_delta = k_end - k_start

    if ops_delta > 0.01:
        ops_trend = "up"
        impact = "suggesting improved offensive efficiency."
    elif ops_delta < -0.01:
        ops_trend = "down"
        impact = "suggesting reduced offensive efficiency."
    else:
        ops_trend = "stable"
        impact = "suggesting steady offensive efficiency."

    if abs(k_delta) < 0.01:
        k_trend = "stable"
    elif k_delta > 0:
        k_trend = "up"
    else:
        k_trend = "down"

    return (
        f"Insight: OPS is trending {ops_trend} over the last {lookback} games "
        f"while K-rate is {k_trend}, {impact}"
    )


def _render_momentum_visual(games_sorted: pd.DataFrame) -> None:
    st.markdown('<div class="sf-card sf-standout">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Recent Performance Trend</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-card-subtitle">Last 10 games at-a-glance: OPS (higher is better) and K Rate (lower is better).</div>',
        unsafe_allow_html=True,
    )

    if games_sorted.empty:
        st.info("No games in scope for momentum view.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    sample_games = games_sorted.head(10).copy()
    sample_games = sample_games.sort_values("game_no")
    rows: list[dict[str, float | str]] = []
    for _, row in sample_games.iterrows():
        game_stats = {
            "ab": float(row["ab"]),
            "h": float(row["h"]),
            "doubles": float(row["doubles"]),
            "triples": float(row["triples"]),
            "hr": float(row["hr"]),
            "bb": float(row["bb"]),
        }
        ops = float(compute_hitting_metrics(game_stats)["OPS"])
        ab = float(row["ab"])
        bb = float(row["bb"])
        pa = ab + bb
        k_rate = (float(row["so"]) / pa) if pa else 0.0
        rows.append(
            {
                "Game": f"G{int(row['game_no'])}",
                "OPS": ops,
                "K Rate": k_rate,
            }
        )
    perf_df = pd.DataFrame(rows)

    if alt is not None:
        long_df = perf_df.melt(id_vars=["Game"], value_vars=["OPS", "K Rate"], var_name="Metric", value_name="Value")
        chart = (
            alt.Chart(long_df)
            .mark_line(point=True, strokeWidth=3)
            .encode(
                x=alt.X("Game:N", sort=None, title="Game"),
                y=alt.Y("Value:Q", axis=alt.Axis(format=".3f"), title="Metric Value"),
                color=alt.Color("Metric:N", scale=alt.Scale(range=["#2EA3FF", "#D64545"])),
                tooltip=[
                    alt.Tooltip("Game:N"),
                    alt.Tooltip("Metric:N"),
                    alt.Tooltip("Value:Q", format=".3f"),
                ],
            )
            .properties(height=250)
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.line_chart(perf_df.set_index("Game")[["OPS", "K Rate"]], use_container_width=True)
    st.caption(_build_recent_trend_insight(perf_df))
    st.markdown("</div>", unsafe_allow_html=True)


def _render_dashboard(ctx: dict[str, Any], practice_df: pd.DataFrame, summaries_df: pd.DataFrame) -> None:
    st.subheader("Dashboard")
    st.caption(HELP_TEXT["dashboard"])
    st.markdown(SECTION_GAP_MD, unsafe_allow_html=True)
    with st.expander("Getting Started", expanded=False):
        st.markdown(
            "- **What this demo is:** A read-only StatForge sample workspace using anonymized data.\n"
            "- **How to use filters:** Choose player, season, and game context from the sidebar.\n"
            "- **Dashboard:** KPI snapshot, trend summaries, and coach-facing insights.\n"
            "- **Development Plan:** Deterministic recommendation engine and drill matches.\n"
            "- **Games / Practice:** Filtered history tables and drill library browsing.\n"
            "- **Trends / Pop Time:** Trendline visuals and catcher timing snapshots.\n"
            "- **Export:** Download the current filtered view as CSV."
        )
    games_sorted = ctx["scoped_games"].sort_values(["season_label", "game_no"], ascending=[False, False])
    if games_sorted.empty:
        _render_empty_state(
            HELP_TEXT["games_empty"],
            "Try selecting 'All' season or clearing game filters to restore data.",
            "empty_dashboard_reset",
        )
        return

    season_metrics = _window_metrics(games_sorted)
    last5_metrics = _window_metrics(games_sorted.head(5))
    last10_metrics = _window_metrics(games_sorted.head(10))
    metric_pack = _build_recommendation_metrics(games_sorted, practice_df)

    _render_executive_summary(metric_pack)
    _render_dashboard_coach_summary(metric_pack)
    _render_key_metric_help_row(season_metrics, metric_pack)
    _render_kpi_cards(season_metrics, last5_metrics, last10_metrics, practice_df)
    st.info(
        "How this helps\n"
        "- Surfaces trend changes faster than manual stat review\n"
        "- Reduces spreadsheet reconciliation time\n"
        "- Focuses coaching conversations on development signals"
    )
    _render_momentum_visual(games_sorted)
    _render_training_suggestions(metric_pack)

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Performance Trends</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-card-subtitle">Compares current scope against the most recent 5 and 10 games.</div>',
        unsafe_allow_html=True,
    )
    trend_rows: list[dict[str, str]] = []
    for key, label in METRIC_LABELS.items():
        season_val = season_metrics[key]
        l5_val = last5_metrics[key]
        l10_val = last10_metrics[key]
        delta5 = None if l5_val is None or season_val is None else (l5_val - season_val)
        delta10 = None if l10_val is None or season_val is None else (l10_val - season_val)
        inverse = key in {"k_rate", "pb_rate"}
        trend_rows.append(
            {
                "Metric": label,
                "Season": _fmt_metric_for_table(key, season_val),
                "Last 5": _fmt_metric_for_table(key, l5_val),
                "Δ vs Season (5)": _fmt_metric_for_table(key, delta5) if delta5 is not None else "—",
                "Trend (5)": "—" if delta5 is None else _trend_arrow(delta5, inverse_better=inverse),
                "Last 10": _fmt_metric_for_table(key, l10_val),
                "Δ vs Season (10)": _fmt_metric_for_table(key, delta10) if delta10 is not None else "—",
                "Trend (10)": "—" if delta10 is None else _trend_arrow(delta10, inverse_better=inverse),
            }
        )
    st.dataframe(pd.DataFrame(trend_rows), use_container_width=True, hide_index=True)
    st.caption("Based on filtered demo data only.")
    st.markdown("</div>", unsafe_allow_html=True)

    totals_cols = [
        "ab",
        "h",
        "doubles",
        "triples",
        "hr",
        "bb",
        "so",
        "rbi",
        "sb",
        "cs",
        "innings_caught",
        "passed_balls",
        "sb_allowed",
        "cs_caught",
    ]
    totals = games_sorted[totals_cols].sum().to_dict() if not games_sorted.empty else {c: 0 for c in totals_cols}
    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Season Totals</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-card-subtitle">Raw volume context for hitting and catching outcomes.</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(pd.DataFrame([totals]), use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    transfer_samples = practice_df["transfer_time"].dropna().astype(float).tolist() if not practice_df.empty else []
    obp_samples: list[float] = []
    for _, row in games_sorted.iterrows():
        ab = float(row["ab"])
        bb = float(row["bb"])
        h = float(row["h"])
        denom = ab + bb
        if denom > 0:
            obp_samples.append((h + bb) / denom)

    transfer_cons = compute_consistency(transfer_samples) if len(transfer_samples) >= 2 else None
    obp_cons = compute_consistency(obp_samples) if len(obp_samples) >= 2 else None
    cons_rows = [
        {
            "Metric": "Transfer Time (s)",
            "Avg": _fmt_float(float(transfer_cons["mean"])) if transfer_cons else "—",
            "SD": _fmt_float(float(transfer_cons["sd"])) if transfer_cons else "—",
            "Grade": transfer_cons["grade"] if transfer_cons else "Not enough data",
            "N": len(transfer_samples),
        },
        {
            "Metric": "OBP",
            "Avg": _fmt_rate(float(obp_cons["mean"])) if obp_cons else "—",
            "SD": _fmt_rate(float(obp_cons["sd"])) if obp_cons else "—",
            "Grade": obp_cons["grade"] if obp_cons else "Not enough data",
            "N": len(obp_samples),
        },
    ]
    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Consistency Grades</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-card-subtitle">Sample variation score for repeatability in transfer time and OBP.</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(pd.DataFrame(cons_rows), use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    summary_rows: list[dict[str, Any]] = []
    for _, row in summaries_df.iterrows():
        raw = {
            "ab": row.get("ab", 0),
            "h": row.get("h", 0),
            "2b": row.get("doubles", 0),
            "3b": row.get("triples", 0),
            "hr": row.get("hr", 0),
            "bb": row.get("bb", 0),
            "so": row.get("so", 0),
            "sb": row.get("sb", 0),
            "cs": row.get("cs", 0),
            "sb_allowed": row.get("sb_allowed", 0),
            "innings_caught": row.get("innings_caught", 0),
            "pb": row.get("pb", 0),
            "transfer_time": row.get("transfer_time", 0),
            "pop_time": row.get("pop_time", 0),
        }
        computed = compute_season_summary_metrics(raw)
        summary_rows.append({"season_label": str(row["season_label"]), **computed})
    if summary_rows:
        st.markdown('<div class="sf-card">', unsafe_allow_html=True)
        st.markdown('<div class="sf-card-title">Season Summary Baseline</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="sf-card-subtitle">Imported baseline metrics to compare against current in-season performance.</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_development_plan(ctx: dict[str, Any], practice_df: pd.DataFrame) -> None:
    st.subheader("Development Plan")
    st.caption(HELP_TEXT["development_plan"])

    games_sorted = ctx["scoped_games"].sort_values(["season_label", "game_no"], ascending=[False, False])
    metric_pack = _build_recommendation_metrics(games_sorted, practice_df)
    recs = generate_recommendations(metric_pack, max_items=3)

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Top 3 Focus Areas</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-card-subtitle">Deterministic rules engine from the current filtered player profile.</div>',
        unsafe_allow_html=True,
    )

    if not recs:
        _render_empty_state(
            "No recommendation triggers were exceeded for this filter scope.",
            "Try changing season or player filters to compare a different sample.",
            "empty_development_reset",
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    plan_lines: list[str] = [f"{ctx['player']['player_name']} Development Plan"]
    coach_summary: list[str] = []
    for idx, rec in enumerate(recs, start=1):
        header = f"{idx}. {rec.title} ({rec.priority} • {rec.category})"
        plan_lines.append(header)
        plan_lines.append(f"Why: {rec.why_this_triggered}")
        time_estimate = f"{max(1, len(rec.drills)) * 10} min total"
        drill_names = ", ".join([drill.name for drill in rec.drills]) if rec.drills else "No drills listed"
        cues = "; ".join([drill.coaching_cues for drill in rec.drills]) if rec.drills else "No cues listed"
        st.markdown('<div class="sf-card sf-plan-card">', unsafe_allow_html=True)
        st.markdown(f"**Trigger:** {rec.title}")
        st.markdown(f"**Why:** {rec.why_this_triggered}")
        st.markdown(f"**Priority:** {rec.priority}  |  **Category:** {rec.category}")
        st.markdown(f"**Time estimate:** {time_estimate}")
        st.markdown(f"**Drills:** {drill_names}")
        st.markdown(f"**Coaching cues:** {cues}")
        with st.expander("View drill details", expanded=(idx == 1)):
            for drill in rec.drills:
                st.markdown(
                    f"- **{drill.name}**  \n"
                    f"  Setup: {drill.setup}  \n"
                    f"  Volume: {drill.reps_sets}  \n"
                    f"  Coaching cues: {drill.coaching_cues}  \n"
                    f"  Progression: {drill.progression}"
                )
                plan_lines.append(f"  - {drill.name}: {drill.reps_sets}")
                _render_drill_library_matches(drill.name, category=rec.category, max_items=1)
        st.markdown("</div>", unsafe_allow_html=True)
        coach_summary.append(f"{rec.title}: {rec.why_this_triggered}")
        plan_lines.append("")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Coach Summary</div>', unsafe_allow_html=True)
    st.markdown(
        f"- Priority focus this cycle: **{recs[0].title}** ({recs[0].priority}).  \n"
        f"- Current K Rate: **{_fmt_rate(metric_pack.get('k_rate_season'))}** | OPS delta (L5 vs season): **{_fmt_signed(metric_pack.get('ops_delta_last5_vs_season'))}**.  \n"
        f"- Catching profile: Exchange **{_fmt_float(metric_pack.get('transfer_avg'))}s**, Pop **{_fmt_float(metric_pack.get('pop_time_avg'))}s**, CS% **{_fmt_rate(metric_pack.get('cs_pct_season'))}**."
    )
    st.markdown("</div>", unsafe_allow_html=True)

    plan_text = "\n".join(plan_lines).strip()
    st.download_button(
        label="Download Plan (TXT)",
        data=plan_text,
        file_name="statforge_development_plan.txt",
        mime="text/plain",
        use_container_width=False,
    )


def _render_games(ctx: dict[str, Any]) -> None:
    st.subheader("Add Game + Stats")
    st.caption("Game log view. Creation, editing, and deletion are available in the desktop app.")

    games_sorted = ctx["scoped_games"].sort_values(["season_label", "game_no"], ascending=[False, False]).copy()
    if games_sorted.empty:
        _render_empty_state(
            HELP_TEXT["games_empty"],
            "Use Reset Filters to return to a broader game selection.",
            "empty_games_reset",
        )
        return
    show = games_sorted.rename(
        columns={
            "season_label": "Season",
            "game_no": "Game #",
            "ab": "AB",
            "h": "H",
            "doubles": "2B",
            "triples": "3B",
            "hr": "HR",
            "bb": "BB",
            "so": "SO",
            "rbi": "RBI",
            "sb": "SB",
            "cs": "CS",
            "innings_caught": "Innings Caught",
            "passed_balls": "Passed Balls",
            "sb_allowed": "SB Allowed",
            "cs_caught": "CS Caught",
        }
    )
    st.dataframe(show, use_container_width=True, hide_index=True)

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Desktop-only Actions</div>', unsafe_allow_html=True)
    st.markdown(
        "- Save Game + Stat Line  \n- Delete Selected Game  \n- Game Notes editing",
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_practice(practice_df: pd.DataFrame) -> None:
    st.subheader("Practice")
    st.caption("Practice history view for coaching review. Session edits remain desktop-only.")

    if practice_df.empty:
        _render_empty_state(
            HELP_TEXT["practice_empty"],
            "Try a different season filter or reset filters to view available practice sessions.",
            "empty_practice_reset",
        )
    else:
        practice_sorted = practice_df.sort_values(["season_label", "session_no"], ascending=[False, False]).copy()
        practice_view = practice_sorted.rename(
            columns={
                "season_label": "Season",
                "session_no": "Session #",
                "transfer_time": "Transfer Time",
                "pop_time": "Pop Time",
            }
        )
        st.dataframe(practice_view, use_container_width=True, hide_index=True)

        count = len(practice_sorted)
        transfer_avg = float(practice_sorted["transfer_time"].astype(float).mean())
        pop_avg = float(practice_sorted["pop_time"].astype(float).mean())
        c1, c2, c3 = st.columns([1, 1, 1], gap="small")
        c1.metric("Sessions", count)
        c2.metric("Avg Transfer", _fmt_seconds(transfer_avg, 2))
        c3.metric("Avg Pop", _fmt_seconds(pop_avg, 2))

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Drill Library</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-card-subtitle">Read-only reference library. Filter by category or keyword.</div>',
        unsafe_allow_html=True,
    )
    categories = sorted({item["category"] for item in DRILL_LIBRARY})
    drill_category = st.selectbox("Category", options=["All"] + categories, key="drill_category_filter")
    drill_query = st.text_input("Search drills", value="", placeholder="e.g., transfer, strikeout, footwork")
    filtered_drills = filter_drill_library(category=drill_category, search_text=drill_query)

    if not filtered_drills:
        st.info("No drills match the current filter.")
    for drill in filtered_drills:
        with st.expander(f"{drill['name']} ({drill['category']})", expanded=False):
            st.write(f"**ID:** {drill['id']}  |  **Duration:** {drill['duration_minutes']} min")
            st.write(f"**Goal:** {drill['goal']}")
            st.write(f"**Setup:** {drill['setup']}")
            st.write(f"**Volume:** {drill['reps_volume']}")
            st.write(f"**Coaching cues:** {drill['coaching_cues']}")
            st.write(f"**Progression:** {drill['progression']}")
            st.write(f"**Equipment:** {drill['equipment']}")
    st.markdown("</div>", unsafe_allow_html=True)


def _render_trends(ctx: dict[str, Any], practice_df: pd.DataFrame, summaries_df: pd.DataFrame) -> None:
    st.subheader("Trends")

    games_sorted = ctx["scoped_games"].sort_values(["season_label", "game_no"], ascending=[True, True])
    if games_sorted.empty:
        _render_empty_state(
            HELP_TEXT["trends_empty"],
            "Trends require games in scope. Reset or widen filters to continue.",
            "empty_trends_reset",
        )
        return

    metric = st.selectbox(
        "Metric",
        options=["ops", "avg", "obp", "slg", "k_rate", "bb_rate", "cs_pct", "pb_rate", "transfer", "pop"],
        format_func=lambda x: METRIC_LABELS.get(x, x.replace("_", " ").title()),
        help=(
            f"OPS: {METRIC_HELP['ops']} | "
            f"K-rate: {METRIC_HELP['k_rate']} | "
            f"CS%: {METRIC_HELP['cs_pct']} | "
            f"Exchange: {METRIC_HELP['exchange']} | "
            f"Pop time: {METRIC_HELP['pop_time']}"
        ),
    )

    season_rows: list[dict[str, Any]] = []
    for season_label, season_games in games_sorted.groupby("season_label"):
        m = _window_metrics(season_games)
        season_rows.append({"season_label": str(season_label), **m})
    season_df = pd.DataFrame(season_rows).sort_values("season_label")

    if metric in {"transfer", "pop"}:
        mcol = "transfer_time" if metric == "transfer" else "pop_time"
        line_df = (
            practice_df.groupby("season_label", as_index=False)[mcol]
            .mean()
            .rename(columns={mcol: metric})
            .sort_values("season_label")
        )
    else:
        line_df = season_df[["season_label", metric]].copy()

    st.markdown('<div class="sf-card-title">Multi-Season Trendline</div>', unsafe_allow_html=True)
    if line_df.empty:
        st.info("No data for selected metric.")
    else:
        st.line_chart(line_df.set_index("season_label"))

    st.markdown('<div class="sf-card-title">In-Season Momentum</div>', unsafe_allow_html=True)
    selected_season = st.selectbox(
        "Season for in-season view",
        options=sorted(games_sorted["season_label"].astype(str).unique().tolist()),
        key="trend_inseason_season",
    )
    in_games = games_sorted.loc[games_sorted["season_label"].astype(str) == str(selected_season)].copy()
    in_games = in_games.sort_values("game_no")
    cumulative_ops: list[float] = []
    for idx in range(1, len(in_games) + 1):
        sub = in_games.iloc[:idx]
        cumulative_ops.append(float(_window_metrics(sub)["ops"] or 0.0))
    if not in_games.empty:
        cum_df = pd.DataFrame({"game_no": in_games["game_no"].astype(int).tolist(), "ops": cumulative_ops})
        st.line_chart(cum_df.set_index("game_no"))

    if not summaries_df.empty:
        st.markdown('<div class="sf-card-title">Baseline Overlay</div>', unsafe_allow_html=True)
        baseline_rows: list[dict[str, Any]] = []
        for _, row in summaries_df.iterrows():
            stats = {
                "ab": row.get("ab", 0),
                "h": row.get("h", 0),
                "2b": row.get("doubles", 0),
                "3b": row.get("triples", 0),
                "hr": row.get("hr", 0),
                "bb": row.get("bb", 0),
                "so": row.get("so", 0),
                "sb": row.get("sb", 0),
                "cs": row.get("cs", 0),
                "sb_allowed": row.get("sb_allowed", 0),
                "innings_caught": row.get("innings_caught", 0),
                "pb": row.get("pb", 0),
            }
            computed = compute_season_summary_metrics(stats)
            baseline_rows.append({"Season": row["season_label"], **computed})
        st.dataframe(pd.DataFrame(baseline_rows), use_container_width=True, hide_index=True)


def _render_pop_time(practice_df: pd.DataFrame) -> None:
    st.subheader("Video Analysis / Pop Time")
    st.caption("Pop-time review snapshot. Frame marking and video workflows run in desktop.")

    if practice_df.empty:
        _render_empty_state(
            "No pop-time rows are available for this selection.",
            "Select a season with catching sessions or reset filters.",
            "empty_pop_reset",
        )
        return

    practice_sorted = practice_df.sort_values(["season_label", "session_no"], ascending=[False, False])
    sample = practice_sorted.iloc[0]
    transfer = float(sample["transfer_time"])
    pop = float(sample["pop_time"])

    calc = calculate_pop_metrics(
        catch_time=0.0,
        release_time=transfer,
        target_time=pop,
        metric_mode="full_pop",
    )

    c1, c2, c3 = st.columns([1, 1, 1], gap="small")
    c1.metric("Transfer", _fmt_seconds(float(calc["transfer"]), 2))
    c2.metric("Throw", _fmt_seconds(float(calc["throw_time"] or 0.0), 2))
    c3.metric("Total Pop", _fmt_seconds(float(calc["pop_total"]), 2))

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Rep Set Snapshot</div>', unsafe_allow_html=True)
    rep_table = practice_sorted.rename(
        columns={
            "season_label": "Season",
            "session_no": "Rep #",
            "transfer_time": "Transfer",
            "pop_time": "Pop",
        }
    )[["Season", "Rep #", "Transfer", "Pop"]]
    st.dataframe(rep_table, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-card-title">Desktop-only Actions</div>', unsafe_allow_html=True)
    st.markdown(
        "- Load Video / timeline scrub  \n- Mark Catch / Release / Target  \n- Auto Detect and Auto Build Rep Set  \n- Save to Practice"
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_export(ctx: dict[str, Any], practice_df: pd.DataFrame, summaries_df: pd.DataFrame) -> None:
    st.subheader("Export")
    st.caption("Read-only export for the current filtered view.")
    if ctx["scoped_games"].empty and practice_df.empty and summaries_df.empty:
        _render_empty_state(
            "No filtered rows found. Export will contain metadata only.",
            "Use reset filters to include game and practice rows in export.",
            "empty_export_reset",
        )
    csv_blob = _build_export_csv(ctx, ctx["scoped_games"], practice_df, summaries_df)
    st.download_button(
        label="Export current view to CSV",
        data=csv_blob,
        file_name="statforge_current_view.csv",
        mime="text/csv",
    )
    st.caption("Includes filter context plus in-scope games, practice, and summary rows.")


def _render_selected_section(
    section: str,
    ctx: dict[str, Any],
    practice_df: pd.DataFrame,
    summaries_df: pd.DataFrame,
) -> None:
    if section == "Dashboard":
        _render_dashboard(ctx, practice_df, summaries_df)
    elif section == "Development Plan ⭐":
        _render_development_plan(ctx, practice_df)
    elif section == "Games":
        _render_games(ctx)
    elif section == "Practice":
        _render_practice(practice_df)
    elif section == "Trends":
        _render_trends(ctx, practice_df, summaries_df)
    elif section == "Pop Time":
        _render_pop_time(practice_df)
    elif section == "Export":
        _render_export(ctx, practice_df, summaries_df)


def main() -> None:
    st.set_page_config(page_title=f"{APP_TITLE} Web Demo", layout="wide")
    _inject_noindex()
    _inject_styles()

    if not _password_gate():
        return

    players, games, practice, summaries = _load_demo_data()
    if players.empty:
        st.error("No players are available in the demo dataset. Please verify demo_data files.")
        return
    ctx = _build_sidebar(players, games)

    player_id = ctx["player_id"]
    season = ctx["season"]

    if season == "All":
        scoped_games = ctx["player_games"].copy()
        scoped_practice = practice.loc[practice["player_id"] == player_id].copy()
        scoped_summaries = summaries.loc[summaries["player_id"] == player_id].copy()
    else:
        scoped_games = ctx["player_games"].loc[ctx["player_games"]["season_label"].astype(str) == season].copy()
        scoped_practice = practice.loc[
            (practice["player_id"] == player_id) & (practice["season_label"].astype(str) == season)
        ].copy()
        scoped_summaries = summaries.loc[
            (summaries["player_id"] == player_id) & (summaries["season_label"].astype(str) == season)
        ].copy()

    date_range = ctx.get("date_range")
    if date_range:
        for col_name in DATE_COLUMNS:
            if col_name in scoped_games.columns:
                scoped_games = scoped_games.assign(_parsed_date=pd.to_datetime(scoped_games[col_name], errors="coerce"))
                scoped_games = scoped_games.loc[
                    scoped_games["_parsed_date"].between(date_range[0], date_range[1], inclusive="both")
                ].drop(columns=["_parsed_date"])
                break
        for col_name in DATE_COLUMNS:
            if col_name in scoped_practice.columns:
                scoped_practice = scoped_practice.assign(
                    _parsed_date=pd.to_datetime(scoped_practice[col_name], errors="coerce")
                )
                scoped_practice = scoped_practice.loc[
                    scoped_practice["_parsed_date"].between(date_range[0], date_range[1], inclusive="both")
                ].drop(columns=["_parsed_date"])
                break

    ctx["scoped_games"] = scoped_games
    _render_sidebar_filters_summary(ctx, scoped_games)
    _render_share_view(ctx)
    _render_sidebar_export(ctx, scoped_games, scoped_practice, scoped_summaries)

    _render_top_header(ctx)

    preferred = ctx["section"]
    ordered_sections = [preferred] + [s for s in WEB_SECTIONS if s != preferred]
    tabs = st.tabs(ordered_sections)
    for idx, section in enumerate(ordered_sections):
        with tabs[idx]:
            _render_selected_section(section, ctx, scoped_practice, scoped_summaries)

    st.markdown(
        '<div class="sf-disclaimer">Decision support tool. Not a replacement for coaching judgment.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sf-footer">StatForge Demo • Read-only • Data is anonymized</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
