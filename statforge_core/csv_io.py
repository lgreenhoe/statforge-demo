from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def export_rows_to_csv(path: str | Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and fieldnames is None:
        fieldnames = []
    if fieldnames is None and rows:
        fieldnames = list(rows[0].keys())

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames or [])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def import_rows_from_csv(path: str | Path) -> list[dict[str, str]]:
    in_path = Path(path)
    with in_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]
