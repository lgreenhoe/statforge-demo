# StatForge Streamlit Demo

This is a separate web demo app that reuses shared logic from `statforge_core/`.

## Privacy / Safety
- Uses bundled anonymized demo data only (multiple fake teams/players).
- Team/opponent labels are generic demo labels only.
- No upload feature is enabled, and no user-uploaded files are stored.
- Web demo runs in read-only draft mode; changes are not persisted.

## Demo vs Desktop
### Web Demo (Read-only)
- Explore workflow with anonymized sample data
- View dashboard, trends, training focus recommendations, and video review checklists
- Draft mode only: no persistent saves
- No real player uploads or cloud storage

### Desktop Edition (Full App)
- Create/edit/save teams, games, players locally
- CSV import/export for real teams
- Position-aware video analysis protocols with local workflows
- Offline local data storage
- Printable reports and exports

## Local Run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
cd ..
streamlit run statforge_web/app.py
```

Set password in env:
```bash
export STATFORGE_WEB_PASSWORD="your-demo-password"
```

## Streamlit Community Cloud Deploy (GitHub-connected)
1. Push this repo to GitHub.
2. In Streamlit Community Cloud, create a new app from your repo.
3. Set `Main file path` to `statforge_web/app.py`.
4. In app `Settings` -> `Secrets`, add:
   ```toml
   APP_PASSWORD = "your-demo-password"
   ```
5. Deploy.

## No Indexing
The app injects a `noindex,nofollow` robots meta tag at runtime to discourage indexing.

## Demo Dataset (JSON)
The web demo can load a deterministic multi-team dataset from:

- `statforge_web/demo_data/demo_dataset.json`

### Editing demo data
Keep the structure stable per team:
- `team_name`
- `players[]` with: `player_id`, `player_name`, `position`, `level`
- `games[]` with: `season_label`, `game_no`, `date`, `opponent`, `player_stats[]`
- `player_stats[]` with:
  `player_id`, `ab`, `h`, `doubles`, `triples`, `hr`, `bb`, `so`, `rbi`, `sb`, `cs`, `innings_caught`, `passed_balls`, `sb_allowed`, `cs_caught`
- `practice_sessions[]` with:
  `player_id`, `season_label`, `session_no`, `date`, `transfer_time`, `pop_time`

### Validate after edits
From repo root:
```bash
python -m statforge_web.demo_data_validator
```
