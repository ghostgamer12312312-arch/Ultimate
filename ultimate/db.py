"""SQLite persistence for Dragon Ball: Multiverse Legends."""

from __future__ import annotations

import json
import random
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

try:
    from . import config, data
except ImportError:
    import config
    import data


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _now() -> str:
    return _utcnow().isoformat(timespec="seconds")


def today_key() -> str:
    return date.today().isoformat()


def week_key() -> str:
    year, week, _ = date.today().isocalendar()
    return f"{year}-W{week:02d}"


def month_key() -> str:
    return date.today().strftime("%Y-%m")


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    series TEXT NOT NULL DEFAULT 'dragonball',
    rank TEXT NOT NULL DEFAULT 'Rookie',
    level INTEGER NOT NULL DEFAULT 1,
    exp INTEGER NOT NULL DEFAULT 0,
    yens INTEGER NOT NULL DEFAULT 3000,
    gems INTEGER NOT NULL DEFAULT 150,
    crystals INTEGER NOT NULL DEFAULT 60,
    tickets INTEGER NOT NULL DEFAULT 5,
    stamina INTEGER NOT NULL DEFAULT 100,
    max_stamina INTEGER NOT NULL DEFAULT 100,
    stamina_updated INTEGER NOT NULL DEFAULT 0,
    hp INTEGER NOT NULL DEFAULT 1000,
    current_hp INTEGER NOT NULL DEFAULT 1000,
    mp INTEGER NOT NULL DEFAULT 200,
    max_mp INTEGER NOT NULL DEFAULT 200,
    atk INTEGER NOT NULL DEFAULT 100,
    def INTEGER NOT NULL DEFAULT 50,
    spd INTEGER NOT NULL DEFAULT 30,
    strength INTEGER NOT NULL DEFAULT 10,
    agility INTEGER NOT NULL DEFAULT 10,
    intellect INTEGER NOT NULL DEFAULT 10,
    vitality INTEGER NOT NULL DEFAULT 10,
    luck INTEGER NOT NULL DEFAULT 10,
    stat_points INTEGER NOT NULL DEFAULT 0,
    skill_points INTEGER NOT NULL DEFAULT 3,
    equipped_char TEXT,
    team TEXT NOT NULL DEFAULT '[]',
    weapon TEXT,
    armor TEXT,
    accessory TEXT,
    title TEXT NOT NULL DEFAULT 'title_rookie',
    avatar TEXT NOT NULL DEFAULT 'rookie',
    clan_id INTEGER,
    daily_day TEXT,
    daily_streak INTEGER NOT NULL DEFAULT 0,
    weekly_week TEXT,
    monthly_month TEXT,
    npc_streak INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    boss_kills INTEGER NOT NULL DEFAULT 0,
    gacha_pulls INTEGER NOT NULL DEFAULT 0,
    pity INTEGER NOT NULL DEFAULT 0,
    pet_pity INTEGER NOT NULL DEFAULT 0,
    starter_claimed INTEGER NOT NULL DEFAULT 0,
    raid_damage INTEGER NOT NULL DEFAULT 0,
    total_battles INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    pvp_wins INTEGER NOT NULL DEFAULT 0,
    arena_rating INTEGER NOT NULL DEFAULT 1000,
    clan_donation INTEGER NOT NULL DEFAULT 0,
    market_sales INTEGER NOT NULL DEFAULT 0,
    travel TEXT NOT NULL DEFAULT 'dragonball',
    banned INTEGER NOT NULL DEFAULT 0,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    char_id TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    stars INTEGER NOT NULL DEFAULT 1,
    exp INTEGER NOT NULL DEFAULT 0,
    awakened INTEGER NOT NULL DEFAULT 0,
    acquired_at TEXT NOT NULL,
    UNIQUE(user_id, char_id)
);

CREATE TABLE IF NOT EXISTS character_shards (
    user_id INTEGER NOT NULL,
    char_id TEXT NOT NULL,
    qty INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(user_id, char_id)
);

CREATE TABLE IF NOT EXISTS pets (
    user_id INTEGER NOT NULL,
    pet_id TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    equipped INTEGER NOT NULL DEFAULT 0,
    acquired_at TEXT NOT NULL,
    PRIMARY KEY(user_id, pet_id)
);

CREATE TABLE IF NOT EXISTS items (
    user_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    qty INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(user_id, item_id)
);

CREATE TABLE IF NOT EXISTS gear (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    gear_id TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    equipped_slot TEXT,
    acquired_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
    user_id INTEGER NOT NULL,
    skill_id TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    equipped INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(user_id, skill_id)
);

CREATE TABLE IF NOT EXISTS counters (
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    period_key TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(user_id, key, period_key)
);

CREATE TABLE IF NOT EXISTS quest_claims (
    user_id INTEGER NOT NULL,
    quest_id TEXT NOT NULL,
    period_key TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY(user_id, quest_id, period_key)
);

CREATE TABLE IF NOT EXISTS achievement_claims (
    user_id INTEGER NOT NULL,
    achievement_id TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY(user_id, achievement_id)
);

CREATE TABLE IF NOT EXISTS clans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    tag TEXT NOT NULL UNIQUE,
    leader_id INTEGER NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    exp INTEGER NOT NULL DEFAULT 0,
    treasury_yens INTEGER NOT NULL DEFAULT 0,
    treasury_gems INTEGER NOT NULL DEFAULT 0,
    treasury_crystals INTEGER NOT NULL DEFAULT 0,
    announcement TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clan_members (
    clan_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TEXT NOT NULL,
    donation INTEGER NOT NULL DEFAULT 0,
    weekly_points INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(clan_id, user_id)
);

CREATE TABLE IF NOT EXISTS clan_raids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clan_id INTEGER NOT NULL,
    raid_id TEXT NOT NULL,
    hp INTEGER NOT NULL,
    max_hp INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL,
    ends_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clan_raid_damage (
    clan_raid_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    damage INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(clan_raid_id, user_id)
);

