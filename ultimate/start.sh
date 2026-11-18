#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN=".venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python || command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "Missing a Python interpreter. Install python3 or create .venv." >&2
  exit 1
fi

exec "$PYTHON_BIN" ultimate/main.py
