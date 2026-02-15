from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Theme:
    NAVY = "#0B1C2C"
    NAVY_2 = "#0F253A"
    GUNMETAL = "#2A2F36"
    LIGHT_BG = "#F4F6F8"
    CARD_BG = "#FFFFFF"
    TEXT = "#101820"
    MUTED = "#6B7785"
    ACCENT = "#2EA3FF"
    SUCCESS = "#2BB673"
    WARNING = "#FFB020"
    DANGER = "#D64545"


def apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(bg=Theme.LIGHT_BG)

    style.configure("TFrame", background=Theme.LIGHT_BG)
    style.configure("Card.TFrame", background=Theme.CARD_BG, relief="solid", borderwidth=1)
    style.configure("Header.TFrame", background=Theme.NAVY)

    style.configure(
        "TLabel",
        background=Theme.LIGHT_BG,
        foreground=Theme.TEXT,
        font=("Segoe UI", 10),
    )
    style.configure(
        "Muted.TLabel",
        background=Theme.LIGHT_BG,
        foreground=Theme.MUTED,
        font=("Segoe UI", 9),
    )
    style.configure("Header.TLabel", background=Theme.NAVY, foreground="#FFFFFF")
    style.configure(
        "HeaderTitle.TLabel",
        background=Theme.NAVY,
        foreground="#FFFFFF",
        font=("Segoe UI", 19, "bold"),
    )
    style.configure(
        "HeaderSubtitle.TLabel",
        background=Theme.NAVY,
        foreground="#8FA0AD",
        font=("Segoe UI", 9),
    )

    style.configure(
        "TButton",
        font=("Segoe UI", 10),
        padding=(12, 7),
        background=Theme.CARD_BG,
        foreground=Theme.TEXT,
        borderwidth=1,
    )
    style.map(
        "TButton",
        background=[("active", Theme.NAVY_2), ("pressed", Theme.NAVY)],
        foreground=[("active", "#FFFFFF"), ("pressed", "#FFFFFF")],
        bordercolor=[("focus", Theme.ACCENT)],
    )

    style.configure(
        "TEntry",
        padding=6,
        fieldbackground=Theme.CARD_BG,
        foreground=Theme.TEXT,
        borderwidth=1,
    )

    style.configure("TCombobox", padding=5)

    style.configure(
        "TNotebook",
        background=Theme.NAVY_2,
        borderwidth=0,
        tabmargins=(8, 8, 8, 0),
    )
    style.configure(
        "TNotebook.Tab",
        font=("Segoe UI", 10, "bold"),
        padding=(14, 8, 14, 8),
        background=Theme.NAVY_2,
        foreground="#FFFFFF",
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", Theme.LIGHT_BG), ("active", Theme.NAVY)],
        foreground=[("selected", Theme.TEXT), ("active", "#FFFFFF")],
        lightcolor=[("selected", Theme.ACCENT), ("active", Theme.NAVY_2)],
        darkcolor=[("selected", Theme.ACCENT), ("active", Theme.NAVY_2)],
        bordercolor=[("selected", Theme.ACCENT), ("active", Theme.NAVY_2)],
    )

    style.configure(
        "Card.TLabelframe",
        background=Theme.CARD_BG,
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=Theme.CARD_BG,
        foreground=Theme.GUNMETAL,
        font=("Segoe UI", 10, "bold"),
    )

    style.configure(
        "Treeview",
        background=Theme.CARD_BG,
        fieldbackground=Theme.CARD_BG,
        foreground=Theme.TEXT,
        rowheight=24,
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        font=("Segoe UI", 10, "bold"),
        background=Theme.NAVY_2,
        foreground="#FFFFFF",
    )
    style.map("Treeview", background=[("selected", Theme.ACCENT)], foreground=[("selected", Theme.TEXT)])
