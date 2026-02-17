from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
import tkinter as tk
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from tkinter import scrolledtext
from tkinter import filedialog, messagebox, ttk
from typing import Any

from styles.icon_draw import get_asset_path
from styles.theme import Theme

from coaching.recommendations import generate_recommendations
from reports.pdf_report import generate_player_report_pdf
from .development_profile import build_player_development_profile, get_player_focus_stats
from .consistency import compute_consistency
from .db import Database
from .metrics import (
    compare_window_to_season,
    compute_catching_metrics,
    compute_hitting_metrics,
    compute_last5_trend,
    per_game_cs_pct,
    per_game_ops,
    per_game_pb_rate,
    per_game_so_rate,
)
from .training_panel import TrainingSuggestionPanel
from .season_summary import compute_season_summary_metrics, parse_season_summary
from statforge_core.pop_time import calculate_pop_metrics
from statforge_core.suggestions import get_suggestions

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except Exception:
    FigureCanvasTkAgg = None  # type: ignore[assignment]
    Figure = None  # type: ignore[assignment]


@dataclass
class RepMark:
    catch_time: float
    release_time: float
    target_time: float | None
    metric_mode: str
    transfer: float
    pop_total: float
    estimated_flight: float | None
    catch_conf: float | None = None
    release_conf: float | None = None


