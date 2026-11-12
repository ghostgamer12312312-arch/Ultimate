"""Async SQLite persistence layer.

A single connection is shared by the bot event loop and protected by an
``asyncio.Lock``. Tests can instantiate :class:`Database` with a temporary
file path and call :meth:`connect` / :meth:`init` / :meth:`close`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    user_id         INTEGER PRIMARY KEY,
    username        TEXT,
    display_name    TEXT,
    race            TEXT NOT NULL DEFAULT 'human',
    class           TEXT NOT NULL DEFAULT 'warrior',
    level           INTEGER NOT NULL DEFAULT 1,
    xp              INTEGER NOT NULL DEFAULT 0,
    gold            INTEGER NOT NULL DEFAULT 200,
    gems            INTEGER NOT NULL DEFAULT 3,
    stat_points     INTEGER NOT NULL DEFAULT 5,
    strength        INTEGER NOT NULL DEFAULT 5,
    agility         INTEGER NOT NULL DEFAULT 5,
    intellect       INTEGER NOT NULL DEFAULT 5,
    vitality        INTEGER NOT NULL DEFAULT 5,
    luck            INTEGER NOT NULL DEFAULT 5,
    hp              INTEGER NOT NULL DEFAULT 100,
    mana            INTEGER NOT NULL DEFAULT 50,
    wins            INTEGER NOT NULL DEFAULT 0,
    losses          INTEGER NOT NULL DEFAULT 0,
    boss_kills      INTEGER NOT NULL DEFAULT 0,
    daily_streak    INTEGER NOT NULL DEFAULT 0,
    last_daily      TEXT,
    clan_id         INTEGER,
    current_quest   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_players_level ON players(level DESC);
CREATE INDEX IF NOT EXISTS idx_players_gold ON players(gold DESC);
CREATE INDEX IF NOT EXISTS idx_players_wins ON players(wins DESC);
CREATE INDEX IF NOT EXISTS idx_players_clan ON players(clan_id);
CREATE INDEX IF NOT EXISTS idx_players_username ON players(username COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS inventory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL,
    item_id     TEXT NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1,
    UNIQUE(player_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_inventory_player ON inventory(player_id);

CREATE TABLE IF NOT EXISTS equipment (
    player_id   INTEGER NOT NULL,
    slot        TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    PRIMARY KEY(player_id, slot)
);

CREATE TABLE IF NOT EXISTS clans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    tag         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    owner_id    INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    bank_gold   INTEGER NOT NULL DEFAULT 0,
    level       INTEGER NOT NULL DEFAULT 1,
    xp          INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    losses      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clans_level ON clans(level DESC, xp DESC);

CREATE TABLE IF NOT EXISTS clan_members (
    clan_id       INTEGER NOT NULL,
    player_id     INTEGER NOT NULL,
    role          TEXT NOT NULL DEFAULT 'member',
    contribution  INTEGER NOT NULL DEFAULT 0,
    joined_at     TEXT NOT NULL,
    PRIMARY KEY(clan_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_clan_members_player ON clan_members(player_id);

CREATE TABLE IF NOT EXISTS clan_invites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    clan_id     INTEGER NOT NULL,
    inviter_id  INTEGER NOT NULL,
    invitee_id  INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE(clan_id, invitee_id)
);
CREATE INDEX IF NOT EXISTS idx_clan_invites_invitee ON clan_invites(invitee_id);

CREATE TABLE IF NOT EXISTS clan_wars (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    attacker_id    INTEGER NOT NULL,
    defender_id    INTEGER NOT NULL,
    attacker_score INTEGER NOT NULL,
    defender_score INTEGER NOT NULL,
    winner_id      INTEGER,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_quests (
    player_id     INTEGER NOT NULL,
    quest_id      TEXT NOT NULL,
    stage         INTEGER NOT NULL DEFAULT 0,
    progress      INTEGER NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1,
    completed_at  TEXT,
    PRIMARY KEY(player_id, quest_id)
);
CREATE INDEX IF NOT EXISTS idx_player_quests_player ON player_quests(player_id);

CREATE TABLE IF NOT EXISTS quests (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    min_level   INTEGER NOT NULL DEFAULT 1,
    stages_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS market_listings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id   INTEGER NOT NULL,
    item_id     TEXT NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1,
    price       INTEGER NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_active ON market_listings(active, created_at DESC);

CREATE TABLE IF NOT EXISTS duel_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    challenger_id INTEGER NOT NULL,
    opponent_id   INTEGER NOT NULL,
    winner_id     INTEGER,
    rounds        INTEGER NOT NULL DEFAULT 0,
    log           TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_duel_logs_players ON duel_logs(challenger_id, opponent_id);
"""

