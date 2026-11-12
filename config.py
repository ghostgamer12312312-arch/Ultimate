"""Configuration loaded from environment / .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)


def _parse_admin_ids(raw: str | None) -> tuple[int, ...]:
    ids: list[int] = []
    for chunk in (raw or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ids.append(int(chunk))
    return tuple(ids)


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS: tuple[int, ...] = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "rpg.db")).strip() or str(BASE_DIR / "rpg.db")
BACKUP_DIR: str = os.getenv("BACKUP_DIR", str(BASE_DIR / "backups")).strip() or str(BASE_DIR / "backups")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

GAME_NAME = "Aetherfall RPG"


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and int(user_id) in ADMIN_IDS


def validate() -> list[str]:
    """Return a list of configuration problems (empty when valid)."""
    problems: list[str] = []
    if not BOT_TOKEN:
        problems.append("BOT_TOKEN is missing. Set it in .env (see .env.example).")
    elif ":" not in BOT_TOKEN:
        problems.append("BOT_TOKEN does not look like a Telegram bot token.")
    if not ADMIN_IDS:
        problems.append("ADMIN_IDS is empty; admin commands will be unavailable.")
    return problems
