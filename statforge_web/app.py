from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

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
from statforge_web.ui_styles import get_app_css

APP_TITLE = "StatForge"
APP_SUBTITLE = "by Anchor & Honor"
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
    provided = st.text_input("Password", type="password")
    if st.button("Enter Demo"):
        if provided == expected:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Invalid password.")
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


def _build_sidebar(players: pd.DataFrame, games: pd.DataFrame) -> dict[str, Any]:
    st.sidebar.markdown("### StatForge")
    st.sidebar.caption("Coach workspace")

    player_name = st.sidebar.selectbox("Player", options=players["player_name"].tolist())
    player_row = players.loc[players["player_name"] == player_name].iloc[0]
    player_id = int(player_row["player_id"])

    player_games = games.loc[games["player_id"] == player_id].copy()
    seasons = sorted(player_games["season_label"].dropna().astype(str).unique().tolist())
    season = st.sidebar.selectbox("Season", options=["All"] + seasons)

    if season != "All":
        scoped_games = player_games.loc[player_games["season_label"].astype(str) == season].copy()
    else:
        scoped_games = player_games.copy()

    scoped_games = scoped_games.sort_values(["season_label", "game_no"], ascending=[False, False])
    game_options = ["All"] + [
        f"{row['season_label']} • Game {int(row['game_no'])}" for _, row in scoped_games.iterrows()
    ]
    selected_game_label = st.sidebar.selectbox("Game", options=game_options)

    nav_options = [f"{NAV_ICONS.get(screen, '')} {screen}" for screen in NAV_SCREENS]
    default_nav = f"{NAV_ICONS.get('Dashboard', '')} Dashboard"
    tk_screen_with_icon = st.sidebar.selectbox(
        "Navigation",
        options=nav_options,
        index=nav_options.index(default_nav) if default_nav in nav_options else 0,
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
        "season": season,
        "selected_game_label": selected_game_label,
        "tk_screen": tk_screen,
        "section": section,
    }


