"""Configuration for Dragon Ball: Multiverse Legends."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent
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
OWNER_IDS: tuple[int, ...] = ADMIN_IDS
DB_PATH: str = (
    os.getenv("ULTIMATE_DB_PATH", "").strip()
    or str(BASE_DIR / "ultimate.db")
)
BACKUP_DIR: str = (
    os.getenv("ULTIMATE_BACKUP_DIR", "").strip()
    or str(BASE_DIR / "backups" / "ultimate")
)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"


def _parse_chat_id(raw: str | None):
    value = (raw or "").strip()
    if not value:
        return None
    if value.lstrip("-").isdigit():
        return int(value)
    return value


QUERY_GROUP_ID = _parse_chat_id(os.getenv("QUERY_GROUP_ID") or os.getenv("QUERY_ADMIN_GC"))

GAME_NAME = "Dragon Ball: Multiverse Legends"
GAME_VERSION = "2.1.0"
DEFAULT_SERIES = "dragonball"

GACHA_COST_TICKET = 1
GACHA_COST_GEMS = 100
GACHA_MULTI_COST_GEMS = 900
GACHA_PITY = 120
STARTING_YENS = 3000
STARTING_GEMS = 150
STARTING_CRYSTALS = 60
STARTING_TICKETS = 5
MAX_STAMINA = 100
STAMINA_REGEN_SECONDS = 240
CLAN_CREATE_YENS = 2500
CLAN_CREATE_CRYSTALS = 50
MAX_TEAM = 3
REWARD_SCALE_MIN = 1
REWARD_SCALE_MAX = 1
BATTLE_REWARD_SCALE_MIN = 1
BATTLE_REWARD_SCALE_MAX = 1
PET_SUMMON_COSTS = {1: 1000, 10: 10000, 50: 50000}
PET_SUMMON_PITY = 100
TRADE_MAX_OFFERS = 20
EQUIP_PULL_COST_YENS = 1200
EQUIP_PULL_MULTI_COST_YENS = 10000
EQUIP_PULL_MULTI_COUNT = 10


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and int(user_id) in ADMIN_IDS


def validate() -> list[str]:
    problems: list[str] = []
    if not BOT_TOKEN:
        problems.append("BOT_TOKEN is missing. Set it in .env.")
    elif ":" not in BOT_TOKEN:
        problems.append("BOT_TOKEN does not look like a Telegram bot token.")
    if not ADMIN_IDS:
        problems.append("ADMIN_IDS is empty; admin commands will be unavailable.")
    return problems

IMAGE_DIR = str(Path(__file__).resolve().parent / "generated")
