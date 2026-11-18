#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"

PYTHON_BIN=".venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python || command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "Missing a Python interpreter. Install python3 or create .venv." >&2
  exit 1
fi

child=""
trap 'kill "$child" 2>/dev/null; exit 0' TERM INT

while true; do
  "$PYTHON_BIN" ultimate/main.py >> ultimate/bot.log 2>&1 &
  child=$!
  wait "$child"
  code=$?
  echo "$(date -u +'%Y-%m-%d %H:%M:%S UTC') | WATCHDOG | bot exited with code $code; restarting in 5s" >> ultimate/bot.log
  sleep 5
done
