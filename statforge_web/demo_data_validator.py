from __future__ import annotations

from pathlib import Path
from typing import Any

from statforge_web.demo_data_loader import DATASET_PATH, load_demo_dataset

REQUIRED_PLAYER_FIELDS = {"player_id", "player_name", "position", "level"}
REQUIRED_GAME_FIELDS = {"season_label", "game_no", "date", "opponent", "player_stats"}
REQUIRED_STAT_FIELDS = {
    "player_id",
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
}
REQUIRED_PRACTICE_FIELDS = {"player_id", "season_label", "session_no", "date", "transfer_time", "pop_time"}


def _missing_fields(row: dict[str, Any], required: set[str]) -> set[str]:
    return {field for field in required if field not in row}


def validate_dataset(path: Path | None = None) -> list[str]:
    errors: list[str] = []
    dataset = load_demo_dataset(path=path)
    teams = dataset.get("teams", [])
    if not teams:
        return ["Dataset has no teams."]

    for team in teams:
        team_name = str(team.get("team_name", ""))
        players = team.get("players", [])
        games = team.get("games", [])
        practice = team.get("practice_sessions", [])
        if not team_name:
            errors.append("A team is missing team_name.")
        if not players:
            errors.append(f"Team '{team_name}' has no players.")
        if not games:
            errors.append(f"Team '{team_name}' has no games.")

        player_ids = set()
        for player in players:
            missing = _missing_fields(player, REQUIRED_PLAYER_FIELDS)
            if missing:
                errors.append(f"Team '{team_name}' player missing fields: {sorted(missing)}")
            else:
                player_ids.add(int(player["player_id"]))

        for game in games:
            missing = _missing_fields(game, REQUIRED_GAME_FIELDS)
            if missing:
                errors.append(f"Team '{team_name}' game missing fields: {sorted(missing)}")
                continue
            stats = game.get("player_stats", [])
            if not stats:
                errors.append(
                    f"Team '{team_name}' game {game.get('season_label')} #{game.get('game_no')} has no player_stats."
                )
            for stat in stats:
                stat_missing = _missing_fields(stat, REQUIRED_STAT_FIELDS)
                if stat_missing:
                    errors.append(
                        f"Team '{team_name}' game {game.get('season_label')} #{game.get('game_no')} stat missing {sorted(stat_missing)}"
                    )
                elif int(stat["player_id"]) not in player_ids:
                    errors.append(
                        f"Team '{team_name}' game {game.get('season_label')} #{game.get('game_no')} references unknown player_id {stat['player_id']}"
                    )

        for session in practice:
            missing = _missing_fields(session, REQUIRED_PRACTICE_FIELDS)
            if missing:
                errors.append(f"Team '{team_name}' practice session missing fields: {sorted(missing)}")
            elif int(session["player_id"]) not in player_ids:
                errors.append(f"Team '{team_name}' practice references unknown player_id {session['player_id']}")

    return errors


if __name__ == "__main__":
    problems = validate_dataset(path=DATASET_PATH)
    if problems:
        print("Demo dataset validation failed:")
        for p in problems:
            print(f"- {p}")
        raise SystemExit(1)
    print("Demo dataset validation passed.")
