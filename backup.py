"""Administrator backups: human-readable JSON and binary SQLite snapshots."""

from __future__ import annotations

import json
import time
from pathlib import Path

import aiosqlite

from database import Database
from game_data import VERSION, utcnow


def _stamp() -> str:
    return utcnow().strftime("%Y%m%d_%H%M%S_%f")


async def export_json(db: Database, directory: str | Path = "backups") -> Path:
    """Dump every gameplay table to a timestamped JSON file."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"aetherfall_backup_{_stamp()}.json"
    payload = {
        "meta": {
            "game": "Aetherfall RPG",
            "version": VERSION,
            "created_at": utcnow().isoformat(),
            "source": db.path,
        },
        "tables": await db.dump_tables(),
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    return path


async def export_sqlite(db: Database, directory: str | Path = "backups") -> Path | None:
    """Create a consistent binary copy of the SQLite database."""
    if db.path == ":memory:":
        return None
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"aetherfall_{_stamp()}.db"
    async with db._lock:
        async with aiosqlite.connect(str(path)) as destination:
            await db.conn.backup(destination)
            await destination.commit()
    return path


async def perform_backup(
    db: Database, directory: str | Path = "backups", include_sqlite: bool = True,
) -> dict:
    started = time.monotonic()
    json_path = await export_json(db, directory)
    sqlite_path = await export_sqlite(db, directory) if include_sqlite else None
    player_count = await db.count_players()
    size = json_path.stat().st_size + (sqlite_path.stat().st_size if sqlite_path else 0)
    return {
        "json": str(json_path),
        "sqlite": str(sqlite_path) if sqlite_path else None,
        "players": player_count,
        "bytes": size,
        "seconds": round(time.monotonic() - started, 3),
    }


def prune_backups(directory: str | Path = "backups", keep: int = 20) -> int:
    """Delete all but the newest *keep* backups. Returns number removed."""
    directory = Path(directory)
    if not directory.exists():
        return 0
    files = sorted(
        (p for p in directory.iterdir() if p.is_file() and p.suffix in (".json", ".db")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for path in files[keep:]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