CREATE TABLE IF NOT EXISTS world_boss (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boss_id TEXT NOT NULL,
    cycle TEXT NOT NULL,
    hp INTEGER NOT NULL,
    max_hp INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL,
    ends_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_boss_damage (
    cycle TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    damage INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(cycle, user_id)
);

CREATE TABLE IF NOT EXISTS market (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    item_id TEXT NOT NULL,
    qty INTEGER NOT NULL DEFAULT 1,
    price INTEGER NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS duel_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenger_id INTEGER NOT NULL,
    opponent_id INTEGER NOT NULL,
    winner_id INTEGER,
    rating_change INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS battle_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    enemy_name TEXT NOT NULL,
    result TEXT NOT NULL,
    damage INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS boss_progress (
    user_id INTEGER NOT NULL,
    boss_id TEXT NOT NULL,
    hp INTEGER NOT NULL,
    max_hp INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL,
    PRIMARY KEY(user_id, boss_id)
);

CREATE TABLE IF NOT EXISTS summon_bosses (
    user_id INTEGER NOT NULL,
    boss_id TEXT NOT NULL,
    hp INTEGER NOT NULL,
    max_hp INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL,
    PRIMARY KEY(user_id, boss_id)
);

CREATE TABLE IF NOT EXISTS chapter_progress (
    user_id INTEGER NOT NULL,
    series TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    cleared_at TEXT NOT NULL,
    PRIMARY KEY(user_id, series, chapter)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    initiator_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    offers TEXT NOT NULL DEFAULT '{}',
    initiator_ok INTEGER NOT NULL DEFAULT 0,
    target_ok INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clan_invites (
    clan_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    invited_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(clan_id, user_id)
);

CREATE TABLE IF NOT EXISTS active_battles (
    battle_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    mode TEXT NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_art (
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    name TEXT NOT NULL,
    file_id TEXT NOT NULL,
    uploaded_by INTEGER,
    uploaded_at TEXT NOT NULL,
    PRIMARY KEY(entity_type, entity_key)
);

CREATE TABLE IF NOT EXISTS redeem_codes (
    code TEXT PRIMARY KEY,
    rewards TEXT NOT NULL,
    max_uses INTEGER NOT NULL DEFAULT 1,
    used_count INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS redeem_claims (
    code TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY(code, user_id)
);

CREATE INDEX IF NOT EXISTS idx_active_battles_user ON active_battles(user_id);
CREATE INDEX IF NOT EXISTS idx_custom_art_type ON custom_art(entity_type);
CREATE INDEX IF NOT EXISTS idx_characters_user ON characters(user_id);
CREATE INDEX IF NOT EXISTS idx_counters_user ON counters(user_id, key);
CREATE INDEX IF NOT EXISTS idx_clan_members_clan ON clan_members(clan_id);
CREATE INDEX IF NOT EXISTS idx_market_seller ON market(seller_id);
CREATE INDEX IF NOT EXISTS idx_world_damage_cycle ON world_boss_damage(cycle);
CREATE INDEX IF NOT EXISTS idx_trades_users ON trades(initiator_id, target_id, status);
CREATE INDEX IF NOT EXISTS idx_chapter_user ON chapter_progress(user_id, series);
"""

PLAYER_COLUMNS = {
    "username", "first_name", "series", "rank", "level", "exp", "yens", "gems",
    "crystals", "tickets", "stamina", "max_stamina", "stamina_updated", "hp",
    "current_hp", "atk", "def", "spd", "skill_points", "equipped_char", "team",
    "weapon", "armor", "accessory", "title", "avatar", "clan_id", "daily_day",
    "daily_streak", "weekly_week", "monthly_month", "npc_streak", "best_streak",
    "boss_kills", "gacha_pulls", "pity", "pet_pity", "starter_claimed", "raid_damage", "total_battles", "wins",
    "losses", "pvp_wins", "arena_rating", "clan_donation", "market_sales",
    "travel", "banned", "is_admin", "last_seen",
}

CURRENCY_COLUMNS = {"yens", "gems", "crystals", "tickets", "stamina", "skill_points"}
COUNTER_METRICS = {
    "hunt", "wins", "boss_kills", "gacha_pulls", "pvp_wins", "clan_donation",
    "raid_damage", "total_battles", "losses", "npc_streak", "market_sales",
    "characters", "level", "arena_rating", "series_dragonball", "series_naruto",
    "series_bleach", "series_jujutsu", "series_tempest", "dungeon", "fish", "mine",
}


class Database:
    def __init__(self, path: str | Path | None = None, *, auto_init: bool = True):
        self.path = str(path or config.DB_PATH)
        self._lock = threading.RLock()
        self._local = threading.local()
        if auto_init:
            self.init()

    def _pool(self) -> list[sqlite3.Connection]:
        pool = getattr(self._local, "pool", None)
        if pool is None:
            pool = []
            self._local.pool = pool
        return pool

    @contextmanager
    def conn(self):
        pool = self._pool()
        connection = pool.pop() if pool else None
        if connection is None:
            connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA cache_size=-8000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if len(pool) < 8:
                pool.append(connection)
            else:
                connection.close()

    def close(self) -> None:
        pool = getattr(self._local, "pool", None) or []
        for connection in pool:
            try:
                connection.close()
            except sqlite3.Error:
                pass
        self._local.pool = []

    def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            self._migrate(c)
            self._ensure_world_boss(c)

    def _migrate(self, c: sqlite3.Connection) -> None:
        migrations = {
            "players": {
                "hp": "INTEGER NOT NULL DEFAULT 1000",
                "current_hp": "INTEGER NOT NULL DEFAULT 1000",
                "mp": "INTEGER NOT NULL DEFAULT 200",
                "max_mp": "INTEGER NOT NULL DEFAULT 200",
                "atk": "INTEGER NOT NULL DEFAULT 100",
                "def": "INTEGER NOT NULL DEFAULT 50",
                "spd": "INTEGER NOT NULL DEFAULT 30",
                "strength": "INTEGER NOT NULL DEFAULT 10",
                "agility": "INTEGER NOT NULL DEFAULT 10",
                "intellect": "INTEGER NOT NULL DEFAULT 10",
                "vitality": "INTEGER NOT NULL DEFAULT 10",
                "luck": "INTEGER NOT NULL DEFAULT 10",
                "stat_points": "INTEGER NOT NULL DEFAULT 0",
                "skill_points": "INTEGER NOT NULL DEFAULT 3",
                "equipped_char": "TEXT",
                "team": "TEXT NOT NULL DEFAULT '[]'",
                "weapon": "TEXT",
                "armor": "TEXT",
                "accessory": "TEXT",
                "title": "TEXT NOT NULL DEFAULT 'title_rookie'",
                "avatar": "TEXT NOT NULL DEFAULT 'rookie'",
                "clan_id": "INTEGER",
                "weekly_week": "TEXT",
                "monthly_month": "TEXT",
                "npc_streak": "INTEGER NOT NULL DEFAULT 0",
                "best_streak": "INTEGER NOT NULL DEFAULT 0",
                "boss_kills": "INTEGER NOT NULL DEFAULT 0",
                "gacha_pulls": "INTEGER NOT NULL DEFAULT 0",
                "pity": "INTEGER NOT NULL DEFAULT 0",
                "pet_pity": "INTEGER NOT NULL DEFAULT 0",
                "starter_claimed": "INTEGER NOT NULL DEFAULT 0",
                "raid_damage": "INTEGER NOT NULL DEFAULT 0",
                "total_battles": "INTEGER NOT NULL DEFAULT 0",
                "wins": "INTEGER NOT NULL DEFAULT 0",
                "losses": "INTEGER NOT NULL DEFAULT 0",
                "pvp_wins": "INTEGER NOT NULL DEFAULT 0",
                "arena_rating": "INTEGER NOT NULL DEFAULT 1000",
                "clan_donation": "INTEGER NOT NULL DEFAULT 0",
                "market_sales": "INTEGER NOT NULL DEFAULT 0",
                "travel": "TEXT NOT NULL DEFAULT 'dragonball'",
                "banned": "INTEGER NOT NULL DEFAULT 0",
                "is_admin": "INTEGER NOT NULL DEFAULT 0",
                "stamina_updated": "INTEGER NOT NULL DEFAULT 0",
            },
            "clans": {
                "description": "TEXT NOT NULL DEFAULT ''",
                "open_join": "INTEGER NOT NULL DEFAULT 1",
                "min_level": "INTEGER NOT NULL DEFAULT 1",
            },
        }
        for table, columns in migrations.items():
            existing = {row["name"] for row in c.execute(f"PRAGMA table_info({table})")}
            for column, definition in columns.items():
                if column not in existing:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ensure_world_boss(self, c: sqlite3.Connection) -> None:
        cycle = self._world_cycle()
        row = c.execute("SELECT * FROM world_boss WHERE cycle=? AND status='active'", (cycle,)).fetchone()
        if row is not None:
            return
        boss = data.WORLD_BOSSES[int(cycle) % len(data.WORLD_BOSSES)]
        now = _utcnow()
        ends = (now + timedelta(days=1)).isoformat(timespec="seconds")
        c.execute(
            "INSERT INTO world_boss(boss_id, cycle, hp, max_hp, status, started_at, ends_at) VALUES(?,?,?,?,'active',?,?)",
            (boss["id"], cycle, boss["hp"], boss["hp"], now.isoformat(timespec="seconds"), ends),
        )

    @staticmethod
    def _world_cycle() -> str:
        return str(int(time.time() // 86400))

    def ping(self) -> bool:
        with self.conn() as c:
            c.execute("SELECT 1").fetchone()
        return True

    def ensure_player(self, user_id: int, username: str | None = None, first_name: str | None = None) -> dict:
        now = _now()
        series = config.DEFAULT_SERIES
        with self.conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO players(user_id, username, first_name, series, created_at, last_seen, stamina_updated) VALUES(?,?,?,?,?,?,?)",
                (int(user_id), username or "", first_name or "", series, now, now, int(time.time())),
            )
            c.execute(
                "UPDATE players SET username=?, first_name=?, last_seen=? WHERE user_id=?",
                (username or "", first_name or "", now, int(user_id)),
            )
            row = c.execute("SELECT starter_claimed FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            starter_claimed = int(row["starter_claimed"] or 0) if row else 0
            created = c.execute("SELECT COUNT(*) AS n FROM characters WHERE user_id=?", (int(user_id),)).fetchone()["n"] == 0
        if created and not starter_claimed:
            self.grant_starter_pack(user_id, series)
        if created:
            self.add_pet(user_id, data.STARTER_PET)
        self.refresh_stamina(user_id)
        return self.player(user_id) or {}

    def grant_starter_pack(self, user_id: int, series: str | None = None) -> dict:
        """Claim the one-time starter pack for an account."""
        import random

        player = self.player(user_id)
        if player is not None and int(player.get("starter_claimed", 0) or 0):
            return {"ok": False, "reason": "You already claimed your starter pack."}
        pool = [
            cid for cid, character in data.CHARACTERS.items()
            if character.get("form") == "Base" and character.get("rarity") not in ("divine", "mythic")
        ] or [cid for cid in data.CHARACTERS if data.CHARACTERS[cid].get("rarity") not in ("divine", "mythic")]
        starter = random.choice(pool)
        self.add_character(user_id, starter, level=5, stars=1)
        self.set_field(user_id, "equipped_char", starter)
        self.set_field(user_id, "team", json.dumps([starter]))
        bundle = {
            "senzu_small": 12, "senzu_large": 4, "stamina_drink": 8,
            "exp_scroll": 5, "exp_tome": 2, "gacha_ticket": 3,
            "elite_key": 4, "boss_key": 5, "raid_token": 5,
            "awakening_stone": 2, "forge_core": 3, "crystal_shard": 5,
            "rank_common_core": 3, "rank_rare_core": 2,
            "weapon_scroll": 2, "armor_scroll": 2, "accessory_scroll": 2,
            "pet_treat": 5, "luck_charm": 2, "skill_scroll": 1,
        }
        for item_id, qty in bundle.items():
            if item_id in data.ITEMS:
                self.add_item(user_id, item_id, qty)
        gear_ids = []
        for slot in ("weapon", "armor", "accessory"):
            gear_pool = data.STARTER_GEAR_POOL.get(slot, [])
            if gear_pool:
                gear_ids.append(self.grant_gear(user_id, random.choice(gear_pool), 1))
        for instance_id, slot in zip(gear_ids, ("weapon", "armor", "accessory")):
            self.equip_gear(user_id, instance_id)
        if not self.pets(user_id):
            self.add_pet(user_id, data.STARTER_PET)
        yens = random.randint(1000, 10000)
        gems = random.randint(200, 800)
        crystals = random.randint(10, 50)
        self.give(user_id, yens=yens, gems=gems, crystals=crystals)
        self.set_field(user_id, "starter_claimed", 1)
        return {
            "ok": True, "starter": starter, "gear": gear_ids, "items": bundle,
            "yens": yens, "gems": gems, "crystals": crystals,
        }

    def claim_starter_pack(self, user_id: int) -> dict:
        return self.grant_starter_pack(user_id)

    def redeem_code_create(self, created_by: int, code: str, rewards: list[dict], max_uses: int = 1, expires_at: str | None = None) -> dict:
        code = (code or "").strip().upper()
        if not code or len(code) > 32 or not all(ch.isalnum() or ch in "-_" for ch in code):
            return {"ok": False, "reason": "Code must be 1-32 letters, numbers, - or _."}
        if not rewards:
            return {"ok": False, "reason": "A code needs at least one reward."}
        max_uses = max(1, min(1000000, int(max_uses)))
        with self.conn() as c:
            if c.execute("SELECT 1 FROM redeem_codes WHERE code=?", (code,)).fetchone():
                return {"ok": False, "reason": "That code already exists."}
            c.execute(
                "INSERT INTO redeem_codes(code, rewards, max_uses, used_count, created_by, created_at, expires_at) VALUES(?,?,?,0,?,?,?)",
                (code, json.dumps(rewards, ensure_ascii=False), max_uses, int(created_by), _now(), expires_at),
            )
        return {"ok": True, "code": code, "rewards": rewards, "max_uses": max_uses, "expires_at": expires_at}

    def redeem_code_info(self, code: str) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM redeem_codes WHERE code=?", ((code or "").strip().upper(),)).fetchone()
        item = _row_to_dict(row)
        if item:
            try:
                item["rewards"] = json.loads(item.get("rewards") or "[]")
            except json.JSONDecodeError:
                item["rewards"] = []
        return item

    def redeem_codes_list(self, limit: int = 20) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM redeem_codes ORDER BY created_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
        result = _rows_to_dicts(rows)
        for item in result:
            try:
                item["rewards"] = json.loads(item.get("rewards") or "[]")
            except json.JSONDecodeError:
                item["rewards"] = []
        return result

    def redeem_code_claim(self, user_id: int, code: str) -> dict:
        code = (code or "").strip().upper()
        if not code:
            return {"ok": False, "reason": "Usage: /redeem <code>"}
        with self.conn() as c:
            row = c.execute("SELECT * FROM redeem_codes WHERE code=?", (code,)).fetchone()
            if row is None:
                return {"ok": False, "reason": "Invalid or unknown code."}
            if row["expires_at"]:
                try:
                    if datetime.fromisoformat(row["expires_at"]) < _utcnow():
                        return {"ok": False, "reason": "That code has expired."}
                except ValueError:
                    pass
            if int(row["used_count"]) >= int(row["max_uses"]):
                return {"ok": False, "reason": "That code has reached its usage limit."}
            if c.execute("SELECT 1 FROM redeem_claims WHERE code=? AND user_id=?", (code, int(user_id))).fetchone():
                return {"ok": False, "reason": "You already redeemed that code."}
            c.execute("INSERT INTO redeem_claims(code, user_id, claimed_at) VALUES(?,?,?)", (code, int(user_id), _now()))
            c.execute("UPDATE redeem_codes SET used_count=used_count+1 WHERE code=?", (code,))
            try:
                rewards = json.loads(row["rewards"] or "[]")
            except json.JSONDecodeError:
                rewards = []
        applied = []
        for reward in rewards:
            kind = str(reward.get("kind", "")).lower()
            qty = max(1, int(reward.get("qty", 1) or 1))
            asset_id = str(reward.get("id", "") or "")
            if kind in CURRENCY_COLUMNS:
                self.add_currency(user_id, kind, qty)
            elif kind == "exp":
                self.add_exp(user_id, qty)
            elif kind == "item" and asset_id in data.ITEMS:
                self.add_item(user_id, asset_id, qty)
            elif kind == "character" and asset_id in data.CHARACTERS:
                self.add_character(user_id, asset_id, level=1, stars=1)
            elif kind == "pet" and asset_id in data.PETS:
                self.add_pet(user_id, asset_id)
            elif kind == "gear" and asset_id in data.GEAR:
                self.grant_gear(user_id, asset_id, qty)
            elif kind == "shard" and asset_id in data.CHARACTERS:
                self.add_shards(user_id, asset_id, qty)
            elif kind == "title" and asset_id in data.TITLES:
                self.set_field(user_id, "title", asset_id)
            else:
                continue
            applied.append({"kind": kind, "id": asset_id, "qty": qty})
        return {"ok": True, "code": code, "rewards": applied}

    def player(self, user_id: int) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM players WHERE user_id=?", (int(user_id),)).fetchone()
        return _row_to_dict(row)

    def require_player(self, user_id: int) -> dict:
        player = self.player(user_id)
        if player is None:
            player = self.ensure_player(user_id)
        return player

    def set_field(self, user_id: int, field: str, value) -> None:
        if field not in PLAYER_COLUMNS:
            raise ValueError(f"Invalid player field: {field}")
        with self.conn() as c:
            c.execute(f"UPDATE players SET {field}=? WHERE user_id=?", (value, int(user_id)))

    def add_currency(self, user_id: int, column: str, amount: int) -> None:
        if column not in CURRENCY_COLUMNS:
            raise ValueError(f"Invalid currency: {column}")
        with self.conn() as c:
            c.execute(f"UPDATE players SET {column}=MAX(0, {column}+?) WHERE user_id=?", (int(amount), int(user_id)))

    def spend(self, user_id: int, **amounts: int) -> bool:
        amounts = {key: int(value) for key, value in amounts.items() if int(value) > 0}
        if not amounts:
            return True
        if any(key not in CURRENCY_COLUMNS for key in amounts):
            raise ValueError("Invalid spend column")
        with self.conn() as c:
            row = c.execute("SELECT * FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if row is None:
                return False
            for key, amount in amounts.items():
                if row[key] < amount:
                    return False
            assignments = ", ".join(f"{key}={key}-?" for key in amounts)
            c.execute(f"UPDATE players SET {assignments} WHERE user_id=?", (*amounts.values(), int(user_id)))
        return True

    def give(self, user_id: int, **amounts: int) -> None:
        amounts = {key: int(value) for key, value in amounts.items() if int(value) != 0}
        for key, amount in amounts.items():
            if key not in CURRENCY_COLUMNS:
                raise ValueError(f"Invalid currency: {key}")
            self.add_currency(user_id, key, amount)

    def refresh_stamina(self, user_id: int) -> None:
        now = int(time.time())
        with self.conn() as c:
            row = c.execute("SELECT stamina, max_stamina, stamina_updated FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if row is None:
                return
            elapsed = max(0, now - int(row["stamina_updated"] or now))
            regen = elapsed // config.STAMINA_REGEN_SECONDS
            if regen <= 0:
                return
            stamina = min(int(row["max_stamina"]), int(row["stamina"]) + int(regen))
            c.execute(
                "UPDATE players SET stamina=?, stamina_updated=? WHERE user_id=?",
                (stamina, now - (elapsed % config.STAMINA_REGEN_SECONDS), int(user_id)),
            )

    def register(self, user_id: int, series: str, username: str | None = None, first_name: str | None = None) -> dict:
        if series not in data.SERIES:
            series = config.DEFAULT_SERIES
        self.ensure_player(user_id, username, first_name)
        self.set_field(user_id, "series", series)
        self.set_field(user_id, "travel", series)
        return self.player(user_id) or {}

    def add_exp(self, user_id: int, amount: int) -> dict:
        amount = max(0, int(amount))
        result = {"level_up": False, "levels": 0, "level": 1}
        with self.conn() as c:
            row = c.execute("SELECT level, exp FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if row is None:
                return result
            level = int(row["level"])
            exp = int(row["exp"]) + amount
            levels = 0
            while level < 100 and exp >= self.exp_needed(level):
                exp -= self.exp_needed(level)
                level += 1
                levels += 1
            c.execute("UPDATE players SET level=?, exp=?, rank=? WHERE user_id=?", (level, exp, data.rank_for_level(level)["name"], int(user_id)))
            result.update(level=level, levels=levels, level_up=levels > 0)
            if levels:
                c.execute("UPDATE players SET skill_points=skill_points+? WHERE user_id=?", (levels, int(user_id)))
        if result["level_up"]:
            self.bump(user_id, "level", result["level"])
        return result

    @staticmethod
    def exp_needed(level: int) -> int:
        return 80 + int(level ** 1.65 * 28)

    def characters(self, user_id: int) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM characters WHERE user_id=? ORDER BY level DESC, stars DESC, id", (int(user_id),)).fetchall()
        result = []
        for row in rows:
            base = data.CHARACTERS.get(row["char_id"])
            if base is None:
                continue
            item = dict(base)
            item.update({
                "instance_id": row["id"],
                "level": row["level"],
                "stars": row["stars"],
                "char_exp": row["exp"],
                "awakened": row["awakened"],
                "acquired_at": row["acquired_at"],
            })
            result.append(item)
        return result

    def has_character(self, user_id: int, char_id: str) -> bool:
        with self.conn() as c:
            row = c.execute("SELECT 1 FROM characters WHERE user_id=? AND char_id=?", (int(user_id), char_id)).fetchone()
        return row is not None

    def add_character(self, user_id: int, char_id: str, level: int = 1, stars: int = 1) -> tuple[bool, dict]:
        base = data.CHARACTERS.get(char_id)
        if base is None:
            raise ValueError(f"Unknown character: {char_id}")
        now = _now()
        with self.conn() as c:
            existing = c.execute("SELECT id FROM characters WHERE user_id=? AND char_id=?", (int(user_id), char_id)).fetchone()
            if existing is not None:
                c.execute(
                    "INSERT INTO character_shards(user_id, char_id, qty) VALUES(?,?,1) ON CONFLICT(user_id,char_id) DO UPDATE SET qty=qty+1",
                    (int(user_id), char_id),
                )
                duplicate = True
            else:
                c.execute(
                    "INSERT INTO characters(user_id, char_id, level, stars, acquired_at) VALUES(?,?,?,?,?)",
                    (int(user_id), char_id, max(1, int(level)), max(1, min(6, int(stars))), now),
                )
                duplicate = False
        if not duplicate:
            self.bump(user_id, "characters", 1)
            self.bump(user_id, f"series_{base['series']}", 1)
        return (not duplicate, base)

    def shards(self, user_id: int, char_id: str) -> int:
        with self.conn() as c:
            row = c.execute("SELECT qty FROM character_shards WHERE user_id=? AND char_id=?", (int(user_id), char_id)).fetchone()
        return int(row["qty"]) if row else 0

    def add_shards(self, user_id: int, char_id: str, qty: int) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO character_shards(user_id, char_id, qty) VALUES(?,?,?) ON CONFLICT(user_id,char_id) DO UPDATE SET qty=qty+?",
                (int(user_id), char_id, int(qty), int(qty)),
            )

    def take_shards(self, user_id: int, char_id: str, qty: int) -> bool:
        with self.conn() as c:
            row = c.execute("SELECT qty FROM character_shards WHERE user_id=? AND char_id=?", (int(user_id), char_id)).fetchone()
            if row is None or int(row["qty"]) < int(qty):
                return False
            c.execute("UPDATE character_shards SET qty=qty-? WHERE user_id=? AND char_id=?", (int(qty), int(user_id), char_id))
        return True

    def pets(self, user_id: int) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM pets WHERE user_id=? ORDER BY equipped DESC, level DESC, pet_id", (int(user_id),)).fetchall()
        result = []
        for row in rows:
            base = data.PETS.get(row["pet_id"])
            if base is None:
                continue
            pet = dict(base)
            pet.update({"pet_id": row["pet_id"], "level": row["level"], "equipped": bool(row["equipped"]), "acquired_at": row["acquired_at"]})
            result.append(pet)
        return result

    def add_pet(self, user_id: int, pet_id: str, level: int = 1) -> tuple[bool, dict]:
        base = data.PETS.get(pet_id)
        if base is None:
            raise ValueError(f"Unknown pet: {pet_id}")
        with self.conn() as c:
            existing = c.execute("SELECT 1 FROM pets WHERE user_id=? AND pet_id=?", (int(user_id), pet_id)).fetchone()
            if existing:
                c.execute("UPDATE pets SET level=MIN(50, level+1) WHERE user_id=? AND pet_id=?", (int(user_id), pet_id))
                return False, base
            equipped = 0 if c.execute("SELECT 1 FROM pets WHERE user_id=? AND equipped=1", (int(user_id),)).fetchone() else 1
            c.execute("INSERT INTO pets(user_id, pet_id, level, equipped, acquired_at) VALUES(?,?,?,?,?)", (int(user_id), pet_id, max(1, int(level)), equipped, _now()))
        return True, base

    def equip_pet(self, user_id: int, pet_id: str) -> bool:
        with self.conn() as c:
            row = c.execute("SELECT 1 FROM pets WHERE user_id=? AND pet_id=?", (int(user_id), pet_id)).fetchone()
            if not row:
                return False
            c.execute("UPDATE pets SET equipped=0 WHERE user_id=?", (int(user_id),))
            c.execute("UPDATE pets SET equipped=1 WHERE user_id=? AND pet_id=?", (int(user_id), pet_id))
        return True

    def feed_pet(self, user_id: int, pet_id: str, levels: int = 1) -> dict:
        levels = max(1, min(20, int(levels)))
        with self.conn() as c:
            row = c.execute("SELECT * FROM pets WHERE user_id=? AND pet_id=?", (int(user_id), pet_id)).fetchone()
            if row is None:
                return {"ok": False, "reason": "You do not own that companion."}
            current = int(row["level"])
            if current >= 50:
                return {"ok": False, "reason": "Companion is already max level."}
            actual = min(levels, 50 - current)
            cost = actual * (150 + current * 40)
            player = c.execute("SELECT yens FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if player is None or int(player["yens"]) < cost:
                return {"ok": False, "reason": f"Need {cost:,} yens."}
            c.execute("UPDATE players SET yens=yens-? WHERE user_id=?", (cost, int(user_id)))
            c.execute("UPDATE pets SET level=level+? WHERE user_id=? AND pet_id=?", (actual, int(user_id), pet_id))
        return {"ok": True, "level": current + actual, "cost": cost}

    def random_pet(self, user_id: int, premium: bool = False) -> dict:
        import random
        pool = list(data.PETS)
        if premium:
            pool = [pet_id for pet_id in pool if data.PETS[pet_id]["rarity"] in ("legendary", "mythic", "divine")]
        pet_id = random.choice(pool)
        new, base = self.add_pet(user_id, pet_id)
        return {"pet": base, "new": new}

    def level_character(self, user_id: int, char_id: str, levels: int = 1) -> dict:
        base = data.CHARACTERS.get(char_id)
        if base is None:
            return {"ok": False, "reason": "Unknown character."}
        levels = max(1, min(50, int(levels)))
        with self.conn() as c:
            row = c.execute("SELECT * FROM characters WHERE user_id=? AND char_id=?", (int(user_id), char_id)).fetchone()
            if row is None:
                return {"ok": False, "reason": "You do not own that character."}
            current = int(row["level"])
            if current >= 100:
                return {"ok": False, "reason": "This character is already level 100."}
            actual = min(levels, 100 - current)
            cost = sum(120 + level * 45 for level in range(current, current + actual))
            player = c.execute("SELECT yens FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if player is None or int(player["yens"]) < cost:
                return {"ok": False, "reason": f"Not enough yens. Need {cost:,}."}
            c.execute("UPDATE players SET yens=yens-? WHERE user_id=?", (cost, int(user_id)))
            c.execute("UPDATE characters SET level=level+? WHERE user_id=? AND char_id=?", (actual, int(user_id), char_id))
        return {"ok": True, "levels": actual, "level": current + actual, "cost": cost}

    def awaken_character(self, user_id: int, char_id: str) -> dict:
        with self.conn() as c:
            row = c.execute("SELECT * FROM characters WHERE user_id=? AND char_id=?", (int(user_id), char_id)).fetchone()
            if row is None:
                return {"ok": False, "reason": "You do not own that character."}
            stars = int(row["stars"])
            if stars >= 6:
                return {"ok": False, "reason": "This character is already 6 stars."}
            shard_row = c.execute("SELECT qty FROM character_shards WHERE user_id=? AND char_id=?", (int(user_id), char_id)).fetchone()
            owned = int(shard_row["qty"]) if shard_row else 0
            cost = 10 * stars
            if owned < cost:
                return {"ok": False, "reason": f"Need {cost} shards; you have {owned}."}
            c.execute("UPDATE character_shards SET qty=qty-? WHERE user_id=? AND char_id=?", (cost, int(user_id), char_id))
            c.execute("UPDATE characters SET stars=stars+1, awakened=1 WHERE user_id=? AND char_id=?", (int(user_id), char_id))
        return {"ok": True, "stars": stars + 1, "cost": cost}

    def team(self, user_id: int) -> list[str]:
        player = self.player(user_id) or {}
        try:
            team = json.loads(player.get("team") or "[]")
        except (TypeError, ValueError):
            team = []
        owned = {character["id"] for character in self.characters(user_id)}
        team = [char_id for char_id in team if char_id in owned]
        main = player.get("equipped_char")
        if main in owned and main not in team:
            team.insert(0, main)
        if not team and main in owned:
            team = [main]
        return team[: config.MAX_TEAM]

    def set_team(self, user_id: int, char_ids: list[str]) -> dict:
        owned = {character["id"] for character in self.characters(user_id)}
        cleaned: list[str] = []
        for char_id in char_ids:
            if char_id in owned and char_id not in cleaned:
                cleaned.append(char_id)
        if not cleaned:
            return {"ok": False, "reason": "You must choose at least one owned character."}
        cleaned = cleaned[: config.MAX_TEAM]
        self.set_field(user_id, "team", json.dumps(cleaned))
        self.set_field(user_id, "equipped_char", cleaned[0])
        return {"ok": True, "team": cleaned}

    def equip_character(self, user_id: int, char_id: str) -> bool:
        owned = {character["id"] for character in self.characters(user_id)}
        if char_id not in owned:
            return False
        team = self.team(user_id)
        if char_id in team:
            team.remove(char_id)
        team.insert(0, char_id)
        self.set_field(user_id, "team", json.dumps(team[: config.MAX_TEAM]))
        self.set_field(user_id, "equipped_char", char_id)
        return True

    def add_item(self, user_id: int, item_id: str, qty: int = 1) -> None:
        if item_id not in data.ITEMS:
            raise ValueError(f"Unknown item: {item_id}")
        with self.conn() as c:
            c.execute(
                "INSERT INTO items(user_id, item_id, qty) VALUES(?,?,?) ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+?",
                (int(user_id), item_id, int(qty), int(qty)),
            )

    def take_item(self, user_id: int, item_id: str, qty: int = 1) -> bool:
        with self.conn() as c:
            row = c.execute("SELECT qty FROM items WHERE user_id=? AND item_id=?", (int(user_id), item_id)).fetchone()
            if row is None or int(row["qty"]) < int(qty):
                return False
            c.execute("UPDATE items SET qty=qty-? WHERE user_id=? AND item_id=?", (int(qty), int(user_id), item_id))
        return True

    def items(self, user_id: int) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM items WHERE user_id=? AND qty>0 ORDER BY item_id", (int(user_id),)).fetchall()
        result = []
        for row in rows:
            base = data.ITEMS.get(row["item_id"])
            if base is None:
                continue
            item = dict(base)
            item.update({"item_id": row["item_id"], "qty": row["qty"]})
            result.append(item)
        return result

    def item_qty(self, user_id: int, item_id: str) -> int:
        with self.conn() as c:
            row = c.execute("SELECT qty FROM items WHERE user_id=? AND item_id=?", (int(user_id), item_id)).fetchone()
        return int(row["qty"]) if row else 0

    def add_dragon_ball(self, user_id: int, star: int | None = None) -> int:
        star = star or (self.dragon_ball_count(user_id) % 7 + 1)
        star = max(1, min(7, int(star)))
        self.add_item(user_id, f"dragon_ball_{star}", 1)
        return star

    def dragon_ball_count(self, user_id: int) -> int:
        with self.conn() as c:
            rows = c.execute("SELECT item_id, qty FROM items WHERE user_id=? AND item_id LIKE 'dragon_ball_%'", (int(user_id),)).fetchall()
        return sum(1 for row in rows if int(row["qty"]) > 0)

    def consume_dragon_balls(self, user_id: int) -> bool:
        with self.conn() as c:
            rows = c.execute("SELECT item_id, qty FROM items WHERE user_id=? AND item_id LIKE 'dragon_ball_%'", (int(user_id),)).fetchall()
            if len(rows) < 7:
                return False
            c.execute("DELETE FROM items WHERE user_id=? AND item_id LIKE 'dragon_ball_%'", (int(user_id),))
        return True

    def grant_gear(self, user_id: int, gear_id: str, level: int = 1) -> int:
        if gear_id not in data.GEAR:
            raise ValueError(f"Unknown gear: {gear_id}")
        with self.conn() as c:
            cursor = c.execute(
                "INSERT INTO gear(user_id, gear_id, level, acquired_at) VALUES(?,?,?,?)",
                (int(user_id), gear_id, max(1, int(level)), _now()),
            )
            return int(cursor.lastrowid)

    def gear(self, user_id: int) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM gear WHERE user_id=? ORDER BY id", (int(user_id),)).fetchall()
        result = []
        for row in rows:
            base = data.GEAR.get(row["gear_id"])
            if base is None:
                continue
            item = dict(base)
            item.update({"instance_id": row["id"], "level": row["level"], "equipped_slot": row["equipped_slot"]})
            result.append(item)
        return result

    def gear_instance(self, user_id: int, instance_id: int) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM gear WHERE user_id=? AND id=?", (int(user_id), int(instance_id))).fetchone()
        if row is None:
            return None
        base = data.GEAR.get(row["gear_id"])
        if base is None:
            return None
        item = dict(base)
        item.update({"instance_id": row["id"], "level": row["level"], "equipped_slot": row["equipped_slot"]})
        return item

    def equip_gear(self, user_id: int, instance_id: int) -> dict:
        item = self.gear_instance(user_id, instance_id)
        if item is None:
            return {"ok": False, "reason": "Gear not found."}
        slot = item["slot"]
        column = {"weapon": "weapon", "armor": "armor", "accessory": "accessory"}.get(slot)
        if column is None:
            return {"ok": False, "reason": "Unknown gear slot."}
        with self.conn() as c:
            c.execute("UPDATE gear SET equipped_slot=NULL WHERE user_id=? AND equipped_slot=?", (int(user_id), slot))
            c.execute("UPDATE gear SET equipped_slot=? WHERE user_id=? AND id=?", (slot, int(user_id), int(instance_id)))
            c.execute(f"UPDATE players SET {column}=? WHERE user_id=?", (int(instance_id), int(user_id)))
        return {"ok": True, "slot": slot, "item": item}

    def unequip_gear(self, user_id: int, slot: str) -> bool:
        column = {"weapon": "weapon", "armor": "armor", "accessory": "accessory"}.get(slot)
        if column is None:
            return False
        with self.conn() as c:
            c.execute("UPDATE gear SET equipped_slot=NULL WHERE user_id=? AND equipped_slot=?", (int(user_id), slot))
            c.execute(f"UPDATE players SET {column}=NULL WHERE user_id=?", (int(user_id),))
        return True

    def enhance_gear(self, user_id: int, instance_id: int) -> dict:
        item = self.gear_instance(user_id, instance_id)
        if item is None:
            return {"ok": False, "reason": "Gear not found."}
        level = int(item["level"])
        if level >= 50:
            return {"ok": False, "reason": "Gear is already max level."}
        cost = 180 * level + 120
        with self.conn() as c:
            player = c.execute("SELECT yens FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if player is None or int(player["yens"]) < cost:
                return {"ok": False, "reason": f"Not enough yens. Need {cost:,}."}
            c.execute("UPDATE players SET yens=yens-? WHERE user_id=?", (cost, int(user_id)))
            c.execute("UPDATE gear SET level=level+1 WHERE user_id=? AND id=?", (int(user_id), int(instance_id)))
        return {"ok": True, "level": level + 1, "cost": cost}

    def learn_skill(self, user_id: int, skill_id: str) -> dict:
        base = data.SKILLS.get(skill_id)
        if base is None or base["type"] != "active":
            return {"ok": False, "reason": "That skill cannot be learned."}
        with self.conn() as c:
            existing = c.execute("SELECT 1 FROM skills WHERE user_id=? AND skill_id=?", (int(user_id), skill_id)).fetchone()
            if existing:
                return {"ok": False, "reason": "Skill already learned."}
            player = c.execute("SELECT skill_points FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if player is None or int(player["skill_points"]) < 1:
                return {"ok": False, "reason": "No skill points available."}
            c.execute("UPDATE players SET skill_points=skill_points-1 WHERE user_id=?", (int(user_id),))
            c.execute("INSERT INTO skills(user_id, skill_id, level, equipped) VALUES(?,?,1,0)", (int(user_id), skill_id))
        return {"ok": True, "skill": base}

    def skills(self, user_id: int) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM skills WHERE user_id=? ORDER BY skill_id", (int(user_id),)).fetchall()
        result = []
        for row in rows:
            base = data.SKILLS.get(row["skill_id"])
            if base is None:
                continue
            item = dict(base)
            item.update({"level": row["level"], "equipped": bool(row["equipped"])})
            result.append(item)
        return result

    def equip_skill(self, user_id: int, skill_id: str) -> dict:
        with self.conn() as c:
            row = c.execute("SELECT * FROM skills WHERE user_id=? AND skill_id=?", (int(user_id), skill_id)).fetchone()
            if row is None:
                return {"ok": False, "reason": "Learn the skill first."}
            equipped_count = c.execute("SELECT COUNT(*) AS n FROM skills WHERE user_id=? AND equipped=1", (int(user_id),)).fetchone()["n"]
            if not row["equipped"] and equipped_count >= 3:
                return {"ok": False, "reason": "You can equip at most 3 skills."}
            c.execute("UPDATE skills SET equipped=? WHERE user_id=? AND skill_id=?", (0 if row["equipped"] else 1, int(user_id), skill_id))
        return {"ok": True, "equipped": not bool(row["equipped"])}

    def bump(self, user_id: int, metric: str, amount: int = 1) -> None:
        if metric not in COUNTER_METRICS:
            return
        amount = int(amount)
        now = date.today()
        keys = ["total", today_key(), week_key(), month_key()]
        with self.conn() as c:
            for key in keys:
                c.execute(
                    "INSERT INTO counters(user_id, key, period_key, value) VALUES(?,?,?,?) ON CONFLICT(user_id,key,period_key) DO UPDATE SET value=value+?",
                    (int(user_id), metric, key, amount, amount),
                )

    def counter(self, user_id: int, metric: str, period: str = "total") -> int:
        if metric == "level":
            player = self.player(user_id)
            return int(player["level"]) if player else 0
        if metric == "arena_rating":
            player = self.player(user_id)
            return int(player["arena_rating"]) if player else 0
        if period == "daily":
            key = today_key()
        elif period == "weekly":
            key = week_key()
        elif period == "monthly":
            key = month_key()
        else:
            key = "total"
        with self.conn() as c:
            row = c.execute("SELECT value FROM counters WHERE user_id=? AND key=? AND period_key=?", (int(user_id), metric, key)).fetchone()
        return int(row["value"]) if row else 0

    def quest_progress(self, user_id: int, quest: dict) -> int:
        return self.counter(user_id, quest["metric"], quest["type"])

    def quest_claimed(self, user_id: int, quest: dict) -> bool:
        period = {"daily": today_key(), "weekly": week_key(), "monthly": month_key()}[quest["type"]]
        with self.conn() as c:
            row = c.execute("SELECT 1 FROM quest_claims WHERE user_id=? AND quest_id=? AND period_key=?", (int(user_id), quest["id"], period)).fetchone()
        return row is not None

    def claim_quests(self, user_id: int, quest_type: str | None = None) -> dict:
        claimed = []
        earned: dict[str, int] = {}
        items: dict[str, int] = {}
        with self.conn() as c:
            for quest in data.QUESTS:
                if quest_type and quest["type"] != quest_type:
                    continue
                period = {"daily": today_key(), "weekly": week_key(), "monthly": month_key()}[quest["type"]]
                if self._quest_progress_tx(c, user_id, quest) < quest["target"]:
                    continue
                if c.execute("SELECT 1 FROM quest_claims WHERE user_id=? AND quest_id=? AND period_key=?", (int(user_id), quest["id"], period)).fetchone():
                    continue
                c.execute("INSERT INTO quest_claims(user_id, quest_id, period_key, claimed_at) VALUES(?,?,?,?)", (int(user_id), quest["id"], period, _now()))
                self._grant_rewards_tx(c, user_id, quest["rewards"])
                claimed.append(quest["name"])
                for key, value in quest["rewards"].items():
                    if key in ("yens", "gems", "crystals", "tickets", "exp", "clan_exp"):
                        earned[key] = earned.get(key, 0) + int(value)
                    elif key in data.ITEMS:
                        items[key] = items.get(key, 0) + int(value)
        return {"claimed": claimed, "earned": earned, "items": items}

    def _quest_progress_tx(self, c: sqlite3.Connection, user_id: int, quest: dict) -> int:
        metric = quest["metric"]
        if metric == "level":
            row = c.execute("SELECT level FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            return int(row["level"]) if row else 0
        if metric == "arena_rating":
            row = c.execute("SELECT arena_rating FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            return int(row["arena_rating"]) if row else 0
        key = {"daily": today_key(), "weekly": week_key(), "monthly": month_key()}[quest["type"]]
        row = c.execute("SELECT value FROM counters WHERE user_id=? AND key=? AND period_key=?", (int(user_id), metric, key)).fetchone()
        return int(row["value"]) if row else 0

    def achievement_progress(self, user_id: int, achievement: dict) -> int:
        return self.counter(user_id, achievement["metric"], "total")

    def achievement_claimed(self, user_id: int, achievement: dict) -> bool:
        with self.conn() as c:
            row = c.execute("SELECT 1 FROM achievement_claims WHERE user_id=? AND achievement_id=?", (int(user_id), achievement["id"])).fetchone()
        return row is not None

    def claim_achievements(self, user_id: int) -> dict:
        claimed = []
        earned: dict[str, int] = {}
        with self.conn() as c:
            for achievement in data.ACHIEVEMENTS:
                if self._achievement_progress_tx(c, user_id, achievement) < achievement["target"]:
                    continue
                if c.execute("SELECT 1 FROM achievement_claims WHERE user_id=? AND achievement_id=?", (int(user_id), achievement["id"])).fetchone():
                    continue
                c.execute("INSERT INTO achievement_claims(user_id, achievement_id, claimed_at) VALUES(?,?,?)", (int(user_id), achievement["id"], _now()))
                self._grant_rewards_tx(c, user_id, achievement["rewards"])
                claimed.append(achievement["name"])
                for key, value in achievement["rewards"].items():
                    if key in ("yens", "gems", "crystals", "tickets", "exp"):
                        earned[key] = earned.get(key, 0) + int(value)
        return {"claimed": claimed, "earned": earned}

    def _achievement_progress_tx(self, c: sqlite3.Connection, user_id: int, achievement: dict) -> int:
        metric = achievement["metric"]
        if metric == "level":
            row = c.execute("SELECT level FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            return int(row["level"]) if row else 0
        if metric == "arena_rating":
            row = c.execute("SELECT arena_rating FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            return int(row["arena_rating"]) if row else 0
        row = c.execute("SELECT value FROM counters WHERE user_id=? AND key=? AND period_key='total'", (int(user_id), metric)).fetchone()
        return int(row["value"]) if row else 0

    def _grant_rewards_tx(self, c: sqlite3.Connection, user_id: int, rewards: dict, scale: tuple[int, int] | None = None) -> None:
        low, high = scale or (config.REWARD_SCALE_MIN, config.REWARD_SCALE_MAX)
        multiplier = random.randint(int(low), int(high))
        for key, value in rewards.items():
            value = int(value) * multiplier
            if key in ("yens", "gems", "crystals", "tickets"):
                c.execute(f"UPDATE players SET {key}=MAX(0, {key}+?) WHERE user_id=?", (value, int(user_id)))
            elif key == "skill_points":
                c.execute("UPDATE players SET skill_points=skill_points+? WHERE user_id=?", (value, int(user_id)))
            elif key == "exp":
                row = c.execute("SELECT level, exp FROM players WHERE user_id=?", (int(user_id),)).fetchone()
                if row:
                    level = int(row["level"])
                    exp = int(row["exp"]) + value
                    levels = 0
                    while level < 100 and exp >= self.exp_needed(level):
                        exp -= self.exp_needed(level)
                        level += 1
                        levels += 1
                    c.execute("UPDATE players SET level=?, exp=?, rank=? WHERE user_id=?", (level, exp, data.rank_for_level(level)["name"], int(user_id)))
                    if levels:
                        c.execute("UPDATE players SET skill_points=skill_points+? WHERE user_id=?", (levels, int(user_id)))
            elif key in data.ITEMS:
                c.execute(
                    "INSERT INTO items(user_id, item_id, qty) VALUES(?,?,?) ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+?",
                    (int(user_id), key, value, value),
                )
            elif key == "clan_exp":
                c.execute(
                    "UPDATE clans SET exp=exp+?, level=1 + ((exp+?) / 10000) WHERE id=(SELECT clan_id FROM players WHERE user_id=?)",
                    (value, value, int(user_id)),
                )

    def claim_daily(self, user_id: int) -> dict:
        player = self.require_player(user_id)
        today = today_key()
        if player["daily_day"] == today:
            return {"ok": False, "reason": "Daily reward already claimed today."}
        streak = int(player["daily_streak"]) + 1 if player["daily_day"] == (date.today() - timedelta(days=1)).isoformat() else 1
        rewards = {
            "yens": 400 + min(streak, 7) * 150,
            "gems": 10 + min(streak, 7) * 3,
            "crystals": 2 + min(streak, 7),
            "tickets": 1 if streak % 7 == 0 else 0,
            "exp": 100 + min(streak, 7) * 40,
        }
        with self.conn() as c:
            c.execute("UPDATE players SET daily_day=?, daily_streak=? WHERE user_id=?", (today, streak, int(user_id)))
            self._grant_rewards_tx(c, user_id, {key: value for key, value in rewards.items() if value})
        return {"ok": True, "streak": streak, "rewards": rewards}

    def claim_weekly(self, user_id: int) -> dict:
        player = self.require_player(user_id)
        current = week_key()
        if player["weekly_week"] == current:
            return {"ok": False, "reason": "Weekly reward already claimed."}
        rewards = {"yens": 3000, "gems": 70, "crystals": 20, "tickets": 2, "exp": 900}
        with self.conn() as c:
            c.execute("UPDATE players SET weekly_week=? WHERE user_id=?", (current, int(user_id)))
            self._grant_rewards_tx(c, user_id, rewards)
        return {"ok": True, "rewards": rewards}

    def claim_monthly(self, user_id: int) -> dict:
        player = self.require_player(user_id)
        current = month_key()
        if player["monthly_month"] == current:
            return {"ok": False, "reason": "Monthly reward already claimed."}
        rewards = {"yens": 12000, "gems": 250, "crystals": 80, "tickets": 6, "exp": 5000}
        with self.conn() as c:
            c.execute("UPDATE players SET monthly_month=? WHERE user_id=?", (current, int(user_id)))
            self._grant_rewards_tx(c, user_id, rewards)
        return {"ok": True, "rewards": rewards}

    def unlocked_titles(self, user_id: int) -> list[str]:
        result = []
        for title_id, title in data.TITLES.items():
            requirement = title["requirement"]
            if requirement is None:
                result.append(title_id)
            elif self.counter(user_id, requirement[0], "total") >= requirement[1]:
                result.append(title_id)
        return result

    def equip_title(self, user_id: int, title_id: str) -> bool:
        if title_id not in self.unlocked_titles(user_id):
            return False
        self.set_field(user_id, "title", title_id)
        return True

    def clan(self, user_id: int) -> dict | None:
        player = self.player(user_id)
        if not player or not player.get("clan_id"):
            return None
        with self.conn() as c:
            row = c.execute("SELECT * FROM clans WHERE id=?", (int(player["clan_id"]),)).fetchone()
        return _row_to_dict(row)

    def clan_by_query(self, query: str) -> dict | None:
        query = query.strip()
        with self.conn() as c:
            row = c.execute("SELECT * FROM clans WHERE CAST(id AS TEXT)=? OR LOWER(name)=LOWER(?) OR LOWER(tag)=LOWER(?)", (query, query, query)).fetchone()
        return _row_to_dict(row)

    def clan_info(self, clan_id: int) -> dict | None:
        with self.conn() as c:
            clan = c.execute("SELECT * FROM clans WHERE id=?", (int(clan_id),)).fetchone()
            if clan is None:
                return None
            members = c.execute(
                "SELECT m.*, p.username, p.first_name, p.level, p.arena_rating FROM clan_members m JOIN players p ON p.user_id=m.user_id WHERE m.clan_id=? ORDER BY CASE m.role WHEN 'leader' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END, m.donation DESC",
                (int(clan_id),),
            ).fetchall()
        result = _row_to_dict(clan) or {}
        result["members"] = _rows_to_dicts(members)
        return result

    def create_clan(self, user_id: int, name: str, tag: str) -> dict:
        name = " ".join(name.split()).strip()
        tag = tag.strip().upper()
        if not 3 <= len(name) <= 24:
            return {"ok": False, "reason": "Clan name must be 3-24 characters."}
        if not tag.isalnum() or not 2 <= len(tag) <= 6:
            return {"ok": False, "reason": "Clan tag must be 2-6 letters or numbers."}
        if self.clan(user_id):
            return {"ok": False, "reason": "You are already in a clan."}
        with self.conn() as c:
            if c.execute("SELECT 1 FROM clans WHERE LOWER(name)=LOWER(?) OR LOWER(tag)=LOWER(?)", (name, tag)).fetchone():
                return {"ok": False, "reason": "That clan name or tag is taken."}
            player = c.execute("SELECT yens, crystals FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if player is None or int(player["yens"]) < config.CLAN_CREATE_YENS or int(player["crystals"]) < config.CLAN_CREATE_CRYSTALS:
                return {"ok": False, "reason": f"Need {config.CLAN_CREATE_YENS:,} yens and {config.CLAN_CREATE_CRYSTALS} crystals."}
            c.execute("UPDATE players SET yens=yens-?, crystals=crystals-? WHERE user_id=?", (config.CLAN_CREATE_YENS, config.CLAN_CREATE_CRYSTALS, int(user_id)))
            cursor = c.execute(
                "INSERT INTO clans(name, tag, leader_id, created_at) VALUES(?,?,?,?)",
                (name, tag, int(user_id), _now()),
            )
            clan_id = int(cursor.lastrowid)
            c.execute("INSERT INTO clan_members(clan_id, user_id, role, joined_at) VALUES(?,?,'leader',?)", (clan_id, int(user_id), _now()))
            c.execute("UPDATE players SET clan_id=? WHERE user_id=?", (clan_id, int(user_id)))
        return {"ok": True, "clan_id": clan_id, "name": name, "tag": tag}

    def join_clan(self, user_id: int, query: str) -> dict:
        if self.clan(user_id):
            return {"ok": False, "reason": "You are already in a clan."}
        clan = self.clan_by_query(query)
        if clan is None:
            return {"ok": False, "reason": "Clan not found."}
        player = self.require_player(user_id)
        if not int(clan.get("open_join", 1)) and not self.clan_invite_pending(int(clan["id"]), int(user_id)):
            return {"ok": False, "reason": "This clan is invite-only. Ask a leader or officer for an invite."}
        if int(player.get("level", 1)) < int(clan.get("min_level", 1)):
            return {"ok": False, "reason": f"That clan requires level {clan.get('min_level', 1)}."}
        with self.conn() as c:
            count = c.execute("SELECT COUNT(*) AS n FROM clan_members WHERE clan_id=?", (int(clan["id"]),)).fetchone()["n"]
            if int(count) >= 30:
                return {"ok": False, "reason": "That clan is full."}
            c.execute("INSERT INTO clan_members(clan_id, user_id, role, joined_at) VALUES(?,?,'member',?)", (int(clan["id"]), int(user_id), _now()))
            c.execute("UPDATE players SET clan_id=? WHERE user_id=?", (int(clan["id"]), int(user_id)))
            c.execute("DELETE FROM clan_invites WHERE clan_id=? AND user_id=?", (int(clan["id"]), int(user_id)))
        return {"ok": True, "clan": clan}

    def leave_clan(self, user_id: int) -> dict:
        clan = self.clan(user_id)
        if clan is None:
            return {"ok": False, "reason": "You are not in a clan."}
        with self.conn() as c:
            member = c.execute("SELECT * FROM clan_members WHERE user_id=?", (int(user_id),)).fetchone()
            count = c.execute("SELECT COUNT(*) AS n FROM clan_members WHERE clan_id=?", (int(clan["id"]),)).fetchone()["n"]
            if member and member["role"] == "leader" and int(count) > 1:
                return {"ok": False, "reason": "Transfer leadership or disband the clan first. Use /clan disband."}
            c.execute("DELETE FROM clan_members WHERE user_id=?", (int(user_id),))
            c.execute("UPDATE players SET clan_id=NULL WHERE user_id=?", (int(user_id),))
            if (member is not None and member["role"] == "leader") or int(count) <= 1:
                c.execute("DELETE FROM clan_raid_damage WHERE clan_raid_id IN (SELECT id FROM clan_raids WHERE clan_id=?)", (int(clan["id"]),))
                c.execute("DELETE FROM clan_raids WHERE clan_id=?", (int(clan["id"]),))
                c.execute("DELETE FROM clan_members WHERE clan_id=?", (int(clan["id"]),))
                c.execute("DELETE FROM clans WHERE id=?", (int(clan["id"]),))
                c.execute("UPDATE players SET clan_id=NULL WHERE clan_id=?", (int(clan["id"]),))
        return {"ok": True}

    def clan_member(self, user_id: int) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM clan_members WHERE user_id=?", (int(user_id),)).fetchone()
        return _row_to_dict(row)

    def clan_member_target(self, clan_id: int, query: str) -> dict | None:
        query = str(query).strip()
        with self.conn() as c:
            row = c.execute(
                "SELECT m.*, p.username, p.first_name FROM clan_members m JOIN players p ON p.user_id=m.user_id WHERE m.clan_id=? AND (CAST(p.user_id AS TEXT)=? OR LOWER(p.username)=LOWER(?) OR LOWER(p.first_name)=LOWER(?)) LIMIT 1",
                (int(clan_id), query, query.lstrip("@"), query),
            ).fetchone()
            if row is None:
                row = c.execute(
                    "SELECT m.*, p.username, p.first_name FROM clan_members m JOIN players p ON p.user_id=m.user_id WHERE m.clan_id=? AND LOWER(p.first_name) LIKE LOWER(?) LIMIT 1",
                    (int(clan_id), f"%{query}%"),
                ).fetchone()
        return _row_to_dict(row)

    def clan_invite_pending(self, clan_id: int, user_id: int) -> bool:
        with self.conn() as c:
            return c.execute("SELECT 1 FROM clan_invites WHERE clan_id=? AND user_id=?", (int(clan_id), int(user_id))).fetchone() is not None

    def clan_invite(self, actor_id: int, target_query: str) -> dict:
        clan = self.clan(actor_id)
        member = self.clan_member(actor_id)
        if clan is None or member is None:
            return {"ok": False, "reason": "You are not in a clan."}
        if member["role"] not in ("leader", "officer"):
            return {"ok": False, "reason": "Only the leader or an officer can invite."}
        target = self.find_player(target_query)
        if target is None:
            return {"ok": False, "reason": "Player not found."}
        if target.get("clan_id"):
            return {"ok": False, "reason": "That player is already in a clan."}
        with self.conn() as c:
            count = c.execute("SELECT COUNT(*) AS n FROM clan_members WHERE clan_id=?", (int(clan["id"]),)).fetchone()["n"]
            if int(count) >= 30:
                return {"ok": False, "reason": "That clan is full."}
            c.execute("INSERT INTO clan_invites(clan_id, user_id, invited_by, created_at) VALUES(?,?,?,?) ON CONFLICT(clan_id,user_id) DO UPDATE SET invited_by=excluded.invited_by, created_at=excluded.created_at", (int(clan["id"]), int(target["user_id"]), int(actor_id), _now()))
        return {"ok": True, "target": target, "clan": clan}

    def clan_accept(self, user_id: int, query: str = "") -> dict:
        if self.clan(user_id):
            return {"ok": False, "reason": "You are already in a clan."}
        with self.conn() as c:
            if query.strip():
                clan = self.clan_by_query(query)
                if clan is None:
                    return {"ok": False, "reason": "Clan not found."}
                row = c.execute("SELECT * FROM clan_invites WHERE clan_id=? AND user_id=?", (int(clan["id"]), int(user_id))).fetchone()
            else:
                row = c.execute("SELECT * FROM clan_invites WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (int(user_id),)).fetchone()
            if row is None:
                return {"ok": False, "reason": "No pending clan invite."}
            clan_id = int(row["clan_id"])
        return self.join_clan(user_id, str(clan_id))

    def clan_add(self, actor_id: int, target_query: str) -> dict:
        clan = self.clan(actor_id)
        member = self.clan_member(actor_id)
        if clan is None or member is None:
            return {"ok": False, "reason": "You are not in a clan."}
        if member["role"] not in ("leader", "officer"):
            return {"ok": False, "reason": "Only the leader or an officer can add members."}
        target = self.find_player(target_query)
        if target is None:
            return {"ok": False, "reason": "Player not found."}
        if target.get("clan_id"):
            return {"ok": False, "reason": "That player is already in a clan."}
        with self.conn() as c:
            count = c.execute("SELECT COUNT(*) AS n FROM clan_members WHERE clan_id=?", (int(clan["id"]),)).fetchone()["n"]
            if int(count) >= 30:
                return {"ok": False, "reason": "That clan is full."}
            c.execute("INSERT INTO clan_members(clan_id, user_id, role, joined_at) VALUES(?,?,'member',?)", (int(clan["id"]), int(target["user_id"]), _now()))
            c.execute("UPDATE players SET clan_id=? WHERE user_id=?", (int(clan["id"]), int(target["user_id"])))
        return {"ok": True, "target": target}

    def clan_transfer(self, actor_id: int, target_query: str) -> dict:
        clan = self.clan(actor_id)
        member = self.clan_member(actor_id)
        if clan is None or member is None or member["role"] != "leader":
            return {"ok": False, "reason": "Only the clan leader can transfer leadership."}
        target = self.clan_member_target(clan["id"], target_query)
        if target is None:
            return {"ok": False, "reason": "Member not found."}
        if int(target["user_id"]) == int(actor_id):
            return {"ok": False, "reason": "You are already the leader."}
        with self.conn() as c:
            c.execute("UPDATE clan_members SET role='officer' WHERE user_id=?", (int(actor_id),))
            c.execute("UPDATE clan_members SET role='leader' WHERE user_id=?", (int(target["user_id"]),))
            c.execute("UPDATE clans SET leader_id=? WHERE id=?", (int(target["user_id"]), int(clan["id"])))
        return {"ok": True, "target": target}

    def clan_set_description(self, actor_id: int, text: str) -> dict:
        clan = self.clan(actor_id)
        member = self.clan_member(actor_id)
        if clan is None or member is None or member["role"] != "leader":
            return {"ok": False, "reason": "Only the clan leader can edit the description."}
        text = text.strip()[:200]
        with self.conn() as c:
            c.execute("UPDATE clans SET description=? WHERE id=?", (text, int(clan["id"])))
        return {"ok": True, "text": text}

    def clan_settings(self, actor_id: int, open_join: bool | None = None, min_level: int | None = None) -> dict:
        clan = self.clan(actor_id)
        member = self.clan_member(actor_id)
        if clan is None or member is None or member["role"] != "leader":
            return {"ok": False, "reason": "Only the clan leader can change settings."}
        with self.conn() as c:
            if open_join is not None:
                c.execute("UPDATE clans SET open_join=? WHERE id=?", (1 if open_join else 0, int(clan["id"])))
            if min_level is not None:
                c.execute("UPDATE clans SET min_level=? WHERE id=?", (max(1, min(100, int(min_level))), int(clan["id"])))
        return {"ok": True, "clan": self.clan(actor_id)}

    def clan_set_role(self, actor_id: int, target_query: str, role: str) -> dict:
        clan = self.clan(actor_id)
        member = self.clan_member(actor_id)
        if clan is None or member is None:
            return {"ok": False, "reason": "You are not in a clan."}
        if member["role"] != "leader":
            return {"ok": False, "reason": "Only the clan leader can change roles."}
        target = self.clan_member_target(clan["id"], target_query)
        if target is None:
            return {"ok": False, "reason": "Member not found."}
        if target["user_id"] == actor_id:
            return {"ok": False, "reason": "You cannot change your own role."}
        if role not in ("member", "officer"):
            return {"ok": False, "reason": "Role must be member or officer."}
        with self.conn() as c:
            c.execute("UPDATE clan_members SET role=? WHERE user_id=?", (role, int(target["user_id"])))
        return {"ok": True, "target": target, "role": role}

    def clan_kick(self, actor_id: int, target_query: str) -> dict:
        clan = self.clan(actor_id)
        member = self.clan_member(actor_id)
        if clan is None or member is None:
            return {"ok": False, "reason": "You are not in a clan."}
        if member["role"] not in ("leader", "officer"):
            return {"ok": False, "reason": "Only the leader or an officer can kick members."}
        target = self.clan_member_target(clan["id"], target_query)
        if target is None:
            return {"ok": False, "reason": "Member not found."}
        if target["role"] == "leader":
            return {"ok": False, "reason": "You cannot kick the clan leader."}
        if member["role"] == "officer" and target["role"] == "officer":
            return {"ok": False, "reason": "Officers cannot kick other officers."}
        with self.conn() as c:
            c.execute("DELETE FROM clan_members WHERE user_id=?", (int(target["user_id"]),))
            c.execute("UPDATE players SET clan_id=NULL WHERE user_id=?", (int(target["user_id"]),))
        return {"ok": True, "target": target}

    def clan_disband(self, user_id: int) -> dict:
        clan = self.clan(user_id)
        member = self.clan_member(user_id)
        if clan is None or member is None:
            return {"ok": False, "reason": "You are not in a clan."}
        if member["role"] != "leader":
            return {"ok": False, "reason": "Only the clan leader can disband."}
        with self.conn() as c:
            c.execute("DELETE FROM clan_raid_damage WHERE clan_raid_id IN (SELECT id FROM clan_raids WHERE clan_id=?)", (int(clan["id"]),))
            c.execute("DELETE FROM clan_raids WHERE clan_id=?", (int(clan["id"]),))
            c.execute("DELETE FROM clan_members WHERE clan_id=?", (int(clan["id"]),))
            c.execute("DELETE FROM clans WHERE id=?", (int(clan["id"]),))
            c.execute("UPDATE players SET clan_id=NULL WHERE clan_id=?", (int(clan["id"]),))
        return {"ok": True}

    def clan_donate(self, user_id: int, currency: str, amount: int) -> dict:
        if currency not in ("yens", "gems", "crystals"):
            return {"ok": False, "reason": "Donate yens, gems, or crystals."}
        amount = int(amount)
        if amount <= 0:
            return {"ok": False, "reason": "Donation must be positive."}
        clan = self.clan(user_id)
        member = self.clan_member(user_id)
        if clan is None or member is None:
            return {"ok": False, "reason": "Join a clan first."}
        if not self.spend(user_id, **{currency: amount}):
            return {"ok": False, "reason": "You do not have enough."}
        exp_gain = max(1, amount // (5 if currency == "yens" else 1))
        with self.conn() as c:
            c.execute(f"UPDATE clans SET treasury_{currency}=treasury_{currency}+?, exp=exp+?, level=1 + ((exp+?) / 10000) WHERE id=?", (amount, exp_gain, exp_gain, int(clan["id"])))
            c.execute("UPDATE clan_members SET donation=donation+?, weekly_points=weekly_points+? WHERE user_id=?", (amount, exp_gain, int(user_id)))
            c.execute("UPDATE players SET clan_donation=clan_donation+? WHERE user_id=?", (amount, int(user_id)))
        self.bump(user_id, "clan_donation", amount)
        return {"ok": True, "amount": amount, "currency": currency, "clan_exp": exp_gain}

    def clan_announce(self, user_id: int, text: str) -> dict:
        clan = self.clan(user_id)
        member = self.clan_member(user_id)
        if clan is None or member is None or member["role"] != "leader":
            return {"ok": False, "reason": "Only the clan leader can set the announcement."}
        text = text.strip()[:300]
        with self.conn() as c:
            c.execute("UPDATE clans SET announcement=? WHERE id=?", (text, int(clan["id"])))
        return {"ok": True, "text": text}

    def clan_leaderboard(self, limit: int = 10) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM clan_members m WHERE m.clan_id=c.id) AS members FROM clans c ORDER BY c.level DESC, c.exp DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return _rows_to_dicts(rows)

    def clan_raid_current(self, clan_id: int) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM clan_raids WHERE clan_id=? AND status='active' ORDER BY id DESC LIMIT 1", (int(clan_id),)).fetchone()
        return _row_to_dict(row)

    def start_clan_raid(self, user_id: int, raid_id: str) -> dict:
        clan = self.clan(user_id)
        member = self.clan_member(user_id)
        if clan is None or member is None:
            return {"ok": False, "reason": "Join a clan first."}
        if member["role"] != "leader":
            return {"ok": False, "reason": "Only the clan leader can start a clan raid."}
        if raid_id not in data.CLAN_RAID_BY_ID:
            return {"ok": False, "reason": "Unknown clan raid."}
        if self.clan_raid_current(clan["id"]):
            return {"ok": False, "reason": "Your clan already has an active raid."}
        raid = data.CLAN_RAID_BY_ID[raid_id]
        with self.conn() as c:
            c.execute(
                "INSERT INTO clan_raids(clan_id, raid_id, hp, max_hp, status, started_at, ends_at) VALUES(?,?,?,?, 'active', ?, ?)",
                (int(clan["id"]), raid_id, raid["hp"], raid["hp"], _now(), (_utcnow() + timedelta(days=3)).isoformat(timespec="seconds")),
            )
            raid_row = c.execute("SELECT * FROM clan_raids WHERE clan_id=? ORDER BY id DESC LIMIT 1", (int(clan["id"]),)).fetchone()
        return {"ok": True, "raid": _row_to_dict(raid_row), "info": raid}

    def record_clan_raid_damage(self, user_id: int, damage: int) -> dict:
        clan = self.clan(user_id)
        if clan is None:
            return {"ok": False, "reason": "Join a clan first."}
        raid_row = self.clan_raid_current(clan["id"])
        if raid_row is None:
            return {"ok": False, "reason": "No active clan raid."}
        damage = max(0, int(damage))
        with self.conn() as c:
            hp = max(0, int(raid_row["hp"]) - damage)
            status = "defeated" if hp == 0 else "active"
            c.execute("UPDATE clan_raids SET hp=?, status=? WHERE id=?", (hp, status, int(raid_row["id"])))
            c.execute(
                "INSERT INTO clan_raid_damage(clan_raid_id, user_id, damage) VALUES(?,?,?) ON CONFLICT(clan_raid_id,user_id) DO UPDATE SET damage=damage+?",
                (int(raid_row["id"]), int(user_id), damage, damage),
            )
            c.execute("UPDATE players SET raid_damage=raid_damage+? WHERE user_id=?", (damage, int(user_id)))
        self.bump(user_id, "raid_damage", damage)
        defeated = status == "defeated"
        if defeated:
            raid = data.CLAN_RAID_BY_ID.get(raid_row["raid_id"], {})
            self.grant_rewards(user_id, raid.get("reward", {}))
        return {"ok": True, "damage": damage, "hp": hp, "max_hp": int(raid_row["max_hp"]), "defeated": defeated, "raid": raid_row}

    def clan_raid_leaderboard(self, clan_raid_id: int) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT d.*, p.username, p.first_name FROM clan_raid_damage d JOIN players p ON p.user_id=d.user_id WHERE d.clan_raid_id=? ORDER BY d.damage DESC LIMIT 10",
                (int(clan_raid_id),),
            ).fetchall()
        return _rows_to_dicts(rows)

    def world_boss_current(self) -> dict:
        cycle = self._world_cycle()
        with self.conn() as c:
            row = c.execute("SELECT * FROM world_boss WHERE cycle=? AND status='active' ORDER BY id DESC LIMIT 1", (cycle,)).fetchone()
            if row is None:
                self._ensure_world_boss(c)
                row = c.execute("SELECT * FROM world_boss WHERE cycle=? AND status='active' ORDER BY id DESC LIMIT 1", (cycle,)).fetchone()
        result = _row_to_dict(row) or {}
        if result:
            result["boss"] = data.WORLD_BOSS_BY_ID.get(result["boss_id"])
        return result

    def record_world_damage(self, user_id: int, damage: int) -> dict:
        boss = self.world_boss_current()
        if not boss:
            return {"ok": False, "reason": "No world boss is active."}
        damage = max(0, int(damage))
        with self.conn() as c:
            hp = max(0, int(boss["hp"]) - damage)
            status = "defeated" if hp == 0 else "active"
            c.execute("UPDATE world_boss SET hp=?, status=? WHERE id=?", (hp, status, int(boss["id"])))
            c.execute(
                "INSERT INTO world_boss_damage(cycle, user_id, damage) VALUES(?,?,?) ON CONFLICT(cycle,user_id) DO UPDATE SET damage=damage+?",
                (boss["cycle"], int(user_id), damage, damage),
            )
            c.execute("UPDATE players SET raid_damage=raid_damage+? WHERE user_id=?", (damage, int(user_id)))
        self.bump(user_id, "raid_damage", damage)
        defeated = status == "defeated"
        if defeated:
            reward = (boss.get("boss") or {}).get("reward", {})
            self.grant_rewards(user_id, reward)
            for key, value in reward.items():
                if key in ("gems", "crystals", "tickets"):
                    pass
        return {"ok": True, "damage": damage, "hp": hp, "max_hp": int(boss["max_hp"]), "defeated": defeated, "boss": boss}

    def world_boss_leaderboard(self, limit: int = 10) -> list[dict]:
        cycle = self._world_cycle()
        with self.conn() as c:
            rows = c.execute(
                "SELECT d.*, p.username, p.first_name FROM world_boss_damage d JOIN players p ON p.user_id=d.user_id WHERE d.cycle=? ORDER BY d.damage DESC LIMIT ?",
                (cycle, int(limit)),
            ).fetchall()
        return _rows_to_dicts(rows)

    def grant_rewards(self, user_id: int, rewards: dict, scale: tuple[int, int] | None = None) -> None:
        with self.conn() as c:
            self._grant_rewards_tx(c, user_id, rewards, scale)

    def market_listings(self, limit: int = 10, offset: int = 0) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT m.*, p.username, p.first_name FROM market m JOIN players p ON p.user_id=m.seller_id ORDER BY m.id DESC LIMIT ? OFFSET ?",
                (int(limit), int(offset)),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            meta = json.loads(item.get("meta") or "{}")
            item["meta"] = meta
            if item["kind"] == "item":
                base = data.ITEMS.get(item["item_id"], {})
                item["name"] = base.get("name", item["item_id"])
                item["emoji"] = base.get("emoji", "📦")
            else:
                base = data.GEAR.get(item["item_id"], {})
                item["name"] = base.get("name", item["item_id"])
                item["emoji"] = data.RARITIES.get(base.get("rarity", "common"), {}).get("emoji", "⚙️")
            result.append(item)
        return result

    def market_count(self) -> int:
        with self.conn() as c:
            return int(c.execute("SELECT COUNT(*) AS n FROM market").fetchone()["n"])

    def market_list(self, user_id: int, kind: str, item_id: str, qty: int, price: int, meta: dict | None = None) -> dict:
        qty = max(1, int(qty))
        price = max(1, int(price))
        if kind == "item":
            if item_id not in data.ITEMS:
                return {"ok": False, "reason": "Unknown item."}
            if not self.take_item(user_id, item_id, qty):
                return {"ok": False, "reason": "You do not have that many."}
        elif kind == "gear":
            instance_id = int(item_id)
            gear = self.gear_instance(user_id, instance_id)
            if gear is None:
                return {"ok": False, "reason": "Gear not found."}
            if gear.get("equipped_slot"):
                self.unequip_gear(user_id, gear["equipped_slot"])
            meta = {"gear_key": gear["id"], "level": gear["level"]}
            with self.conn() as c:
                deleted = c.execute("DELETE FROM gear WHERE user_id=? AND id=?", (int(user_id), instance_id))
                if deleted.rowcount == 0:
                    return {"ok": False, "reason": "Gear not found."}
            item_id = meta["gear_key"]
        else:
            return {"ok": False, "reason": "Unsupported listing type."}
        with self.conn() as c:
            cursor = c.execute(
                "INSERT INTO market(seller_id, kind, item_id, qty, price, meta, created_at) VALUES(?,?,?,?,?,?,?)",
                (int(user_id), kind, item_id, qty, price, json.dumps(meta or {}), _now()),
            )
        return {"ok": True, "listing_id": int(cursor.lastrowid)}

    def market_buy(self, user_id: int, listing_id: int) -> dict:
        with self.conn() as c:
            row = c.execute("SELECT * FROM market WHERE id=?", (int(listing_id),)).fetchone()
            if row is None:
                return {"ok": False, "reason": "Listing not found."}
            if int(row["seller_id"]) == int(user_id):
                return {"ok": False, "reason": "You cannot buy your own listing."}
            buyer = c.execute("SELECT yens FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if buyer is None or int(buyer["yens"]) < int(row["price"]):
                return {"ok": False, "reason": "Not enough yens."}
            c.execute("UPDATE players SET yens=yens-? WHERE user_id=?", (int(row["price"]), int(user_id)))
            c.execute("UPDATE players SET yens=yens+?, market_sales=market_sales+1 WHERE user_id=?", (int(row["price"]), int(row["seller_id"])))
            meta = json.loads(row["meta"] or "{}")
            if row["kind"] == "item":
                c.execute(
                    "INSERT INTO items(user_id, item_id, qty) VALUES(?,?,?) ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+?",
                    (int(user_id), row["item_id"], int(row["qty"]), int(row["qty"])),
                )
            elif row["kind"] == "gear":
                gear_key = meta.get("gear_key") or row["item_id"]
                level = int(meta.get("level", 1))
                c.execute("INSERT INTO gear(user_id, gear_id, level, acquired_at) VALUES(?,?,?,?)", (int(user_id), gear_key, level, _now()))
            c.execute("DELETE FROM market WHERE id=?", (int(listing_id),))
        self.bump(int(row["seller_id"]), "market_sales", 1)
        return {"ok": True, "price": int(row["price"]), "name": row["item_id"], "kind": row["kind"]}

    def market_cancel(self, user_id: int, listing_id: int) -> dict:
        with self.conn() as c:
            row = c.execute("SELECT * FROM market WHERE id=? AND seller_id=?", (int(listing_id), int(user_id))).fetchone()
            if row is None:
                return {"ok": False, "reason": "Listing not found."}
            meta = json.loads(row["meta"] or "{}")
            if row["kind"] == "item":
                c.execute(
                    "INSERT INTO items(user_id, item_id, qty) VALUES(?,?,?) ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+?",
                    (int(user_id), row["item_id"], int(row["qty"]), int(row["qty"])),
                )
            elif row["kind"] == "gear":
                c.execute("INSERT INTO gear(user_id, gear_id, level, acquired_at) VALUES(?,?,?,?)", (int(user_id), meta.get("gear_key", row["item_id"]), int(meta.get("level", 1)), _now()))
            c.execute("DELETE FROM market WHERE id=?", (int(listing_id),))
        return {"ok": True, "name": row["item_id"], "kind": row["kind"]}

    def leaderboard_wealth(self, limit: int = 5) -> dict[str, list[dict]]:
        columns = ("yens", "gems", "crystals")
        result: dict[str, list[dict]] = {}
        with self.conn() as c:
            for column in columns:
                rows = c.execute(
                    f"SELECT user_id, username, first_name, level, rank, {column} AS amount FROM players "
                    f"WHERE banned=0 ORDER BY {column} DESC, level DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
                result[column] = _rows_to_dicts(rows)
            rows = c.execute(
                "SELECT p.user_id, p.username, p.first_name, p.level, p.rank, COUNT(c.char_id) AS amount "
                "FROM players p LEFT JOIN characters c ON c.user_id=p.user_id "
                "WHERE p.banned=0 GROUP BY p.user_id ORDER BY amount DESC, p.level DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            result["characters"] = _rows_to_dicts(rows)
        return result

    def leaderboard_players(self, limit: int = 10, order: str = "level") -> list[dict]:
        allowed = {
            "level": "level DESC, exp DESC",
            "wins": "wins DESC, level DESC",
            "arena": "arena_rating DESC, wins DESC",
            "gacha": "gacha_pulls DESC",
            "raid": "raid_damage DESC",
        }
        ordering = allowed.get(order, allowed["level"])
        with self.conn() as c:
            rows = c.execute(f"SELECT user_id, username, first_name, level, rank, wins, losses, arena_rating, gacha_pulls, raid_damage, clan_id FROM players ORDER BY {ordering} LIMIT ?", (int(limit),)).fetchall()
        return _rows_to_dicts(rows)

    def duel_record(self, challenger_id: int, opponent_id: int, winner_id: int | None, rating_change: int = 0) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO duel_logs(challenger_id, opponent_id, winner_id, rating_change, created_at) VALUES(?,?,?,?,?)",
                (int(challenger_id), int(opponent_id), winner_id, int(rating_change), _now()),
            )

    def battle_record(self, user_id: int, enemy_name: str, result: str, damage: int = 0) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO battle_logs(user_id, enemy_name, result, damage, created_at) VALUES(?,?,?,?,?)",
                (int(user_id), enemy_name, result, int(damage), _now()),
            )

    def random_opponent(self, user_id: int) -> dict | None:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM players WHERE user_id<>? AND banned=0 AND equipped_char IS NOT NULL ORDER BY ABS(arena_rating - (SELECT arena_rating FROM players WHERE user_id=?)) LIMIT 5",
                (int(user_id), int(user_id)),
            ).fetchall()
        if not rows:
            return None
        import random
        return dict(random.choice(rows))

    def find_player(self, query: str) -> dict | None:
        query = str(query).strip().lstrip("@")
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM players WHERE CAST(user_id AS TEXT)=? OR LOWER(username)=LOWER(?) OR LOWER(first_name)=LOWER(?) ORDER BY last_seen DESC LIMIT 1",
                (query, query, query),
            ).fetchone()
        return _row_to_dict(row)

    def player_count(self) -> int:
        with self.conn() as c:
            return int(c.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"])

    def all_players(self, limit: int = 50) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM players ORDER BY last_seen DESC LIMIT ?", (int(limit),)).fetchall()
        return _rows_to_dicts(rows)

    def admin_set(self, user_id: int, field: str, value) -> None:
        self.set_field(user_id, field, value)

    def ban(self, user_id: int, banned: bool = True) -> None:
        self.set_field(user_id, "banned", 1 if banned else 0)
    def _transfer_tx(self, c: sqlite3.Connection, source_id: int, target_id: int, kind: str, asset_id, qty: int = 1) -> dict:
        source_id, target_id = int(source_id), int(target_id)
        if source_id == target_id:
            raise ValueError("Cannot transfer to yourself.")
        kind = str(kind).lower().strip()
        aliases = {"money": "yens", "gacha_ticket": "tickets", "gacha_tickets": "tickets", "sp": "skill_points"}
        kind = aliases.get(kind, kind)
        if kind in CURRENCY_COLUMNS:
            amount = int(asset_id if str(asset_id).lstrip("-").isdigit() else qty)
            if amount <= 0:
                raise ValueError("Amount must be positive.")
            row = c.execute(f"SELECT {kind} FROM players WHERE user_id=?", (source_id,)).fetchone()
            if row is None or int(row[kind]) < amount:
                raise ValueError(f"Not enough {kind}.")
            c.execute(f"UPDATE players SET {kind}={kind}-? WHERE user_id=?", (amount, source_id))
            if kind == "stamina":
                c.execute("UPDATE players SET stamina=MIN(max_stamina, stamina+?) WHERE user_id=?", (amount, target_id))
            else:
                c.execute(f"UPDATE players SET {kind}={kind}+? WHERE user_id=?", (amount, target_id))
            return {"kind": kind, "id": amount, "qty": 1, "label": f"{amount:,} {kind}"}
        if kind == "item":
            item_id = str(asset_id)
            qty = max(1, int(qty))
            if item_id not in data.ITEMS:
                raise ValueError("Unknown item.")
            row = c.execute("SELECT qty FROM items WHERE user_id=? AND item_id=?", (source_id, item_id)).fetchone()
            if row is None or int(row["qty"]) < qty:
                raise ValueError("You do not own that many.")
            c.execute("UPDATE items SET qty=qty-? WHERE user_id=? AND item_id=?", (qty, source_id, item_id))
            c.execute(
                "INSERT INTO items(user_id, item_id, qty) VALUES(?,?,?) ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+?",
                (target_id, item_id, qty, qty),
            )
            return {"kind": kind, "id": item_id, "qty": qty, "label": f"{data.ITEMS[item_id]['name']} x{qty}"}
        if kind == "shard":
            char_id = str(asset_id)
            qty = max(1, int(qty))
            row = c.execute("SELECT qty FROM character_shards WHERE user_id=? AND char_id=?", (source_id, char_id)).fetchone()
            if row is None or int(row["qty"]) < qty:
                raise ValueError("You do not own enough shards.")
            c.execute("UPDATE character_shards SET qty=qty-? WHERE user_id=? AND char_id=?", (qty, source_id, char_id))
            c.execute(
                "INSERT INTO character_shards(user_id, char_id, qty) VALUES(?,?,?) ON CONFLICT(user_id,char_id) DO UPDATE SET qty=qty+?",
                (target_id, char_id, qty, qty),
            )
            return {"kind": kind, "id": char_id, "qty": qty, "label": f"{qty} shards"}
        if kind == "character":
            char_id = str(asset_id)
            row = c.execute("SELECT * FROM characters WHERE user_id=? AND char_id=?", (source_id, char_id)).fetchone()
            if row is None:
                raise ValueError("You do not own that character.")
            if c.execute("SELECT 1 FROM characters WHERE user_id=? AND char_id=?", (target_id, char_id)).fetchone():
                raise ValueError("Target already owns that character.")
            c.execute("UPDATE characters SET user_id=? WHERE id=?", (target_id, int(row["id"])))
            src = c.execute("SELECT team, equipped_char FROM players WHERE user_id=?", (source_id,)).fetchone()
            if src:
                try:
                    team = json.loads(src["team"] or "[]")
                except (TypeError, ValueError):
                    team = []
                team = [cid for cid in team if cid != char_id]
                equipped = team[0] if team else None
                if src["equipped_char"] == char_id:
                    c.execute("UPDATE players SET team=?, equipped_char=? WHERE user_id=?", (json.dumps(team), equipped, source_id))
            dst = c.execute("SELECT team, equipped_char FROM players WHERE user_id=?", (target_id,)).fetchone()
            if dst and not dst["equipped_char"]:
                c.execute("UPDATE players SET equipped_char=?, team=? WHERE user_id=?", (char_id, json.dumps([char_id]), target_id))
            return {"kind": kind, "id": char_id, "qty": 1, "label": data.CHARACTERS[char_id]["name"]}
        if kind == "gear":
            instance_id = int(asset_id)
            row = c.execute("SELECT * FROM gear WHERE user_id=? AND id=?", (source_id, instance_id)).fetchone()
            if row is None:
                raise ValueError("Gear not found.")
            c.execute("UPDATE gear SET user_id=?, equipped_slot=NULL WHERE id=?", (target_id, instance_id))
            for slot in ("weapon", "armor", "accessory"):
                c.execute(f"UPDATE players SET {slot}=NULL WHERE user_id=? AND {slot}=?", (source_id, instance_id))
            base = data.GEAR.get(row["gear_id"], {})
            return {"kind": kind, "id": instance_id, "qty": 1, "label": f"{base.get('name', row['gear_id'])} Lv.{row['level']}"}
        if kind == "pet":
            pet_id = str(asset_id)
            row = c.execute("SELECT * FROM pets WHERE user_id=? AND pet_id=?", (source_id, pet_id)).fetchone()
            if row is None:
                raise ValueError("You do not own that companion.")
            if c.execute("SELECT 1 FROM pets WHERE user_id=? AND pet_id=?", (target_id, pet_id)).fetchone():
                raise ValueError("Target already owns that companion.")
            c.execute("UPDATE pets SET user_id=?, equipped=0 WHERE user_id=? AND pet_id=?", (target_id, source_id, pet_id))
            target_has = c.execute("SELECT 1 FROM pets WHERE user_id=? AND equipped=1", (target_id,)).fetchone()
            if not target_has:
                c.execute("UPDATE pets SET equipped=1 WHERE user_id=? AND pet_id=?", (target_id, pet_id))
            return {"kind": kind, "id": pet_id, "qty": 1, "label": data.PETS[pet_id]["name"]}
        raise ValueError("Unsupported asset type.")

    def transfer_asset(self, source_id: int, target_id: int, kind: str, asset_id, qty: int = 1) -> dict:
        try:
            with self.conn() as c:
                if c.execute("SELECT 1 FROM players WHERE user_id=?", (int(target_id),)).fetchone() is None:
                    return {"ok": False, "reason": "Target player not found."}
                moved = self._transfer_tx(c, source_id, target_id, kind, asset_id, qty)
        except ValueError as exc:
            return {"ok": False, "reason": str(exc)}
        return {"ok": True, **moved}

    def grant_asset(self, target_id: int, kind: str, asset_id, qty: int = 1) -> dict:
        kind = str(kind).lower().strip()
        aliases = {"money": "yens", "gacha_ticket": "tickets", "gacha_tickets": "tickets", "sp": "skill_points", "char": "character"}
        kind = aliases.get(kind, kind)
        target_id = int(target_id)
        if self.player(target_id) is None:
            return {"ok": False, "reason": "Player not found."}
        qty = max(1, int(qty))
        if kind in ("yens", "gems", "crystals", "tickets", "stamina", "skill_points"):
            amount = int(asset_id if str(asset_id).lstrip("-").isdigit() else qty)
            if amount < 0:
                return {"ok": False, "reason": "Amount cannot be negative."}
            self.add_currency(target_id, kind, amount)
            return {"ok": True, "message": f"Added {amount:,} {kind}."}
        if kind == "exp":
            amount = int(asset_id if str(asset_id).lstrip("-").isdigit() else qty)
            result = self.add_exp(target_id, amount)
            return {"ok": True, "message": f"Added {amount:,} EXP."}
        if kind == "level":
            level = max(1, min(100, int(asset_id if str(asset_id).isdigit() else qty)))
            self.set_field(target_id, "level", level)
            self.set_field(target_id, "rank", data.rank_for_level(level)["name"])
            self.bump(target_id, "level", level)
            return {"ok": True, "message": f"Set level to {level}."}
        if kind == "character":
            char_id = str(asset_id)
            if char_id not in data.CHARACTERS:
                return {"ok": False, "reason": "Unknown character."}
            new, base = self.add_character(target_id, char_id, level=max(1, min(100, qty)))
            return {"ok": True, "message": f"{'Added' if new else 'Added duplicate shards for'} {base['name']}."}
        if kind == "gear":
            gear_id = str(asset_id)
            if gear_id not in data.GEAR:
                return {"ok": False, "reason": "Unknown gear."}
            instance = self.grant_gear(target_id, gear_id, max(1, min(50, qty)))
            return {"ok": True, "message": f"Added {data.GEAR[gear_id]['name']} Lv.{qty} (instance {instance})."}
        if kind == "item":
            item_id = str(asset_id)
            if item_id not in data.ITEMS:
                return {"ok": False, "reason": "Unknown item."}
            self.add_item(target_id, item_id, qty)
            return {"ok": True, "message": f"Added {data.ITEMS[item_id]['name']} x{qty}."}
        if kind in ("shard", "shards"):
            char_id = str(asset_id)
            if char_id not in data.CHARACTERS:
                return {"ok": False, "reason": "Unknown character."}
            self.add_shards(target_id, char_id, qty)
            return {"ok": True, "message": f"Added {qty} shards for {data.CHARACTERS[char_id]['name']}."}
        if kind == "pet":
            pet_id = str(asset_id)
            if pet_id not in data.PETS:
                return {"ok": False, "reason": "Unknown companion."}
            new, base = self.add_pet(target_id, pet_id, level=max(1, min(50, qty)))
            return {"ok": True, "message": f"Added {base['name']}."}
        if kind == "title":
            title_id = str(asset_id)
            if title_id not in data.TITLES:
                return {"ok": False, "reason": "Unknown title."}
            self.set_field(target_id, "title", title_id)
            return {"ok": True, "message": f"Equipped title {data.TITLES[title_id]['name']}."}
        if kind in ("all", "everything", "bundle"):
            self.give(target_id, yens=100000, gems=10000, crystals=5000, tickets=100, skill_points=100)
            char_id = random.choice(list(data.CHARACTERS))
            self.add_character(target_id, char_id, level=50)
            gear_id = random.choice(list(data.GEAR))
            self.grant_gear(target_id, gear_id, 10)
            pet_id = random.choice(list(data.PETS))
            self.add_pet(target_id, pet_id, 10)
            for item_id in ("senzu_large", "exp_tome", "awakening_stone", "forge_core", "rank_divine_core", "boss_key", "raid_token"):
                if item_id in data.ITEMS:
                    self.add_item(target_id, item_id, 99)
            return {"ok": True, "message": f"Granted the ultimate bundle to {target_id}."}
        return {"ok": False, "reason": "Unknown asset type."}

    def trade_create(self, initiator_id: int, target_id: int) -> dict:
        initiator_id, target_id = int(initiator_id), int(target_id)
        if initiator_id == target_id:
            return {"ok": False, "reason": "You cannot trade with yourself."}
        if self.player(target_id) is None:
            return {"ok": False, "reason": "Player not found."}
        with self.conn() as c:
            active = c.execute("SELECT * FROM trades WHERE status='active' AND (initiator_id=? OR target_id=? OR initiator_id=? OR target_id=?)", (initiator_id, initiator_id, target_id, target_id)).fetchone()
            if active:
                return {"ok": False, "reason": "One of you already has an active trade."}
            cursor = c.execute(
                "INSERT INTO trades(initiator_id, target_id, offers, status, created_at, updated_at) VALUES(?,?, '{}', 'active', ?, ?)",
                (initiator_id, target_id, _now(), _now()),
            )
            row = c.execute("SELECT * FROM trades WHERE id=?", (int(cursor.lastrowid),)).fetchone()
        return {"ok": True, "trade": _row_to_dict(row)}

    def trade_for(self, user_id: int) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM trades WHERE status='active' AND (initiator_id=? OR target_id=?) ORDER BY id DESC LIMIT 1", (int(user_id), int(user_id))).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def _trade_side(trade: dict, user_id: int) -> str | None:
        if int(trade["initiator_id"]) == int(user_id):
            return "initiator"
        if int(trade["target_id"]) == int(user_id):
            return "target"
        return None

    def _trade_offers(self, trade: dict) -> dict:
        try:
            offers = json.loads(trade.get("offers") or "{}")
        except (TypeError, ValueError):
            offers = {}
        return {"initiator": list(offers.get("initiator", [])), "target": list(offers.get("target", []))}

    def _offered_amount(self, offers: list[dict], kind: str, asset_id: str) -> int:
        total = 0
        for offer in offers:
            if offer.get("kind") == kind and str(offer.get("id")) == str(asset_id):
                total += int(offer.get("qty", 0))
        return total

    def trade_add(self, user_id: int, kind: str, asset_id, qty: int = 1) -> dict:
        trade = self.trade_for(user_id)
        if trade is None:
            return {"ok": False, "reason": "You have no active trade. Start one with /trade <user>."}
        side = self._trade_side(trade, user_id)
        if side is None:
            return {"ok": False, "reason": "You are not part of that trade."}
        kind = {"money": "yens", "gacha_ticket": "tickets", "sp": "skill_points"}.get(kind.lower(), kind.lower())
        qty = max(1, int(qty))
        with self.conn() as c:
            player = c.execute("SELECT * FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            if player is None:
                return {"ok": False, "reason": "Player not found."}
            offers = self._trade_offers(trade)
            mine = offers[side]
            if len(mine) >= config.TRADE_MAX_OFFERS:
                return {"ok": False, "reason": "Too many offers in this trade."}
            if kind in CURRENCY_COLUMNS:
                amount = int(asset_id if str(asset_id).lstrip("-").isdigit() else qty)
                if amount <= 0:
                    return {"ok": False, "reason": "Amount must be positive."}
                offered = sum(int(offer.get("id", 0)) for offer in mine if offer.get("kind") == kind)
                available = int(player[kind]) - offered
                if amount > available:
                    return {"ok": False, "reason": f"Not enough {kind}."}
                mine.append({"kind": kind, "id": str(amount), "qty": 1})
            elif kind == "item":
                item_id = str(asset_id)
                if item_id not in data.ITEMS:
                    return {"ok": False, "reason": "Unknown item."}
                owned = int((c.execute("SELECT qty FROM items WHERE user_id=? AND item_id=?", (int(user_id), item_id)).fetchone() or {"qty": 0})["qty"])
                if owned - self._offered_amount(mine, kind, item_id) < qty:
                    return {"ok": False, "reason": "You do not own that many."}
                mine.append({"kind": kind, "id": item_id, "qty": qty})
            elif kind == "character":
                char_id = str(asset_id)
                if not c.execute("SELECT 1 FROM characters WHERE user_id=? AND char_id=?", (int(user_id), char_id)).fetchone():
                    return {"ok": False, "reason": "You do not own that character."}
                if any(offer["kind"] == kind and offer["id"] == char_id for offer in mine):
                    return {"ok": False, "reason": "That character is already offered."}
                mine.append({"kind": kind, "id": char_id, "qty": 1})
            elif kind == "gear":
                instance_id = int(asset_id)
                if c.execute("SELECT 1 FROM gear WHERE user_id=? AND id=?", (int(user_id), instance_id)).fetchone() is None:
                    return {"ok": False, "reason": "Gear not found."}
                if any(offer["kind"] == kind and str(offer["id"]) == str(instance_id) for offer in mine):
                    return {"ok": False, "reason": "That gear is already offered."}
                mine.append({"kind": kind, "id": str(instance_id), "qty": 1})
            elif kind == "pet":
                pet_id = str(asset_id)
                if not c.execute("SELECT 1 FROM pets WHERE user_id=? AND pet_id=?", (int(user_id), pet_id)).fetchone():
                    return {"ok": False, "reason": "You do not own that companion."}
                if any(offer["kind"] == kind and offer["id"] == pet_id for offer in mine):
                    return {"ok": False, "reason": "That companion is already offered."}
                mine.append({"kind": kind, "id": pet_id, "qty": 1})
            elif kind in ("shard", "shards"):
                char_id = str(asset_id)
                owned = int((c.execute("SELECT qty FROM character_shards WHERE user_id=? AND char_id=?", (int(user_id), char_id)).fetchone() or {"qty": 0})["qty"])
                if owned - self._offered_amount(mine, "shard", char_id) < qty:
                    return {"ok": False, "reason": "You do not own enough shards."}
                mine.append({"kind": "shard", "id": char_id, "qty": qty})
            else:
                return {"ok": False, "reason": "Trade characters, gear, items, pets, shards, or currencies."}
            offers[side] = mine
            c.execute("UPDATE trades SET offers=?, initiator_ok=0, target_ok=0, updated_at=? WHERE id=?", (json.dumps(offers), _now(), int(trade["id"])))
        return {"ok": True, "trade": self.trade_for(user_id), "offers": offers}

    def trade_remove(self, user_id: int, kind: str, asset_id=None) -> dict:
        trade = self.trade_for(user_id)
        if trade is None:
            return {"ok": False, "reason": "You have no active trade."}
        side = self._trade_side(trade, user_id)
        if side is None:
            return {"ok": False, "reason": "You are not part of that trade."}
        kind = {"money": "yens", "gacha_ticket": "tickets", "sp": "skill_points"}.get(kind.lower(), kind.lower())
        with self.conn() as c:
            offers = self._trade_offers(trade)
            kept = []
            removed = False
            for offer in offers[side]:
                if not removed and offer["kind"] == kind and (asset_id is None or str(offer["id"]) == str(asset_id)):
                    removed = True
                    continue
                kept.append(offer)
            if not removed:
                return {"ok": False, "reason": "Offer not found."}
            offers[side] = kept
            c.execute("UPDATE trades SET offers=?, initiator_ok=0, target_ok=0, updated_at=? WHERE id=?", (json.dumps(offers), _now(), int(trade["id"])))
        return {"ok": True, "trade": self.trade_for(user_id)}

    def trade_confirm(self, user_id: int) -> dict:
        trade = self.trade_for(user_id)
        if trade is None:
            return {"ok": False, "reason": "You have no active trade."}
        side = self._trade_side(trade, user_id)
        if side is None:
            return {"ok": False, "reason": "You are not part of that trade."}
        offers = self._trade_offers(trade)
        if not offers[side]:
            return {"ok": False, "reason": "Offer at least one item before confirming."}
        with self.conn() as c:
            c.execute(f"UPDATE trades SET {side}_ok=1, updated_at=? WHERE id=?", (_now(), int(trade["id"])))
            row = c.execute("SELECT * FROM trades WHERE id=?", (int(trade["id"]),)).fetchone()
            if not (row["initiator_ok"] and row["target_ok"]):
                return {"ok": True, "waiting": True, "trade": _row_to_dict(row)}
            offers = self._trade_offers(dict(row))
            if not offers["initiator"] or not offers["target"]:
                c.execute("UPDATE trades SET initiator_ok=0, target_ok=0, updated_at=? WHERE id=?", (_now(), int(row["id"])))
                return {"ok": False, "reason": "Both players must offer at least one item before the trade can complete."}
            c.execute("SAVEPOINT trade_execute")
            try:
                for offer in offers["initiator"]:
                    self._transfer_tx(c, int(row["initiator_id"]), int(row["target_id"]), offer["kind"], offer["id"], int(offer.get("qty", 1)))
                for offer in offers["target"]:
                    self._transfer_tx(c, int(row["target_id"]), int(row["initiator_id"]), offer["kind"], offer["id"], int(offer.get("qty", 1)))
            except ValueError as exc:
                c.execute("ROLLBACK TO trade_execute")
                c.execute("RELEASE trade_execute")
                c.execute("UPDATE trades SET initiator_ok=0, target_ok=0, updated_at=? WHERE id=?", (_now(), int(row["id"])))
                return {"ok": False, "reason": str(exc)}
            c.execute("RELEASE trade_execute")
            c.execute("UPDATE trades SET status='completed', offers='{}', updated_at=? WHERE id=?", (_now(), int(row["id"])))
        return {"ok": True, "completed": True, "trade": trade, "offers": offers}

    def trade_cancel(self, user_id: int) -> dict:
        trade = self.trade_for(user_id)
        if trade is None:
            return {"ok": False, "reason": "You have no active trade."}
        with self.conn() as c:
            c.execute("UPDATE trades SET status='cancelled', updated_at=? WHERE id=?", (_now(), int(trade["id"])))
        return {"ok": True, "trade": trade}

    def boss_state(self, user_id: int, boss: dict) -> dict:
        now = _now()
        with self.conn() as c:
            row = c.execute("SELECT * FROM boss_progress WHERE user_id=? AND boss_id=?", (int(user_id), boss["id"])).fetchone()
            if row is None:
                c.execute("INSERT INTO boss_progress(user_id, boss_id, hp, max_hp, status, updated_at) VALUES(?,?,?,?, 'active', ?)", (int(user_id), boss["id"], int(boss["hp"]), int(boss["hp"]), now))
                row = c.execute("SELECT * FROM boss_progress WHERE user_id=? AND boss_id=?", (int(user_id), boss["id"])).fetchone()
        result = _row_to_dict(row) or {}
        result["boss"] = boss
        return result

    def damage_boss(self, user_id: int, boss: dict, damage: int) -> dict:
        state = self.boss_state(user_id, boss)
        hp = max(0, int(state["hp"]) - max(0, int(damage)))
        status = "defeated" if hp == 0 else "active"
        with self.conn() as c:
            c.execute("UPDATE boss_progress SET hp=?, status=?, updated_at=? WHERE user_id=? AND boss_id=?", (hp, status, _now(), int(user_id), boss["id"]))
        state.update({"hp": hp, "status": status})
        return state

    def reset_boss(self, user_id: int, boss_id: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM boss_progress WHERE user_id=? AND boss_id=?", (int(user_id), boss_id))

    def summon_state(self, user_id: int, boss: dict) -> dict:
        with self.conn() as c:
            row = c.execute("SELECT * FROM summon_bosses WHERE user_id=? AND boss_id=?", (int(user_id), boss["id"])).fetchone()
            if row is None or row["status"] == "defeated":
                c.execute(
                    "INSERT INTO summon_bosses(user_id, boss_id, hp, max_hp, status, updated_at) VALUES(?,?,?,?, 'active', ?) ON CONFLICT(user_id,boss_id) DO UPDATE SET hp=excluded.hp, max_hp=excluded.max_hp, status='active', updated_at=excluded.updated_at",
                    (int(user_id), boss["id"], int(boss["hp"]), int(boss["hp"]), _now()),
                )
                row = c.execute("SELECT * FROM summon_bosses WHERE user_id=? AND boss_id=?", (int(user_id), boss["id"])).fetchone()
        result = _row_to_dict(row) or {}
        result["boss"] = boss
        return result

    def damage_summon(self, user_id: int, boss: dict, damage: int) -> dict:
        state = self.summon_state(user_id, boss)
        hp = max(0, int(state["hp"]) - max(0, int(damage)))
        status = "defeated" if hp == 0 else "active"
        with self.conn() as c:
            c.execute("UPDATE summon_bosses SET hp=?, status=?, updated_at=? WHERE user_id=? AND boss_id=?", (hp, status, _now(), int(user_id), boss["id"]))
        state.update({"hp": hp, "status": status})
        return state

    def chapter_progress(self, user_id: int, series: str) -> dict[int, str]:
        with self.conn() as c:
            rows = c.execute("SELECT chapter, cleared_at FROM chapter_progress WHERE user_id=? AND series=?", (int(user_id), series)).fetchall()
        return {int(row["chapter"]): row["cleared_at"] for row in rows}

    def clear_chapter(self, user_id: int, series: str, chapter: int) -> None:
        with self.conn() as c:
            c.execute("INSERT OR IGNORE INTO chapter_progress(user_id, series, chapter, cleared_at) VALUES(?,?,?,?)", (int(user_id), series, int(chapter), _now()))


    def set_vitals(self, user_id: int, *, hp: int | None = None, mp: int | None = None) -> dict:
        updates: list[str] = []
        values: list[int] = []
        if hp is not None:
            updates.append("current_hp=?")
            values.append(max(0, int(hp)))
        if mp is not None:
            updates.append("mp=?")
            values.append(max(0, int(mp)))
        if updates:
            values.append(int(user_id))
            with self.conn() as c:
                c.execute(f"UPDATE players SET {', '.join(updates)} WHERE user_id=?", values)
        return self.require_player(user_id)

    def heal_player(self, user_id: int, hp: int = 0, mp: int = 0) -> dict:
        player = self.require_player(user_id)
        new_hp = min(int(player.get("hp", 1)), max(0, int(player.get("current_hp", 1))) + max(0, int(hp)))
        new_mp = min(int(player.get("max_mp", 200)), max(0, int(player.get("mp", 0))) + max(0, int(mp)))
        self.set_vitals(user_id, hp=new_hp, mp=new_mp)
        return {"hp": new_hp, "max_hp": int(player.get("hp", 1)), "mp": new_mp, "max_mp": int(player.get("max_mp", 200))}

    def allocate_stat(self, user_id: int, stat: str, points: int = 1) -> dict:
        allowed = {"strength", "agility", "intellect", "vitality", "luck"}
        stat = stat.lower()
        if stat not in allowed:
            return {"ok": False, "reason": "Unknown stat."}
        points = max(1, int(points))
        player = self.require_player(user_id)
        if int(player.get("stat_points", 0)) < points:
            return {"ok": False, "reason": "Not enough stat points."}
        with self.conn() as c:
            c.execute(
                f"UPDATE players SET {stat}={stat}+?, stat_points=stat_points-? WHERE user_id=? AND stat_points>=?",
                (points, points, int(user_id), points),
            )
        return {"ok": True, "stat": stat, "points": points}

    def active_battle(self, user_id: int) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM active_battles WHERE user_id=? ORDER BY updated_at DESC LIMIT 1", (int(user_id),)).fetchone()
        battle = _row_to_dict(row)
        if battle:
            try:
                battle["state"] = json.loads(battle["state"])
            except (TypeError, ValueError):
                battle["state"] = {}
        return battle

    def save_battle(self, battle: dict) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO active_battles(battle_id, user_id, mode, title, state, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(battle_id) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at",
                (
                    battle["battle_id"], int(battle["user_id"]), battle["mode"], battle["title"],
                    json.dumps(battle["state"], ensure_ascii=False), battle["created_at"], _now(),
                ),
            )

    def clear_battle(self, user_id: int) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM active_battles WHERE user_id=?", (int(user_id),))

    def art_set(self, entity_type: str, entity_key: str, name: str, file_id: str, uploaded_by: int | None = None) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO custom_art(entity_type, entity_key, name, file_id, uploaded_by, uploaded_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(entity_type,entity_key) DO UPDATE SET name=excluded.name, file_id=excluded.file_id, uploaded_by=excluded.uploaded_by, uploaded_at=excluded.uploaded_at",
                (entity_type, entity_key, name, file_id, int(uploaded_by) if uploaded_by else None, _now()),
            )

    def art_get(self, entity_type: str, entity_key: str) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM custom_art WHERE entity_type=? AND entity_key=?", (entity_type, entity_key)).fetchone()
        return _row_to_dict(row)

    def art_list(self, entity_type: str | None = None) -> list[dict]:
        with self.conn() as c:
            if entity_type:
                rows = c.execute("SELECT * FROM custom_art WHERE entity_type=? ORDER BY name", (entity_type,)).fetchall()
            else:
                rows = c.execute("SELECT * FROM custom_art ORDER BY entity_type, name").fetchall()
        return _rows_to_dicts(rows)

    def art_keys(self, entity_type: str) -> set[str]:
        with self.conn() as c:
            rows = c.execute("SELECT entity_key FROM custom_art WHERE entity_type=?", (entity_type,)).fetchall()
        return {row["entity_key"] for row in rows}

    def reset_player(self, user_id: int) -> None:
        with self.conn() as c:
            for table in ("characters", "character_shards", "pets", "items", "gear", "skills", "counters", "quest_claims", "achievement_claims", "active_battles"):
                c.execute(f"DELETE FROM {table} WHERE user_id=?", (int(user_id),))
            c.execute("UPDATE players SET clan_id=NULL WHERE user_id=?", (int(user_id),))
            c.execute("DELETE FROM clan_members WHERE user_id=?", (int(user_id),))
            c.execute("DELETE FROM players WHERE user_id=?", (int(user_id),))
