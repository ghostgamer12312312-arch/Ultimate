from __future__ import annotations

import pytest_asyncio

import game
from database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_rpg.db"))
    await database.connect()
    await database.init()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def player(db):
    character, error = await game.create_character(
        db, user_id=1001, username="hero_one", display_name="Hero One",
        race_id="human", class_id="warrior",
    )
    assert error == ""
    assert character is not None
    return character


@pytest_asyncio.fixture
async def strong_player(db):
    character, error = await game.create_character(
        db, user_id=2001, username="champion", display_name="Champion",
        race_id="orc", class_id="berserker",
    )
    assert error == ""
    await db.update_player(2001, level=20, gold=50_000, hp=5000, mana=500)
    return await game.load_player(db, 2001)
