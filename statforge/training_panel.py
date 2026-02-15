from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from styles.theme import Theme
from .training_data import get_stat_training


class TrainingSuggestionPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        stat_key: str,
        stat_title: str,
        current_value: str = "—",
    ) -> None:
        super().__init__(parent, padding=12, style="Card.TFrame")
        self.stat_key = stat_key
        self.stat_title = stat_title
        self.current_value = current_value
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self,
            text=f"{self.stat_title} Development",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        payload = get_stat_training(self.stat_key)
        if payload is None:
            ttk.Label(self, text="Training suggestions coming soon.", style="Muted.TLabel").pack(anchor="w")
            return

        ttk.Label(self, text=payload.get("description", ""), wraplength=560, justify=tk.LEFT).pack(anchor="w", pady=(0, 8))
        ttk.Label(self, text=f"Current Value: {self.current_value}").pack(anchor="w")
        ttk.Label(self, text=f"Target Range: {payload.get('target_range', '—')}").pack(anchor="w", pady=(0, 8))

        ttk.Label(self, text="Focus Areas", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        for area in payload.get("focus_areas", []):
            ttk.Label(self, text=f"- {area}", style="Muted.TLabel").pack(anchor="w")

        drills = payload.get("drills", [])
        if drills:
            ttk.Label(self, text="Drills", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(10, 4))
            for drill in drills[:3]:
                card = ttk.LabelFrame(self, text=str(drill.get("name", "Drill")), padding=8, style="Card.TLabelframe")
                card.pack(fill=tk.X, pady=4)
                ttk.Label(card, text=f"Why: {drill.get('why', '—')}", wraplength=540, justify=tk.LEFT).pack(anchor="w")
                ttk.Label(card, text=f"Sets/Reps: {drill.get('sets', '—')}", foreground=Theme.MUTED).pack(anchor="w", pady=(4, 0))
