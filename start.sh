#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv/bin/python" >&2
  exit 1
fi

child=""
trap 'kill "$child" 2>/dev/null; exit 0' TERM INT

while true; do
  .venv/bin/python ultimate/main.py >> ultimate/bot.log 2>&1 &
  child=$!
  wait "$child"
  code=$?
  echo "$(date -u +'%Y-%m-%d %H:%M:%S UTC') | WATCHDOG | bot exited with code $code; restarting in 5s" >> ultimate/bot.log
  sleep 5
done
