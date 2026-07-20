#!/usr/bin/env bash
# One-command launcher: sets up a venv, installs Flask, and serves the app on your
# local network so your phone (same Wi-Fi) can reach it.
set -e
cd "$(dirname "$0")/.."                     # repo root
if [ ! -d .venv ]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r webapp/requirements.txt
export MTG_HOST="${MTG_HOST:-0.0.0.0}"      # allow phone access on the LAN
export MTG_PORT="${MTG_PORT:-5000}"
exec python3 webapp/app.py