PLAYER_COLUMNS = {
    "username", "display_name", "race", "class", "level", "xp", "gold", "gems",
    "stat_points", "strength", "agility", "intellect", "vitality", "luck",
    "hp", "mana", "wins", "losses", "boss_kills", "daily_streak", "last_daily",
    "clan_id", "current_quest", "updated_at",
}

LEADERBOARD_COLUMNS = {"level", "gold", "wins", "boss_kills", "xp", "gems"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row: aiosqlite.Row | None) -> dict | None:
    return dict(row) if row is not None else None


class Database:
    """Small async wrapper around a single SQLite connection."""

    def __init__(self, path: str = "rpg.db") -> None:
        self.path = str(path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    # -- lifecycle ---------------------------------------------------------
    async def connect(self) -> "Database":
        if self._conn is not None:
            return self
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.commit()
        return self

    async def init(self) -> "Database":
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        async with self._lock:
            await self._conn.executescript(SCHEMA)
            await self._conn.commit()
        return self

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._conn

    # -- primitives --------------------------------------------------------
    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            await self.conn.commit()
            return int(cur.lastrowid or 0)

    async def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        async with self._lock:
            await self.conn.executemany(sql, [tuple(p) for p in seq])
            await self.conn.commit()

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            return _row(await cur.fetchone())

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def scalar(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            row = await cur.fetchone()
            if row is None:
                return default
            return row[0]

    # -- players -----------------------------------------------------------
    async def create_player(
        self,
        user_id: int,
        username: str | None,
        display_name: str,
        race: str,
        class_id: str,
        stats: dict[str, int],
        hp: int,
        mana: int,
        gold: int = 200,
        gems: int = 3,
        stat_points: int = 5,
    ) -> dict:
        now = _now()
        await self.execute(
            """
            INSERT INTO players (
                user_id, username, display_name, race, class, level, xp, gold, gems,
                stat_points, strength, agility, intellect, vitality, luck, hp, mana,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (
                user_id, (username or "").lower() or None, display_name, race, class_id,
                gold, gems, stat_points,
                int(stats.get("strength", 5)), int(stats.get("agility", 5)),
                int(stats.get("intellect", 5)), int(stats.get("vitality", 5)),
                int(stats.get("luck", 5)), hp, mana, now, now,
            ),
        )
        player = await self.get_player(user_id)
        assert player is not None
        return player

    async def get_player(self, user_id: int) -> dict | None:
        return await self.fetchone("SELECT * FROM players WHERE user_id = ?", (user_id,))

    async def get_player_by_username(self, username: str) -> dict | None:
        username = (username or "").lstrip("@").strip().lower()
        if not username:
            return None
        return await self.fetchone(
            "SELECT * FROM players WHERE username = ? COLLATE NOCASE", (username,)
        )

    async def player_exists(self, user_id: int) -> bool:
        return await self.scalar("SELECT 1 FROM players WHERE user_id = ?", (user_id,)) is not None

    async def update_player(self, user_id: int, **fields: Any) -> None:
        data = {k: v for k, v in fields.items() if k in PLAYER_COLUMNS}
        if not data:
            return
        data["updated_at"] = _now()
        columns = ", ".join(f"{key} = ?" for key in data)
        await self.execute(
            f"UPDATE players SET {columns} WHERE user_id = ?", (*data.values(), user_id)
        )

    async def add_gold(self, user_id: int, amount: int) -> None:
        await self.execute(
            "UPDATE players SET gold = MAX(0, gold + ?), updated_at = ? WHERE user_id = ?",
            (amount, _now(), user_id),
        )

    async def add_gems(self, user_id: int, amount: int) -> None:
        await self.execute(
            "UPDATE players SET gems = MAX(0, gems + ?), updated_at = ? WHERE user_id = ?",
            (amount, _now(), user_id),
        )

    async def count_players(self) -> int:
        return int(await self.scalar("SELECT COUNT(*) FROM players", default=0) or 0)

    async def get_all_players(self) -> list[dict]:
        return await self.fetchall("SELECT * FROM players ORDER BY user_id")

    async def get_top_players(self, column: str = "level", limit: int = 10) -> list[dict]:
        if column not in LEADERBOARD_COLUMNS:
            column = "level"
        return await self.fetchall(
            f"SELECT * FROM players ORDER BY {column} DESC, level DESC, xp DESC LIMIT ?",
            (max(1, int(limit)),),
        )

    async def increment_pvp(self, user_id: int, won: bool) -> None:
        column = "wins" if won else "losses"
        await self.execute(
            f"UPDATE players SET {column} = {column} + 1, updated_at = ? WHERE user_id = ?",
            (_now(), user_id),
        )

    async def increment_boss_kills(self, user_id: int, amount: int = 1) -> None:
        await self.execute(
            "UPDATE players SET boss_kills = boss_kills + ?, updated_at = ? WHERE user_id = ?",
            (amount, _now(), user_id),
        )

    # -- inventory ---------------------------------------------------------
    async def add_item(self, player_id: int, item_id: str, quantity: int = 1) -> None:
        if quantity <= 0:
            return
        await self.execute(
            """
            INSERT INTO inventory (player_id, item_id, quantity) VALUES (?, ?, ?)
            ON CONFLICT(player_id, item_id)
            DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (player_id, item_id, quantity),
        )

    async def remove_item(self, player_id: int, item_id: str, quantity: int = 1) -> bool:
        if quantity <= 0:
            return True
        async with self._lock:
            cur = await self.conn.execute(
                "SELECT quantity FROM inventory WHERE player_id = ? AND item_id = ?",
                (player_id, item_id),
            )
            row = await cur.fetchone()
            if row is None or row["quantity"] < quantity:
                return False
            if row["quantity"] == quantity:
                await self.conn.execute(
                    "DELETE FROM inventory WHERE player_id = ? AND item_id = ?",
                    (player_id, item_id),
                )
            else:
                await self.conn.execute(
                    "UPDATE inventory SET quantity = quantity - ? WHERE player_id = ? AND item_id = ?",
                    (quantity, player_id, item_id),
                )
            await self.conn.commit()
            return True

    async def get_inventory(self, player_id: int) -> list[dict]:
        return await self.fetchall(
            "SELECT item_id, quantity FROM inventory WHERE player_id = ? AND quantity > 0 ORDER BY item_id",
            (player_id,),
        )

    async def get_item_quantity(self, player_id: int, item_id: str) -> int:
        return int(await self.scalar(
            "SELECT quantity FROM inventory WHERE player_id = ? AND item_id = ?",
            (player_id, item_id), default=0,
        ) or 0)

    async def has_item(self, player_id: int, item_id: str, quantity: int = 1) -> bool:
        return await self.get_item_quantity(player_id, item_id) >= quantity

    # -- equipment ---------------------------------------------------------
    async def get_equipment(self, player_id: int) -> dict[str, str]:
        rows = await self.fetchall(
            "SELECT slot, item_id FROM equipment WHERE player_id = ?", (player_id,)
        )
        return {row["slot"]: row["item_id"] for row in rows}

    async def set_equipment(self, player_id: int, slot: str, item_id: str) -> str | None:
        async with self._lock:
            cur = await self.conn.execute(
                "SELECT item_id FROM equipment WHERE player_id = ? AND slot = ?",
                (player_id, slot),
            )
            row = await cur.fetchone()
            previous = row["item_id"] if row else None
            await self.conn.execute(
                """
                INSERT INTO equipment (player_id, slot, item_id) VALUES (?, ?, ?)
                ON CONFLICT(player_id, slot) DO UPDATE SET item_id = excluded.item_id
                """,
                (player_id, slot, item_id),
            )
            await self.conn.commit()
            return previous

    async def clear_equipment_slot(self, player_id: int, slot: str) -> str | None:
        async with self._lock:
            cur = await self.conn.execute(
                "SELECT item_id FROM equipment WHERE player_id = ? AND slot = ?",
                (player_id, slot),
            )
            row = await cur.fetchone()
            if row:
                await self.conn.execute(
                    "DELETE FROM equipment WHERE player_id = ? AND slot = ?",
                    (player_id, slot),
                )
                await self.conn.commit()
                return row["item_id"]
            return None

    # -- clans -------------------------------------------------------------
    async def create_clan(self, name: str, tag: str, owner_id: int, description: str = "") -> int:
        now = _now()
        async with self._lock:
            cur = await self.conn.execute(
                "INSERT INTO clans (name, tag, owner_id, description, created_at) VALUES (?, ?, ?, ?, ?)",
                (name.strip(), tag.strip().upper(), owner_id, description.strip(), now),
            )
            clan_id = int(cur.lastrowid)
            await self.conn.execute(
                "INSERT INTO clan_members (clan_id, player_id, role, joined_at) VALUES (?, ?, 'leader', ?)",
                (clan_id, owner_id, now),
            )
            await self.conn.execute(
                "UPDATE players SET clan_id = ?, updated_at = ? WHERE user_id = ?",
                (clan_id, now, owner_id),
            )
            await self.conn.commit()
            return clan_id

    async def get_clan(self, clan_id: int) -> dict | None:
        return await self.fetchone("SELECT * FROM clans WHERE id = ?", (clan_id,))

    async def get_clan_by_name(self, name: str) -> dict | None:
        return await self.fetchone(
            "SELECT * FROM clans WHERE name = ? COLLATE NOCASE", ((name or "").strip(),)
        )

    async def get_clan_by_tag(self, tag: str) -> dict | None:
        return await self.fetchone(
            "SELECT * FROM clans WHERE tag = ? COLLATE NOCASE", ((tag or "").strip().upper(),)
        )

    async def update_clan(self, clan_id: int, **fields: Any) -> None:
        allowed = {"name", "tag", "owner_id", "description", "bank_gold", "level", "xp", "wins", "losses"}
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return
        columns = ", ".join(f"{key} = ?" for key in data)
        await self.execute(
            f"UPDATE clans SET {columns} WHERE id = ?", (*data.values(), clan_id)
        )

    async def delete_clan(self, clan_id: int) -> None:
        async with self._lock:
            await self.conn.execute("DELETE FROM clan_members WHERE clan_id = ?", (clan_id,))
            await self.conn.execute("DELETE FROM clan_invites WHERE clan_id = ?", (clan_id,))
            await self.conn.execute("UPDATE players SET clan_id = NULL WHERE clan_id = ?", (clan_id,))
            await self.conn.execute("DELETE FROM clans WHERE id = ?", (clan_id,))
            await self.conn.commit()

    async def add_clan_member(self, clan_id: int, player_id: int, role: str = "member") -> None:
        now = _now()
        async with self._lock:
            await self.conn.execute(
                "INSERT INTO clan_members (clan_id, player_id, role, joined_at) VALUES (?, ?, ?, ?)",
                (clan_id, player_id, role, now),
            )
            await self.conn.execute(
                "UPDATE players SET clan_id = ?, updated_at = ? WHERE user_id = ?",
                (clan_id, now, player_id),
            )
            await self.conn.commit()

    async def remove_clan_member(self, clan_id: int, player_id: int) -> None:
        now = _now()
        async with self._lock:
            await self.conn.execute(
                "DELETE FROM clan_members WHERE clan_id = ? AND player_id = ?",
                (clan_id, player_id),
            )
            await self.conn.execute(
                "UPDATE players SET clan_id = NULL, updated_at = ? WHERE user_id = ?",
                (now, player_id),
            )
            await self.conn.commit()

    async def get_clan_member(self, player_id: int) -> dict | None:
        return await self.fetchone(
            "SELECT * FROM clan_members WHERE player_id = ?", (player_id,)
        )

    async def get_clan_member_count(self, clan_id: int) -> int:
        return int(await self.scalar(
            "SELECT COUNT(*) FROM clan_members WHERE clan_id = ?", (clan_id,), default=0
        ) or 0)

    async def get_clan_members(self, clan_id: int) -> list[dict]:
        return await self.fetchall(
            """
            SELECT cm.*, p.display_name, p.username, p.level, p.class, p.race,
                   p.strength, p.agility, p.intellect, p.vitality, p.luck, p.hp
            FROM clan_members cm
            JOIN players p ON p.user_id = cm.player_id
            WHERE cm.clan_id = ?
            ORDER BY CASE cm.role WHEN 'leader' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END,
                     cm.contribution DESC
            """,
            (clan_id,),
        )

    async def get_player_clan(self, player_id: int) -> dict | None:
        return await self.fetchone(
            """
            SELECT c.*, cm.role AS member_role, cm.contribution AS member_contribution
            FROM clans c
            JOIN clan_members cm ON cm.clan_id = c.id
            WHERE cm.player_id = ?
            """,
            (player_id,),
        )

    async def add_clan_contribution(self, clan_id: int, player_id: int, amount: int) -> None:
        async with self._lock:
            await self.conn.execute(
                "UPDATE clans SET bank_gold = bank_gold + ? WHERE id = ?", (amount, clan_id)
            )
            await self.conn.execute(
                "UPDATE clan_members SET contribution = contribution + ? WHERE clan_id = ? AND player_id = ?",
                (amount, clan_id, player_id),
            )
            await self.conn.commit()

    async def get_clan_leaderboard(self, limit: int = 10) -> list[dict]:
        return await self.fetchall(
            """
            SELECT c.*, COUNT(cm.player_id) AS member_count
            FROM clans c LEFT JOIN clan_members cm ON cm.clan_id = c.id
            GROUP BY c.id
            ORDER BY c.level DESC, c.xp DESC, c.bank_gold DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    # -- clan invites / wars ----------------------------------------------
    async def add_clan_invite(self, clan_id: int, inviter_id: int, invitee_id: int) -> None:
        await self.execute(
            """INSERT INTO clan_invites (clan_id, inviter_id, invitee_id, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(clan_id, invitee_id) DO UPDATE SET inviter_id = excluded.inviter_id""",
            (clan_id, inviter_id, invitee_id, _now()),
        )

    async def get_clan_invites(self, invitee_id: int) -> list[dict]:
        return await self.fetchall(
            """SELECT ci.*, c.name AS clan_name, c.tag AS clan_tag
               FROM clan_invites ci JOIN clans c ON c.id = ci.clan_id
               WHERE ci.invitee_id = ? ORDER BY ci.created_at DESC""",
            (invitee_id,),
        )

    async def get_clan_invite(self, clan_id: int, invitee_id: int) -> dict | None:
        return await self.fetchone(
            "SELECT * FROM clan_invites WHERE clan_id = ? AND invitee_id = ?",
            (clan_id, invitee_id),
        )

    async def delete_clan_invite(self, clan_id: int, invitee_id: int) -> None:
        await self.execute(
            "DELETE FROM clan_invites WHERE clan_id = ? AND invitee_id = ?",
            (clan_id, invitee_id),
        )

    async def create_clan_war(
        self, attacker_id: int, defender_id: int, attacker_score: int,
        defender_score: int, winner_id: int | None,
    ) -> int:
        return await self.execute(
            """INSERT INTO clan_wars
               (attacker_id, defender_id, attacker_score, defender_score, winner_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (attacker_id, defender_id, attacker_score, defender_score, winner_id, _now()),
        )

    async def get_clan_wars(self, clan_id: int, limit: int = 10) -> list[dict]:
        return await self.fetchall(
            """SELECT * FROM clan_wars WHERE attacker_id = ? OR defender_id = ?
               ORDER BY id DESC LIMIT ?""",
            (clan_id, clan_id, max(1, int(limit))),
        )

    # -- quests ------------------------------------------------------------
    async def get_player_quest(self, player_id: int, quest_id: str) -> dict | None:
        return await self.fetchone(
            "SELECT * FROM player_quests WHERE player_id = ? AND quest_id = ?",
            (player_id, quest_id),
        )

    async def get_player_quests(self, player_id: int) -> list[dict]:
        return await self.fetchall(
            "SELECT * FROM player_quests WHERE player_id = ? ORDER BY active DESC, quest_id",
            (player_id,),
        )

    async def get_active_quests(self, player_id: int) -> list[dict]:
        return await self.fetchall(
            "SELECT * FROM player_quests WHERE player_id = ? AND active = 1",
            (player_id,),
        )

    async def start_quest(self, player_id: int, quest_id: str) -> None:
        await self.execute(
            """INSERT INTO player_quests (player_id, quest_id, stage, progress, active)
               VALUES (?, ?, 0, 0, 1)
               ON CONFLICT(player_id, quest_id) DO UPDATE SET stage = 0, progress = 0, active = 1,
                   completed_at = NULL""",
            (player_id, quest_id),
        )

    async def update_quest_progress(self, player_id: int, quest_id: str, stage: int, progress: int) -> None:
        await self.execute(
            "UPDATE player_quests SET stage = ?, progress = ? WHERE player_id = ? AND quest_id = ?",
            (stage, progress, player_id, quest_id),
        )

    async def complete_player_quest(self, player_id: int, quest_id: str) -> None:
        await self.execute(
            """UPDATE player_quests SET active = 0, progress = 0, completed_at = ?
               WHERE player_id = ? AND quest_id = ?""",
            (_now(), player_id, quest_id),
        )

    async def count_completed_quests(self, player_id: int) -> int:
        return int(await self.scalar(
            "SELECT COUNT(*) FROM player_quests WHERE player_id = ? AND active = 0",
            (player_id,), default=0,
        ) or 0)

    # -- market ------------------------------------------------------------
    async def create_listing(self, seller_id: int, item_id: str, quantity: int, price: int) -> int:
        return await self.execute(
            "INSERT INTO market_listings (seller_id, item_id, quantity, price, created_at) VALUES (?, ?, ?, ?, ?)",
            (seller_id, item_id, quantity, price, _now()),
        )

    async def get_listing(self, listing_id: int) -> dict | None:
        return await self.fetchone("SELECT * FROM market_listings WHERE id = ?", (listing_id,))

    async def get_active_listings(self, limit: int = 10, offset: int = 0) -> list[dict]:
        return await self.fetchall(
            """SELECT ml.*, p.display_name AS seller_name FROM market_listings ml
               JOIN players p ON p.user_id = ml.seller_id
               WHERE ml.active = 1 ORDER BY ml.created_at DESC LIMIT ? OFFSET ?""",
            (max(1, int(limit)), max(0, int(offset))),
        )

    async def get_player_listings(self, seller_id: int) -> list[dict]:
        return await self.fetchall(
            "SELECT * FROM market_listings WHERE seller_id = ? AND active = 1 ORDER BY id DESC",
            (seller_id,),
        )

    async def buy_listing(self, listing_id: int, buyer_id: int) -> dict:
        async with self._lock:
            cur = await self.conn.execute(
                "SELECT * FROM market_listings WHERE id = ? AND active = 1", (listing_id,)
            )
            listing = await cur.fetchone()
            if listing is None:
                return {"ok": False, "reason": "This listing is no longer available."}
            listing = dict(listing)
            if listing["seller_id"] == buyer_id:
                return {"ok": False, "reason": "You cannot buy your own listing."}
            cur = await self.conn.execute(
                "SELECT gold FROM players WHERE user_id = ?", (buyer_id,)
            )
            buyer = await cur.fetchone()
            if buyer is None:
                return {"ok": False, "reason": "Buyer not found."}
            if buyer["gold"] < listing["price"]:
                return {"ok": False, "reason": "You do not have enough gold."}
            await self.conn.execute(
                "UPDATE players SET gold = gold - ?, updated_at = ? WHERE user_id = ?",
                (listing["price"], _now(), buyer_id),
            )
            await self.conn.execute(
                "UPDATE players SET gold = gold + ?, updated_at = ? WHERE user_id = ?",
                (listing["price"], _now(), listing["seller_id"]),
            )
            await self.conn.execute(
                """INSERT INTO inventory (player_id, item_id, quantity) VALUES (?, ?, ?)
                   ON CONFLICT(player_id, item_id)
                   DO UPDATE SET quantity = quantity + excluded.quantity""",
                (buyer_id, listing["item_id"], listing["quantity"]),
            )
            await self.conn.execute(
                "UPDATE market_listings SET active = 0 WHERE id = ?", (listing_id,)
            )
            await self.conn.commit()
            return {"ok": True, "listing": listing}

    async def cancel_listing(self, listing_id: int, seller_id: int) -> dict:
        async with self._lock:
            cur = await self.conn.execute(
                "SELECT * FROM market_listings WHERE id = ? AND active = 1", (listing_id,)
            )
            listing = await cur.fetchone()
            if listing is None or listing["seller_id"] != seller_id:
                return {"ok": False, "reason": "Listing not found."}
            await self.conn.execute(
                "UPDATE market_listings SET active = 0 WHERE id = ?", (listing_id,)
            )
            await self.conn.execute(
                """INSERT INTO inventory (player_id, item_id, quantity) VALUES (?, ?, ?)
                   ON CONFLICT(player_id, item_id)
                   DO UPDATE SET quantity = quantity + excluded.quantity""",
                (seller_id, listing["item_id"], listing["quantity"]),
            )
            await self.conn.commit()
            return {"ok": True, "listing": dict(listing)}

    # -- duels -------------------------------------------------------------
    async def log_duel(self, challenger_id: int, opponent_id: int, winner_id: int | None,
                       rounds: int, log: str = "") -> int:
        return await self.execute(
            """INSERT INTO duel_logs (challenger_id, opponent_id, winner_id, rounds, log, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (challenger_id, opponent_id, winner_id, rounds, log[:4000], _now()),
        )

    async def get_duel_history(self, player_id: int, limit: int = 10) -> list[dict]:
        return await self.fetchall(
            """SELECT * FROM duel_logs WHERE challenger_id = ? OR opponent_id = ?
               ORDER BY id DESC LIMIT ?""",
            (player_id, player_id, max(1, int(limit))),
        )

    # -- backup ------------------------------------------------------------
    async def dump_tables(self) -> dict[str, list[dict]]:
        tables = [
            "players", "inventory", "equipment", "clans", "clan_members",
            "clan_invites", "clan_wars", "player_quests", "quests",
            "market_listings", "duel_logs",
        ]
        data: dict[str, list[dict]] = {}
        for table in tables:
            data[table] = await self.fetchall(f"SELECT * FROM {table}")
        return data
