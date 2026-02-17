import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DB_FILENAME = "statforge.db"


class Database:
    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).resolve().parent.parent / DB_FILENAME
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._enable_foreign_keys()
        self.initialize()

    def _enable_foreign_keys(self) -> None:
        self.conn.execute("PRAGMA foreign_keys = ON")

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                number TEXT,
                team_id INTEGER,
                position TEXT NOT NULL,
                bats TEXT,
                throws TEXT,
                level TEXT,
                FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                game_date TEXT,
                season TEXT,
                opponent TEXT,
                notes TEXT DEFAULT '',
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS stat_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                ab INTEGER NOT NULL DEFAULT 0,
                h INTEGER NOT NULL DEFAULT 0,
                doubles INTEGER NOT NULL DEFAULT 0,
                triples INTEGER NOT NULL DEFAULT 0,
                hr INTEGER NOT NULL DEFAULT 0,
                bb INTEGER NOT NULL DEFAULT 0,
                so INTEGER NOT NULL DEFAULT 0,
                rbi INTEGER NOT NULL DEFAULT 0,
                sb INTEGER NOT NULL DEFAULT 0,
                cs INTEGER NOT NULL DEFAULT 0,
                innings_caught REAL NOT NULL DEFAULT 0,
                passed_balls INTEGER NOT NULL DEFAULT 0,
                sb_allowed INTEGER NOT NULL DEFAULT 0,
                cs_caught INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS practice_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                session_date TEXT NOT NULL,
                category TEXT NOT NULL,
                focus TEXT NOT NULL,
                duration_min INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                video_path TEXT DEFAULT '',
                pop_time_best REAL,
                pop_time_avg REAL,
                throws INTEGER,
                blocks INTEGER,
                swings INTEGER,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS video_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                analysis_date TEXT NOT NULL,
                position TEXT NOT NULL,
                analysis_type TEXT NOT NULL,
                video_path TEXT DEFAULT '',
                fps REAL,
                start_frame INTEGER,
                end_frame INTEGER,
                duration_seconds REAL,
                extra_json TEXT DEFAULT '{}',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS season_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                season_label TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                stats_json TEXT NOT NULL,
                source_text TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS stat_timeline_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                source_id INTEGER,
                period_label TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                metrics_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            """
        )
        self._migrate_players_add_number()
        self._migrate_players_add_team_id()
        self._migrate_games_add_game_date()
        self._migrate_games_add_season()
        self._migrate_games_add_notes()
        self._migrate_practice_add_video_path()
        self._migrate_create_video_analysis()
        self._ensure_games_indexes()
        self._ensure_practice_indexes()
        self._ensure_video_analysis_indexes()
        self._ensure_players_indexes()
        self._ensure_season_summary_indexes()
        self._ensure_timeline_indexes()
        self.conn.commit()

    def _migrate_players_add_number(self) -> None:
        columns = self.query_all("PRAGMA table_info(players)")
        column_names = {str(col["name"]) for col in columns}
        if "number" not in column_names:
            self.conn.execute("ALTER TABLE players ADD COLUMN number TEXT")

    def _migrate_games_add_season(self) -> None:
        columns = self.query_all("PRAGMA table_info(games)")
        column_names = {str(col["name"]) for col in columns}
        if "season" not in column_names:
            self.conn.execute("ALTER TABLE games ADD COLUMN season TEXT")

    def _migrate_games_add_game_date(self) -> None:
        columns = self.query_all("PRAGMA table_info(games)")
        column_names = {str(col["name"]) for col in columns}
        if "game_date" not in column_names:
            self.conn.execute("ALTER TABLE games ADD COLUMN game_date TEXT")
        self.conn.execute("UPDATE games SET game_date = date WHERE game_date IS NULL OR game_date = ''")

    def _migrate_games_add_notes(self) -> None:
        columns = self.query_all("PRAGMA table_info(games)")
        column_names = {str(col["name"]) for col in columns}
        if "notes" not in column_names:
            self.conn.execute("ALTER TABLE games ADD COLUMN notes TEXT DEFAULT ''")

    def _migrate_players_add_team_id(self) -> None:
        columns = self.query_all("PRAGMA table_info(players)")
        column_names = {str(col["name"]) for col in columns}
        if "team_id" not in column_names:
            self.conn.execute("ALTER TABLE players ADD COLUMN team_id INTEGER")

    def _migrate_practice_add_video_path(self) -> None:
        columns = self.query_all("PRAGMA table_info(practice_sessions)")
        column_names = {str(col["name"]) for col in columns}
        if "video_path" not in column_names:
            self.conn.execute("ALTER TABLE practice_sessions ADD COLUMN video_path TEXT DEFAULT ''")

    def _migrate_create_video_analysis(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS video_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                analysis_date TEXT NOT NULL,
                position TEXT NOT NULL,
                analysis_type TEXT NOT NULL,
                video_path TEXT DEFAULT '',
                fps REAL,
                start_frame INTEGER,
                end_frame INTEGER,
                duration_seconds REAL,
                extra_json TEXT DEFAULT '{}',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            )
            """
        )

    def _ensure_games_indexes(self) -> None:
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_games_player_date ON games(player_id, game_date)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_player_season_date ON games(player_id, season, game_date)"
        )

    def _ensure_practice_indexes(self) -> None:
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_practice_player_date ON practice_sessions(player_id, session_date)"
        )

    def _ensure_video_analysis_indexes(self) -> None:
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_video_analysis_player_date "
            "ON video_analysis(player_id, analysis_date DESC)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_video_analysis_type "
            "ON video_analysis(player_id, analysis_type, analysis_date DESC)"
        )

    def _ensure_players_indexes(self) -> None:
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id)")

    def _ensure_season_summary_indexes(self) -> None:
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_season_summaries_player_created "
            "ON season_summaries(player_id, created_at DESC)"
        )

    def _ensure_timeline_indexes(self) -> None:
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_timeline_player_period "
            "ON stat_timeline_points(player_id, period_label)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_timeline_player_source "
            "ON stat_timeline_points(player_id, source_type, source_id)"
        )

    def close(self) -> None:
        self.conn.close()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(query, params)
        self.conn.commit()
        return cur

    def query_all(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        cur = self.conn.execute(query, params)
        return list(cur.fetchall())

    def query_one(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        cur = self.conn.execute(query, params)
        return cur.fetchone()

    def add_player(
        self,
        name: str,
        number: str | None,
        team_id: int | None,
        position: str,
        bats: str | None,
        throws: str | None,
        level: str | None,
    ) -> int:
        cur = self.execute(
            """
            INSERT INTO players(name, number, team_id, position, bats, throws, level)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, number or None, team_id, position, bats or None, throws or None, level or None),
        )
        return int(cur.lastrowid)

    def update_player(
        self,
        player_id: int,
        name: str,
        number: str | None,
        team_id: int | None,
        position: str,
        bats: str | None,
        throws: str | None,
        level: str | None,
    ) -> None:
        self.execute(
            """
            UPDATE players
            SET name = ?, number = ?, team_id = ?, position = ?, bats = ?, throws = ?, level = ?
            WHERE id = ?
            """,
            (name, number or None, team_id, position, bats or None, throws or None, level or None, player_id),
        )

    def get_players(self) -> list[sqlite3.Row]:
        return self.query_all("SELECT * FROM players ORDER BY name")

    def get_player(self, player_id: int) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM players WHERE id = ?", (player_id,))

    def create_team(self, name: str) -> int:
        cur = self.execute("INSERT INTO teams(name) VALUES (?)", (name,))
        return int(cur.lastrowid)

    def get_teams(self) -> list[sqlite3.Row]:
        return self.query_all("SELECT id, name FROM teams ORDER BY name")

    def get_team(self, team_id: int) -> sqlite3.Row | None:
        return self.query_one("SELECT id, name FROM teams WHERE id = ?", (team_id,))

    def assign_player_to_team(self, player_id: int, team_id: int | None) -> None:
        self.execute("UPDATE players SET team_id = ? WHERE id = ?", (team_id, player_id))

    def get_players_for_team(self, team_id: int) -> list[sqlite3.Row]:
        return self.query_all(
            """
            SELECT id, name, number, position, level, team_id
            FROM players
            WHERE team_id = ?
            ORDER BY name
            """,
            (team_id,),
        )

    def add_game(
        self,
        player_id: int,
        game_date: str,
        season: str | None,
        opponent: str | None,
        notes: str | None,
    ) -> int:
        cur = self.execute(
            """
            INSERT INTO games(player_id, date, game_date, season, opponent, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (player_id, game_date, game_date, season or None, opponent or None, notes or ""),
        )
        return int(cur.lastrowid)

    def add_stat_line(self, game_id: int, stats: dict[str, Any]) -> int:
        columns = [
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
        values = [stats.get(col, 0) for col in columns]
        placeholders = ", ".join("?" for _ in columns)
        cur = self.execute(
            f"""
            INSERT INTO stat_lines(game_id, {', '.join(columns)})
            VALUES (?, {placeholders})
            """,
            (game_id, *values),
        )
        return int(cur.lastrowid)

    def update_game(
        self,
        game_id: int,
        game_date: str,
        season: str | None,
        opponent: str | None,
        notes: str | None,
    ) -> None:
        self.execute(
            """
            UPDATE games
            SET date = ?, game_date = ?, season = ?, opponent = ?, notes = ?
            WHERE id = ?
            """,
            (game_date, game_date, season or None, opponent or None, notes or "", game_id),
        )

    def update_or_insert_stat_line(self, game_id: int, stats: dict[str, Any]) -> None:
        existing = self.query_one("SELECT id FROM stat_lines WHERE game_id = ?", (game_id,))
        columns = [
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
        values = [stats.get(col, 0) for col in columns]
        if existing:
            set_clause = ", ".join(f"{col} = ?" for col in columns)
            self.execute(
                f"UPDATE stat_lines SET {set_clause} WHERE game_id = ?",
                (*values, game_id),
            )
        else:
            self.add_stat_line(game_id, stats)

    def get_game_with_stats(self, game_id: int) -> sqlite3.Row | None:
        return self.query_one(
            """
            SELECT
                g.id,
                g.player_id,
                g.game_date AS date,
                g.season,
                g.opponent,
                g.notes,
                sl.ab,
                sl.h,
                sl.doubles,
                sl.triples,
                sl.hr,
                sl.bb,
                sl.so,
                sl.rbi,
                sl.sb,
                sl.cs,
                sl.innings_caught,
                sl.passed_balls,
                sl.sb_allowed,
                sl.cs_caught
            FROM games g
            LEFT JOIN stat_lines sl ON sl.game_id = g.id
            WHERE g.id = ?
            """,
            (game_id,),
        )

    def get_games_for_player(self, player_id: int) -> list[sqlite3.Row]:
        return self.get_games(
            player_id=player_id,
            season=None,
            start_date=None,
            end_date=None,
            limit=None,
        )

    def add_practice_session(
        self,
        player_id: int,
        session_date: str,
        category: str,
        focus: str,
        duration_min: int = 0,
        notes: str = "",
        video_path: str = "",
        pop_time_best: float | None = None,
        pop_time_avg: float | None = None,
        throws: int | None = None,
        blocks: int | None = None,
        swings: int | None = None,
    ) -> int:
        cur = self.execute(
            """
            INSERT INTO practice_sessions(
                player_id, session_date, category, focus, duration_min, notes,
                video_path, pop_time_best, pop_time_avg, throws, blocks, swings
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                session_date,
                category,
                focus,
                duration_min,
                notes or "",
                video_path or "",
                pop_time_best,
                pop_time_avg,
                throws,
                blocks,
                swings,
            ),
        )
        return int(cur.lastrowid)

    def delete_practice_session(self, session_id: int) -> bool:
        cur = self.execute("DELETE FROM practice_sessions WHERE id = ?", (session_id,))
        return cur.rowcount > 0

    def add_video_analysis(
        self,
        player_id: int,
        analysis_date: str,
        position: str,
        analysis_type: str,
        video_path: str = "",
        fps: float | None = None,
        start_frame: int | None = None,
        end_frame: int | None = None,
        duration_seconds: float | None = None,
        extra: dict[str, Any] | None = None,
        notes: str = "",
    ) -> int:
        cur = self.execute(
            """
            INSERT INTO video_analysis(
                player_id, analysis_date, position, analysis_type, video_path, fps,
                start_frame, end_frame, duration_seconds, extra_json, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                analysis_date,
                position,
                analysis_type,
                video_path or "",
                fps,
                start_frame,
                end_frame,
                duration_seconds,
                json.dumps(extra or {}, separators=(",", ":")),
                notes or "",
            ),
        )
        return int(cur.lastrowid)

    def get_recent_video_analysis(self, player_id: int, limit: int = 20) -> list[sqlite3.Row]:
        return self.query_all(
            """
            SELECT
                id,
                analysis_date,
                position,
                analysis_type,
                video_path,
                fps,
                start_frame,
                end_frame,
                duration_seconds,
                extra_json,
                notes,
                created_at
            FROM video_analysis
            WHERE player_id = ?
            ORDER BY analysis_date DESC, id DESC
            LIMIT ?
            """,
            (player_id, limit),
        )

    def get_recent_practice_sessions(self, player_id: int, limit: int = 20) -> list[sqlite3.Row]:
        return self.query_all(
            """
            SELECT
                id,
                session_date,
                category,
                focus,
                duration_min,
                notes,
                video_path,
                pop_time_best,
                pop_time_avg,
                throws,
                blocks,
                swings
            FROM practice_sessions
            WHERE player_id = ?
            ORDER BY session_date DESC, id DESC
            LIMIT ?
            """,
            (player_id, limit),
        )

    def get_practice_session(self, session_id: int) -> sqlite3.Row | None:
        return self.query_one(
            """
            SELECT
                id,
                player_id,
                session_date,
                category,
                focus,
                duration_min,
                notes,
                video_path,
                pop_time_best,
                pop_time_avg,
                throws,
                blocks,
                swings
            FROM practice_sessions
            WHERE id = ?
            """,
            (session_id,),
        )

    def _build_practice_filters(
        self,
        player_id: int,
        season: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[str, list[Any]]:
        where_parts = ["player_id = ?"]
        params: list[Any] = [player_id]
        if season:
            where_parts.append("substr(session_date, 1, 4) = ?")
            params.append(str(season)[:4])
        if start_date:
            where_parts.append("session_date >= ?")
            params.append(start_date)
        if end_date:
            where_parts.append("session_date <= ?")
            params.append(end_date)
        return " AND ".join(where_parts), params

    def get_transfer_samples(
        self,
        player_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
        season: str | None = None,
    ) -> list[float]:
        rows = self.query_all(
            f"""
            SELECT focus, notes, pop_time_avg
            FROM practice_sessions
            WHERE {self._build_practice_filters(player_id, season=season, start_date=start_date, end_date=end_date)[0]}
            ORDER BY session_date DESC, id DESC
            """,
            tuple(self._build_practice_filters(player_id, season=season, start_date=start_date, end_date=end_date)[1]),
        )
        samples: list[float] = []
        for row in rows:
            focus = str(row["focus"] or "").lower()
            notes = str(row["notes"] or "")
            if "pop time" not in focus and "mode:" not in notes.lower() and row["pop_time_avg"] is None:
                continue
            rep_pairs = re.findall(
                r"c=([0-9]+(?:\.[0-9]+)?)s\s+r=([0-9]+(?:\.[0-9]+)?)s",
                notes,
                flags=re.IGNORECASE,
            )
            added_rep = False
            for c_raw, r_raw in rep_pairs:
                try:
                    c_val = float(c_raw)
                    r_val = float(r_raw)
                except ValueError:
                    continue
                transfer = r_val - c_val
                if transfer > 0:
                    samples.append(transfer)
                    added_rep = True
            if added_rep:
                continue
            m = re.search(r"best_transfer=([0-9]+(?:\.[0-9]+)?)s", notes, flags=re.IGNORECASE)
            if m:
                try:
                    samples.append(float(m.group(1)))
                    continue
                except ValueError:
                    pass
            if row["pop_time_avg"] is not None:
                try:
                    samples.append(float(row["pop_time_avg"]))
                except (TypeError, ValueError):
                    pass
        return samples

    def get_transfer_samples_detail(
        self,
        player_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
        season: str | None = None,
    ) -> dict[str, Any]:
        rows = self.query_all(
            f"""
            SELECT focus, notes, pop_time_avg
            FROM practice_sessions
            WHERE {self._build_practice_filters(player_id, season=season, start_date=start_date, end_date=end_date)[0]}
            ORDER BY session_date DESC, id DESC
            """,
            tuple(self._build_practice_filters(player_id, season=season, start_date=start_date, end_date=end_date)[1]),
        )
        samples: list[float] = []
        rep_count = 0
        set_level_count = 0
        for row in rows:
            focus = str(row["focus"] or "").lower()
            notes = str(row["notes"] or "")
            if "pop time" not in focus and "mode:" not in notes.lower() and row["pop_time_avg"] is None:
                continue
            rep_pairs = re.findall(
                r"c=([0-9]+(?:\.[0-9]+)?)s\s+r=([0-9]+(?:\.[0-9]+)?)s",
                notes,
                flags=re.IGNORECASE,
            )
            used_rep = False
            for c_raw, r_raw in rep_pairs:
                try:
                    c_val = float(c_raw)
                    r_val = float(r_raw)
                except ValueError:
                    continue
                transfer = r_val - c_val
                if transfer > 0:
                    samples.append(transfer)
                    rep_count += 1
                    used_rep = True
            if used_rep:
                continue
            m = re.search(r"best_transfer=([0-9]+(?:\.[0-9]+)?)s", notes, flags=re.IGNORECASE)
            if m:
                try:
                    samples.append(float(m.group(1)))
                    set_level_count += 1
                    continue
                except ValueError:
                    pass
            if row["pop_time_avg"] is not None:
                try:
                    samples.append(float(row["pop_time_avg"]))
                    set_level_count += 1
                except (TypeError, ValueError):
                    pass
        return {"samples": samples, "set_level": rep_count == 0 and set_level_count > 0}

    def get_obp_samples(
        self,
        player_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
        season: str | None = None,
    ) -> list[float]:
        rows = self.get_stat_lines(
            player_id=player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
            limit=None,
        )
        samples: list[float] = []
        for row in rows:
            ab = float(row["ab"] or 0)
            h = float(row["h"] or 0)
            bb = float(row["bb"] or 0)
            sf = 0.0
            denom = ab + bb + sf
            if denom <= 0:
                continue
            samples.append((h + bb) / denom)
        return samples

    def get_practice_summary_last_days(
        self,
        player_id: int,
        days: int = 7,
        reference_date: str | None = None,
    ) -> dict[str, Any]:
        ref = date.fromisoformat(reference_date) if reference_date else date.today()
        start = (ref - timedelta(days=days - 1)).isoformat()
        end = ref.isoformat()

        totals = self.query_one(
            """
            SELECT
                COUNT(*) AS session_count,
                COALESCE(SUM(duration_min), 0) AS total_minutes
            FROM practice_sessions
            WHERE player_id = ? AND session_date >= ? AND session_date <= ?
            """,
            (player_id, start, end),
        )
        top_focus = self.query_all(
            """
            SELECT focus, COUNT(*) AS c
            FROM practice_sessions
            WHERE player_id = ? AND session_date >= ? AND session_date <= ?
            GROUP BY focus
            ORDER BY c DESC, focus ASC
            LIMIT 3
            """,
            (player_id, start, end),
        )
        last_sessions = self.query_all(
            """
            SELECT session_date, focus, duration_min
            FROM practice_sessions
            WHERE player_id = ?
            ORDER BY session_date DESC, id DESC
            LIMIT 3
            """,
            (player_id,),
        )
        recent_focuses = self.query_all(
            """
            SELECT DISTINCT lower(focus) AS focus
            FROM practice_sessions
            WHERE player_id = ? AND session_date >= ? AND session_date <= ?
            """,
            (player_id, start, end),
        )

        return {
            "session_count": int(totals["session_count"] if totals else 0),
            "total_minutes": int(totals["total_minutes"] if totals else 0),
            "top_focuses": [(str(r["focus"]), int(r["c"])) for r in top_focus],
            "last_sessions": [dict(r) for r in last_sessions],
            "recent_focuses": [str(r["focus"]) for r in recent_focuses if r["focus"]],
        }

    def update_game_notes(self, game_id: int, notes: str) -> None:
        self.execute("UPDATE games SET notes = ? WHERE id = ?", (notes or "", game_id))

    def get_game_notes(self, game_id: int) -> str:
        row = self.query_one("SELECT notes FROM games WHERE id = ?", (game_id,))
        return str(row["notes"]) if row and row["notes"] is not None else ""

    def get_recent_notes(
        self,
        player_id: int,
        limit: int = 5,
        season: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[sqlite3.Row]:
        where_clause, params = self._build_game_filters(player_id, season=season, start_date=start_date, end_date=end_date)
        params.append(limit)
        return self.query_all(
            f"""
            SELECT g.id, g.game_date AS date, g.opponent, g.notes
            FROM games g
            WHERE {where_clause}
            ORDER BY g.game_date DESC, g.id DESC
            LIMIT ?
            """,
            tuple(params),
        )

    def get_seasons_for_player(self, player_id: int) -> list[str]:
        rows = self.query_all(
            """
            SELECT DISTINCT season
            FROM games
            WHERE player_id = ? AND season IS NOT NULL AND season <> ''
            ORDER BY season DESC
            """,
            (player_id,),
        )
        return [str(r["season"]) for r in rows]

    def _build_game_filters(
        self,
        player_id: int,
        season: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[str, list[Any]]:
        where_parts = ["g.player_id = ?"]
        params: list[Any] = [player_id]

        if season:
            where_parts.append("g.season = ?")
            params.append(season)
        if start_date:
            where_parts.append("g.game_date >= ?")
            params.append(start_date)
        if end_date:
            where_parts.append("g.game_date <= ?")
            params.append(end_date)

        return " AND ".join(where_parts), params

    def get_games(
        self,
        player_id: int,
        season: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[sqlite3.Row]:
        where_clause, params = self._build_game_filters(
            player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
        )
        sql = (
            "SELECT g.id, g.player_id, g.game_date AS date, g.season, g.opponent, g.notes "
            "FROM games g "
            f"WHERE {where_clause} "
            "ORDER BY g.game_date DESC, g.id DESC"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return self.query_all(sql, tuple(params))

    def get_stat_lines(
        self,
        player_id: int,
        season: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[sqlite3.Row]:
        where_clause, params = self._build_game_filters(
            player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
        )
        sql = (
            "SELECT g.id, g.game_date AS date, g.season, "
            "sl.ab, sl.h, sl.doubles, sl.triples, sl.hr, sl.bb, sl.so, sl.rbi, sl.sb, sl.cs, "
            "sl.passed_balls, sl.innings_caught, sl.sb_allowed, sl.cs_caught "
            "FROM games g JOIN stat_lines sl ON sl.game_id = g.id "
            f"WHERE {where_clause} "
            "ORDER BY g.game_date DESC, g.id DESC"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return self.query_all(sql, tuple(params))

    def delete_game(self, game_id: int) -> bool:
        try:
            self.conn.execute("BEGIN")
            self.conn.execute("DELETE FROM stat_lines WHERE game_id = ?", (game_id,))
            games_cur = self.conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
            self.conn.commit()
            return games_cur.rowcount > 0
        except sqlite3.Error:
            self.conn.rollback()
            raise

    def get_season_totals(
        self,
        player_id: int,
        season: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> dict[str, float]:
        rows = self.get_stat_lines(
            player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        totals = self._aggregate_stat_rows(rows)
        return {
            "ab": totals["ab"],
            "h": totals["h"],
            "doubles": totals["doubles"],
            "triples": totals["triples"],
            "hr": totals["hr"],
            "bb": totals["bb"],
            "so": totals["so"],
            "rbi": totals.get("rbi", 0.0),
            "sb": totals.get("sb", 0.0),
            "cs": totals.get("cs", 0.0),
            "innings_caught": totals["innings_caught"],
            "passed_balls": totals["passed_balls"],
            "sb_allowed": totals["sb_allowed"],
            "cs_caught": totals["cs_caught"],
        }

    def _aggregate_stat_rows(self, rows: list[sqlite3.Row]) -> dict[str, float]:
        fields = [
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
            "passed_balls",
            "innings_caught",
            "sb_allowed",
            "cs_caught",
        ]
        totals: dict[str, float] = {field: 0.0 for field in fields}
        totals["sf"] = 0.0
        for row in rows:
            for field in fields:
                totals[field] += float(row[field] or 0)
        return totals

    def get_recent_games_with_stats(
        self,
        player_id: int,
        limit: int = 10,
        season: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[sqlite3.Row]:
        return self.get_stat_lines(
            player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def calculate_stat_windows(
        self,
        player_id: int,
        season: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, dict[str, float | None]]:
        rows = self.get_stat_lines(
            player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
            limit=None,
        )
        season_totals = self._aggregate_stat_rows(rows)
        last5_totals = self._aggregate_stat_rows(rows[:5])
        last10_totals = self._aggregate_stat_rows(rows[:10])
        return {
            "season": self._window_metrics_from_totals(season_totals),
            "last5": self._window_metrics_from_totals(last5_totals),
            "last10": self._window_metrics_from_totals(last10_totals),
        }

    def add_season_summary(
        self,
        player_id: int,
        season_label: str,
        start_date: str | None,
        end_date: str | None,
        stats: dict[str, Any],
        source_text: str,
    ) -> int:
        cur = self.execute(
            """
            INSERT INTO season_summaries(player_id, season_label, start_date, end_date, stats_json, source_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                season_label.strip(),
                start_date or None,
                end_date or None,
                json.dumps(stats, separators=(",", ":"), ensure_ascii=True),
                source_text,
            ),
        )
        return int(cur.lastrowid)

    def get_season_summaries(self, player_id: int) -> list[sqlite3.Row]:
        return self.query_all(
            """
            SELECT id, player_id, season_label, start_date, end_date, stats_json, source_text, created_at
            FROM season_summaries
            WHERE player_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (player_id,),
        )

    def get_season_summary(self, summary_id: int) -> sqlite3.Row | None:
        return self.query_one(
            """
            SELECT id, player_id, season_label, start_date, end_date, stats_json, source_text, created_at
            FROM season_summaries
            WHERE id = ?
            """,
            (summary_id,),
        )

    def upsert_stat_timeline_point(
        self,
        player_id: int,
        source_type: str,
        source_id: int | None,
        period_label: str,
        start_date: str | None,
        end_date: str | None,
        metrics: dict[str, Any],
    ) -> int:
        if source_id is None:
            self.execute(
                """
                DELETE FROM stat_timeline_points
                WHERE player_id = ? AND source_type = ? AND source_id IS NULL AND period_label = ?
                """,
                (player_id, source_type, period_label),
            )
        else:
            self.execute(
                """
                DELETE FROM stat_timeline_points
                WHERE player_id = ? AND source_type = ? AND source_id = ?
                """,
                (player_id, source_type, source_id),
            )
        cur = self.execute(
            """
            INSERT INTO stat_timeline_points(
                player_id, source_type, source_id, period_label, start_date, end_date, metrics_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                source_type,
                source_id,
                period_label,
                start_date or None,
                end_date or None,
                json.dumps(metrics, separators=(",", ":"), ensure_ascii=True),
            ),
        )
        return int(cur.lastrowid)

    def get_stat_timeline_points(self, player_id: int) -> list[sqlite3.Row]:
        return self.query_all(
            """
            SELECT id, player_id, source_type, source_id, period_label, start_date, end_date, metrics_json, created_at
            FROM stat_timeline_points
            WHERE player_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (player_id,),
        )

    def _window_metrics_from_totals(self, totals: dict[str, float]) -> dict[str, float | None]:
        ab = totals.get("ab", 0.0)
        h = totals.get("h", 0.0)
        doubles = totals.get("doubles", 0.0)
        triples = totals.get("triples", 0.0)
        hr = totals.get("hr", 0.0)
        bb = totals.get("bb", 0.0)
        so = totals.get("so", 0.0)
        sf = totals.get("sf", 0.0)
        passed_balls = totals.get("passed_balls", 0.0)
        innings_caught = totals.get("innings_caught", 0.0)
        sb_allowed = totals.get("sb_allowed", 0.0)
        cs_caught = totals.get("cs_caught", 0.0)

        singles = h - doubles - triples - hr
        tb = singles + (2 * doubles) + (3 * triples) + (4 * hr)
        pa = ab + bb + sf
        return {
            "AVG": (h / ab) if ab else 0.0,
            "OBP": ((h + bb) / (ab + bb + sf)) if (ab + bb + sf) else 0.0,
            "SLG": (tb / ab) if ab else 0.0,
            "K_RATE": (so / pa) if pa else 0.0,
            "BB_RATE": (bb / pa) if pa else 0.0,
            "CS_PCT": (cs_caught / sb_allowed) if sb_allowed else None,
            "PB_RATE": (passed_balls / innings_caught) if innings_caught else None,
        }