def _render_top_header(ctx: dict[str, Any]) -> None:
    player = ctx["player"]
    season = ctx["season"]
    game = ctx["selected_game_label"]
    st.markdown(
        (
            '<div class="sf-header"><div class="sf-header-top">'
            f'<div class="sf-brand"><div class="sf-wordmark">{APP_TITLE}</div>'
            '<div class="sf-tagline">Turning Stats into Player Development</div>'
            f'<div class="sf-subtitle">{APP_SUBTITLE}</div></div>'
            '<span class="sf-badge">Sample Workspace · Read-only</span>'
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
    practice_df: pd.DataFrame,
) -> None:
    c1, c2, c3, c4 = st.columns(4)
    practice_sorted = practice_df.sort_values(["season_label", "session_no"], ascending=[False, False])
    transfer_avg = practice_sorted["transfer_time"].astype(float).mean() if not practice_sorted.empty else None
    pop_avg = practice_sorted["pop_time"].astype(float).mean() if not practice_sorted.empty else None
    transfer_last5 = practice_sorted.head(5)["transfer_time"].astype(float).mean() if not practice_sorted.empty else None
    pop_last5 = practice_sorted.head(5)["pop_time"].astype(float).mean() if not practice_sorted.empty else None

    for col, title, value, last5, delta, is_rate in [
        (
            c1,
            "Batting Avg",
            _fmt_rate(season_metrics["avg"]),
            _fmt_rate(last5_metrics["avg"]),
            None if last5_metrics["avg"] is None or season_metrics["avg"] is None else float(last5_metrics["avg"]) - float(season_metrics["avg"]),
            True,
        ),
        (
            c2,
            "OPS",
            _fmt_rate(season_metrics["ops"]),
            _fmt_rate(last5_metrics["ops"]),
            None if last5_metrics["ops"] is None or season_metrics["ops"] is None else float(last5_metrics["ops"]) - float(season_metrics["ops"]),
            True,
        ),
        (
            c3,
            "Exchange (s)",
            _fmt_float(transfer_avg),
            _fmt_float(transfer_last5),
            None if transfer_last5 is None or transfer_avg is None else float(transfer_last5) - float(transfer_avg),
            False,
        ),
        (
            c4,
            "Pop Time (s)",
            _fmt_float(pop_avg),
            _fmt_float(pop_last5),
            None if pop_last5 is None or pop_avg is None else float(pop_last5) - float(pop_avg),
            False,
        ),
    ]:
        with col:
            delta_text = ""
            helper = "Season: — | Last 5: — | Δ: —"
            if delta is not None:
                direction = "▲" if delta > 0 else ("▼" if delta < 0 else "→")
                signed = _fmt_signed(delta) if not is_rate else _fmt_signed(delta, places=3)
                delta_text = f'<div class="sf-kpi-delta">{direction} {signed}</div>'
            season_helper = value if value != "—" else "—"
            last5_helper = last5 if last5 != "—" else "—"
            helper_delta = _fmt_signed(delta, places=3) if delta is not None else "—"
            helper = f"Season: {season_helper} | Last 5: {last5_helper} | Δ: {helper_delta}"
            st.markdown(
                f'<div class="sf-kpi-card"><div class="sf-kpi-title">{title}</div>'
                f'<div class="sf-kpi-value">{value}</div>{delta_text}<div class="sf-kpi-helper">{helper}</div></div>',
                unsafe_allow_html=True,
            )


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
    games_sorted = ctx["scoped_games"].sort_values(["season_label", "game_no"], ascending=[False, False])

    season_metrics = _window_metrics(games_sorted)
    last5_metrics = _window_metrics(games_sorted.head(5))
    last10_metrics = _window_metrics(games_sorted.head(10))

    _render_kpi_cards(season_metrics, last5_metrics, practice_df)
    st.info(
        "How this helps\n"
        "- Surfaces trend changes faster than manual stat review\n"
        "- Reduces spreadsheet reconciliation time\n"
        "- Focuses coaching conversations on development signals"
    )
    _render_momentum_visual(games_sorted)

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
                "Season": _fmt_rate(season_val),
                "Last 5": _fmt_rate(l5_val),
                "Δ vs Season (5)": _fmt_rate(delta5) if delta5 is not None else "—",
                "Trend (5)": "—" if delta5 is None else _trend_arrow(delta5, inverse_better=inverse),
                "Last 10": _fmt_rate(l10_val),
                "Δ vs Season (10)": _fmt_rate(delta10) if delta10 is not None else "—",
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
    st.caption("Stat-driven drill recommendations generated from current dashboard metrics.")

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
        st.info("No trigger thresholds were exceeded in this scope. Keep monitoring trend and consistency cards.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    plan_lines: list[str] = [f"{ctx['player']['player_name']} Development Plan"]
    coach_summary: list[str] = []
    for idx, rec in enumerate(recs, start=1):
        header = f"{idx}. {rec.title} ({rec.priority} • {rec.category})"
        plan_lines.append(header)
        plan_lines.append(f"Why: {rec.why_this_triggered}")
        with st.expander(header, expanded=(idx == 1)):
            st.write(f"**Why this triggered:** {rec.why_this_triggered}")
            st.write(f"**Priority:** {rec.priority}  |  **Category:** {rec.category}")
            st.write("**Recommended drills:**")
            for drill in rec.drills:
                st.markdown(
                    f"- **{drill.name}**  \n"
                    f"  Setup: {drill.setup}  \n"
                    f"  Volume: {drill.reps_sets}  \n"
                    f"  Coaching cues: {drill.coaching_cues}  \n"
                    f"  Progression: {drill.progression}"
                )
                plan_lines.append(f"  - {drill.name}: {drill.reps_sets}")
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
        st.info("No practice sessions in this demo selection.")
        return

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
    c1, c2, c3 = st.columns(3)
    c1.metric("Sessions", count)
    c2.metric("Avg Transfer", _fmt_float(transfer_avg))
    c3.metric("Avg Pop", _fmt_float(pop_avg))


def _render_trends(ctx: dict[str, Any], practice_df: pd.DataFrame, summaries_df: pd.DataFrame) -> None:
    st.subheader("Trends")

    games_sorted = ctx["scoped_games"].sort_values(["season_label", "game_no"], ascending=[True, True])
    if games_sorted.empty:
        st.info("No game data available for trends.")
        return

    metric = st.selectbox(
        "Metric",
        options=["ops", "avg", "obp", "slg", "k_rate", "bb_rate", "cs_pct", "pb_rate", "transfer", "pop"],
        format_func=lambda x: METRIC_LABELS.get(x, x.replace("_", " ").title()),
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
        st.info("No pop-time rows in the selected demo scope.")
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

    c1, c2, c3 = st.columns(3)
    c1.metric("Transfer", _fmt_float(float(calc["transfer"])))
    c2.metric("Throw", _fmt_float(float(calc["throw_time"] or 0.0)))
    c3.metric("Total Pop", _fmt_float(float(calc["pop_total"])))

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


def _render_export() -> None:
    st.subheader("Export")
    st.caption("Report export is available in desktop to preserve local file workflow.")
    st.button("Export Report (PDF)", disabled=True)
    st.info("Desktop only: report generation uses local file save and full app context.")


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
        _render_export()


def main() -> None:
    st.set_page_config(page_title=f"{APP_TITLE} Web Demo", layout="wide")
    _inject_noindex()
    _inject_styles()

    if not _password_gate():
        return

    players, games, practice, summaries = _load_demo_data()
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

    ctx["scoped_games"] = scoped_games

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


if __name__ == "__main__":
    main()
