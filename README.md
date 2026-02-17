# StatForge by Anchor & Honor

Local, offline-first desktop stat tracker plus private Streamlit demo.

## Project Layout
- `statforge_core/`: shared reusable logic (metrics, trends, season-summary parsing, consistency, pop-time math, CSV import/export).
- `statforge_tk/`: Tkinter desktop app package (UI + DB) using `statforge_core`.
- `statforge_web/`: Streamlit web demo app using `statforge_core` and anonymized bundled data.
- `app.py`: desktop Tkinter entrypoint.

## Requirements
- Python 3.11+
- Tkinter (included with most standard Python installs)
- ReportLab for PDF export:
  ```bash
  pip install reportlab
  ```
- Video ingestion dependencies:
  ```bash
  pip install opencv-python ffmpeg-python imageio-ffmpeg numpy scipy matplotlib streamlit pandas
  ```
- Auto-detect audio extraction uses system `ffmpeg` when available and falls back to `imageio-ffmpeg`.

## Run
### Option 1 (no terminal typing)
- In Finder, open `/Users/louisgreenhoe/Documents/StatForge_v1_/`
- Double-click `StatForge.command` (it auto-creates `.venv`, installs `requirements.txt`, then launches)

### Option 2 (terminal)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

On first run, a local SQLite database file (`statforge.db`) is created automatically in the project root.

## Quick Smoke Test
- Desktop (full app with local storage):
  ```bash
  python app.py
  ```
- Web demo (read-only showroom):
  ```bash
  streamlit run statforge_web/app.py
  ```

## Features (V1)
- Create and edit players
- Select active player
- Add game (date/opponent/notes)
- Enter stat line for each game
- Dashboard with season totals and derived metrics
- Last-5-game trend arrows (vs previous 5) for OPS, SO rate, CS%, PB rate

## Streamlit Web Demo (Anonymized)
The web demo is intentionally separate and uses anonymized data only.

### Local run
```bash
export STATFORGE_WEB_PASSWORD="set-a-demo-password"
streamlit run statforge_web/app.py
```

### Streamlit Community Cloud deploy (GitHub-connected)
1. Push this repository to GitHub.
2. In Streamlit Community Cloud, create a new app from the repo.
3. Set `Main file path` to `statforge_web/app.py`.
4. In app `Settings` -> `Secrets`, add:
   ```toml
   APP_PASSWORD = "set-a-strong-demo-password"
   ```
5. Deploy and share with your tester.

### Demo privacy defaults
- Player names are anonymized (`Demo Catcher`, `Demo Player 2`).
- No team names, opponent fields, jersey numbers, or personal dates in demo data.
- No upload storage flow in the Streamlit demo.

### Demo dataset maintenance
- Main deterministic dataset: `statforge_web/demo_data/demo_dataset.json`
- Validator: `python -m statforge_web.demo_data_validator`
- Keep all demo-only data isolated under `statforge_web/` so desktop/local DB workflows remain unaffected.
