#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv/bin/python" >&2
  exit 1
fi

exec .venv/bin/python ultimate/main.py >> ultimate/bot.log 2>&1
