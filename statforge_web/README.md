# StatForge Streamlit Demo

This is a separate web demo app that reuses shared logic from `statforge_core/`.

## Privacy / Safety
- Uses bundled anonymized demo data only:
  - `Demo Catcher`
  - `Demo Player 2`
- No team names, opponent names, jersey numbers, or real player dates.
- No upload feature is enabled, and no user-uploaded files are stored.

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
