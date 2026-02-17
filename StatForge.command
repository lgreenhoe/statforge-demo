#!/bin/zsh

echo "Starting StatForge..."
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

echo "Launching Desktop App..."
python app.py
exit_code=$?

if [[ $exit_code -ne 0 ]]; then
  echo "Desktop app exited with code $exit_code."
  read -p "Press Enter to close..."
fi