class StatForgeApp:
    def __init__(self, root: tk.Tk, db: Database) -> None:
        self.root = root
        self.db = db

        self.root.title("StatForge by Anchor & Honor")
        self.root.geometry("980x700")

        self.active_player_id: int | None = None
        self.active_team_id: int | None = None
        self.player_name_to_id: dict[str, int] = {}
        self.assign_player_name_to_id: dict[str, int] = {}
        self.team_name_to_id: dict[str, int] = {}
        self.app_icon: tk.PhotoImage | None = None
        self.loaded_game_id: int | None = None
        self.filter_season_var = tk.StringVar(value="All")
        self.filter_start_date_var = tk.StringVar()
        self.filter_end_date_var = tk.StringVar()
        self.video_path: str | None = None
        self.video_capture: Any | None = None
        self.video_fps: float = 0.0
        self.video_frame_count: int = 0
        self.video_duration: float = 0.0
        self.video_is_playing = False
        self.video_play_after_id: str | None = None
        self.video_scrub_after_id: str | None = None
        self.video_pending_scrub_time: float | None = None
        self.video_current_time: float = 0.0
        self.video_last_frame_time: float | None = None
        self.video_last_frame_bgr: Any | None = None
        self.video_photo: tk.PhotoImage | None = None
        self.video_marker_catch: float | None = None
        self.video_marker_release: float | None = None
        self.video_marker_target: float | None = None
        self.video_last_transfer: float | None = None
        self.video_last_throw: float | None = None
        self.video_last_pop: float | None = None
        self.rep_marks: list[RepMark] = []
        self.video_updating_timeline = False
        self.video_source_width: int = 0
        self.video_source_height: int = 0
        self.video_image_offset: tuple[int, int] = (0, 0)
        self.video_display_width: int = 0
        self.video_display_height: int = 0
        self.video_roi_select_mode = False
        self.video_roi_drag_start: tuple[int, int] | None = None
        self.video_roi_drag_rect_id: int | None = None
        self.custom_roi_norm: tuple[float, float, float, float] | None = None
        self.video_roi_by_path: dict[str, tuple[float, float, float, float]] = {}
        self.practice_video_paths: dict[int, str] = {}
        self.video_audio_cache: dict[str, Path] = {}
        self.dashboard_stat_values: dict[str, float | None] = {}
        self.season_summary_parsed: dict[str, Any] = {}
        self.season_summary_unknown_lines: list[str] = []
        self.baseline_summary_id_to_row: dict[int, dict[str, Any]] = {}
        self.trends_metric_var = tk.StringVar(value="OPS")
        self.trends_inseason_var = tk.BooleanVar(value=False)
        self.current_focus_stat_training_key: str | None = None

        self._set_window_icon()
        self._build_ui()
        self.refresh_players()

    def _set_window_icon(self) -> None:
        icon_path = get_asset_path("assets/icons/statforge_icon.png")
        if not icon_path.exists():
            print(f"[StatForge] Icon not found at: {icon_path}")
            return
        try:
            self.app_icon = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self.app_icon)
        except (tk.TclError, OSError) as exc:
            print(f"[StatForge] Failed to load app icon: {icon_path} ({exc})")

    def _build_ui(self) -> None:
        self._build_header()

        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(container)
        notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook = notebook

        self.player_tab = ttk.Frame(notebook)
        self.teams_tab = ttk.Frame(notebook)
        self.game_tab = ttk.Frame(notebook)
        self.practice_tab = ttk.Frame(notebook)
        self.season_summary_tab = ttk.Frame(notebook)
        self.team_dashboard_tab = ttk.Frame(notebook)
        self.video_tab = ttk.Frame(notebook)
        self.dashboard_tab = ttk.Frame(notebook)
        self.trends_tab = ttk.Frame(notebook)

        self.player_content = self._make_scrollable_tab(self.player_tab)
        self.teams_content = self._make_scrollable_tab(self.teams_tab)
        self.game_content = self._make_scrollable_tab(self.game_tab)
        self.practice_content = self._make_scrollable_tab(self.practice_tab)
        self.season_summary_content = self._make_scrollable_tab(self.season_summary_tab)
        self.team_dashboard_content = self._make_scrollable_tab(self.team_dashboard_tab)
        self.video_content = self._make_scrollable_tab(self.video_tab)
        self.dashboard_content = self._make_scrollable_tab(self.dashboard_tab)
        self.trends_content = self._make_scrollable_tab(self.trends_tab)

        notebook.add(self.player_tab, text="Player")
        notebook.add(self.teams_tab, text="Teams")
        notebook.add(self.game_tab, text="Add Game + Stats")
        notebook.add(self.practice_tab, text="Practice")
        notebook.add(self.season_summary_tab, text="Season Summary")
        notebook.add(self.team_dashboard_tab, text="Team Dashboard")
        notebook.add(self.video_tab, text="Video Analysis")
        notebook.add(self.dashboard_tab, text="Dashboard")
        notebook.add(self.trends_tab, text="Trends")

        self._build_player_tab()
        self._build_teams_tab()
        self._build_game_tab()
        self._build_practice_tab()
        self._build_season_summary_tab()
        self._build_team_dashboard_tab()
        self._build_video_tab()
        self._build_dashboard_tab()
        self._build_trends_tab()

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=Theme.NAVY, height=84)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)
        header.grid_columnconfigure(2, weight=1)
        header.grid_rowconfigure(0, weight=1)

        left_spacer = ttk.Frame(header, style="Header.TFrame")
        left_spacer.grid(row=0, column=0, sticky="nsew")

        brand_frame = ttk.Frame(header, style="Header.TFrame")
        brand_frame.grid(row=0, column=1, pady=(12, 6))
        brand_frame.grid_columnconfigure(0, weight=1)

        brand_top_row = ttk.Frame(brand_frame, style="Header.TFrame")
        brand_top_row.grid(row=0, column=0)

        ttk.Label(brand_top_row, text="Stat", style="HeaderTitle.TLabel").pack(side=tk.LEFT, padx=(0, 6))

        mark = tk.Canvas(
            brand_top_row,
            width=38,
            height=24,
            bg=Theme.NAVY,
            highlightthickness=0,
            bd=0,
        )
        mark.pack(side=tk.LEFT, padx=0, pady=(1, 0))
        self._draw_wordmark_symbol(mark)

        ttk.Label(brand_top_row, text="Forge", style="HeaderTitle.TLabel").pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(
            brand_frame,
            text="by Anchor & Honor",
            style="HeaderSubtitle.TLabel",
        ).grid(row=1, column=0, pady=(2, 0))

        right_spacer = ttk.Frame(header, style="Header.TFrame")
        right_spacer.grid(row=0, column=2, sticky="nsew")

        divider = tk.Frame(self.root, bg="#1D3348", height=1)
        divider.pack(fill=tk.X, side=tk.TOP)

    def _draw_wordmark_symbol(self, canvas: tk.Canvas) -> None:
        steel = "#D8DEE5"
        white = "#FFFFFF"
        accent = Theme.ACCENT

        # Hammer head and peen
        canvas.create_rectangle(7, 6, 20, 10, fill=steel, outline="")
        canvas.create_rectangle(20, 7, 24, 9, fill=white, outline="")
        # Hammer handle
        canvas.create_line(16, 10, 27, 21, fill=white, width=3)

        # Wire tips and single arc line
        canvas.create_oval(4, 17, 6, 19, fill=accent, outline=accent)
        canvas.create_oval(31, 11, 33, 13, fill=accent, outline=accent)
        canvas.create_line(6, 18, 12, 14, 17, 16, 23, 11, 31, 12, fill=accent, width=2)


    def _make_scrollable_tab(self, parent: ttk.Frame) -> ttk.Frame:
        canvas = tk.Canvas(parent, highlightthickness=0, bg=Theme.LIGHT_BG)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=12)

        content_window = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def on_content_configure(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event: tk.Event) -> None:
            canvas.itemconfigure(content_window, width=event.width)

        content.bind("<Configure>", on_content_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._bind_mousewheel(canvas)
        return content

    def _bind_mousewheel(self, canvas: tk.Canvas) -> None:
        def _on_mousewheel(event: tk.Event) -> None:
            if getattr(event, "delta", 0):
                canvas.yview_scroll(int(-event.delta / 120), "units")

        def _on_mousewheel_linux_up(_event: tk.Event) -> None:
            canvas.yview_scroll(-1, "units")

        def _on_mousewheel_linux_down(_event: tk.Event) -> None:
            canvas.yview_scroll(1, "units")

        canvas.bind("<MouseWheel>", _on_mousewheel)
        canvas.bind("<Button-4>", _on_mousewheel_linux_up)
        canvas.bind("<Button-5>", _on_mousewheel_linux_down)

    def _build_player_tab(self) -> None:
        active_frame = ttk.LabelFrame(self.player_content, text="Active Player", padding=10, style="Card.TLabelframe")
        active_frame.pack(fill=tk.X, pady=6)

        ttk.Label(active_frame, text="Select:").grid(row=0, column=0, sticky="w")
        self.active_player_var = tk.StringVar()
        self.active_player_combo = ttk.Combobox(
            active_frame,
            textvariable=self.active_player_var,
            state="readonly",
            width=42,
        )
        self.active_player_combo.grid(row=0, column=1, padx=6, sticky="w")
        self.active_player_combo.bind("<<ComboboxSelected>>", self._on_active_player_selected)

        self.player_details_var = tk.StringVar(value="No player selected")
        ttk.Label(active_frame, textvariable=self.player_details_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        form_frame = ttk.LabelFrame(self.player_content, text="Create / Edit Player", padding=10, style="Card.TLabelframe")
        form_frame.pack(fill=tk.X, pady=6)

        self.player_form_vars = {
            "name": tk.StringVar(value="Xander"),
            "number": tk.StringVar(),
            "team": tk.StringVar(value="Unassigned"),
            "position": tk.StringVar(value="C"),
            "bats": tk.StringVar(),
            "throws": tk.StringVar(),
            "level": tk.StringVar(),
        }

        fields = [
            ("Name", "name"),
            ("Number", "number"),
            ("Team", "team"),
            ("Position", "position"),
            ("Bats", "bats"),
            ("Throws", "throws"),
            ("Level", "level"),
        ]
        for idx, (label, key) in enumerate(fields):
            ttk.Label(form_frame, text=f"{label}:").grid(row=idx, column=0, sticky="w", pady=2)
            if key == "team":
                self.player_team_combo = ttk.Combobox(
                    form_frame,
                    textvariable=self.player_form_vars["team"],
                    state="readonly",
                    width=28,
                )
                self.player_team_combo.grid(row=idx, column=1, sticky="w", pady=2, padx=6)
            else:
                ttk.Entry(form_frame, textvariable=self.player_form_vars[key], width=30).grid(
                    row=idx, column=1, sticky="w", pady=2, padx=6
                )

        actions = ttk.Frame(form_frame)
        actions.grid(row=len(fields), column=0, columnspan=2, pady=(10, 0), sticky="w")
        ttk.Button(actions, text="Create Player", command=self.create_player).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="Load Active Into Form", command=self.load_active_into_form).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions, text="Update Active Player", command=self.update_active_player).pack(side=tk.LEFT)

    def _build_game_tab(self) -> None:
        game_frame = ttk.LabelFrame(self.game_content, text="Add Game", padding=10, style="Card.TLabelframe")
        game_frame.pack(fill=tk.X, pady=6)

        self.game_date_var = tk.StringVar(value=date.today().isoformat())
        self.game_season_var = tk.StringVar(value=str(date.today().year))
        self.game_opponent_var = tk.StringVar()

        ttk.Label(game_frame, text="Date (YYYY-MM-DD):").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(game_frame, textvariable=self.game_date_var, width=20).grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(game_frame, text="Season:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(game_frame, textvariable=self.game_season_var, width=20).grid(row=1, column=1, sticky="w", padx=6)

        ttk.Label(game_frame, text="Opponent:").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(game_frame, textvariable=self.game_opponent_var, width=40).grid(row=2, column=1, sticky="w", padx=6)

        notes_frame = ttk.LabelFrame(self.game_content, text="Game Notes", padding=10, style="Card.TLabelframe")
        notes_frame.pack(fill=tk.X, pady=6)
        self.game_notes_text = scrolledtext.ScrolledText(
            notes_frame,
            height=5,
            wrap=tk.WORD,
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="solid",
            borderwidth=1,
        )
        self.game_notes_text.pack(fill=tk.X, expand=True)

        stats_frame = ttk.LabelFrame(self.game_content, text="Stat Line", padding=10, style="Card.TLabelframe")
        stats_frame.pack(fill=tk.BOTH, expand=True, pady=6)

        self.stat_vars: dict[str, tk.StringVar] = {}
        hitting_fields = [
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
        ]
        catching_fields = ["innings_caught", "passed_balls", "sb_allowed", "cs_caught"]

        for idx, field in enumerate(hitting_fields):
            self.stat_vars[field] = tk.StringVar(value="0")
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(stats_frame, text=f"{field.upper()}:").grid(row=row, column=col, sticky="w", pady=2)
            ttk.Entry(stats_frame, textvariable=self.stat_vars[field], width=10).grid(
                row=row, column=col + 1, sticky="w", padx=6, pady=2
            )

        offset = (len(hitting_fields) + 1) // 2
        for idx, field in enumerate(catching_fields):
            self.stat_vars[field] = tk.StringVar(value="0")
            row = offset + idx
            label = field.replace("_", " ").title()
            ttk.Label(stats_frame, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(stats_frame, textvariable=self.stat_vars[field], width=10).grid(
                row=row, column=1, sticky="w", padx=6, pady=2
            )

        ttk.Button(self.game_content, text="Save Game + Stat Line", command=self.save_game_and_stats).pack(
            anchor="w", pady=8
        )

        history_frame = ttk.LabelFrame(self.game_content, text="Game History", padding=10, style="Card.TLabelframe")
        history_frame.pack(fill=tk.BOTH, expand=True, pady=6)

        history_filter_frame = ttk.Frame(history_frame, style="Card.TFrame")
        history_filter_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(history_filter_frame, text="Season:").grid(row=0, column=0, sticky="w")
        self.game_history_season_combo = ttk.Combobox(
            history_filter_frame,
            textvariable=self.filter_season_var,
            state="readonly",
            width=12,
        )
        self.game_history_season_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.game_history_season_combo.bind("<<ComboboxSelected>>", self._on_filters_changed)
        ttk.Label(history_filter_frame, text="Start:").grid(row=0, column=2, sticky="w")
        ttk.Entry(history_filter_frame, textvariable=self.filter_start_date_var, width=13).grid(
            row=0, column=3, sticky="w", padx=6
        )
        ttk.Label(history_filter_frame, text="End:").grid(row=0, column=4, sticky="w")
        ttk.Entry(history_filter_frame, textvariable=self.filter_end_date_var, width=13).grid(
            row=0, column=5, sticky="w", padx=6
        )
        ttk.Button(history_filter_frame, text="Apply", command=self._apply_filters).grid(row=0, column=6, padx=(8, 0))
        ttk.Button(history_filter_frame, text="Clear", command=self._clear_filters).grid(row=0, column=7, padx=(6, 0))
        ttk.Button(history_filter_frame, text="Last 30 Days", command=self._set_last_30_days).grid(
            row=0, column=8, padx=(6, 0)
        )
        ttk.Button(history_filter_frame, text="All", command=self._set_all_filters).grid(row=0, column=9, padx=(6, 0))

        self.game_history_tree = ttk.Treeview(
            history_frame,
            columns=("date", "opponent"),
            show="headings",
            height=8,
        )
        self.game_history_tree.heading("date", text="Date")
        self.game_history_tree.heading("opponent", text="Opponent")
        self.game_history_tree.column("date", width=150, anchor="w")
        self.game_history_tree.column("opponent", width=500, anchor="w")
        self.game_history_tree.pack(fill=tk.BOTH, expand=True)

        ttk.Button(
            history_frame,
            text="Delete Selected Game",
            command=self.delete_selected_game,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Button(
            history_frame,
            text="Load Game",
            command=self.load_selected_game,
        ).pack(anchor="w", pady=(6, 0))

    def _build_teams_tab(self) -> None:
        create_frame = ttk.LabelFrame(self.teams_content, text="Create Team", padding=10, style="Card.TLabelframe")
        create_frame.pack(fill=tk.X, pady=6)
        self.new_team_name_var = tk.StringVar()
        ttk.Label(create_frame, text="Team Name:").grid(row=0, column=0, sticky="w")
        ttk.Entry(create_frame, textvariable=self.new_team_name_var, width=30).grid(row=0, column=1, padx=6, sticky="w")
        ttk.Button(create_frame, text="Create Team", command=self.create_team).grid(row=0, column=2, padx=(8, 0))

        select_frame = ttk.LabelFrame(self.teams_content, text="Active Team", padding=10, style="Card.TLabelframe")
        select_frame.pack(fill=tk.X, pady=6)
        ttk.Label(select_frame, text="Select Team:").grid(row=0, column=0, sticky="w")
        self.active_team_var = tk.StringVar(value="No team")
        self.active_team_combo = ttk.Combobox(
            select_frame,
            textvariable=self.active_team_var,
            state="readonly",
            width=36,
        )
        self.active_team_combo.grid(row=0, column=1, padx=6, sticky="w")
        self.active_team_combo.bind("<<ComboboxSelected>>", self._on_active_team_selected)

        assign_frame = ttk.LabelFrame(self.teams_content, text="Assign Player to Team", padding=10, style="Card.TLabelframe")
        assign_frame.pack(fill=tk.X, pady=6)
        ttk.Label(assign_frame, text="Player:").grid(row=0, column=0, sticky="w")
        self.team_assign_player_var = tk.StringVar()
        self.team_assign_player_combo = ttk.Combobox(
            assign_frame,
            textvariable=self.team_assign_player_var,
            state="readonly",
            width=42,
        )
        self.team_assign_player_combo.grid(row=0, column=1, padx=6, sticky="w")
        ttk.Button(assign_frame, text="Assign to Active Team", command=self.assign_selected_player_to_active_team).grid(
            row=0, column=2, padx=(8, 0)
        )

        roster_frame = ttk.LabelFrame(self.teams_content, text="Players in Team", padding=10, style="Card.TLabelframe")
        roster_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        self.team_players_tree = ttk.Treeview(
            roster_frame,
            columns=("name", "position", "level"),
            show="headings",
            height=10,
        )
        self.team_players_tree.heading("name", text="Player")
        self.team_players_tree.heading("position", text="Position")
        self.team_players_tree.heading("level", text="Level")
        self.team_players_tree.column("name", width=280, anchor="w")
        self.team_players_tree.column("position", width=120, anchor="w")
        self.team_players_tree.column("level", width=140, anchor="w")
        self.team_players_tree.pack(fill=tk.BOTH, expand=True)

    def _build_team_dashboard_tab(self) -> None:
        header = ttk.LabelFrame(self.team_dashboard_content, text="Team Dashboard", padding=10, style="Card.TLabelframe")
        header.pack(fill=tk.X, pady=6)
        self.team_dashboard_team_var = tk.StringVar(value="No active team")
        ttk.Label(header, textvariable=self.team_dashboard_team_var, font=("TkDefaultFont", 11, "bold")).pack(anchor="w")

        filters_frame = ttk.Frame(header, style="Card.TFrame")
        filters_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(filters_frame, text="Season:").grid(row=0, column=0, sticky="w")
        self.team_dash_season_combo = ttk.Combobox(
            filters_frame,
            textvariable=self.filter_season_var,
            state="readonly",
            width=12,
        )
        self.team_dash_season_combo.grid(row=0, column=1, padx=6, sticky="w")
        self.team_dash_season_combo.bind("<<ComboboxSelected>>", self._on_filters_changed)
        ttk.Label(filters_frame, text="Start:").grid(row=0, column=2, sticky="w")
        ttk.Entry(filters_frame, textvariable=self.filter_start_date_var, width=13).grid(row=0, column=3, padx=6, sticky="w")
        ttk.Label(filters_frame, text="End:").grid(row=0, column=4, sticky="w")
        ttk.Entry(filters_frame, textvariable=self.filter_end_date_var, width=13).grid(row=0, column=5, padx=6, sticky="w")
        ttk.Button(filters_frame, text="Apply", command=self._apply_filters).grid(row=0, column=6, padx=(8, 0))
        ttk.Button(filters_frame, text="Clear", command=self._clear_filters).grid(row=0, column=7, padx=(6, 0))

        table_frame = ttk.LabelFrame(
            self.team_dashboard_content,
            text="Players Summary",
            padding=10,
            style="Card.TLabelframe",
        )
        table_frame.pack(fill=tk.BOTH, expand=True, pady=6)

        self.team_dashboard_tree = ttk.Treeview(
            table_frame,
            columns=("name", "position", "ops", "k_rate", "cs_pct", "focus"),
            show="headings",
            height=12,
        )
        self.team_dashboard_tree.heading("name", text="Player Name")
        self.team_dashboard_tree.heading("position", text="Position")
        self.team_dashboard_tree.heading("ops", text="OPS")
        self.team_dashboard_tree.heading("k_rate", text="K Rate")
        self.team_dashboard_tree.heading("cs_pct", text="CS%")
        self.team_dashboard_tree.heading("focus", text="Top Focus Suggestion")
        self.team_dashboard_tree.column("name", width=220, anchor="w")
        self.team_dashboard_tree.column("position", width=100, anchor="w")
        self.team_dashboard_tree.column("ops", width=90, anchor="w")
        self.team_dashboard_tree.column("k_rate", width=90, anchor="w")
        self.team_dashboard_tree.column("cs_pct", width=90, anchor="w")
        self.team_dashboard_tree.column("focus", width=320, anchor="w")
        self.team_dashboard_tree.pack(fill=tk.BOTH, expand=True)
        self.team_dashboard_tree.bind("<Double-1>", self._activate_player_from_team_dashboard)

    def _build_video_tab(self) -> None:
        container = ttk.Frame(self.video_content)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=0)
        container.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(container, text="Video", padding=10, style="Card.TLabelframe")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ttk.LabelFrame(container, text="Controls", padding=10, style="Card.TLabelframe")
        right.grid(row=0, column=1, sticky="ns")
        right.configure(width=330)
        right.grid_propagate(False)

        self.video_canvas_label = tk.Canvas(
            left,
            bg="#0A0A0A",
            highlightthickness=0,
            bd=0,
        )
        self.video_canvas_label.pack(fill=tk.BOTH, expand=True)
        self.video_canvas_label.bind("<ButtonPress-1>", self._on_video_roi_mouse_down)
        self.video_canvas_label.bind("<B1-Motion>", self._on_video_roi_mouse_drag)
        self.video_canvas_label.bind("<ButtonRelease-1>", self._on_video_roi_mouse_up)
        self.video_canvas_message_id = self.video_canvas_label.create_text(
            20,
            20,
            text="Load a video to begin",
            fill="#D8DEE5",
            anchor="nw",
            font=("TkDefaultFont", 12),
        )

        self.video_timeline_var = tk.DoubleVar(value=0.0)
        self.video_timeline = tk.Scale(
            left,
            from_=0.0,
            to=1.0,
            resolution=0.001,
            orient=tk.HORIZONTAL,
            variable=self.video_timeline_var,
            command=self._on_video_timeline_changed,
            state=tk.DISABLED,
            highlightthickness=0,
        )
        self.video_timeline.pack(fill=tk.X, pady=(8, 0))

        self.video_time_var = tk.StringVar(value="Time: 0.000s | Frame: 0")
        ttk.Label(left, textvariable=self.video_time_var).pack(anchor="w", pady=(6, 0))

        self.video_btn_load = ttk.Button(right, text="Load Video", width=24, command=self.load_video_file)
        self.video_btn_load.pack(fill=tk.X, pady=(0, 6))
        self.video_btn_play = ttk.Button(right, text="Play", width=24, command=self.toggle_video_playback, state=tk.DISABLED)
        self.video_btn_play.pack(fill=tk.X, pady=(0, 6))
        self.video_btn_step_back = ttk.Button(
            right,
            text="Step Back Frame",
            width=24,
            command=lambda: self.step_video_frame(-1),
            state=tk.DISABLED,
        )
        self.video_btn_step_back.pack(fill=tk.X, pady=(0, 6))
        self.video_btn_step_fwd = ttk.Button(
            right,
            text="Step Forward Frame",
            width=24,
            command=lambda: self.step_video_frame(1),
            state=tk.DISABLED,
        )
        self.video_btn_step_fwd.pack(fill=tk.X, pady=(0, 6))

        self.video_btn_mark_catch = ttk.Button(
            right,
            text="Mark Catch",
            width=24,
            command=lambda: self.mark_video_time("catch"),
            state=tk.DISABLED,
        )
        self.video_btn_mark_catch.pack(fill=tk.X, pady=(0, 6))
        self.video_btn_mark_release = ttk.Button(
            right,
            text="Mark Release",
            width=24,
            command=lambda: self.mark_video_time("release"),
            state=tk.DISABLED,
        )
        self.video_btn_mark_release.pack(fill=tk.X, pady=(0, 6))
        self.video_btn_mark_target = ttk.Button(
            right,
            text="Mark Target Catch",
            width=24,
            command=lambda: self.mark_video_time("target"),
            state=tk.DISABLED,
        )
        self.video_btn_mark_target.pack(fill=tk.X, pady=(0, 6))
        self.video_btn_calc = ttk.Button(
            right,
            text="Calculate Pop Time",
            width=24,
            command=self.calculate_pop_time,
            state=tk.DISABLED,
        )
        self.video_btn_calc.pack(fill=tk.X, pady=(0, 10))
        self.video_btn_auto_detect = ttk.Button(
            right,
            text="Auto Detect (Catch/Release)",
            width=24,
            command=self.auto_detect_video_markers,
            state=tk.DISABLED,
        )
        self.video_btn_auto_detect.pack(fill=tk.X, pady=(0, 8))
        self.video_btn_auto_build = ttk.Button(
            right,
            text="Auto Build Rep Set",
            width=24,
            command=self.auto_build_rep_set,
            state=tk.DISABLED,
        )
        self.video_btn_auto_build.pack(fill=tk.X, pady=(0, 8))

        metric_controls = ttk.LabelFrame(right, text="Metric Mode", padding=8, style="Card.TLabelframe")
        metric_controls.pack(fill=tk.X, pady=(0, 8))
        self.video_metric_mode_var = tk.StringVar(value="Transfer (Catch→Release)")
        self.video_metric_mode_combo = ttk.Combobox(
            metric_controls,
            textvariable=self.video_metric_mode_var,
            values=[
                "Transfer (Catch→Release)",
                "Full Pop (Catch→Target)",
                "Estimated Pop (Transfer + Flight Est.)",
            ],
            state="readonly",
            width=30,
        )
        self.video_metric_mode_combo.grid(row=0, column=0, columnspan=2, sticky="w")
        self.video_metric_mode_combo.bind("<<ComboboxSelected>>", self._on_metric_mode_changed)
        ttk.Label(metric_controls, text="Estimated Flight Time (s):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.video_est_flight_var = tk.StringVar(value="0.80")
        self.video_est_flight_entry = ttk.Entry(metric_controls, textvariable=self.video_est_flight_var, width=10)
        self.video_est_flight_entry.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))

        detect_controls = ttk.LabelFrame(right, text="Detection Window", padding=8, style="Card.TLabelframe")
        detect_controls.pack(fill=tk.X, pady=(0, 8))
        self.video_release_window_var = tk.StringVar(value="1.2")
        self.video_batch_max_reps_var = tk.StringVar(value="12")
        self.video_batch_min_spacing_var = tk.StringVar(value="1.5")
        self.video_batch_conf_threshold_var = tk.StringVar(value="0.35")
        self.video_roi_preset_var = tk.StringVar(value="Auto")
        ttk.Label(detect_controls, text="Max Reps:").grid(row=0, column=0, sticky="w")
        ttk.Entry(detect_controls, textvariable=self.video_batch_max_reps_var, width=10).grid(
            row=0, column=1, sticky="w", padx=6
        )
        ttk.Label(detect_controls, text="Min Catch Spacing (s):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(detect_controls, textvariable=self.video_batch_min_spacing_var, width=10).grid(
            row=1, column=1, sticky="w", padx=6, pady=(6, 0)
        )
        ttk.Label(detect_controls, text="Confidence Threshold:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(detect_controls, textvariable=self.video_batch_conf_threshold_var, width=10).grid(
            row=2, column=1, sticky="w", padx=6, pady=(6, 0)
        )
        ttk.Label(detect_controls, text="Release End (s):").grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(detect_controls, textvariable=self.video_release_window_var, width=10).grid(
            row=3, column=1, sticky="w", padx=6, pady=(6, 0)
        )
        ttk.Label(detect_controls, text="ROI Preset:").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.video_roi_combo = ttk.Combobox(
            detect_controls,
            textvariable=self.video_roi_preset_var,
            values=["Auto", "Lower Middle", "Lower Left", "Lower Right", "Custom"],
            state="readonly",
            width=18,
        )
        self.video_roi_combo.grid(row=4, column=1, sticky="w", padx=6, pady=(6, 0))
        self.video_roi_combo.bind("<<ComboboxSelected>>", self._on_roi_preset_changed)
        self.video_btn_set_roi = ttk.Button(detect_controls, text="Set ROI", command=self.start_roi_selection)
        self.video_btn_set_roi.grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.video_btn_clear_roi = ttk.Button(detect_controls, text="Clear ROI", command=self.clear_custom_roi)
        self.video_btn_clear_roi.grid(row=5, column=1, sticky="w", padx=6, pady=(6, 0))
        self.video_roi_label_var = tk.StringVar(value="ROI: Auto")
        ttk.Label(detect_controls, textvariable=self.video_roi_label_var).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        results = ttk.LabelFrame(right, text="Results", padding=8, style="Card.TLabelframe")
        results.pack(fill=tk.X)
        self.video_result_catch_var = tk.StringVar(value="Catch Time: —")
        self.video_result_release_var = tk.StringVar(value="Release Time: —")
        self.video_result_transfer_var = tk.StringVar(value="Transfer Time: —")
        self.video_result_throw_var = tk.StringVar(value="Throw Time: —")
        self.video_result_pop_var = tk.StringVar(value="Total Pop Time: —")
        for var in [
            self.video_result_catch_var,
            self.video_result_release_var,
            self.video_result_transfer_var,
            self.video_result_throw_var,
            self.video_result_pop_var,
        ]:
            ttk.Label(results, textvariable=var).pack(anchor="w")
        self.video_detect_conf_var = tk.StringVar(value="Detect Conf: Catch — | Release —")
        ttk.Label(results, textvariable=self.video_detect_conf_var).pack(anchor="w", pady=(4, 0))

        self.video_current_rep_var = tk.StringVar(value="Current Rep: 1 of 0")
        ttk.Label(right, textvariable=self.video_current_rep_var).pack(anchor="w", pady=(8, 4))
        self.video_btn_add_rep = ttk.Button(right, text="Add Rep", width=24, command=self.add_current_rep, state=tk.DISABLED)
        self.video_btn_add_rep.pack(fill=tk.X, pady=(0, 6))
        self.video_btn_clear_markers = ttk.Button(
            right,
            text="Clear Markers",
            width=24,
            command=self.clear_current_markers,
            state=tk.DISABLED,
        )
        self.video_btn_clear_markers.pack(fill=tk.X, pady=(0, 6))
        self.video_btn_delete_rep = ttk.Button(
            right,
            text="Delete Selected Rep",
            width=24,
            command=self.delete_selected_rep,
            state=tk.DISABLED,
        )
        self.video_btn_delete_rep.pack(fill=tk.X, pady=(0, 6))
        self.video_btn_clear_reps = ttk.Button(
            right,
            text="Clear All Reps",
            width=24,
            command=self.clear_all_reps,
            state=tk.DISABLED,
        )
        self.video_btn_clear_reps.pack(fill=tk.X, pady=(0, 8))

        rep_frame = ttk.LabelFrame(right, text="Rep List", padding=8, style="Card.TLabelframe")
        rep_frame.pack(fill=tk.X, pady=(0, 10))
        self.rep_tree = ttk.Treeview(
            rep_frame,
            columns=("rep", "catch", "release", "target", "transfer", "pop", "conf"),
            show="headings",
            height=6,
        )
        self.rep_tree.heading("rep", text="Rep #")
        self.rep_tree.heading("catch", text="Catch")
        self.rep_tree.heading("release", text="Release")
        self.rep_tree.heading("target", text="Target")
        self.rep_tree.heading("transfer", text="Transfer")
        self.rep_tree.heading("pop", text="Pop Time")
        self.rep_tree.heading("conf", text="Conf")
        self.rep_tree.column("rep", width=42, anchor="w")
        self.rep_tree.column("catch", width=52, anchor="w")
        self.rep_tree.column("release", width=56, anchor="w")
        self.rep_tree.column("target", width=50, anchor="w")
        self.rep_tree.column("transfer", width=58, anchor="w")
        self.rep_tree.column("pop", width=58, anchor="w")
        self.rep_tree.column("conf", width=86, anchor="w")
        self.rep_tree.pack(fill=tk.X)

        set_summary = ttk.LabelFrame(right, text="Set Summary", padding=8, style="Card.TLabelframe")
        set_summary.pack(fill=tk.X, pady=(0, 10))
        self.video_set_reps_var = tk.StringVar(value="Reps: 0")
        self.video_set_best_transfer_var = tk.StringVar(value="Best Transfer: —")
        self.video_set_avg_transfer_var = tk.StringVar(value="Avg Transfer: —")
        self.video_set_best_pop_var = tk.StringVar(value="Best Pop: —")
        self.video_set_avg_pop_var = tk.StringVar(value="Avg Pop: —")
        self.video_set_build_summary_var = tk.StringVar(value="Build Summary: —")
        for var in [
            self.video_set_reps_var,
            self.video_set_best_transfer_var,
            self.video_set_avg_transfer_var,
            self.video_set_best_pop_var,
            self.video_set_avg_pop_var,
            self.video_set_build_summary_var,
        ]:
            ttk.Label(set_summary, textvariable=var).pack(anchor="w")

        save_box = ttk.LabelFrame(right, text="Save To Practice", padding=8, style="Card.TLabelframe")
        save_box.pack(fill=tk.X, pady=(10, 0))
        self.video_reps_var = tk.StringVar(value="1")
        ttk.Label(save_box, text="Reps:").grid(row=0, column=0, sticky="w")
        ttk.Entry(save_box, textvariable=self.video_reps_var, width=10).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(save_box, text="Notes:").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self.video_session_notes_text = scrolledtext.ScrolledText(
            save_box,
            height=3,
            width=34,
            wrap=tk.WORD,
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="solid",
            borderwidth=1,
        )
        self.video_session_notes_text.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        self.video_btn_save_practice = ttk.Button(
            save_box,
            text="Save to Practice",
            command=self.save_video_to_practice,
            state=tk.DISABLED,
        )
        self.video_btn_save_practice.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._apply_metric_mode_controls()

    def _build_practice_tab(self) -> None:
        form_frame = ttk.LabelFrame(
            self.practice_content,
            text="Log Practice Session",
            padding=10,
            style="Card.TLabelframe",
        )
        form_frame.pack(fill=tk.X, pady=6)

        self.practice_date_var = tk.StringVar(value=date.today().isoformat())
        self.practice_category_var = tk.StringVar(value="Hitting")
        self.practice_focus_var = tk.StringVar(value="Contact & Timing")
        self.practice_duration_var = tk.StringVar(value="0")
        self.practice_pop_best_var = tk.StringVar()
        self.practice_pop_avg_var = tk.StringVar()
        self.practice_throws_var = tk.StringVar()
        self.practice_blocks_var = tk.StringVar()
        self.practice_swings_var = tk.StringVar()

        self.practice_categories = ["Hitting", "Catching", "Defense", "Strength", "Conditioning", "Mental"]
        self.practice_focuses = [
            "Contact & Timing",
            "Plate Discipline",
            "Gap Power",
            "Pop Time / Transfer",
            "Blocking Consistency",
            "Throwing Accuracy",
        ]

        ttk.Label(form_frame, text="Date (YYYY-MM-DD):").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(form_frame, textvariable=self.practice_date_var, width=18).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(form_frame, text="Category:").grid(row=0, column=2, sticky="w", pady=2)
        self.practice_category_combo = ttk.Combobox(
            form_frame,
            textvariable=self.practice_category_var,
            values=self.practice_categories,
            state="readonly",
            width=18,
        )
        self.practice_category_combo.grid(row=0, column=3, sticky="w", padx=6)

        ttk.Label(form_frame, text="Focus:").grid(row=1, column=0, sticky="w", pady=2)
        self.practice_focus_combo = ttk.Combobox(
            form_frame,
            textvariable=self.practice_focus_var,
            values=self.practice_focuses,
            width=28,
        )
        self.practice_focus_combo.grid(row=1, column=1, columnspan=3, sticky="w", padx=6)

        ttk.Label(form_frame, text="Duration (min):").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(form_frame, textvariable=self.practice_duration_var, width=12).grid(row=2, column=1, sticky="w", padx=6)

        ttk.Label(form_frame, text="Pop Time Best:").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Entry(form_frame, textvariable=self.practice_pop_best_var, width=12).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Label(form_frame, text="Pop Time Avg:").grid(row=3, column=2, sticky="w", pady=2)
        ttk.Entry(form_frame, textvariable=self.practice_pop_avg_var, width=12).grid(row=3, column=3, sticky="w", padx=6)

        ttk.Label(form_frame, text="Throws:").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Entry(form_frame, textvariable=self.practice_throws_var, width=12).grid(row=4, column=1, sticky="w", padx=6)
        ttk.Label(form_frame, text="Blocks:").grid(row=4, column=2, sticky="w", pady=2)
        ttk.Entry(form_frame, textvariable=self.practice_blocks_var, width=12).grid(row=4, column=3, sticky="w", padx=6)
        ttk.Label(form_frame, text="Swings:").grid(row=5, column=0, sticky="w", pady=2)
        ttk.Entry(form_frame, textvariable=self.practice_swings_var, width=12).grid(row=5, column=1, sticky="w", padx=6)

        notes_frame = ttk.LabelFrame(
            self.practice_content,
            text="Practice Notes",
            padding=10,
            style="Card.TLabelframe",
        )
        notes_frame.pack(fill=tk.X, pady=6)
        self.practice_notes_text = scrolledtext.ScrolledText(
            notes_frame,
            height=5,
            wrap=tk.WORD,
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="solid",
            borderwidth=1,
        )
        self.practice_notes_text.pack(fill=tk.X, expand=True)

        ttk.Button(
            self.practice_content,
            text="Save Practice Session",
            command=self.save_practice_session,
        ).pack(anchor="w", pady=8)

        list_frame = ttk.LabelFrame(
            self.practice_content,
            text="Recent Practice Sessions",
            padding=10,
            style="Card.TLabelframe",
        )
        list_frame.pack(fill=tk.BOTH, expand=True, pady=6)

        self.practice_tree = ttk.Treeview(
            list_frame,
            columns=("date", "category", "focus", "duration", "mode", "video"),
            show="headings",
            height=10,
        )
        self.practice_tree.heading("date", text="Date")
        self.practice_tree.heading("category", text="Category")
        self.practice_tree.heading("focus", text="Focus")
        self.practice_tree.heading("duration", text="Duration")
        self.practice_tree.heading("mode", text="Mode")
        self.practice_tree.heading("video", text="Video")
        self.practice_tree.column("date", width=120, anchor="w")
        self.practice_tree.column("category", width=140, anchor="w")
        self.practice_tree.column("focus", width=220, anchor="w")
        self.practice_tree.column("duration", width=100, anchor="w")
        self.practice_tree.column("mode", width=120, anchor="w")
        self.practice_tree.column("video", width=90, anchor="w")
        self.practice_tree.pack(fill=tk.BOTH, expand=True)

        ttk.Button(
            list_frame,
            text="Delete Selected Session",
            command=self.delete_selected_practice_session,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Button(
            list_frame,
            text="Open Video",
            command=self.open_selected_practice_video,
        ).pack(anchor="w", pady=(6, 0))

    def _build_dashboard_tab(self) -> None:
        self.dashboard_player_var = tk.StringVar(value="No active player")
        ttk.Label(
            self.dashboard_content,
            textvariable=self.dashboard_player_var,
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        filters_frame = ttk.LabelFrame(
            self.dashboard_content,
            text="Filters",
            padding=10,
            style="Card.TLabelframe",
        )
        filters_frame.pack(fill=tk.X, pady=6)

        ttk.Label(filters_frame, text="Season:").grid(row=0, column=0, sticky="w", pady=2)
        self.dashboard_season_combo = ttk.Combobox(
            filters_frame,
            textvariable=self.filter_season_var,
            state="readonly",
            width=14,
        )
        self.dashboard_season_combo.grid(row=0, column=1, sticky="w", padx=6, pady=2)
        self.dashboard_season_combo.bind("<<ComboboxSelected>>", self._on_filters_changed)

        ttk.Label(filters_frame, text="Start Date (YYYY-MM-DD):").grid(row=0, column=2, sticky="w", pady=2)
        ttk.Entry(filters_frame, textvariable=self.filter_start_date_var, width=16).grid(
            row=0, column=3, sticky="w", padx=6, pady=2
        )
        ttk.Label(filters_frame, text="End Date (YYYY-MM-DD):").grid(row=0, column=4, sticky="w", pady=2)
        ttk.Entry(filters_frame, textvariable=self.filter_end_date_var, width=16).grid(
            row=0, column=5, sticky="w", padx=6, pady=2
        )
        ttk.Button(filters_frame, text="Apply", command=self._apply_filters).grid(
            row=0, column=6, sticky="w", padx=(8, 0), pady=2
        )
        ttk.Button(filters_frame, text="Clear", command=self._clear_filters).grid(
            row=0, column=7, sticky="w", padx=(6, 0), pady=2
        )
        ttk.Button(filters_frame, text="Last 30 Days", command=self._set_last_30_days).grid(
            row=0, column=8, sticky="w", padx=(6, 0), pady=2
        )
        ttk.Button(filters_frame, text="All", command=self._set_all_filters).grid(
            row=0, column=9, sticky="w", padx=(6, 0), pady=2
        )
        ttk.Label(filters_frame, text="Baseline Season:").grid(row=1, column=0, sticky="w", pady=(6, 2))
        self.baseline_summary_var = tk.StringVar(value="None")
        self.baseline_summary_combo = ttk.Combobox(
            filters_frame,
            textvariable=self.baseline_summary_var,
            state="readonly",
            width=36,
        )
        self.baseline_summary_combo.grid(row=1, column=1, columnspan=4, sticky="w", padx=6, pady=(6, 2))
        self.baseline_summary_combo.bind("<<ComboboxSelected>>", self._on_filters_changed)

        totals_frame = ttk.LabelFrame(self.dashboard_content, text="Season Totals", padding=10, style="Card.TLabelframe")
        totals_frame.pack(fill=tk.X, pady=6)

        self.totals_text = tk.Text(totals_frame, height=12, width=110)
        self.totals_text.pack(fill=tk.X)
        self.totals_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
        )
        self.totals_text.configure(state=tk.DISABLED)

        baseline_frame = ttk.LabelFrame(self.dashboard_content, text="Baseline Comparison", padding=10, style="Card.TLabelframe")
        baseline_frame.pack(fill=tk.X, pady=6)
        self.baseline_compare_text = tk.Text(baseline_frame, height=6, width=110)
        self.baseline_compare_text.pack(fill=tk.X)
        self.baseline_compare_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
            state=tk.DISABLED,
        )

        trends_frame = ttk.LabelFrame(self.dashboard_content, text="Last 5 Games Trends", padding=10, style="Card.TLabelframe")
        trends_frame.pack(fill=tk.X, pady=6)

        self.trends_vars = {
            "OPS": tk.StringVar(value="OPS: —"),
            "SO_RATE": tk.StringVar(value="SO Rate: —"),
            "CS_PCT": tk.StringVar(value="CS%: —"),
            "PB_RATE": tk.StringVar(value="PB Rate: —"),
        }
        for key in ["OPS", "SO_RATE", "CS_PCT", "PB_RATE"]:
            ttk.Label(trends_frame, textvariable=self.trends_vars[key], font=("TkDefaultFont", 10)).pack(anchor="w")

        perf_frame = ttk.LabelFrame(
            self.dashboard_content,
            text="Performance Trends",
            padding=10,
            style="Card.TLabelframe",
        )
        perf_frame.pack(fill=tk.X, pady=6)

        self.avg_momentum_var = tk.StringVar(value="AVG Momentum: STABLE")
        self.avg_momentum_label = tk.Label(
            perf_frame,
            textvariable=self.avg_momentum_var,
            bg=Theme.CARD_BG,
            fg="#8A96A3",
            font=("Segoe UI", 10, "bold"),
        )
        self.avg_momentum_label.pack(anchor="w", pady=(0, 6))

        table = ttk.Frame(perf_frame, style="Card.TFrame")
        table.pack(fill=tk.X)
        headers = ["Metric", "Season", "Last 5", "Trend", "Last 10", "Trend"]
        for col, title in enumerate(headers):
            ttk.Label(table, text=title, font=("TkDefaultFont", 10, "bold")).grid(
                row=0, column=col, sticky="w", padx=(0, 14), pady=(0, 6)
            )

        self.performance_metric_order = ["AVG", "OBP", "SLG", "K_RATE", "BB_RATE", "CS_PCT", "PB_RATE"]
        self.performance_cells: dict[str, dict[str, tk.StringVar | tk.Label]] = {}
        self.metric_display_names = {
            "AVG": "AVG",
            "OBP": "OBP",
            "SLG": "SLG",
            "OPS": "OPS",
            "K_RATE": "K Rate",
            "BB_RATE": "BB Rate",
            "CS_PCT": "CS%",
            "PB_RATE": "PB Rate",
            "POP_TIME": "Pop Time",
            "TRANSFER_TIME": "Transfer Time",
        }

        for row_idx, metric in enumerate(self.performance_metric_order, start=1):
            season_var = tk.StringVar(value="—")
            last5_var = tk.StringVar(value="—")
            last10_var = tk.StringVar(value="—")
            trend5_var = tk.StringVar(value="→")
            trend10_var = tk.StringVar(value="→")

            metric_label = tk.Label(
                table,
                text=self.metric_display_names.get(metric, metric),
                bg=Theme.CARD_BG,
                fg=Theme.ACCENT,
                cursor="hand2",
                font=("TkDefaultFont", 10, "underline"),
            )
            metric_label.grid(row=row_idx, column=0, sticky="w", padx=(0, 14), pady=2)
            metric_label.bind(
                "<Button-1>",
                lambda _e, stat_key=metric: self.open_training_suggestion(stat_key),
            )
            ttk.Label(table, textvariable=season_var).grid(row=row_idx, column=1, sticky="w", padx=(0, 14), pady=2)
            ttk.Label(table, textvariable=last5_var).grid(row=row_idx, column=2, sticky="w", padx=(0, 14), pady=2)
            trend5_label = tk.Label(table, textvariable=trend5_var, bg=Theme.CARD_BG, fg="#8A96A3", font=("Segoe UI", 10))
            trend5_label.grid(row=row_idx, column=3, sticky="w", padx=(0, 14), pady=2)
            ttk.Label(table, textvariable=last10_var).grid(row=row_idx, column=4, sticky="w", padx=(0, 14), pady=2)
            trend10_label = tk.Label(table, textvariable=trend10_var, bg=Theme.CARD_BG, fg="#8A96A3", font=("Segoe UI", 10))
            trend10_label.grid(row=row_idx, column=5, sticky="w", padx=(0, 14), pady=2)

            self.performance_cells[metric] = {
                "season": season_var,
                "last5": last5_var,
                "last10": last10_var,
                "trend5": trend5_var,
                "trend10": trend10_var,
                "trend5_label": trend5_label,
                "trend10_label": trend10_label,
            }

        recent_notes_frame = ttk.LabelFrame(
            self.dashboard_content,
            text="Recent Notes",
            padding=10,
            style="Card.TLabelframe",
        )
        recent_notes_frame.pack(fill=tk.X, pady=6)

        self.recent_notes_text = tk.Text(recent_notes_frame, height=7, width=110)
        self.recent_notes_text.pack(fill=tk.X)
        self.recent_notes_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
            state=tk.DISABLED,
        )

        practice_week_frame = ttk.LabelFrame(
            self.dashboard_content,
            text="Practice This Week",
            padding=10,
            style="Card.TLabelframe",
        )
        practice_week_frame.pack(fill=tk.X, pady=6)
        self.practice_week_text = tk.Text(practice_week_frame, height=7, width=110)
        self.practice_week_text.pack(fill=tk.X)
        self.practice_week_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
            state=tk.DISABLED,
        )

        development_frame = ttk.LabelFrame(
            self.dashboard_content,
            text="Development Profile",
            padding=10,
            style="Card.TLabelframe",
        )
        development_frame.pack(fill=tk.X, pady=6)
        self.development_profile_text = tk.Text(development_frame, height=8, width=110)
        self.development_profile_text.pack(fill=tk.X)
        self.development_profile_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
            state=tk.DISABLED,
        )

        consistency_frame = ttk.LabelFrame(
            self.dashboard_content,
            text="Consistency",
            padding=10,
            style="Card.TLabelframe",
        )
        consistency_frame.pack(fill=tk.X, pady=6)
        self.consistency_text = tk.Text(consistency_frame, height=6, width=110)
        self.consistency_text.pack(fill=tk.X)
        self.consistency_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
            state=tk.DISABLED,
        )

        current_focus_frame = ttk.LabelFrame(
            self.dashboard_content,
            text="🎯 Current Development Focus",
            padding=10,
            style="Card.TLabelframe",
        )
        current_focus_frame.pack(fill=tk.X, pady=6)
        self.current_focus_text = tk.Text(current_focus_frame, height=6, width=110)
        self.current_focus_text.pack(fill=tk.X)
        self.current_focus_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
            state=tk.DISABLED,
        )
        self.current_focus_btn = ttk.Button(
            current_focus_frame,
            text="View Training Suggestions",
            command=self.open_current_focus_training,
        )
        self.current_focus_btn.pack(anchor="w", pady=(6, 0))

        focus_frame = ttk.LabelFrame(
            self.dashboard_content,
            text="Focus This Week",
            padding=10,
            style="Card.TLabelframe",
        )
        focus_frame.pack(fill=tk.X, pady=6)
        ttk.Label(
            focus_frame,
            text="Based on last 5 vs season trends",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        self.focus_text = tk.Text(focus_frame, height=11, width=110)
        self.focus_text.pack(fill=tk.X)
        self.focus_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
            state=tk.DISABLED,
        )

        shared_suggestions_frame = ttk.LabelFrame(
            self.dashboard_content,
            text="Suggested Development Focus (Shared Engine)",
            padding=10,
            style="Card.TLabelframe",
        )
        shared_suggestions_frame.pack(fill=tk.X, pady=6)
        self.shared_suggestions_text = tk.Text(shared_suggestions_frame, height=8, width=110)
        self.shared_suggestions_text.pack(fill=tk.X)
        self.shared_suggestions_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
            state=tk.DISABLED,
        )

        actions = ttk.Frame(self.dashboard_content)
        actions.pack(anchor="w", pady=8)
        ttk.Button(actions, text="Refresh Dashboard", command=self.refresh_dashboard).pack(side=tk.LEFT)
        ttk.Button(actions, text="Export Report (PDF)", command=self.export_report_pdf).pack(side=tk.LEFT, padx=(8, 0))

    def _build_season_summary_tab(self) -> None:
        form = ttk.LabelFrame(self.season_summary_content, text="Import Season Summary", padding=10, style="Card.TLabelframe")
        form.pack(fill=tk.X, pady=6)

        self.season_summary_player_var = tk.StringVar()
        self.season_summary_label_var = tk.StringVar()
        self.season_summary_start_var = tk.StringVar()
        self.season_summary_end_var = tk.StringVar()

        ttk.Label(form, text="Player:").grid(row=0, column=0, sticky="w")
        self.season_summary_player_combo = ttk.Combobox(
            form,
            textvariable=self.season_summary_player_var,
            state="readonly",
            width=40,
        )
        self.season_summary_player_combo.grid(row=0, column=1, sticky="w", padx=6, pady=2)
        self.season_summary_player_combo.bind("<<ComboboxSelected>>", self._on_season_summary_player_changed)

        ttk.Label(form, text="Season Label:").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.season_summary_label_var, width=30).grid(row=1, column=1, sticky="w", padx=6, pady=2)
        ttk.Label(form, text="Start (YYYY-MM-DD):").grid(row=2, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.season_summary_start_var, width=18).grid(row=2, column=1, sticky="w", padx=6, pady=2)
        ttk.Label(form, text="End (YYYY-MM-DD):").grid(row=3, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.season_summary_end_var, width=18).grid(row=3, column=1, sticky="w", padx=6, pady=2)

        paste_frame = ttk.LabelFrame(self.season_summary_content, text="Paste Season Stats Here", padding=10, style="Card.TLabelframe")
        paste_frame.pack(fill=tk.X, pady=6)
        self.season_summary_text = scrolledtext.ScrolledText(
            paste_frame,
            height=8,
            wrap=tk.WORD,
            bg=Theme.CARD_BG,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="solid",
            borderwidth=1,
        )
        self.season_summary_text.pack(fill=tk.X)

        btns = ttk.Frame(self.season_summary_content, style="Card.TFrame")
        btns.pack(fill=tk.X, pady=(2, 6))
        ttk.Button(btns, text="Parse", command=self.parse_current_season_summary).pack(side=tk.LEFT)
        ttk.Button(btns, text="Save Season Summary", command=self.save_current_season_summary).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="Clear", command=self.clear_season_summary_form).pack(side=tk.LEFT, padx=(8, 0))

        preview_frame = ttk.LabelFrame(self.season_summary_content, text="Parsed Preview", padding=10, style="Card.TLabelframe")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        self.season_summary_preview_tree = ttk.Treeview(
            preview_frame,
            columns=("field", "value"),
            show="headings",
            height=10,
        )
        self.season_summary_preview_tree.heading("field", text="Field")
        self.season_summary_preview_tree.heading("value", text="Value")
        self.season_summary_preview_tree.column("field", width=220, anchor="w")
        self.season_summary_preview_tree.column("value", width=180, anchor="w")
        self.season_summary_preview_tree.pack(fill=tk.BOTH, expand=True)

        unknown_frame = ttk.LabelFrame(self.season_summary_content, text="Unknown / Unparsed Lines", padding=10, style="Card.TLabelframe")
        unknown_frame.pack(fill=tk.X, pady=6)
        self.season_summary_unknown_text = tk.Text(unknown_frame, height=4, width=100)
        self.season_summary_unknown_text.pack(fill=tk.X)
        self.season_summary_unknown_text.configure(
            bg=Theme.CARD_BG,
            fg=Theme.DANGER,
            bd=0,
            highlightthickness=0,
            insertbackground=Theme.TEXT,
            state=tk.DISABLED,
        )

    def _build_trends_tab(self) -> None:
        controls = ttk.LabelFrame(self.trends_content, text="Trend Controls", padding=10, style="Card.TLabelframe")
        controls.pack(fill=tk.X, pady=6)
        self.trends_metric_options = {
            "OPS": "ops",
            "AVG": "avg",
            "OBP": "obp",
            "SLG": "slg",
            "K%": "k_rate",
            "BB%": "bb_rate",
            "CS%": "cs_pct",
            "PB Rate": "pb_rate",
            "Transfer": "transfer_avg",
            "Pop": "pop_avg",
        }
        ttk.Label(controls, text="Metric:").grid(row=0, column=0, sticky="w")
        self.trends_metric_combo = ttk.Combobox(
            controls,
            textvariable=self.trends_metric_var,
            values=list(self.trends_metric_options.keys()),
            state="readonly",
            width=20,
        )
        self.trends_metric_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.trends_metric_combo.bind("<<ComboboxSelected>>", self._on_trends_controls_changed)
        self.trends_inseason_toggle = ttk.Checkbutton(
            controls,
            text="In-season cumulative",
            variable=self.trends_inseason_var,
            command=self.refresh_trends_chart,
        )
        self.trends_inseason_toggle.grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Button(controls, text="Refresh Trends", command=self.refresh_trends_chart).grid(row=0, column=3, padx=(12, 0))

        chart_frame = ttk.LabelFrame(self.trends_content, text="Trend Chart", padding=10, style="Card.TLabelframe")
        chart_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        self.trends_chart_host = chart_frame
        if Figure is None or FigureCanvasTkAgg is None:
            ttk.Label(
                chart_frame,
                text="Matplotlib is not installed. Install with: pip install matplotlib",
                style="Muted.TLabel",
            ).pack(anchor="w")
            self.trends_chart_canvas = None
            self.trends_chart_axes = None
            return
        self.trends_chart_figure = Figure(figsize=(8.8, 4.2), dpi=100)
        self.trends_chart_axes = self.trends_chart_figure.add_subplot(111)
        self.trends_chart_canvas = FigureCanvasTkAgg(self.trends_chart_figure, master=chart_frame)
        self.trends_chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def refresh_players(self) -> None:
        players = self.db.get_players()
        display_names = []
        self.player_name_to_id = {}
        assign_display_names = []
        self.assign_player_name_to_id = {}
        for p in players:
            if p["number"]:
                label = f"{p['name']} (No. {p['number']}, {p['position']})"
            else:
                label = f"{p['name']} ({p['position']})"
            display_names.append(label)
            self.player_name_to_id[label] = int(p["id"])
            assign_display_names.append(label)
            self.assign_player_name_to_id[label] = int(p["id"])

        self.active_player_combo["values"] = display_names
        if hasattr(self, "season_summary_player_combo"):
            self.season_summary_player_combo["values"] = display_names
        if hasattr(self, "team_assign_player_combo"):
            self.team_assign_player_combo["values"] = assign_display_names

        if self.active_player_id is not None:
            for label, pid in self.player_name_to_id.items():
                if pid == self.active_player_id:
                    self.active_player_var.set(label)
                    self._update_player_details(pid)
                    break
        elif display_names:
            self.active_player_var.set(display_names[0])
            self.active_player_id = self.player_name_to_id[display_names[0]]
            self._update_player_details(self.active_player_id)

        if hasattr(self, "season_summary_player_var"):
            if self.active_player_var.get():
                self.season_summary_player_var.set(self.active_player_var.get())
            elif display_names:
                self.season_summary_player_var.set(display_names[0])

        self.refresh_teams()
        self.refresh_dashboard_filter_options()
        self.refresh_game_history()
        self.refresh_practice_sessions()
        self.refresh_baseline_summary_options()
        self.refresh_team_dashboard()
        self.refresh_dashboard()

    def _on_active_player_selected(self, _event: tk.Event) -> None:
        selected = self.active_player_var.get()
        self.active_player_id = self.player_name_to_id.get(selected)
        if self.active_player_id:
            self._update_player_details(self.active_player_id)
            if hasattr(self, "season_summary_player_var"):
                self.season_summary_player_var.set(selected)
            self.refresh_dashboard_filter_options()
            self.refresh_game_history()
            self.refresh_practice_sessions()
            self.refresh_baseline_summary_options()
            self.refresh_team_dashboard()
            self.refresh_dashboard()

    def _on_season_summary_player_changed(self, _event: tk.Event | None = None) -> None:
        self.refresh_baseline_summary_options()

    def _selected_season_summary_player_id(self) -> int | None:
        label = self.season_summary_player_var.get().strip()
        return self.player_name_to_id.get(label)

    def clear_season_summary_form(self) -> None:
        self.season_summary_text.delete("1.0", tk.END)
        self.season_summary_label_var.set("")
        self.season_summary_start_var.set("")
        self.season_summary_end_var.set("")
        self.season_summary_parsed = {}
        self.season_summary_unknown_lines = []
        for iid in self.season_summary_preview_tree.get_children():
            self.season_summary_preview_tree.delete(iid)
        self._set_season_summary_unknown_text("")

    def parse_current_season_summary(self) -> None:
        raw = self.season_summary_text.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showerror("Validation", "Paste season summary text first.")
            return
        parsed = parse_season_summary(raw)
        stats = dict(parsed.get("stats", {}))
        unknown = list(parsed.get("unknown_lines", []))
        computed = compute_season_summary_metrics(stats)
        self.season_summary_parsed = stats
        self.season_summary_unknown_lines = unknown

        for iid in self.season_summary_preview_tree.get_children():
            self.season_summary_preview_tree.delete(iid)
        for key in sorted(stats.keys()):
            self.season_summary_preview_tree.insert("", tk.END, values=(key, stats[key]))
        if computed:
            self.season_summary_preview_tree.insert("", tk.END, values=("--- computed ---", ""))
            for key in sorted(computed.keys()):
                self.season_summary_preview_tree.insert("", tk.END, values=(key, f"{computed[key]:.4f}"))

        self._set_season_summary_unknown_text("\n".join(unknown) if unknown else "None")
        messagebox.showinfo("Parsed", f"Detected {len(stats)} field(s).")

    def save_current_season_summary(self) -> None:
        player_id = self._selected_season_summary_player_id() or self.active_player_id
        if not player_id:
            messagebox.showerror("Validation", "Select a player for season summary.")
            return
        season_label = self.season_summary_label_var.get().strip()
        if not season_label:
            messagebox.showerror("Validation", "Season label is required.")
            return
        start_date = self.season_summary_start_var.get().strip() or None
        end_date = self.season_summary_end_var.get().strip() or None
        if start_date and not self._validate_date(start_date):
            messagebox.showerror("Validation", "Start date must be YYYY-MM-DD.")
            return
        if end_date and not self._validate_date(end_date):
            messagebox.showerror("Validation", "End date must be YYYY-MM-DD.")
            return
        source_text = self.season_summary_text.get("1.0", tk.END).strip()
        if not source_text:
            messagebox.showerror("Validation", "Paste season summary text first.")
            return
        if not self.season_summary_parsed:
            self.parse_current_season_summary()
            if not self.season_summary_parsed:
                return
        summary_id = self.db.add_season_summary(
            player_id=player_id,
            season_label=season_label,
            start_date=start_date,
            end_date=end_date,
            stats=self.season_summary_parsed,
            source_text=source_text,
        )
        row = self.db.get_season_summary(summary_id)
        if row:
            self._upsert_timeline_from_season_summary_row(dict(row))
        self.refresh_baseline_summary_options()
        self.refresh_dashboard()
        self.refresh_trends_chart()
        messagebox.showinfo("Saved", "Season summary saved.")

    def _upsert_timeline_from_season_summary_row(self, row: dict[str, Any]) -> None:
        try:
            stats = json.loads(str(row.get("stats_json") or "{}"))
        except json.JSONDecodeError:
            stats = {}
        metrics = compute_season_summary_metrics(stats)
        # Preserve provided rates if imported.
        for key in ("avg", "obp", "slg", "ops", "transfer_time", "pop_time"):
            if key in stats and key not in metrics:
                try:
                    metrics[key] = float(stats[key])
                except (TypeError, ValueError):
                    pass
        unified = {
            "avg": metrics.get("avg"),
            "obp": metrics.get("obp"),
            "slg": metrics.get("slg"),
            "ops": metrics.get("ops"),
            "k_rate": metrics.get("k_pct"),
            "bb_rate": metrics.get("bb_pct"),
            "cs_pct": metrics.get("cs_rate"),
            "pb_rate": metrics.get("pb_per_inning"),
            "transfer_avg": metrics.get("transfer_time"),
            "transfer_best": metrics.get("transfer_time"),
            "pop_avg": metrics.get("pop_time"),
            "pop_best": metrics.get("pop_time"),
            "totals": stats,
        }
        self.db.upsert_stat_timeline_point(
            player_id=int(row["player_id"]),
            source_type="season_summary",
            source_id=int(row["id"]),
            period_label=str(row.get("season_label") or "Season Summary"),
            start_date=row.get("start_date"),
            end_date=row.get("end_date"),
            metrics=unified,
        )

    def rebuild_game_aggregate_timeline(self, player_id: int, season_label: str | None) -> None:
        rows = self.db.get_stat_lines(player_id, season=season_label, start_date=None, end_date=None, limit=None)
        if not rows:
            return
        totals = self.db.get_season_totals(player_id, season=season_label, start_date=None, end_date=None, limit=None)
        hitting = compute_hitting_metrics(totals)
        catching = compute_catching_metrics(totals)
        windows = self.db.calculate_stat_windows(player_id, season=season_label, start_date=None, end_date=None)
        season_metrics = windows.get("season", {})

        practice_rows = self.db.get_recent_practice_sessions(player_id, limit=500)
        transfer_vals: list[float] = []
        pop_avg_vals: list[float] = []
        pop_best_vals: list[float] = []
        for pr in practice_rows:
            session_date = str(pr["session_date"] or "")
            if season_label and not session_date.startswith(str(season_label)):
                continue
            notes = str(pr["notes"] or "")
            m = re.search(r"best_transfer=([0-9]+(?:\.[0-9]+)?)s", notes)
            if m:
                try:
                    transfer_vals.append(float(m.group(1)))
                except ValueError:
                    pass
            if pr["pop_time_avg"] is not None:
                try:
                    pop_avg_vals.append(float(pr["pop_time_avg"]))
                except (TypeError, ValueError):
                    pass
            if pr["pop_time_best"] is not None:
                try:
                    pop_best_vals.append(float(pr["pop_time_best"]))
                except (TypeError, ValueError):
                    pass

        period_label = str(season_label or f"{date.today().year} YTD")
        unified = {
            "avg": hitting.get("AVG"),
            "obp": hitting.get("OBP"),
            "slg": hitting.get("SLG"),
            "ops": hitting.get("OPS"),
            "k_rate": season_metrics.get("K_RATE"),
            "bb_rate": season_metrics.get("BB_RATE"),
            "cs_pct": catching.get("CS%"),
            "pb_rate": catching.get("PB Rate"),
            "transfer_avg": (sum(transfer_vals) / len(transfer_vals)) if transfer_vals else None,
            "transfer_best": min(transfer_vals) if transfer_vals else None,
            "pop_avg": (sum(pop_avg_vals) / len(pop_avg_vals)) if pop_avg_vals else None,
            "pop_best": min(pop_best_vals) if pop_best_vals else None,
            "totals": {
                "ab": totals.get("ab"),
                "h": totals.get("h"),
                "bb": totals.get("bb"),
                "so": totals.get("so"),
                "sb_allowed": totals.get("sb_allowed"),
                "cs_caught": totals.get("cs_caught"),
                "passed_balls": totals.get("passed_balls"),
                "innings_caught": totals.get("innings_caught"),
            },
        }
        start_date = str(rows[-1]["date"]) if rows else None
        end_date = str(rows[0]["date"]) if rows else None
        self.db.upsert_stat_timeline_point(
            player_id=player_id,
            source_type="game_aggregate",
            source_id=None,
            period_label=period_label,
            start_date=start_date,
            end_date=end_date,
            metrics=unified,
        )

    def rebuild_all_timeline_points_for_player(self, player_id: int) -> None:
        summaries = self.db.get_season_summaries(player_id)
        for row in summaries:
            self._upsert_timeline_from_season_summary_row(dict(row))
        seasons = self.db.get_seasons_for_player(player_id)
        for season_label in seasons:
            self.rebuild_game_aggregate_timeline(player_id, season_label)

    def _on_trends_controls_changed(self, _event: tk.Event | None = None) -> None:
        self.refresh_trends_chart()

    def refresh_teams(self) -> None:
        teams = self.db.get_teams()
        display = []
        self.team_name_to_id = {}
        for t in teams:
            label = f"{t['name']} (#{t['id']})"
            display.append(label)
            self.team_name_to_id[label] = int(t["id"])

        if hasattr(self, "active_team_combo"):
            self.active_team_combo["values"] = display
        if hasattr(self, "player_team_combo"):
            self.player_team_combo["values"] = ["Unassigned", *display]

        if self.active_team_id is not None:
            for label, tid in self.team_name_to_id.items():
                if tid == self.active_team_id:
                    self.active_team_var.set(label)
                    break
        elif display:
            self.active_team_var.set(display[0])
            self.active_team_id = self.team_name_to_id[display[0]]
        else:
            self.active_team_var.set("No team")
            self.active_team_id = None

        self.refresh_team_players_list()
        self.refresh_team_dashboard()

    def _on_active_team_selected(self, _event: tk.Event) -> None:
        selected = self.active_team_var.get()
        self.active_team_id = self.team_name_to_id.get(selected)
        self.refresh_team_players_list()
        self.refresh_team_dashboard()

    def create_team(self) -> None:
        name = self.new_team_name_var.get().strip()
        if not name:
            messagebox.showerror("Validation", "Team name is required.")
            return
        try:
            team_id = self.db.create_team(name)
        except Exception as err:
            messagebox.showerror("Create Team Failed", f"Unable to create team: {err}")
            return
        self.active_team_id = team_id
        self.new_team_name_var.set("")
        self.refresh_teams()
        messagebox.showinfo("Saved", "Team created.")

    def assign_selected_player_to_active_team(self) -> None:
        if not self.active_team_id:
            messagebox.showerror("No Team", "Select or create a team first.")
            return
        selected_player = self.team_assign_player_var.get()
        player_id = self.assign_player_name_to_id.get(selected_player)
        if not player_id:
            messagebox.showerror("No Player", "Select a player to assign.")
            return
        self.db.assign_player_to_team(player_id, self.active_team_id)
        self.refresh_players()
        messagebox.showinfo("Updated", "Player assigned to team.")

    def refresh_team_players_list(self) -> None:
        if not hasattr(self, "team_players_tree"):
            return
        for iid in self.team_players_tree.get_children():
            self.team_players_tree.delete(iid)
        if not self.active_team_id:
            return
        rows = self.db.get_players_for_team(self.active_team_id)
        for r in rows:
            self.team_players_tree.insert(
                "",
                tk.END,
                iid=str(r["id"]),
                values=(r["name"], r["position"], r["level"] or "-"),
            )

    def _activate_player_from_team_dashboard(self, _event: tk.Event) -> None:
        selected = self.team_dashboard_tree.selection()
        if not selected:
            return
        player_id = int(selected[0])
        self.active_player_id = player_id
        self.refresh_players()
        self.notebook.select(self.dashboard_tab)

    def _update_player_details(self, player_id: int) -> None:
        player = self.db.get_player(player_id)
        if not player:
            self.player_details_var.set("No player selected")
            self.dashboard_player_var.set("No active player")
            return

        team_name = "-"
        if player["team_id"]:
            team = self.db.get_team(int(player["team_id"]))
            if team:
                team_name = str(team["name"])

        details = (
            f"Name: {player['name']} | Number: {player['number'] or '-'} | Position: {player['position']} | "
            f"Bats: {player['bats'] or '-'} | Throws: {player['throws'] or '-'} | Level: {player['level'] or '-'} | Team: {team_name}"
        )
        self.player_details_var.set(details)
        self.dashboard_player_var.set(f"Dashboard for {player['name']}")

    def _team_id_from_form(self) -> int | None:
        label = self.player_form_vars["team"].get()
        if not label or label == "Unassigned":
            return None
        return self.team_name_to_id.get(label)

    def _team_label_from_id(self, team_id: int | None) -> str:
        if not team_id:
            return "Unassigned"
        for label, tid in self.team_name_to_id.items():
            if tid == int(team_id):
                return label
        team = self.db.get_team(int(team_id))
        if not team:
            return "Unassigned"
        label = f"{team['name']} (#{team['id']})"
        self.team_name_to_id[label] = int(team["id"])
        return label

    def create_player(self) -> None:
        name = self.player_form_vars["name"].get().strip()
        position = self.player_form_vars["position"].get().strip()
        if not name or not position:
            messagebox.showerror("Validation", "Name and Position are required.")
            return

        player_id = self.db.add_player(
            name,
            self.player_form_vars["number"].get().strip(),
            self._team_id_from_form(),
            position,
            self.player_form_vars["bats"].get().strip(),
            self.player_form_vars["throws"].get().strip(),
            self.player_form_vars["level"].get().strip(),
        )
        self.active_player_id = player_id
        self.refresh_players()
        messagebox.showinfo("Saved", "Player created.")

    def load_active_into_form(self) -> None:
        if not self.active_player_id:
            messagebox.showwarning("No Player", "Select or create a player first.")
            return
        player = self.db.get_player(self.active_player_id)
        if not player:
            messagebox.showwarning("No Player", "Active player not found.")
            return

        self.player_form_vars["name"].set(player["name"])
        self.player_form_vars["number"].set(player["number"] or "")
        self.player_form_vars["team"].set(self._team_label_from_id(player["team_id"]))
        self.player_form_vars["position"].set(player["position"])
        self.player_form_vars["bats"].set(player["bats"] or "")
        self.player_form_vars["throws"].set(player["throws"] or "")
        self.player_form_vars["level"].set(player["level"] or "")

    def update_active_player(self) -> None:
        if not self.active_player_id:
            messagebox.showwarning("No Player", "Select or create a player first.")
            return

        name = self.player_form_vars["name"].get().strip()
        position = self.player_form_vars["position"].get().strip()
        if not name or not position:
            messagebox.showerror("Validation", "Name and Position are required.")
            return

        self.db.update_player(
            self.active_player_id,
            name,
            self.player_form_vars["number"].get().strip(),
            self._team_id_from_form(),
            position,
            self.player_form_vars["bats"].get().strip(),
            self.player_form_vars["throws"].get().strip(),
            self.player_form_vars["level"].get().strip(),
        )
        self.refresh_players()
        messagebox.showinfo("Updated", "Player updated.")

    def _parse_int(self, value: str, field_name: str) -> int:
        try:
            parsed = int(value)
            if parsed < 0:
                raise ValueError
            return parsed
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a non-negative integer") from exc

    def _parse_float(self, value: str, field_name: str) -> float:
        try:
            parsed = float(value)
            if parsed < 0:
                raise ValueError
            return parsed
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a non-negative number") from exc

    def _validate_date(self, value: str) -> bool:
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False

    def _import_cv2(self) -> Any:
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("OpenCV is not installed. Install with: pip install opencv-python") from exc
        return cv2

    def _format_seconds(self, value: float | None) -> str:
        return "—" if value is None else f"{value:.3f}s"

    def _video_release_capture(self) -> None:
        if self.video_capture is not None:
            try:
                self.video_capture.release()
            except Exception:
                pass
        self.video_capture = None
        self.video_is_playing = False
        if self.video_play_after_id:
            self.root.after_cancel(self.video_play_after_id)
            self.video_play_after_id = None

    def _video_set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in [
            self.video_btn_play,
            self.video_btn_step_back,
            self.video_btn_step_fwd,
            self.video_btn_mark_catch,
            self.video_btn_mark_release,
            self.video_btn_mark_target,
            self.video_btn_calc,
            self.video_btn_save_practice,
            self.video_btn_add_rep,
            self.video_btn_clear_markers,
            self.video_btn_delete_rep,
            self.video_btn_clear_reps,
            self.video_btn_auto_detect,
            self.video_btn_auto_build,
            self.video_btn_set_roi,
            self.video_btn_clear_roi,
        ]:
            btn.configure(state=state)
        self.video_timeline.configure(state=state)
        self._apply_metric_mode_controls()

    def load_video_file(self) -> None:
        print("[StatForge] Load Video clicked")
        filepath = filedialog.askopenfilename(
            parent=self.root,
            title="Load Video",
            filetypes=[
                ("Video Files", "*.mov *.mp4 *.m4v"),
                ("MOV", "*.mov"),
                ("MP4", "*.mp4"),
                ("M4V", "*.m4v"),
            ],
        )
        if not filepath:
            print("[StatForge] Load Video canceled")
            return
        print(f"[StatForge] Selected video path: {filepath}")

        try:
            from video.video_loader import load_video_metadata
            metadata = load_video_metadata(filepath)
        except Exception as exc:
            print(f"[StatForge] Video metadata load failed: {exc}")
            messagebox.showerror("Video Load Error", str(exc))
            return

        cv2 = self._import_cv2()
        self._video_release_capture()
        cap = cv2.VideoCapture(str(Path(filepath)), cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(str(Path(filepath)))
        if not cap.isOpened():
            print("[StatForge] VideoCapture open failed for selected file")
            messagebox.showerror("Video Load Error", "Unable to open video stream.")
            return

        self.video_path = filepath
        self.video_capture = cap
        self.video_fps = float(metadata["fps"])
        self.video_frame_count = int(metadata["frame_count"])
        self.video_duration = float(metadata["duration"])
        self.video_source_width = int(metadata.get("width", 0) or 0)
        self.video_source_height = int(metadata.get("height", 0) or 0)
        self.video_current_time = 0.0
        self.video_last_frame_time = None
        self.video_last_frame_bgr = None
        self.video_marker_catch = None
        self.video_marker_release = None
        self.video_marker_target = None
        self.video_last_transfer = None
        self.video_last_throw = None
        self.video_last_pop = None
        self.rep_marks = []
        self.video_roi_select_mode = False
        self.video_roi_drag_start = None
        if self.video_roi_drag_rect_id is not None:
            self.video_canvas_label.delete(self.video_roi_drag_rect_id)
            self.video_roi_drag_rect_id = None
        resolved_video_path = str(Path(filepath).resolve())
        self.custom_roi_norm = self.video_roi_by_path.get(resolved_video_path)
        if self.custom_roi_norm is not None:
            self.video_roi_preset_var.set("Custom")
        else:
            if self.video_roi_preset_var.get() == "Custom":
                self.video_roi_preset_var.set("Auto")
            self.video_roi_label_var.set("ROI: Auto")
        self.video_btn_play.configure(text="Play")
        self.video_timeline.configure(to=max(self.video_duration, 0.001))
        self.video_updating_timeline = True
        self.video_timeline_var.set(0.0)
        self.video_updating_timeline = False
        self._video_set_controls_enabled(True)
        self._reset_video_results()
        self._refresh_rep_list()
        self._video_seek_and_render(0.0)
        self._update_roi_label()

    def _on_video_timeline_changed(self, value: str) -> None:
        if self.video_updating_timeline:
            return
        if self.video_capture is None:
            return
        try:
            self.video_pending_scrub_time = float(value)
        except ValueError:
            return
        if self.video_scrub_after_id:
            self.root.after_cancel(self.video_scrub_after_id)
        self.video_scrub_after_id = self.root.after(40, self._apply_video_scrub)

    def _apply_video_scrub(self) -> None:
        self.video_scrub_after_id = None
        if self.video_pending_scrub_time is None:
            return
        self._video_seek_and_render(self.video_pending_scrub_time)
        self.video_pending_scrub_time = None

    def _video_seek_and_render(self, time_seconds: float) -> None:
        if self.video_capture is None:
            return
        cv2 = self._import_cv2()
        clamped = max(0.0, min(float(time_seconds), max(self.video_duration, 0.0)))
        if self.video_last_frame_time is not None and abs(clamped - self.video_last_frame_time) < 0.0005:
            frame = self.video_last_frame_bgr
        else:
            self.video_capture.set(cv2.CAP_PROP_POS_MSEC, clamped * 1000.0)
            ok, frame = self.video_capture.read()
            if not ok or frame is None:
                return
            self.video_last_frame_time = clamped
            self.video_last_frame_bgr = frame

        self.video_current_time = clamped
        self._render_video_frame(frame)
        self.video_updating_timeline = True
        self.video_timeline_var.set(clamped)
        self.video_updating_timeline = False
        frame_num = int(round(clamped * self.video_fps)) if self.video_fps > 0 else 0
        self.video_time_var.set(f"Time: {clamped:.3f}s | Frame: {frame_num}")

    def _render_video_frame(self, frame_bgr: Any) -> None:
        cv2 = self._import_cv2()
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        max_w, max_h = 860, 480
        h, w = rgb.shape[:2]
        self.video_source_width = w
        self.video_source_height = h
        scale = min(max_w / w, max_h / h, 1.0)
        display_w, display_h = w, h
        if scale < 1.0:
            display_w = int(w * scale)
            display_h = int(h * scale)
            rgb = cv2.resize(rgb, (display_w, display_h), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        if not ok:
            return
        encoded = base64.b64encode(buf.tobytes()).decode("ascii")
        self.video_photo = tk.PhotoImage(data=encoded)
        canvas_w = max(1, int(self.video_canvas_label.winfo_width()))
        canvas_h = max(1, int(self.video_canvas_label.winfo_height()))
        offset_x = max(0, (canvas_w - display_w) // 2)
        offset_y = max(0, (canvas_h - display_h) // 2)
        self.video_image_offset = (offset_x, offset_y)
        self.video_display_width = display_w
        self.video_display_height = display_h

        self.video_canvas_label.delete("all")
        self.video_canvas_label.create_image(offset_x, offset_y, image=self.video_photo, anchor="nw", tags="frame")
        self._draw_custom_roi_overlay()

    def toggle_video_playback(self) -> None:
        if self.video_capture is None:
            return
        self.video_is_playing = not self.video_is_playing
        self.video_btn_play.configure(text="Pause" if self.video_is_playing else "Play")
        if self.video_is_playing:
            self._video_play_loop()

    def _video_play_loop(self) -> None:
        if not self.video_is_playing or self.video_capture is None:
            return
        step = 1.0 / self.video_fps if self.video_fps > 0 else 1.0 / 30.0
        next_time = self.video_current_time + step
        if next_time >= self.video_duration:
            self.video_is_playing = False
            self.video_btn_play.configure(text="Play")
            self._video_seek_and_render(self.video_duration)
            return
        self._video_seek_and_render(next_time)
        delay_ms = max(10, int(step * 1000))
        self.video_play_after_id = self.root.after(delay_ms, self._video_play_loop)

    def step_video_frame(self, direction: int) -> None:
        if self.video_capture is None:
            return
        if self.video_is_playing:
            self.video_is_playing = False
            self.video_btn_play.configure(text="Play")
        step = 1.0 / self.video_fps if self.video_fps > 0 else 1.0 / 30.0
        self._video_seek_and_render(self.video_current_time + (step * direction))

    def mark_video_time(self, marker: str) -> None:
        t = float(self.video_current_time)
        self.video_last_transfer = None
        self.video_last_throw = None
        self.video_last_pop = None
        self.video_result_transfer_var.set("Transfer Time: —")
        self.video_result_throw_var.set("Throw Time: —")
        self.video_result_pop_var.set("Total Pop Time: —")
        if marker == "catch":
            self.video_marker_catch = t
            self.video_result_catch_var.set(f"Catch Time: {self._format_seconds(t)}")
        elif marker == "release":
            self.video_marker_release = t
            self.video_result_release_var.set(f"Release Time: {self._format_seconds(t)}")
        elif marker == "target":
            self.video_marker_target = t

    def _reset_video_results(self) -> None:
        self.video_result_catch_var.set("Catch Time: —")
        self.video_result_release_var.set("Release Time: —")
        self.video_result_transfer_var.set("Transfer Time: —")
        self.video_result_throw_var.set("Throw Time: —")
        self.video_result_pop_var.set("Total Pop Time: —")
        self.video_last_transfer = None
        self.video_last_throw = None
        self.video_last_pop = None
        self.video_detect_conf_var.set("Detect Conf: Catch — | Release —")
        self.video_current_rep_var.set(f"Current Rep: {len(self.rep_marks)+1} of {len(self.rep_marks)}")

    def _parse_release_window_seconds(self) -> float:
        raw = self.video_release_window_var.get().strip()
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError("Release End (s) must be a valid number.") from exc
        if value <= 0 or value > 3.0:
            raise ValueError("Release End (s) must be > 0 and <= 3.0.")
        return value

    def _parse_batch_max_reps(self) -> int:
        raw = self.video_batch_max_reps_var.get().strip()
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError("Max Reps must be an integer.") from exc
        if value <= 0 or value > 50:
            raise ValueError("Max Reps must be between 1 and 50.")
        return value

    def _parse_batch_min_spacing(self) -> float:
        raw = self.video_batch_min_spacing_var.get().strip()
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError("Min Catch Spacing (s) must be a valid number.") from exc
        if value < 0.1 or value > 10.0:
            raise ValueError("Min Catch Spacing (s) must be between 0.1 and 10.0.")
        return value

    def _parse_confidence_threshold(self) -> float:
        raw = self.video_batch_conf_threshold_var.get().strip()
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError("Confidence Threshold must be a valid number.") from exc
        if value < 0.0 or value > 1.0:
            raise ValueError("Confidence Threshold must be between 0.0 and 1.0.")
        return value

    def _parse_estimated_flight_seconds(self) -> float:
        raw = self.video_est_flight_var.get().strip()
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError("Estimated Flight Time (s) must be a valid number.") from exc
        if value < 0.0 or value > 5.0:
            raise ValueError("Estimated Flight Time (s) must be between 0.0 and 5.0.")
        return value

    def _get_metric_mode_key(self) -> str:
        label = self.video_metric_mode_var.get().strip()
        if label.startswith("Full Pop"):
            return "full_pop"
        if label.startswith("Estimated Pop"):
            return "estimated_pop"
        return "transfer"

    def _metric_mode_note_label(self, mode_key: str) -> str:
        if mode_key == "full_pop":
            return "Full Pop"
        if mode_key == "estimated_pop":
            return "Estimated Pop"
        return "Transfer"

    def _apply_metric_mode_controls(self) -> None:
        mode = self._get_metric_mode_key() if hasattr(self, "video_metric_mode_var") else "transfer"
        controls_enabled = self.video_capture is not None

        if mode == "full_pop":
            self.video_est_flight_entry.configure(state=tk.DISABLED)
            self.video_btn_mark_target.configure(state=tk.NORMAL if controls_enabled else tk.DISABLED)
        else:
            self.video_est_flight_entry.configure(state=tk.NORMAL if mode == "estimated_pop" else tk.DISABLED)
            self.video_marker_target = None
            # Keep target marker intentionally disabled outside full pop mode.
            self.video_btn_mark_target.configure(state=tk.DISABLED)

    def _on_metric_mode_changed(self, _event: tk.Event | None = None) -> None:
        self._apply_metric_mode_controls()

    def _get_roi_preset(self) -> str:
        preset = self.video_roi_preset_var.get().strip()
        if preset in {"Auto", "Lower Middle", "Lower Left", "Lower Right", "Custom"}:
            return preset
        return "Auto"

    def _on_roi_preset_changed(self, _event: tk.Event | None = None) -> None:
        if self.video_roi_preset_var.get() == "Custom" and self.custom_roi_norm is None:
            self.video_roi_preset_var.set("Auto")
            self.video_roi_label_var.set("ROI: Auto")
            messagebox.showinfo("ROI", "No custom ROI is set. Click Set ROI to draw one.")
        self._update_roi_label()
        self._draw_custom_roi_overlay()

    def _update_roi_label(self) -> None:
        if self.custom_roi_norm is None:
            self.video_roi_label_var.set("ROI: Auto")
            return
        if self.video_source_width <= 0 or self.video_source_height <= 0:
            self.video_roi_label_var.set("ROI: Custom")
            return
        x1 = int(self.custom_roi_norm[0] * self.video_source_width)
        y1 = int(self.custom_roi_norm[1] * self.video_source_height)
        x2 = int(self.custom_roi_norm[2] * self.video_source_width)
        y2 = int(self.custom_roi_norm[3] * self.video_source_height)
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        self.video_roi_label_var.set(f"ROI: x={x1}, y={y1}, w={w}, h={h}")

    def start_roi_selection(self) -> None:
        if self.video_capture is None:
            messagebox.showwarning("No Video", "Load a video first.")
            return
        self.video_roi_select_mode = True
        self.video_roi_drag_start = None
        if self.video_roi_drag_rect_id is not None:
            self.video_canvas_label.delete(self.video_roi_drag_rect_id)
            self.video_roi_drag_rect_id = None
        self.video_roi_label_var.set("ROI: Draw rectangle on video")

    def clear_custom_roi(self) -> None:
        self.custom_roi_norm = None
        self.video_roi_select_mode = False
        self.video_roi_drag_start = None
        if self.video_path:
            self.video_roi_by_path.pop(str(Path(self.video_path).resolve()), None)
        if self.video_roi_drag_rect_id is not None:
            self.video_canvas_label.delete(self.video_roi_drag_rect_id)
            self.video_roi_drag_rect_id = None
        if self.video_roi_preset_var.get() == "Custom":
            self.video_roi_preset_var.set("Auto")
        self._update_roi_label()
        self._draw_custom_roi_overlay()

    def _norm_from_canvas_xy(self, x: int, y: int) -> tuple[float, float] | None:
        if self.video_display_width <= 0 or self.video_display_height <= 0:
            return None
        ox, oy = self.video_image_offset
        rx = (x - ox) / float(self.video_display_width)
        ry = (y - oy) / float(self.video_display_height)
        if rx < 0.0 or ry < 0.0 or rx > 1.0 or ry > 1.0:
            return None
        return max(0.0, min(1.0, rx)), max(0.0, min(1.0, ry))

    def _norm_from_canvas_xy_clamped(self, x: int, y: int) -> tuple[float, float] | None:
        if self.video_display_width <= 0 or self.video_display_height <= 0:
            return None
        ox, oy = self.video_image_offset
        rx = (x - ox) / float(self.video_display_width)
        ry = (y - oy) / float(self.video_display_height)
        return max(0.0, min(1.0, rx)), max(0.0, min(1.0, ry))

    def _on_video_roi_mouse_down(self, event: tk.Event) -> None:
        if not self.video_roi_select_mode:
            return
        norm = self._norm_from_canvas_xy(int(event.x), int(event.y))
        if norm is None:
            return
        self.video_roi_drag_start = (int(event.x), int(event.y))
        if self.video_roi_drag_rect_id is not None:
            self.video_canvas_label.delete(self.video_roi_drag_rect_id)
        self.video_roi_drag_rect_id = self.video_canvas_label.create_rectangle(
            int(event.x),
            int(event.y),
            int(event.x),
            int(event.y),
            outline=Theme.ACCENT,
            width=2,
            dash=(4, 2),
        )

    def _on_video_roi_mouse_drag(self, event: tk.Event) -> None:
        if not self.video_roi_select_mode or self.video_roi_drag_start is None:
            return
        if self.video_roi_drag_rect_id is None:
            return
        x0, y0 = self.video_roi_drag_start
        self.video_canvas_label.coords(self.video_roi_drag_rect_id, x0, y0, int(event.x), int(event.y))

    def _on_video_roi_mouse_up(self, event: tk.Event) -> None:
        if not self.video_roi_select_mode or self.video_roi_drag_start is None:
            return
        x0, y0 = self.video_roi_drag_start
        x1, y1 = int(event.x), int(event.y)
        start_norm = self._norm_from_canvas_xy(x0, y0)
        end_norm = self._norm_from_canvas_xy_clamped(x1, y1)
        self.video_roi_drag_start = None
        if self.video_roi_drag_rect_id is not None:
            self.video_canvas_label.delete(self.video_roi_drag_rect_id)
            self.video_roi_drag_rect_id = None
        if start_norm is None or end_norm is None:
            self.video_roi_select_mode = False
            self._update_roi_label()
            return
        nx1, ny1 = start_norm
        nx2, ny2 = end_norm
        left = min(nx1, nx2)
        top = min(ny1, ny2)
        right = max(nx1, nx2)
        bottom = max(ny1, ny2)
        if right - left < 0.01 or bottom - top < 0.01:
            messagebox.showwarning("ROI", "Selected ROI is too small. Please draw a larger box.")
            self.video_roi_select_mode = False
            self._update_roi_label()
            return
        self.custom_roi_norm = (left, top, right, bottom)
        if self.video_path:
            self.video_roi_by_path[str(Path(self.video_path).resolve())] = self.custom_roi_norm
        self.video_roi_preset_var.set("Custom")
        self.video_roi_select_mode = False
        self._update_roi_label()
        self._draw_custom_roi_overlay()

    def _draw_custom_roi_overlay(self) -> None:
        self.video_canvas_label.delete("roi_overlay")
        if self.custom_roi_norm is None:
            return
        if self.video_display_width <= 0 or self.video_display_height <= 0:
            return
        ox, oy = self.video_image_offset
        x1 = ox + int(self.custom_roi_norm[0] * self.video_display_width)
        y1 = oy + int(self.custom_roi_norm[1] * self.video_display_height)
        x2 = ox + int(self.custom_roi_norm[2] * self.video_display_width)
        y2 = oy + int(self.custom_roi_norm[3] * self.video_display_height)
        self.video_canvas_label.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            outline=Theme.ACCENT,
            width=2,
            tags="roi_overlay",
        )

    def _get_motion_roi_arg(self) -> tuple[float, float, float, float] | str:
        if self.custom_roi_norm is not None and self.video_roi_preset_var.get() == "Custom":
            return self.custom_roi_norm
        return self._get_roi_preset()

    def _cached_wav_path_for_video(self, video_path: str) -> Path:
        cache_dir = Path(tempfile.gettempdir()) / "statforge_audio_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(video_path.encode("utf-8")).hexdigest()[:12]
        return cache_dir / f"{Path(video_path).stem}_{digest}.wav"

    def _ensure_audio_wav_for_video(self, video_path: str) -> Path | None:
        try:
            from video.audio_tools import extract_audio_wav
        except Exception:
            return None

        wav_path = self.video_audio_cache.get(video_path) or self._cached_wav_path_for_video(video_path)
        self.video_audio_cache[video_path] = wav_path

        should_extract = not wav_path.exists()
        if wav_path.exists():
            try:
                should_extract = wav_path.stat().st_mtime < Path(video_path).stat().st_mtime
            except OSError:
                should_extract = True
        if should_extract:
            ok = extract_audio_wav(video_path, wav_path)
            if not ok:
                return None
        return wav_path

    def auto_detect_video_markers(self) -> None:
        if not self.video_path or self.video_capture is None:
            messagebox.showerror("No Video", "Load a video first.")
            return

        try:
            release_window_sec = self._parse_release_window_seconds()
        except ValueError as exc:
            messagebox.showerror("Validation", str(exc))
            return
        roi_arg = self._get_motion_roi_arg()

        try:
            from video.audio_tools import detect_catch_time_from_audio
            from video.motion_tools import detect_release_time_by_motion
        except Exception as exc:
            messagebox.showerror("Auto Detect Error", f"Auto detect modules failed to load: {exc}")
            return

        video_path = str(Path(self.video_path).resolve())
        wav_path = self._ensure_audio_wav_for_video(video_path)
        if wav_path is None:
            messagebox.showerror(
                "Auto Detect",
                "FFmpeg audio extraction failed. Install ffmpeg or choose manual.",
            )
            return

        try:
            catch_result = detect_catch_time_from_audio(wav_path)
            catch_time = float(catch_result["catch_time"])
            catch_conf = float(catch_result.get("confidence", 0.0))
        except Exception as exc:
            messagebox.showerror("Auto Detect Error", f"Catch detection failed: {exc}")
            return

        try:
            release_result = detect_release_time_by_motion(
                video_path,
                catch_time=catch_time,
                roi=roi_arg,
                release_window_sec=release_window_sec,
            )
            release_time = float(release_result["release_time"])
            release_conf = float(release_result.get("confidence", 0.0))
        except Exception as exc:
            messagebox.showerror("Auto Detect Error", f"Release detection failed: {exc}")
            return

        self.video_marker_catch = catch_time
        self.video_marker_release = release_time
        self.video_result_catch_var.set(f"Catch Time: {self._format_seconds(catch_time)}")
        self.video_result_release_var.set(f"Release Time: {self._format_seconds(release_time)}")
        self.video_result_transfer_var.set("Transfer Time: —")
        self.video_result_throw_var.set("Throw Time: —")
        self.video_result_pop_var.set("Total Pop Time: —")
        self.video_last_transfer = None
        self.video_last_throw = None
        self.video_last_pop = None
        self.video_detect_conf_var.set(
            f"Detect Conf: Catch {catch_conf:.2f} | Release {release_conf:.2f}"
        )
        self._video_seek_and_render(catch_time)

        if catch_conf < 0.35 or release_conf < 0.35:
            messagebox.showwarning(
                "Auto Detect",
                "Auto-detected markers were applied with low confidence. Please verify manually.",
            )

    def auto_build_rep_set(self) -> None:
        if not self.video_path or self.video_capture is None:
            messagebox.showerror("No Video", "Load a video first.")
            return
        try:
            max_reps = self._parse_batch_max_reps()
            min_spacing = self._parse_batch_min_spacing()
            release_window_sec = self._parse_release_window_seconds()
            conf_threshold = self._parse_confidence_threshold()
        except ValueError as exc:
            messagebox.showerror("Validation", str(exc))
            return

        metric_mode = self._get_metric_mode_key()
        if metric_mode == "full_pop":
            messagebox.showwarning(
                "Auto Build",
                "Full Pop mode requires Target markers. Use Transfer or Estimated Pop for auto-build.",
            )
            return
        est_flight = None
        if metric_mode == "estimated_pop":
            try:
                est_flight = self._parse_estimated_flight_seconds()
            except ValueError as exc:
                messagebox.showerror("Validation", str(exc))
                return

        roi_arg = self._get_motion_roi_arg()
        try:
            from video.audio_tools import detect_catch_candidates_from_audio
            from video.motion_tools import detect_release_time_by_motion
        except Exception as exc:
            messagebox.showerror("Auto Build Error", f"Auto detect modules failed to load: {exc}")
            return

        video_path = str(Path(self.video_path).resolve())
        wav_path = self._ensure_audio_wav_for_video(video_path)
        if wav_path is None:
            messagebox.showerror(
                "Auto Detect",
                "FFmpeg audio extraction failed. Install ffmpeg or choose manual.",
            )
            return

        try:
            catch_result = detect_catch_candidates_from_audio(
                wav_path,
                max_reps=max_reps,
                min_spacing_seconds=min_spacing,
            )
            catch_candidates = list(catch_result.get("candidates", []))
        except Exception as exc:
            messagebox.showerror("Auto Build Error", f"Catch detection failed: {exc}")
            return

        if not catch_candidates:
            self.video_set_build_summary_var.set("Build Summary: Found 0 / Kept 0 / Dropped 0")
            messagebox.showwarning("Auto Build", "No catch events found.")
            return

        new_reps: list[RepMark] = []
        dropped = 0
        for cand in catch_candidates:
            catch_time = float(cand.get("time", 0.0))
            catch_conf = float(cand.get("confidence", 0.0))
            try:
                release_result = detect_release_time_by_motion(
                    video_path,
                    catch_time=catch_time,
                    roi=roi_arg,
                    release_window_sec=release_window_sec,
                )
            except Exception:
                dropped += 1
                continue

            release_time = float(release_result.get("release_time", 0.0))
            release_conf = float(release_result.get("confidence", 0.0))
            if release_time <= catch_time:
                dropped += 1
                continue
            if catch_conf < conf_threshold or release_conf < conf_threshold:
                dropped += 1
                continue

            transfer = release_time - catch_time
            pop_total = transfer if metric_mode == "transfer" else transfer + float(est_flight or 0.0)
            new_reps.append(
                RepMark(
                    catch_time=catch_time,
                    release_time=release_time,
                    target_time=None,
                    metric_mode=metric_mode,
                    transfer=transfer,
                    pop_total=pop_total,
                    estimated_flight=est_flight,
                    catch_conf=catch_conf,
                    release_conf=release_conf,
                )
            )

        if not new_reps:
            self.video_set_build_summary_var.set(
                f"Build Summary: Found {len(catch_candidates)} / Kept 0 / Dropped {len(catch_candidates)}"
            )
            messagebox.showwarning("Auto Build", "No valid reps passed confidence/sanity checks.")
            return

        self.rep_marks = new_reps
        self._refresh_rep_list()
        self.video_set_build_summary_var.set(
            f"Build Summary: Found {len(catch_candidates)} / Kept {len(new_reps)} / Dropped {dropped}"
        )

        first = self.rep_marks[0]
        self.rep_tree.selection_set("1")
        self.rep_tree.focus("1")
        self.video_marker_catch = first.catch_time
        self.video_marker_release = first.release_time
        self.video_marker_target = None
        self.video_result_catch_var.set(f"Catch Time: {self._format_seconds(first.catch_time)}")
        self.video_result_release_var.set(f"Release Time: {self._format_seconds(first.release_time)}")
        self.video_result_transfer_var.set(f"Transfer Time: {self._format_seconds(first.transfer)}")
        if first.metric_mode == "estimated_pop":
            self.video_result_throw_var.set(f"Estimated Flight: {self._format_seconds(first.estimated_flight)}")
            self.video_result_pop_var.set(f"Estimated Total Pop: {self._format_seconds(first.pop_total)}")
        else:
            self.video_result_throw_var.set("Throw Time: —")
            self.video_result_pop_var.set(f"Total Pop Time: {self._format_seconds(first.pop_total)}")
        self.video_detect_conf_var.set(
            f"Detect Conf: Catch {float(first.catch_conf or 0.0):.2f} | Release {float(first.release_conf or 0.0):.2f}"
        )
        self._video_seek_and_render(first.catch_time)

    def _validate_current_rep(self, show_error: bool = True) -> RepMark | None:
        catch = self.video_marker_catch
        release = self.video_marker_release
        target = self.video_marker_target
        mode = self._get_metric_mode_key()
        if catch is None or release is None:
            if show_error:
                messagebox.showerror("Missing Markers", "Set Catch and Release markers first.")
            return None
        if release <= catch:
            if show_error:
                messagebox.showerror("Invalid Markers", "Release must be after Catch.")
            return None
        if mode == "full_pop" and target is not None and target <= release:
            if show_error:
                messagebox.showerror("Invalid Markers", "Target Catch must be after Release.")
            return None

        estimated_flight: float | None = None
        if mode == "estimated_pop":
            try:
                estimated_flight = self._parse_estimated_flight_seconds()
            except ValueError as exc:
                if show_error:
                    messagebox.showerror("Validation", str(exc))
                return None
        if mode == "full_pop" and target is None:
            if show_error:
                messagebox.showerror("Missing Marker", "Full Pop mode requires Target Catch marker.")
            return None
        try:
            pop_result = calculate_pop_metrics(
                catch_time=float(catch),
                release_time=float(release),
                target_time=None if mode != "full_pop" else float(target) if target is not None else None,
                metric_mode=mode,
                estimated_flight=estimated_flight,
            )
        except ValueError as exc:
            if show_error:
                messagebox.showerror("Validation", str(exc))
            return None
        transfer = float(pop_result["transfer"])
        pop_total = float(pop_result["pop_total"])
        if mode != "full_pop":
            target = None

        return RepMark(
            catch_time=catch,
            release_time=release,
            target_time=target,
            metric_mode=mode,
            transfer=transfer,
            pop_total=pop_total,
            estimated_flight=estimated_flight,
        )

    def clear_current_markers(self) -> None:
        self.video_marker_catch = None
        self.video_marker_release = None
        self.video_marker_target = None
        self._reset_video_results()

    def add_current_rep(self) -> None:
        rep = self._validate_current_rep(show_error=True)
        if rep is None:
            return
        self.rep_marks.append(rep)
        self._refresh_rep_list()
        self.clear_current_markers()
        messagebox.showinfo("Rep Added", f"Rep {len(self.rep_marks)} added.")

    def delete_selected_rep(self) -> None:
        selected = self.rep_tree.selection()
        if not selected:
            messagebox.showerror("Selection Required", "Select a rep to delete.")
            return
        idx = int(selected[0]) - 1
        if idx < 0 or idx >= len(self.rep_marks):
            return
        del self.rep_marks[idx]
        self._refresh_rep_list()

    def clear_all_reps(self) -> None:
        self.rep_marks.clear()
        self._refresh_rep_list()

    def _refresh_rep_list(self) -> None:
        for iid in self.rep_tree.get_children():
            self.rep_tree.delete(iid)

        for idx, rep in enumerate(self.rep_marks, start=1):
            catch_conf = "—" if rep.catch_conf is None else f"{rep.catch_conf:.2f}"
            release_conf = "—" if rep.release_conf is None else f"{rep.release_conf:.2f}"
            self.rep_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    str(idx),
                    f"{rep.catch_time:.3f}",
                    f"{rep.release_time:.3f}",
                    "—" if rep.target_time is None else f"{rep.target_time:.3f}",
                    f"{rep.transfer:.3f}",
                    f"{rep.pop_total:.3f}",
                    f"C={catch_conf} R={release_conf}",
                ),
            )

        self.video_current_rep_var.set(f"Current Rep: {len(self.rep_marks)+1} of {len(self.rep_marks)}")
        self._refresh_set_summary()

    def _refresh_set_summary(self) -> None:
        self.video_set_reps_var.set(f"Reps: {len(self.rep_marks)}")
        self.video_reps_var.set(str(len(self.rep_marks) if self.rep_marks else 1))
        if not self.rep_marks:
            self.video_set_best_transfer_var.set("Best Transfer: —")
            self.video_set_avg_transfer_var.set("Avg Transfer: —")
            self.video_set_best_pop_var.set("Best Pop: —")
            self.video_set_avg_pop_var.set("Avg Pop: —")
            self.video_set_build_summary_var.set("Build Summary: —")
            return

        transfers = [r.transfer for r in self.rep_marks]
        pops = [r.pop_total for r in self.rep_marks]
        self.video_set_best_transfer_var.set(f"Best Transfer: {min(transfers):.3f}s")
        self.video_set_avg_transfer_var.set(f"Avg Transfer: {(sum(transfers)/len(transfers)):.3f}s")
        self.video_set_best_pop_var.set(f"Best Pop: {min(pops):.3f}s")
        self.video_set_avg_pop_var.set(f"Avg Pop: {(sum(pops)/len(pops)):.3f}s")

    def calculate_pop_time(self) -> None:
        rep = self._validate_current_rep(show_error=True)
        if rep is None:
            return
        throw: float | None = None
        if rep.metric_mode == "full_pop" and rep.target_time is not None:
            throw = rep.target_time - rep.release_time
        elif rep.metric_mode == "estimated_pop":
            throw = rep.estimated_flight

        self.video_last_transfer = rep.transfer
        self.video_last_throw = throw
        self.video_last_pop = rep.pop_total
        self.video_result_catch_var.set(f"Catch Time: {self._format_seconds(rep.catch_time)}")
        self.video_result_release_var.set(f"Release Time: {self._format_seconds(rep.release_time)}")
        self.video_result_transfer_var.set(f"Transfer Time: {self._format_seconds(rep.transfer)}")
        if rep.metric_mode == "estimated_pop":
            self.video_result_throw_var.set(f"Estimated Flight: {self._format_seconds(throw)}")
            self.video_result_pop_var.set(f"Estimated Total Pop: {self._format_seconds(rep.pop_total)}")
        elif rep.metric_mode == "full_pop":
            self.video_result_throw_var.set(f"Throw Time: {self._format_seconds(throw)}")
            self.video_result_pop_var.set(f"Total Pop Time: {self._format_seconds(rep.pop_total)}")
        else:
            self.video_result_throw_var.set("Throw Time: —")
            self.video_result_pop_var.set(f"Total Pop Time: {self._format_seconds(rep.pop_total)}")

    def _parse_optional_int(self, value: str, field_name: str) -> int | None:
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = int(raw)
            if parsed < 0:
                raise ValueError
            return parsed
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a non-negative integer") from exc

    def _parse_optional_float(self, value: str, field_name: str) -> float | None:
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = float(raw)
            if parsed < 0:
                raise ValueError
            return parsed
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a non-negative number") from exc

    def _on_filters_changed(self, _event: tk.Event | None = None) -> None:
        self.refresh_game_history()
        self.refresh_team_dashboard()
        self.refresh_dashboard()

    def _apply_filters(self) -> None:
        self._on_filters_changed()

    def _clear_filters(self) -> None:
        self.filter_start_date_var.set("")
        self.filter_end_date_var.set("")
        self._on_filters_changed()

    def _set_last_30_days(self) -> None:
        today = date.today()
        self.filter_end_date_var.set(today.isoformat())
        self.filter_start_date_var.set((today - timedelta(days=30)).isoformat())
        self._on_filters_changed()

    def _set_all_filters(self) -> None:
        self.filter_season_var.set("All")
        self.filter_start_date_var.set("")
        self.filter_end_date_var.set("")
        self._on_filters_changed()

    def refresh_dashboard_filter_options(self) -> None:
        if not self.active_player_id:
            values = ["All"]
            self.dashboard_season_combo["values"] = values
            self.game_history_season_combo["values"] = values
            if hasattr(self, "team_dash_season_combo"):
                self.team_dash_season_combo["values"] = values
            self.filter_season_var.set("All")
            self.refresh_baseline_summary_options()
            return

        seasons = self.db.get_seasons_for_player(self.active_player_id)
        values = ["All", *seasons]
        self.dashboard_season_combo["values"] = values
        self.game_history_season_combo["values"] = values
        if hasattr(self, "team_dash_season_combo"):
            self.team_dash_season_combo["values"] = values
        if self.filter_season_var.get() not in values:
            self.filter_season_var.set("All")

    def refresh_baseline_summary_options(self) -> None:
        if not hasattr(self, "baseline_summary_combo"):
            return
        player_id = self.active_player_id
        if not player_id:
            self.baseline_summary_id_to_row = {}
            self.baseline_summary_combo["values"] = ["None"]
            self.baseline_summary_var.set("None")
            return
        rows = self.db.get_season_summaries(player_id)
        self.baseline_summary_id_to_row = {int(r["id"]): dict(r) for r in rows}
        labels = ["None"]
        for r in rows:
            label = f"{r['season_label']} ({r['created_at']}) [#{r['id']}]"
            labels.append(label)
        self.baseline_summary_combo["values"] = labels
        if self.baseline_summary_var.get() not in labels:
            self.baseline_summary_var.set(labels[1] if len(labels) > 1 else "None")

    def _selected_baseline_summary(self) -> dict[str, Any] | None:
        label = self.baseline_summary_var.get().strip()
        if not label or label == "None":
            return None
        match = re.search(r"\[#(\d+)\]\s*$", label)
        if not match:
            return None
        summary_id = int(match.group(1))
        return self.baseline_summary_id_to_row.get(summary_id)

    def refresh_team_dashboard(self) -> None:
        if not hasattr(self, "team_dashboard_tree"):
            return
        for iid in self.team_dashboard_tree.get_children():
            self.team_dashboard_tree.delete(iid)

        if not self.active_team_id:
            self.team_dashboard_team_var.set("No active team")
            return

        team = self.db.get_team(self.active_team_id)
        self.team_dashboard_team_var.set(f"Team Dashboard: {team['name'] if team else 'Unknown'}")

        filters = self._get_active_filters()
        if filters is None:
            return
        season, start_date, end_date = filters

        players = self.db.get_players_for_team(self.active_team_id)
        for p in players:
            player_id = int(p["id"])
            totals = self.db.get_season_totals(
                player_id,
                season=season,
                start_date=start_date,
                end_date=end_date,
                limit=None,
            )
            hitting = compute_hitting_metrics(totals)
            windows = self.db.calculate_stat_windows(
                player_id,
                season=season,
                start_date=start_date,
                end_date=end_date,
            )
            for key in ["season", "last5", "last10"]:
                obp = windows[key].get("OBP")
                slg = windows[key].get("SLG")
                windows[key]["OPS"] = (float(obp) + float(slg)) if (obp is not None and slg is not None) else None
            recs = generate_recommendations(windows)
            top_focus = recs[0].title if recs else "—"

            cs_pct = windows["season"].get("CS_PCT")
            self.team_dashboard_tree.insert(
                "",
                tk.END,
                iid=str(player_id),
                values=(
                    p["name"],
                    p["position"],
                    self._format_metric_value(hitting["OPS"]),
                    self._format_metric_value(windows["season"].get("K_RATE")),
                    self._format_metric_value(cs_pct),
                    top_focus,
                ),
            )

    def _get_active_filters(self) -> tuple[str | None, str | None, str | None] | None:
        selected_season = self.filter_season_var.get().strip()
        season = selected_season if selected_season and selected_season != "All" else None

        date_from = self.filter_start_date_var.get().strip() or None
        date_to = self.filter_end_date_var.get().strip() or None

        if date_from and not self._validate_date(date_from):
            messagebox.showerror("Validation", "Start Date must be YYYY-MM-DD.")
            return None
        if date_to and not self._validate_date(date_to):
            messagebox.showerror("Validation", "End Date must be YYYY-MM-DD.")
            return None
        if date_from and date_to and date_from > date_to:
            messagebox.showerror("Validation", "Start Date cannot be after End Date.")
            return None
        return season, date_from, date_to

    def save_practice_session(self) -> None:
        if not self.active_player_id:
            messagebox.showwarning("No Player", "Select or create a player first.")
            return

        session_date = self.practice_date_var.get().strip()
        if not self._validate_date(session_date):
            messagebox.showerror("Validation", "Practice date must be YYYY-MM-DD.")
            return

        category = self.practice_category_var.get().strip()
        focus = self.practice_focus_var.get().strip()
        if not category or not focus:
            messagebox.showerror("Validation", "Category and Focus are required.")
            return

        try:
            duration = self._parse_optional_int(self.practice_duration_var.get(), "Duration")
            throws = self._parse_optional_int(self.practice_throws_var.get(), "Throws")
            blocks = self._parse_optional_int(self.practice_blocks_var.get(), "Blocks")
            swings = self._parse_optional_int(self.practice_swings_var.get(), "Swings")
            pop_best = self._parse_optional_float(self.practice_pop_best_var.get(), "Pop Time Best")
            pop_avg = self._parse_optional_float(self.practice_pop_avg_var.get(), "Pop Time Avg")
        except ValueError as err:
            messagebox.showerror("Validation", str(err))
            return

        self.db.add_practice_session(
            player_id=self.active_player_id,
            session_date=session_date,
            category=category,
            focus=focus,
            duration_min=duration or 0,
            notes=self.practice_notes_text.get("1.0", tk.END).strip(),
            video_path="",
            pop_time_best=pop_best,
            pop_time_avg=pop_avg,
            throws=throws,
            blocks=blocks,
            swings=swings,
        )

        self.practice_date_var.set(date.today().isoformat())
        self.practice_duration_var.set("0")
        self.practice_pop_best_var.set("")
        self.practice_pop_avg_var.set("")
        self.practice_throws_var.set("")
        self.practice_blocks_var.set("")
        self.practice_swings_var.set("")
        self.practice_notes_text.delete("1.0", tk.END)

        self.refresh_practice_sessions()
        self.refresh_dashboard()
        messagebox.showinfo("Saved", "Practice session saved.")

    def refresh_practice_sessions(self) -> None:
        if not hasattr(self, "practice_tree"):
            return
        self.practice_video_paths = {}
        for item_id in self.practice_tree.get_children():
            self.practice_tree.delete(item_id)
        if not self.active_player_id:
            return

        rows = self.db.get_recent_practice_sessions(self.active_player_id, limit=20)
        for row in rows:
            duration = int(row["duration_min"] or 0)
            video_path = str(row["video_path"] or "")
            notes_text = str(row["notes"] or "")
            mode_tag = ""
            if notes_text.startswith("Mode:"):
                first_line = notes_text.splitlines()[0].strip()
                mode_tag = first_line.replace("Mode:", "", 1).strip()
            self.practice_video_paths[int(row["id"])] = video_path
            self.practice_tree.insert(
                "",
                tk.END,
                iid=str(row["id"]),
                values=(
                    row["session_date"],
                    row["category"],
                    row["focus"],
                    f"{duration} min",
                    mode_tag,
                    "Video" if video_path else "",
                ),
            )

    def delete_selected_practice_session(self) -> None:
        selected = self.practice_tree.selection()
        if not selected:
            messagebox.showerror("Selection Required", "Please select a practice session to delete.")
            return

        session_id = int(selected[0])
        values = self.practice_tree.item(selected[0], "values")
        session_date = values[0] if values else "Unknown Date"
        focus = values[2] if values and len(values) > 2 else "Unknown Focus"
        confirmed = messagebox.askyesno(
            "Confirm Delete",
            f"Delete practice session on {session_date} ({focus})? This cannot be undone.",
        )
        if not confirmed:
            return

        deleted = self.db.delete_practice_session(session_id)
        if not deleted:
            messagebox.showerror("Delete Failed", "Practice session not found.")
            return

        self.refresh_practice_sessions()
        self.refresh_dashboard()
        messagebox.showinfo("Deleted", "Practice session deleted.")

    def open_selected_practice_video(self) -> None:
        selected = self.practice_tree.selection()
        if not selected:
            messagebox.showerror("Selection Required", "Please select a practice session first.")
            return
        session_id = int(selected[0])
        video_path = self.practice_video_paths.get(session_id, "")
        if not video_path:
            messagebox.showwarning("No Video", "This practice session has no linked video.")
            return
        if not Path(video_path).exists():
            messagebox.showwarning("Missing File", "Video file was not found at the saved path.")
            return
        try:
            system = platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", video_path])
            elif system == "Windows":
                os.startfile(video_path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", video_path])
        except Exception as exc:
            messagebox.showerror("Open Video Failed", f"Unable to open video: {exc}")

    def save_video_to_practice(self) -> None:
        if not self.active_player_id:
            messagebox.showwarning("No Player", "Select or create a player first.")
            return
        if not self.video_path or self.video_capture is None:
            messagebox.showerror("No Video", "Load a video first.")
            return
        if not self.rep_marks:
            messagebox.showerror("No Reps", "Add at least one rep before saving to practice.")
            return

        try:
            reps_raw = self.video_reps_var.get().strip()
            reps = self._parse_int(reps_raw, "Reps") if reps_raw else len(self.rep_marks)
        except ValueError as err:
            messagebox.showerror("Validation", str(err))
            return
        if reps <= 0:
            messagebox.showerror("Validation", "Reps must be at least 1.")
            return

        filename = Path(self.video_path).name
        transfers = [rep.transfer for rep in self.rep_marks]
        best_transfer = min(transfers)
        avg_transfer = sum(transfers) / len(transfers)
        mode_key = self._get_metric_mode_key()
        mode_label = self._metric_mode_note_label(mode_key)
        est_flight: float | None = None
        if mode_key == "estimated_pop":
            try:
                est_flight = self._parse_estimated_flight_seconds()
            except ValueError as err:
                messagebox.showerror("Validation", str(err))
                return

        pop_values: list[float] = []
        for rep in self.rep_marks:
            if mode_key == "full_pop":
                if rep.target_time is None:
                    messagebox.showerror(
                        "Validation",
                        "Full Pop mode requires target markers for all reps before saving.",
                    )
                    return
                pop_values.append(rep.target_time - rep.catch_time)
            elif mode_key == "estimated_pop":
                pop_values.append(rep.transfer + float(est_flight or 0.0))
            else:
                pop_values.append(rep.transfer)

        best_pop = min(pop_values)
        avg_pop = sum(pop_values) / len(pop_values)

        rep_parts: list[str] = []
        for idx, rep in enumerate(self.rep_marks, start=1):
            target_text = "—" if rep.target_time is None else f"{rep.target_time:.3f}s"
            if mode_key == "full_pop" and rep.target_time is not None:
                pop_value = rep.target_time - rep.catch_time
            elif mode_key == "estimated_pop":
                pop_value = rep.transfer + float(est_flight or 0.0)
            else:
                pop_value = rep.transfer
            pop_text = f"{pop_value:.3f}s"
            rep_parts.append(
                f"R{idx}: c={rep.catch_time:.3f}s r={rep.release_time:.3f}s t={target_text} pop={pop_text}"
            )
        auto_note = (
            f"Mode: {mode_label}\n"
            f"Video: {filename} | reps={len(self.rep_marks)} "
            f"| best_transfer={best_transfer:.3f}s avg_transfer={avg_transfer:.3f}s "
            f"| best_pop={best_pop:.3f}s avg_pop={avg_pop:.3f}s\n"
            + " | ".join(rep_parts)
        )
        user_notes = self.video_session_notes_text.get("1.0", tk.END).strip()
        notes = auto_note if not user_notes else f"{auto_note}\n{user_notes}"

        self.db.add_practice_session(
            player_id=self.active_player_id,
            session_date=date.today().isoformat(),
            category="Catching",
            focus="Pop Time",
            duration_min=0,
            notes=notes,
            video_path=str(Path(self.video_path).resolve()),
            pop_time_best=best_pop,
            pop_time_avg=avg_pop,
            throws=reps,
            blocks=None,
            swings=None,
        )

        self.refresh_practice_sessions()
        self.refresh_dashboard()
        messagebox.showinfo("Saved", "Video rep set saved to practice.")

    def save_game_and_stats(self) -> None:
        if not self.active_player_id:
            messagebox.showwarning("No Player", "Select or create a player first.")
            return

        game_date = self.game_date_var.get().strip()
        if not self._validate_date(game_date):
            messagebox.showerror("Validation", "Date must be in YYYY-MM-DD format.")
            return
        game_season = self.game_season_var.get().strip() or game_date[:4]

        try:
            stats: dict[str, int | float] = {
                "ab": self._parse_int(self.stat_vars["ab"].get().strip(), "AB"),
                "h": self._parse_int(self.stat_vars["h"].get().strip(), "H"),
                "doubles": self._parse_int(self.stat_vars["doubles"].get().strip(), "2B"),
                "triples": self._parse_int(self.stat_vars["triples"].get().strip(), "3B"),
                "hr": self._parse_int(self.stat_vars["hr"].get().strip(), "HR"),
                "bb": self._parse_int(self.stat_vars["bb"].get().strip(), "BB"),
                "so": self._parse_int(self.stat_vars["so"].get().strip(), "SO"),
                "rbi": self._parse_int(self.stat_vars["rbi"].get().strip(), "RBI"),
                "sb": self._parse_int(self.stat_vars["sb"].get().strip(), "SB"),
                "cs": self._parse_int(self.stat_vars["cs"].get().strip(), "CS"),
                "innings_caught": self._parse_float(self.stat_vars["innings_caught"].get().strip(), "Innings Caught"),
                "passed_balls": self._parse_int(self.stat_vars["passed_balls"].get().strip(), "Passed Balls"),
                "sb_allowed": self._parse_int(self.stat_vars["sb_allowed"].get().strip(), "SB Allowed"),
                "cs_caught": self._parse_int(self.stat_vars["cs_caught"].get().strip(), "CS Caught"),
            }
        except ValueError as err:
            messagebox.showerror("Validation", str(err))
            return

        if stats["h"] > stats["ab"]:
            messagebox.showerror("Validation", "H cannot exceed AB.")
            return

        if stats["doubles"] + stats["triples"] + stats["hr"] > stats["h"]:
            messagebox.showerror("Validation", "2B + 3B + HR cannot exceed H.")
            return

        notes_text = self.game_notes_text.get("1.0", tk.END).strip()

        if self.loaded_game_id is None:
            game_id = self.db.add_game(
                self.active_player_id,
                game_date,
                game_season,
                self.game_opponent_var.get().strip(),
                notes_text,
            )
            self.db.add_stat_line(game_id, stats)
        else:
            game_id = self.loaded_game_id
            self.db.update_game(
                game_id,
                game_date,
                game_season,
                self.game_opponent_var.get().strip(),
                notes_text,
            )
            self.db.update_or_insert_stat_line(game_id, stats)
            self.db.update_game_notes(game_id, notes_text)

        self.clear_game_entry_fields()
        self.refresh_dashboard_filter_options()
        self.refresh_game_history()
        self.refresh_dashboard()
        messagebox.showinfo("Saved", "Saved game + notes.")

    def refresh_game_history(self) -> None:
        for item_id in self.game_history_tree.get_children():
            self.game_history_tree.delete(item_id)

        if not self.active_player_id:
            return

        filters = self._get_active_filters()
        if filters is None:
            return
        season, start_date, end_date = filters

        games = self.db.get_games(
            self.active_player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
        )
        for game in games:
            self.game_history_tree.insert(
                "",
                tk.END,
                iid=str(game["id"]),
                values=(game["date"], game["opponent"] or ""),
            )

    def clear_game_entry_fields(self) -> None:
        self.game_date_var.set(date.today().isoformat())
        self.game_season_var.set(str(date.today().year))
        self.game_opponent_var.set("")
        self.game_notes_text.delete("1.0", tk.END)
        self.loaded_game_id = None
        for key in self.stat_vars:
            self.stat_vars[key].set("0")
        self.game_history_tree.selection_remove(self.game_history_tree.selection())

    def load_selected_game(self) -> None:
        selected = self.game_history_tree.selection()
        if not selected:
            messagebox.showerror("Selection Required", "Please select a game to load.")
            return

        game_id = int(selected[0])
        row = self.db.get_game_with_stats(game_id)
        if not row:
            messagebox.showerror("Load Failed", "Game not found.")
            return

        self.loaded_game_id = game_id
        self.game_date_var.set(str(row["date"] or ""))
        self.game_season_var.set(str(row["season"] or ""))
        self.game_opponent_var.set(str(row["opponent"] or ""))
        self.game_notes_text.delete("1.0", tk.END)
        self.game_notes_text.insert(tk.END, str(row["notes"] or ""))

        for key in self.stat_vars:
            value = row[key]
            if value is None:
                self.stat_vars[key].set("0")
            elif key == "innings_caught":
                self.stat_vars[key].set(str(float(value)))
            else:
                self.stat_vars[key].set(str(int(value)))

        messagebox.showinfo("Loaded", "Game loaded. Edit fields and press Save to update.")

    def delete_selected_game(self) -> None:
        selected = self.game_history_tree.selection()
        if not selected:
            messagebox.showerror("Selection Required", "Please select a game to delete.")
            return

        selected_item = selected[0]
        game_id = int(selected_item)
        values = self.game_history_tree.item(selected_item, "values")
        game_date = values[0] if values else "Unknown Date"
        opponent = values[1] if values and len(values) > 1 else ""
        opponent_display = opponent if opponent else "Unknown Opponent"

        confirmed = messagebox.askyesno(
            "Confirm Delete",
            (
                f"Delete game on {game_date} vs {opponent_display}? "
                "This will also delete its stat line. This cannot be undone."
            ),
        )
        if not confirmed:
            return

        try:
            deleted = self.db.delete_game(game_id)
        except Exception as err:
            messagebox.showerror("Delete Failed", f"Unable to delete game: {err}")
            return

        if not deleted:
            messagebox.showerror("Delete Failed", "Game was not found.")
            self.refresh_game_history()
            return

        self.clear_game_entry_fields()
        self.refresh_dashboard_filter_options()
        self.refresh_game_history()
        self.refresh_dashboard()
        messagebox.showinfo("Deleted", "Game deleted.")

    def _set_totals_text(self, text: str, click_tokens: dict[str, str] | None = None) -> None:
        self.totals_text.configure(state=tk.NORMAL)
        self.totals_text.delete("1.0", tk.END)
        self.totals_text.insert(tk.END, text)
        if click_tokens:
            for token, stat_key in click_tokens.items():
                tag = f"click_{stat_key}"
                self.totals_text.tag_delete(tag)
                start = "1.0"
                while True:
                    idx = self.totals_text.search(token, start, stopindex=tk.END)
                    if not idx:
                        break
                    end = f"{idx}+{len(token)}c"
                    self.totals_text.tag_add(tag, idx, end)
                    start = end
                self.totals_text.tag_configure(tag, foreground=Theme.ACCENT, underline=True)
                self.totals_text.tag_bind(
                    tag,
                    "<Button-1>",
                    lambda _e, sk=stat_key: self.open_training_suggestion(sk),
                )
                self.totals_text.tag_bind(tag, "<Enter>", lambda _e: self.totals_text.configure(cursor="hand2"))
                self.totals_text.tag_bind(tag, "<Leave>", lambda _e: self.totals_text.configure(cursor="xterm"))
        self.totals_text.configure(state=tk.DISABLED)

    def _format_training_current_value(self, stat_key: str) -> str:
        value = self.dashboard_stat_values.get(stat_key)
        if value is None:
            return "—"
        if stat_key in {"K_RATE", "BB_RATE", "CS_PCT"}:
            return f"{value * 100:.1f}%"
        return self._format_metric_value(float(value))

    def open_training_suggestion(self, stat_key: str) -> None:
        stat_title = self.metric_display_names.get(stat_key, stat_key)
        current_value = self._format_training_current_value(stat_key)
        win = tk.Toplevel(self.root)
        win.title(f"{stat_title} Development")
        win.geometry("640x560")
        win.transient(self.root)
        win.grab_set()

        panel = TrainingSuggestionPanel(
            win,
            stat_key=stat_key,
            stat_title=stat_title,
            current_value=current_value,
        )
        panel.pack(fill=tk.BOTH, expand=True)

    def _set_recent_notes_text(self, text: str) -> None:
        self.recent_notes_text.configure(state=tk.NORMAL)
        self.recent_notes_text.delete("1.0", tk.END)
        self.recent_notes_text.insert(tk.END, text)
        self.recent_notes_text.configure(state=tk.DISABLED)

    def _set_focus_text(self, text: str) -> None:
        self.focus_text.configure(state=tk.NORMAL)
        self.focus_text.delete("1.0", tk.END)
        self.focus_text.insert(tk.END, text)
        self.focus_text.configure(state=tk.DISABLED)

    def _set_shared_suggestions_text(self, text: str) -> None:
        self.shared_suggestions_text.configure(state=tk.NORMAL)
        self.shared_suggestions_text.delete("1.0", tk.END)
        self.shared_suggestions_text.insert(tk.END, text)
        self.shared_suggestions_text.configure(state=tk.DISABLED)

    def _set_practice_week_text(self, text: str) -> None:
        self.practice_week_text.configure(state=tk.NORMAL)
        self.practice_week_text.delete("1.0", tk.END)
        self.practice_week_text.insert(tk.END, text)
        self.practice_week_text.configure(state=tk.DISABLED)

    def _set_baseline_compare_text(self, text: str) -> None:
        self.baseline_compare_text.configure(state=tk.NORMAL)
        self.baseline_compare_text.delete("1.0", tk.END)
        self.baseline_compare_text.insert(tk.END, text)
        self.baseline_compare_text.configure(state=tk.DISABLED)

    def _set_season_summary_unknown_text(self, text: str) -> None:
        self.season_summary_unknown_text.configure(state=tk.NORMAL)
        self.season_summary_unknown_text.delete("1.0", tk.END)
        self.season_summary_unknown_text.insert(tk.END, text)
        self.season_summary_unknown_text.configure(state=tk.DISABLED)

    def _set_development_profile_text(self, text: str) -> None:
        self.development_profile_text.configure(state=tk.NORMAL)
        self.development_profile_text.delete("1.0", tk.END)
        self.development_profile_text.insert(tk.END, text)
        self.development_profile_text.configure(state=tk.DISABLED)

    def _set_consistency_text(self, text: str) -> None:
        self.consistency_text.configure(state=tk.NORMAL)
        self.consistency_text.delete("1.0", tk.END)
        self.consistency_text.insert(tk.END, text)
        self.consistency_text.configure(state=tk.DISABLED)

    def _set_current_focus_text(self, text: str) -> None:
        self.current_focus_text.configure(state=tk.NORMAL)
        self.current_focus_text.delete("1.0", tk.END)
        self.current_focus_text.insert(tk.END, text)
        self.current_focus_text.configure(state=tk.DISABLED)

    def open_current_focus_training(self) -> None:
        if not self.current_focus_stat_training_key:
            messagebox.showinfo("Focus", "No current focus stat available yet.")
            return
        self.open_training_suggestion(self.current_focus_stat_training_key)

    def _refresh_consistency(
        self,
        season: str | None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> None:
        if not self.active_player_id:
            self._set_consistency_text("No player selected.")
            return
        transfer_detail = self.db.get_transfer_samples_detail(
            self.active_player_id,
            start_date=start_date,
            end_date=end_date,
            season=season,
        )
        transfer_samples = list(transfer_detail.get("samples", []))
        obp_samples = self.db.get_obp_samples(
            self.active_player_id,
            start_date=start_date,
            end_date=end_date,
            season=season,
        )

        transfer_cons = compute_consistency(transfer_samples) if len(transfer_samples) >= 2 else None
        obp_cons = compute_consistency(obp_samples) if len(obp_samples) >= 2 else None

        lines = ["Metric | Avg | SD | CV | Grade | N", "-" * 56]
        if transfer_cons is None:
            transfer_label = "Transfer Time (set-level)" if transfer_detail.get("set_level") else "Transfer Time"
            lines.append(f"{transfer_label} | — | — | — | Not enough data | {len(transfer_samples)}")
        else:
            suffix = " set-level" if transfer_detail.get("set_level") else ""
            transfer_cv = transfer_cons["cv"]
            transfer_cv_text = "—" if transfer_cv is None else f"{float(transfer_cv):.3f}"
            lines.append(
                f"Transfer Time{suffix} | {transfer_cons['mean']:.3f}s | {transfer_cons['sd']:.3f}s | {transfer_cv_text} | "
                f"{transfer_cons['grade']} | {transfer_cons['n']}"
            )
        if obp_cons is None:
            lines.append(f"OBP | — | — | — | Not enough data | {len(obp_samples)}")
        else:
            obp_cv = obp_cons["cv"]
            obp_cv_text = "—" if obp_cv is None else f"{float(obp_cv):.3f}"
            lines.append(
                f"OBP | {obp_cons['mean']:.3f} | {obp_cons['sd']:.3f} | {obp_cv_text} | "
                f"{obp_cons['grade']} | {obp_cons['n']}"
            )
        self._set_consistency_text("\n".join(lines))

    def _refresh_current_development_focus(self) -> None:
        if not self.active_player_id:
            self.current_focus_stat_training_key = None
            self._set_current_focus_text("No player selected.")
            return
        player = self.db.get_player(self.active_player_id)
        age_level = str(player["level"]) if player and player["level"] else None
        focus_rows = get_player_focus_stats(self.db, self.active_player_id, age_level)
        if not focus_rows:
            self.current_focus_stat_training_key = None
            self._set_current_focus_text("Not enough benchmark data for current level.")
            return

        display_name_map = {
            "transfer_time": "Transfer Time",
            "pop_time": "Pop Time",
        }
        training_key_map = {
            "transfer_time": "TRANSFER_TIME",
            "pop_time": "POP_TIME",
        }
        lines: list[str] = []
        for row in focus_rows:
            stat_key = str(row["stat_key"])
            name = display_name_map.get(stat_key, stat_key)
            value = row["value"]
            value_text = "—" if value is None else f"{float(value):.3f}s"
            lines.extend(
                [
                    f"{name}",
                    f"Player Value: {value_text}",
                    f"Benchmark Range: {row.get('benchmark_range', '—')}",
                    f"Priority Level: {row.get('priority', 'Medium')}",
                    "",
                ]
            )
        self.current_focus_stat_training_key = training_key_map.get(str(focus_rows[0]["stat_key"]))
        self._set_current_focus_text("\n".join(lines).strip())

    def _refresh_development_profile(self) -> None:
        if not self.active_player_id:
            self._set_development_profile_text("No player selected.")
            return
        profile = build_player_development_profile(self.db, self.active_player_id)
        evaluations = profile.get("evaluations", {})
        name_map = {"transfer_time": "Transfer Time", "pop_time": "Pop Time"}

        def line_for(stat_key: str) -> str:
            payload = evaluations.get(stat_key, {})
            value = payload.get("value")
            label = name_map.get(stat_key, stat_key)
            if value is None:
                return f"{label}: —"
            return f"{label}: {float(value):.3f}s"

        strengths = [name_map.get(k, k) for k in profile.get("strengths", [])]
        growth = [name_map.get(k, k) for k in profile.get("growth", [])]
        neutral = [name_map.get(k, k) for k in profile.get("neutral", [])]
        level = profile.get("age_level") or "Unknown"

        lines = [
            f"Benchmark Level: {level}",
            "",
            "Strengths [green]",
            f"- {', '.join(strengths) if strengths else '—'}",
            "",
            "Growth Focus [yellow]",
            f"- {', '.join(growth) if growth else '—'}",
            "",
            "Stable [gray]",
            f"- {', '.join(neutral) if neutral else '—'}",
            "",
            line_for("transfer_time"),
            line_for("pop_time"),
        ]
        self._set_development_profile_text("\n".join(lines))
        self._refresh_current_development_focus()

    def _format_metric_value(self, value: float | None) -> str:
        if value is None:
            return "—"
        formatted = f"{value:.3f}"
        if formatted.startswith("0."):
            return "." + formatted[2:]
        if formatted.startswith("-0."):
            return "-." + formatted[3:]
        return formatted

    def _render_window_trend(self, trend: str, delta: float) -> tuple[str, str]:
        if trend == "UP":
            return f"▲ {delta:+.3f}", Theme.SUCCESS
        if trend == "DOWN":
            return f"▼ {delta:+.3f}", Theme.DANGER
        return f"→ {delta:+.3f}", "#8A96A3"

    def _refresh_performance_trends(
        self,
        season: str | None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> None:
        if not self.active_player_id:
            self.avg_momentum_var.set("AVG Momentum: STABLE")
            self.avg_momentum_label.configure(fg="#8A96A3")
            for metric in self.performance_metric_order:
                cells = self.performance_cells[metric]
                for key in ["season", "last5", "last10", "trend5", "trend10"]:
                    cells[key].set("—")  # type: ignore[index]
            return

        windows = self.db.calculate_stat_windows(
            self.active_player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
        )
        season_metrics = windows["season"]
        last5_metrics = windows["last5"]
        last10_metrics = windows["last10"]

        season_avg = season_metrics.get("AVG")
        last5_avg = last5_metrics.get("AVG")
        if season_avg is None or last5_avg is None:
            momentum = "STABLE"
        else:
            avg_delta = float(last5_avg) - float(season_avg)
            if avg_delta > 0.020:
                momentum = "HOT"
            elif avg_delta < -0.020:
                momentum = "COLD"
            else:
                momentum = "STABLE"
        momentum_color = Theme.SUCCESS if momentum == "HOT" else Theme.DANGER if momentum == "COLD" else "#8A96A3"
        self.avg_momentum_var.set(f"AVG Momentum: {momentum}")
        self.avg_momentum_label.configure(fg=momentum_color)

        for metric in self.performance_metric_order:
            season_value = season_metrics.get(metric)
            last5_value = last5_metrics.get(metric)
            last10_value = last10_metrics.get(metric)
            if season_value is None or last5_value is None:
                trend5_text, trend5_color = "—", "#8A96A3"
            else:
                cmp5 = compare_window_to_season(last5_value, season_value)
                trend5_text, trend5_color = self._render_window_trend(str(cmp5["trend"]), float(cmp5["delta"]))
            if season_value is None or last10_value is None:
                trend10_text, trend10_color = "—", "#8A96A3"
            else:
                cmp10 = compare_window_to_season(last10_value, season_value)
                trend10_text, trend10_color = self._render_window_trend(str(cmp10["trend"]), float(cmp10["delta"]))

            cells = self.performance_cells[metric]
            cells["season"].set(self._format_metric_value(season_value))  # type: ignore[index]
            cells["last5"].set(self._format_metric_value(last5_value))  # type: ignore[index]
            cells["last10"].set(self._format_metric_value(last10_value))  # type: ignore[index]
            cells["trend5"].set(trend5_text)  # type: ignore[index]
            cells["trend10"].set(trend10_text)  # type: ignore[index]
            cells["trend5_label"].configure(fg=trend5_color)  # type: ignore[index]
            cells["trend10_label"].configure(fg=trend10_color)  # type: ignore[index]

    def _refresh_recent_notes(
        self,
        season: str | None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> None:
        if not self.active_player_id:
            self._set_recent_notes_text("No player selected.")
            return

        recent = self.db.get_recent_notes(
            self.active_player_id,
            limit=5,
            season=season,
            start_date=start_date,
            end_date=end_date,
        )
        lines: list[str] = []
        for row in recent:
            note = str(row["notes"] or "").strip()
            if not note:
                note = "—"
            if len(note) > 80:
                note = note[:80].rstrip() + "..."
            opponent = row["opponent"] or "Unknown Opponent"
            lines.append(f"{row['date']} vs {opponent}: {note}")

        self._set_recent_notes_text("\n".join(lines) if lines else "No recent notes.")

    def _refresh_practice_week_panel(self) -> dict:
        if not self.active_player_id:
            self._set_practice_week_text("No player selected.")
            return {"session_count": 0, "recent_focuses": []}

        summary = self.db.get_practice_summary_last_days(self.active_player_id, days=7)
        lines = [
            f"Sessions (last 7 days): {summary['session_count']}",
            f"Total minutes (last 7 days): {summary['total_minutes']}",
        ]

        top_focuses = summary["top_focuses"]
        if top_focuses:
            focus_text = ", ".join(f"{focus} ({count})" for focus, count in top_focuses)
            lines.append(f"Top focus areas: {focus_text}")
        else:
            lines.append("Top focus areas: —")

        last_sessions = summary["last_sessions"]
        if last_sessions:
            lines.append("Last 3 sessions:")
            for s in last_sessions:
                lines.append(f"- {s['session_date']} | {s['focus']} | {int(s['duration_min'] or 0)} min")
        else:
            lines.append("Last 3 sessions: —")

        self._set_practice_week_text("\n".join(lines))
        return summary

    def _refresh_focus_suggestions(
        self,
        season: str | None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> None:
        if not self.active_player_id:
            self._set_focus_text("No player selected.")
            return

        windows = self.db.calculate_stat_windows(
            self.active_player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
        )
        for key in ["season", "last5", "last10"]:
            obp = windows[key].get("OBP")
            slg = windows[key].get("SLG")
            if obp is not None and slg is not None:
                windows[key]["OPS"] = float(obp) + float(slg)
            else:
                windows[key]["OPS"] = None

        practice_summary = self.db.get_practice_summary_last_days(self.active_player_id, days=7)
        recent_focuses = [f.lower() for f in practice_summary.get("recent_focuses", [])]

        recommendations = generate_recommendations(windows)
        if not recommendations:
            self._set_focus_text(
                f"Last 7 days sessions: {practice_summary.get('session_count', 0)}\n"
                "No priority focus flags in current filter scope."
            )
            return

        lines: list[str] = [f"Last 7 days sessions: {practice_summary.get('session_count', 0)}", ""]
        title_focus_map = {
            "Contact & Timing": ["contact", "timing"],
            "Plate Discipline": ["discipline", "plate", "zone"],
            "Gap Power": ["gap", "power"],
            "Pop Time / Transfer": ["pop time", "transfer", "throw"],
            "Blocking Consistency": ["block", "blocking"],
        }
        for rec in recommendations:
            markers = title_focus_map.get(rec.title, [rec.title.lower()])
            in_progress = any(any(marker in focus for marker in markers) for focus in recent_focuses)
            title = f"{rec.title} (in progress)" if in_progress else rec.title
            lines.append(title)
            lines.append(f"Reason: {rec.reason}")
            for drill in rec.drills:
                lines.append(f"- {drill}")
            lines.append("")
        self._set_focus_text("\n".join(lines).rstrip())

    def _period_sort_key(self, label: str) -> tuple[int, str]:
        match = re.search(r"(19|20)\d{2}", label)
        if match:
            return (int(match.group(0)), label)
        return (0, label)

    def refresh_trends_chart(self) -> None:
        if not hasattr(self, "trends_chart_axes"):
            return
        if self.trends_chart_axes is None or self.trends_chart_canvas is None:
            return
        ax = self.trends_chart_axes
        ax.clear()
        if not self.active_player_id:
            ax.set_title("No active player")
            self.trends_chart_canvas.draw()
            return

        self.rebuild_all_timeline_points_for_player(self.active_player_id)
        metric_label = self.trends_metric_var.get().strip()
        metric_key = self.trends_metric_options.get(metric_label, "ops")

        if self.trends_inseason_var.get():
            selected_season = self.filter_season_var.get().strip()
            season = selected_season if selected_season and selected_season != "All" else None
            if not season:
                ax.set_title("Select a season to view in-season cumulative trend")
                self.trends_chart_canvas.draw()
                return
            rows = self.db.get_stat_lines(self.active_player_id, season=season, start_date=None, end_date=None, limit=None)
            if not rows:
                ax.set_title("No game data available for selected season")
                self.trends_chart_canvas.draw()
                return
            if metric_key not in {"avg", "obp", "ops"}:
                ax.set_title("In-season cumulative supports AVG / OBP / OPS")
                self.trends_chart_canvas.draw()
                return
            cumulative = {"ab": 0.0, "h": 0.0, "bb": 0.0, "sf": 0.0, "doubles": 0.0, "triples": 0.0, "hr": 0.0}
            x_labels: list[str] = []
            values: list[float] = []
            for row in reversed(rows):
                cumulative["ab"] += float(row["ab"] or 0)
                cumulative["h"] += float(row["h"] or 0)
                cumulative["bb"] += float(row["bb"] or 0)
                cumulative["sf"] += 0.0
                cumulative["doubles"] += float(row["doubles"] or 0)
                cumulative["triples"] += float(row["triples"] or 0)
                cumulative["hr"] += float(row["hr"] or 0)
                ab = cumulative["ab"]
                h = cumulative["h"]
                bb = cumulative["bb"]
                sf = cumulative["sf"]
                singles = h - cumulative["doubles"] - cumulative["triples"] - cumulative["hr"]
                tb = singles + (2 * cumulative["doubles"]) + (3 * cumulative["triples"]) + (4 * cumulative["hr"])
                avg_v = (h / ab) if ab else 0.0
                obp_v = ((h + bb) / (ab + bb + sf)) if (ab + bb + sf) else 0.0
                slg_v = (tb / ab) if ab else 0.0
                ops_v = obp_v + slg_v
                value = avg_v if metric_key == "avg" else obp_v if metric_key == "obp" else ops_v
                x_labels.append(str(row["date"]))
                values.append(float(value))
            ax.plot(range(len(values)), values, marker="o", color=Theme.ACCENT)
            ax.set_xticks(range(len(x_labels)))
            ax.set_xticklabels(x_labels, rotation=35, ha="right", fontsize=8)
            ax.set_title(f"In-season cumulative {metric_label} ({season})")
            ax.grid(alpha=0.25)
            self.trends_chart_figure.tight_layout()
            self.trends_chart_canvas.draw()
            return

        points = self.db.get_stat_timeline_points(self.active_player_id)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for p in points:
            row = dict(p)
            try:
                row["metrics"] = json.loads(str(row.get("metrics_json") or "{}"))
            except json.JSONDecodeError:
                row["metrics"] = {}
            grouped.setdefault(str(row["period_label"]), []).append(row)

        selected_season = self.filter_season_var.get().strip()
        current_period = selected_season if selected_season and selected_season != "All" else str(date.today().year)
        chosen_rows: list[dict[str, Any]] = []
        for period_label, rows_for_period in grouped.items():
            game_rows = [r for r in rows_for_period if r.get("source_type") == "game_aggregate"]
            summary_rows = [r for r in rows_for_period if r.get("source_type") == "season_summary"]
            if current_period in period_label and game_rows:
                chosen = game_rows[-1]
            elif summary_rows:
                chosen = summary_rows[-1]
            elif game_rows:
                chosen = game_rows[-1]
            else:
                chosen = rows_for_period[-1]
            chosen_rows.append(chosen)

        chosen_rows.sort(key=lambda r: self._period_sort_key(str(r.get("period_label", ""))))
        labels: list[str] = []
        values: list[float] = []
        for row in chosen_rows:
            metrics = row.get("metrics", {})
            val = metrics.get(metric_key)
            if val is None:
                continue
            try:
                labels.append(str(row.get("period_label", "")))
                values.append(float(val))
            except (TypeError, ValueError):
                continue
        if not values:
            ax.set_title("No timeline data for selected metric")
            self.trends_chart_canvas.draw()
            return
        ax.plot(range(len(values)), values, marker="o", color=Theme.ACCENT)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=25, ha="right")
        ax.set_title(f"Multi-season {metric_label} Trend")
        ax.grid(alpha=0.25)
        self.trends_chart_figure.tight_layout()
        self.trends_chart_canvas.draw()

    def _scope_label(self, season: str | None, start_date: str | None, end_date: str | None) -> str:
        if season and not start_date and not end_date:
            return f"Season {season}"
        if start_date or end_date:
            return f"{start_date or 'Start'} to {end_date or 'Now'}" + (f" | Season {season}" if season else "")
        return "All"

    def _build_export_payload(self) -> dict | None:
        if not self.active_player_id:
            return None
        filters = self._get_active_filters()
        if filters is None:
            return None
        season, start_date, end_date = filters

        player_row = self.db.get_player(self.active_player_id)
        if not player_row:
            return None
        player = dict(player_row)
        player["scope_label"] = self._scope_label(season, start_date, end_date)

        totals = self.db.get_season_totals(
            self.active_player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
            limit=None,
        )
        hitting = compute_hitting_metrics(totals)
        catching = compute_catching_metrics(totals)
        windows = self.db.calculate_stat_windows(
            self.active_player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
        )
        for key in ["season", "last5", "last10"]:
            obp = windows[key].get("OBP")
            slg = windows[key].get("SLG")
            windows[key]["OPS"] = (float(obp) + float(slg)) if (obp is not None and slg is not None) else None

        metric_order = ["AVG", "OBP", "SLG", "OPS", "K_RATE", "BB_RATE", "CS_PCT", "PB_RATE"]
        trend_rows: list[dict] = []
        for metric in metric_order:
            season_v = windows["season"].get(metric)
            last5_v = windows["last5"].get(metric)
            last10_v = windows["last10"].get(metric)
            cmp5 = compare_window_to_season(last5_v, season_v) if (season_v is not None and last5_v is not None) else None
            cmp10 = compare_window_to_season(last10_v, season_v) if (season_v is not None and last10_v is not None) else None
            trend_rows.append(
                {
                    "metric": metric,
                    "season": season_v,
                    "last5": last5_v,
                    "delta5": None if cmp5 is None else float(cmp5["delta"]),
                    "trend5": "—" if cmp5 is None else str(cmp5["trend"]),
                    "last10": last10_v,
                    "delta10": None if cmp10 is None else float(cmp10["delta"]),
                    "trend10": "—" if cmp10 is None else str(cmp10["trend"]),
                }
            )

        recommendations = generate_recommendations(windows)
        recommendation_dicts = [
            {"title": rec.title, "reason": rec.reason, "drills": rec.drills, "priority": rec.priority}
            for rec in recommendations
        ]

        practice_summary = self.db.get_practice_summary_last_days(self.active_player_id, days=7)
        recent_notes = [
            dict(r)
            for r in self.db.get_recent_notes(
                self.active_player_id,
                limit=3,
                season=season,
                start_date=start_date,
                end_date=end_date,
            )
        ]

        performance = {
            "AVG": hitting["AVG"],
            "OBP": hitting["OBP"],
            "SLG": hitting["SLG"],
            "OPS": hitting["OPS"],
            "K_RATE": windows["season"].get("K_RATE"),
            "BB_RATE": windows["season"].get("BB_RATE"),
            "CS_PCT": catching.get("CS%"),
            "PB_RATE": catching.get("PB Rate"),
        }

        return {
            "player": player,
            "filters": {"season": season, "start_date": start_date, "end_date": end_date, "scope_label": player["scope_label"]},
            "metrics": {"performance": performance},
            "trends": trend_rows,
            "recommendations": recommendation_dicts,
            "practice_summary": practice_summary,
            "recent_notes": recent_notes,
        }

    def export_report_pdf(self) -> None:
        payload = self._build_export_payload()
        if payload is None:
            messagebox.showerror("Export Error", "No active player or invalid filters.")
            return

        player_name = str(payload["player"].get("name", "Player")).replace(" ", "_")
        season = payload["filters"].get("season")
        start_date = payload["filters"].get("start_date")
        end_date = payload["filters"].get("end_date")
        if season:
            scope = f"Season_{season}"
        elif start_date or end_date:
            scope = f"{start_date or 'Start'}_to_{end_date or 'Now'}".replace("-", "")
        else:
            scope = "All"
        default_filename = f"StatForge_{player_name}_{scope}.pdf"

        filepath = filedialog.asksaveasfilename(
            title="Export Report (PDF)",
            defaultextension=".pdf",
            initialfile=default_filename,
            filetypes=[("PDF files", "*.pdf")],
        )
        if not filepath:
            return

        try:
            generate_player_report_pdf(
                filepath=filepath,
                player=payload["player"],
                filters=payload["filters"],
                metrics=payload["metrics"],
                trends=payload["trends"],
                recommendations=payload["recommendations"],
                practice_summary=payload["practice_summary"],
                recent_notes=payload["recent_notes"],
            )
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))
            return
        messagebox.showinfo("Export Complete", "Report exported.")

    def refresh_dashboard(self) -> None:
        if not self.active_player_id:
            self.dashboard_player_var.set("No active player")
            self.dashboard_stat_values = {}
            self._set_totals_text("No player selected.")
            self._set_baseline_compare_text("No baseline selected.")
            self._set_recent_notes_text("No player selected.")
            self._set_practice_week_text("No player selected.")
            self._set_development_profile_text("No player selected.")
            self._set_consistency_text("No player selected.")
            self._set_current_focus_text("No player selected.")
            self.current_focus_stat_training_key = None
            self._set_focus_text("No player selected.")
            self._set_shared_suggestions_text("No player selected.")
            for var in self.trends_vars.values():
                var.set(var.get().split(":")[0] + ": —")
            self._refresh_performance_trends(season=None)
            self.refresh_trends_chart()
            return

        filters = self._get_active_filters()
        if filters is None:
            return
        season, start_date, end_date = filters

        self._update_player_details(self.active_player_id)
        self.rebuild_all_timeline_points_for_player(self.active_player_id)
        totals = self.db.get_season_totals(
            self.active_player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
            limit=None,
        )
        hitting = compute_hitting_metrics(totals)
        catching = compute_catching_metrics(totals)
        windows = self.db.calculate_stat_windows(
            self.active_player_id,
            season=season,
            start_date=start_date,
            end_date=end_date,
        )
        season_window = windows.get("season", {})
        practice_rows = self.db.get_recent_practice_sessions(self.active_player_id, limit=20)
        pop_values = [float(r["pop_time_avg"]) for r in practice_rows if r["pop_time_avg"] is not None]
        pop_best_values = [float(r["pop_time_best"]) for r in practice_rows if r["pop_time_best"] is not None]
        pop_avg = (sum(pop_values) / len(pop_values)) if pop_values else None
        pop_best = min(pop_best_values) if pop_best_values else None

        self.dashboard_stat_values = {
            "AVG": float(hitting["AVG"]),
            "OBP": float(hitting["OBP"]),
            "SLG": float(hitting["SLG"]),
            "OPS": float(hitting["OPS"]),
            "K_RATE": float(season_window.get("K_RATE")) if season_window.get("K_RATE") is not None else None,
            "BB_RATE": float(season_window.get("BB_RATE")) if season_window.get("BB_RATE") is not None else None,
            "CS_PCT": float(catching["CS%"]),
            "PB_RATE": float(catching["PB Rate"]),
            "POP_TIME": pop_avg,
        }

        display = (
            f"AB: {int(totals.get('ab', 0))}    H: {int(totals.get('h', 0))}    2B: {int(totals.get('doubles', 0))}    "
            f"3B: {int(totals.get('triples', 0))}    HR: {int(totals.get('hr', 0))}\n"
            f"BB: {int(totals.get('bb', 0))}    SO: {int(totals.get('so', 0))}    RBI: {int(totals.get('rbi', 0))}    "
            f"SB: {int(totals.get('sb', 0))}    CS: {int(totals.get('cs', 0))}\n"
            f"Innings Caught: {totals.get('innings_caught', 0):.1f}    PB: {int(totals.get('passed_balls', 0))}    "
            f"SB Allowed: {int(totals.get('sb_allowed', 0))}    CS Caught: {int(totals.get('cs_caught', 0))}\n\n"
            f"AVG: {hitting['AVG']:.3f}    OBP: {hitting['OBP']:.3f}    SLG: {hitting['SLG']:.3f}    OPS: {hitting['OPS']:.3f}\n"
            f"CS%: {catching['CS%']:.3f}    PB Rate: {catching['PB Rate']:.3f}\n"
            f"Pop Time Best: {'—' if pop_best is None else f'{pop_best:.3f}'}    "
            f"Pop Time Avg: {'—' if pop_avg is None else f'{pop_avg:.3f}'}"
        )
        self._set_totals_text(
            display,
            click_tokens={
                "AVG:": "AVG",
                "OBP:": "OBP",
                "SLG:": "SLG",
                "OPS:": "OPS",
                "CS%:": "CS_PCT",
                "PB Rate:": "PB_RATE",
                "Pop Time Best:": "POP_TIME",
                "Pop Time Avg:": "POP_TIME",
            },
        )
        baseline_row = self._selected_baseline_summary()
        if baseline_row:
            try:
                baseline_stats = json.loads(str(baseline_row.get("stats_json", "{}")))
            except json.JSONDecodeError:
                baseline_stats = {}
            baseline_metrics = compute_season_summary_metrics(baseline_stats)
            baseline_totals_bits = []
            for k in ("games", "pa", "ab", "h", "bb", "so", "pb"):
                if k in baseline_stats:
                    baseline_totals_bits.append(f"{k.upper()}={baseline_stats[k]}")
            current_avg = hitting["AVG"]
            current_cs = catching["CS%"]
            current_pb = catching["PB Rate"]
            current_pop = pop_avg
            lines = [
                f"Baseline: {baseline_row.get('season_label', 'Unknown')}",
                ("Baseline Totals: " + ", ".join(baseline_totals_bits)) if baseline_totals_bits else "Baseline Totals: —",
                f"AVG: {current_avg:.3f} vs {baseline_metrics.get('avg', float('nan')):.3f}" if "avg" in baseline_metrics else f"AVG: {current_avg:.3f} vs —",
                (
                    f"Pop Time Avg: {current_pop:.3f} vs {baseline_metrics.get('pop_time', float('nan')):.3f}"
                    if current_pop is not None and "pop_time" in baseline_metrics
                    else (f"Pop Time Avg: {current_pop:.3f} vs —" if current_pop is not None else "Pop Time Avg: —")
                ),
                f"CS Rate: {current_cs:.3f} vs {baseline_metrics.get('cs_rate', float('nan')):.3f}" if "cs_rate" in baseline_metrics else f"CS Rate: {current_cs:.3f} vs —",
                f"PB Rate: {current_pb:.3f} vs {baseline_metrics.get('pb_per_inning', float('nan')):.3f}" if "pb_per_inning" in baseline_metrics else f"PB Rate: {current_pb:.3f} vs —",
            ]
            self._set_baseline_compare_text("\n".join(lines))
        else:
            self._set_baseline_compare_text("No baseline selected. Save/import a season summary and choose it in Baseline Season.")

        rows = [
            dict(r)
            for r in self.db.get_recent_games_with_stats(
                self.active_player_id,
                limit=10,
                season=season,
                start_date=start_date,
                end_date=end_date,
            )
        ]
        self.trends_vars["OPS"].set(f"OPS: {compute_last5_trend(rows, per_game_ops)}")
        self.trends_vars["SO_RATE"].set(
            f"SO Rate (SO/PA): {compute_last5_trend(rows, per_game_so_rate, inverse_better=True)}"
        )
        self.trends_vars["CS_PCT"].set(f"CS%: {compute_last5_trend(rows, per_game_cs_pct)}")
        self.trends_vars["PB_RATE"].set(
            f"PB Rate: {compute_last5_trend(rows, per_game_pb_rate, inverse_better=True)}"
        )
        self._refresh_performance_trends(season=season, start_date=start_date, end_date=end_date)
        self._refresh_recent_notes(season=season, start_date=start_date, end_date=end_date)
        self._refresh_practice_week_panel()
        self._refresh_development_profile()
        self._refresh_consistency(season=season, start_date=start_date, end_date=end_date)
        self._refresh_focus_suggestions(season=season, start_date=start_date, end_date=end_date)
        shared_suggestions = get_suggestions(
            {
                "ops": hitting.get("OPS"),
                "k_rate": season_window.get("K_RATE"),
                "cs_pct": catching.get("CS%"),
                "pb_rate": catching.get("PB Rate"),
                "pop_time": pop_avg,
                "exchange": None,
            }
        )
        lines = []
        for idx, s in enumerate(shared_suggestions, start=1):
            lines.append(f"{idx}. {s['title']}")
            lines.append(f"   Why: {s['why']}")
            for drill in s.get("drills", [])[:2]:
                lines.append(f"   - {drill}")
            lines.append("")
        self._set_shared_suggestions_text("\n".join(lines).strip())
        self.refresh_trends_chart()
