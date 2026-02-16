from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

DATASET_PATH = Path(__file__).resolve().parent / "demo_data" / "demo_dataset.json"


def load_demo_dataset(path: Path | None = None) -> dict[str, Any]:
    dataset_path = path or DATASET_PATH
    with dataset_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_demo_teams(dataset: dict[str, Any]) -> list[str]:
    return [str(team.get("team_name", "")) for team in dataset.get("teams", []) if team.get("team_name")]


def list_players(dataset: dict[str, Any], team: str) -> list[dict[str, Any]]:
    for entry in dataset.get("teams", []):
        if str(entry.get("team_name")) == str(team):
            return list(entry.get("players", []))
    return []


def get_games(dataset: dict[str, Any], team: str, season: str = "All") -> list[dict[str, Any]]:
    for entry in dataset.get("teams", []):
        if str(entry.get("team_name")) != str(team):
            continue
        games = list(entry.get("games", []))
        if season == "All":
            return games
        return [g for g in games if str(g.get("season_label")) == str(season)]
    return []


def _flatten_players(dataset: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for team in dataset.get("teams", []):
        team_name = str(team.get("team_name", ""))
        for player in team.get("players", []):
            rows.append(
                {
                    "team": team_name,
                    "player_id": int(player["player_id"]),
                    "player_name": str(player.get("player_name", "")),
                    "position": str(player.get("position", "UTIL")),
                    "level": str(player.get("level", "13U")),
                }
            )
    return pd.DataFrame(rows)


def _flatten_games(dataset: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for team in dataset.get("teams", []):
        team_name = str(team.get("team_name", ""))
        for game in team.get("games", []):
            season_label = str(game.get("season_label", ""))
            game_no = int(game.get("game_no", 0))
            game_date = str(game.get("date", ""))
            opponent = str(game.get("opponent", ""))
            for stat_row in game.get("player_stats", []):
                rows.append(
                    {
                        "team": team_name,
                        "player_id": int(stat_row["player_id"]),
                        "season_label": season_label,
                        "game_no": game_no,
                        "game_date": game_date,
                        "opponent": opponent,
                        "ab": int(stat_row.get("ab", 0)),
                        "h": int(stat_row.get("h", 0)),
                        "doubles": int(stat_row.get("doubles", 0)),
                        "triples": int(stat_row.get("triples", 0)),
                        "hr": int(stat_row.get("hr", 0)),
                        "bb": int(stat_row.get("bb", 0)),
                        "so": int(stat_row.get("so", 0)),
                        "rbi": int(stat_row.get("rbi", 0)),
                        "sb": int(stat_row.get("sb", 0)),
                        "cs": int(stat_row.get("cs", 0)),
                        "innings_caught": float(stat_row.get("innings_caught", 0.0)),
                        "passed_balls": int(stat_row.get("passed_balls", 0)),
                        "sb_allowed": int(stat_row.get("sb_allowed", 0)),
                        "cs_caught": int(stat_row.get("cs_caught", 0)),
                    }
                )
    return pd.DataFrame(rows)


def _flatten_practice(dataset: dict[str, Any], players_df: pd.DataFrame) -> pd.DataFrame:
    team_by_player = {int(r["player_id"]): str(r["team"]) for _, r in players_df.iterrows()}
    rows: list[dict[str, Any]] = []
    for team in dataset.get("teams", []):
        for practice in team.get("practice_sessions", []):
            player_id = int(practice["player_id"])
            rows.append(
                {
                    "team": team_by_player.get(player_id, str(team.get("team_name", ""))),
                    "player_id": player_id,
                    "season_label": str(practice.get("season_label", "")),
                    "session_no": int(practice.get("session_no", 0)),
                    "session_date": str(practice.get("date", "")),
                    "transfer_time": float(practice.get("transfer_time", 0.0)),
                    "pop_time": float(practice.get("pop_time", 0.0)),
                }
            )
    return pd.DataFrame(rows)


def _build_season_summaries(games_df: pd.DataFrame, practice_df: pd.DataFrame) -> pd.DataFrame:
    if games_df.empty:
        return pd.DataFrame(
            columns=[
                "team",
                "player_id",
                "season_label",
                "ab",
                "h",
                "doubles",
                "triples",
                "hr",
                "bb",
                "so",
                "sb",
                "cs",
                "sb_allowed",
                "innings_caught",
                "pb",
                "transfer_time",
                "pop_time",
            ]
        )

    grouped = (
        games_df.groupby(["team", "player_id", "season_label"], as_index=False)[
            [
                "ab",
                "h",
                "doubles",
                "triples",
                "hr",
                "bb",
                "so",
                "sb",
                "cs",
                "sb_allowed",
                "innings_caught",
                "passed_balls",
            ]
        ]
        .sum()
        .rename(columns={"passed_balls": "pb"})
    )
    if practice_df.empty:
        grouped["transfer_time"] = 0.0
        grouped["pop_time"] = 0.0
        return grouped

    practice_means = (
        practice_df.groupby(["team", "player_id", "season_label"], as_index=False)[["transfer_time", "pop_time"]]
        .mean()
        .fillna(0.0)
    )
    merged = grouped.merge(practice_means, on=["team", "player_id", "season_label"], how="left")
    merged["transfer_time"] = merged["transfer_time"].fillna(0.0)
    merged["pop_time"] = merged["pop_time"].fillna(0.0)
    return merged


def compute_or_map_metrics(dataset: dict[str, Any], filters: dict[str, Any] | None = None) -> dict[str, pd.DataFrame]:
    players_df = _flatten_players(dataset)
    games_df = _flatten_games(dataset)
    practice_df = _flatten_practice(dataset, players_df=players_df)
    summaries_df = _build_season_summaries(games_df=games_df, practice_df=practice_df)

    if not filters:
        return {
            "players": players_df,
            "games": games_df,
            "practice": practice_df,
            "season_summaries": summaries_df,
        }

    team = filters.get("team")
    season = filters.get("season")
    if team:
        players_df = players_df.loc[players_df["team"] == str(team)].copy()
        games_df = games_df.loc[games_df["team"] == str(team)].copy()
        practice_df = practice_df.loc[practice_df["team"] == str(team)].copy()
        summaries_df = summaries_df.loc[summaries_df["team"] == str(team)].copy()
    if season and str(season) != "All":
        games_df = games_df.loc[games_df["season_label"].astype(str) == str(season)].copy()
        practice_df = practice_df.loc[practice_df["season_label"].astype(str) == str(season)].copy()
        summaries_df = summaries_df.loc[summaries_df["season_label"].astype(str) == str(season)].copy()

    return {
        "players": players_df,
        "games": games_df,
        "practice": practice_df,
        "season_summaries": summaries_df,
    }
