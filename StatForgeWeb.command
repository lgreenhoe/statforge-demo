#!/bin/zsh

echo "Starting StatForge Web..."
cd ~/Documents/StatForge_v1_ || {
  echo "Could not change to project root."
  read -p "Press Enter to close..."
  exit 1
}

echo "Activating environment..."
if [[ -f ".venv/bin/activate" ]]; then
  source .venv/bin/activate
else
  echo ".venv not found, skipping activation."
fi

echo "Diagnostics:"
pwd
python --version
which python
if ! command -v streamlit >/dev/null 2>&1; then
  echo "Error: streamlit command not found. Install dependencies in .venv first."
  read -p "Press Enter to close..."
  exit 1
fi
which streamlit

echo "Launching Streamlit..."
streamlit run statforge_web/app.py --server.port 8501 &
streamlit_pid=$!

sleep 2
open "http://localhost:8501"

wait $streamlit_pid
exit_code=$?

if [[ $exit_code -ne 0 ]]; then
  echo "Streamlit exited with code $exit_code."
  read -p "Press Enter to close..."
fi
