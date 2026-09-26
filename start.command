#!/usr/bin/env bash
# Launcher: cd's into this project regardless of where it's run from,
# sets up the virtualenv on first run, then starts the TUI.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [[ ! -d .venv ]]; then
  echo "First run: creating virtual environment and installing dependencies..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip -q
  .venv/bin/pip install -r requirements.txt -q
fi

exec .venv/bin/python run.py
