from __future__ import annotations

import json

import pytest

from backup import export_json, export_sqlite, perform_backup, prune_backups
from database import Database


@pytest.mark.asyncio
async def test_backup_json_and_sqlite(db, player, tmp_path):
    result = await perform_backup(db, tmp_path / "backups")
    assert result["players"] == 1
    assert result["bytes"] > 0
    json_path = result["json"]
    sqlite_path = result["sqlite"]
    assert json_path and sqlite_path

    with open(json_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["meta"]["game"] == "Aetherfall RPG"
    assert payload["tables"]["players"][0]["user_id"] == player["user_id"]
    assert "inventory" in payload["tables"]

    copy = Database(sqlite_path)
    await copy.connect()
    assert (await copy.get_player(player["user_id"]))["display_name"] == "Hero One"
    await copy.close()


@pytest.mark.asyncio
async def test_export_json_only(db, tmp_path):
    path = await export_json(db, tmp_path / "json_only")
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["tables"]["players"] == []


@pytest.mark.asyncio
async def test_memory_sqlite_export_returns_none():
    mem = Database(":memory:")
    await mem.connect()
    await mem.init()
    assert await export_sqlite(mem) is None
    await mem.close()


@pytest.mark.asyncio
async def test_prune_backups(db, tmp_path):
    directory = tmp_path / "prune"
    for _ in range(3):
        await export_json(db, directory)
    assert len(list(directory.glob("*.json"))) == 3
    removed = prune_backups(directory, keep=1)
    assert removed == 2
    assert len(list(directory.glob("*.json"))) == 1
    assert prune_backups(tmp_path / "missing", keep=1) == 0
