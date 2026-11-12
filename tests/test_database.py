from __future__ import annotations

import pytest

import game
from database import Database


@pytest.mark.asyncio
async def test_player_crud_and_username_lookup(db):
    assert await db.count_players() == 0
    p, err = await game.create_character(db, 42, "MixedCase", "Aria", "elf", "mage")
    assert err == ""
    assert await db.count_players() == 1
    assert (await db.get_player(42))["display_name"] == "Aria"
    found = await db.get_player_by_username("@mixedcase")
    assert found["user_id"] == 42
    assert await db.get_player_by_username("nobody") is None

    duplicate, err = await game.create_character(db, 42, "MixedCase", "Aria", "elf", "mage")
    assert duplicate is None and "already" in err.lower()

    await db.update_player(42, gold=999, hp=50, ignored_column="DROP TABLE players")
    updated = await db.get_player(42)
    assert updated["gold"] == 999
    assert updated["hp"] == 50
    assert "ignored_column" not in updated

    await db.add_gold(42, -1000)
    assert (await db.get_player(42))["gold"] == 0
    await db.increment_pvp(42, True)
    await db.increment_boss_kills(42, 2)
    row = await db.get_player(42)
    assert row["wins"] == 1 and row["boss_kills"] == 2


@pytest.mark.asyncio
async def test_inventory_and_equipment(db, player):
    uid = player["user_id"]
    await db.add_item(uid, "iron_ore", 5)
    await db.add_item(uid, "iron_ore", 3)
    assert await db.get_item_quantity(uid, "iron_ore") == 8
    assert await db.remove_item(uid, "iron_ore", 3)
    assert await db.get_item_quantity(uid, "iron_ore") == 5
    assert not await db.remove_item(uid, "iron_ore", 99)
    assert await db.get_item_quantity(uid, "iron_ore") == 5
    assert await db.remove_item(uid, "iron_ore", 5)
    assert await db.get_item_quantity(uid, "iron_ore") == 0

    inventory = await db.get_inventory(uid)
    assert any(row["item_id"] == "small_potion" for row in inventory)

    previous = await db.set_equipment(uid, "weapon", "iron_sword")
    assert previous == "wooden_sword"
    assert (await db.get_equipment(uid))["weapon"] == "iron_sword"
    assert await db.clear_equipment_slot(uid, "weapon") == "iron_sword"
    assert "weapon" not in await db.get_equipment(uid)


@pytest.mark.asyncio
async def test_clan_tables(db, strong_player):
    p = strong_player
    clan_id = await db.create_clan("Iron Wolves", "IW", p["user_id"], "Wolves of iron")
    assert clan_id > 0
    assert (await db.get_clan_by_name("iron wolves"))["id"] == clan_id
    assert (await db.get_clan_by_tag("iw"))["id"] == clan_id
    assert (await db.get_player_clan(p["user_id"]))["member_role"] == "leader"

    p2, _ = await game.create_character(db, 2002, "second", "Second", "dwarf", "paladin")
    await db.add_clan_member(clan_id, 2002, "officer")
    assert await db.get_clan_member_count(clan_id) == 2
    assert len(await db.get_clan_members(clan_id)) == 2
    assert (await db.get_player_clan(2002))["name"] == "Iron Wolves"

    await db.add_clan_contribution(clan_id, p["user_id"], 500)
    clan = await db.get_clan(clan_id)
    assert clan["bank_gold"] == 500
    assert (await db.get_player_clan(p["user_id"]))["member_contribution"] == 500

    await db.add_clan_invite(clan_id, p["user_id"], 3003)
    invites = await db.get_clan_invites(3003)
    assert len(invites) == 1 and invites[0]["clan_name"] == "Iron Wolves"
    await db.delete_clan_invite(clan_id, 3003)
    assert await db.get_clan_invites(3003) == []

    await game.create_character(db, 2004, "storm", "Storm", "elf", "ranger")
    clan2 = await db.create_clan("Storm Riders", "SR", 2004)
    await db.create_clan_war(clan_id, clan2, 1000, 800, clan_id)
    wars = await db.get_clan_wars(clan_id)
    assert wars and wars[0]["winner_id"] == clan_id
    rankings = await db.get_clan_leaderboard()
    assert len(rankings) == 2

    await db.remove_clan_member(clan_id, 2002)
    assert await db.get_player_clan(2002) is None
    await db.delete_clan(clan_id)
    assert await db.get_clan(clan_id) is None
    assert await db.get_player_clan(p["user_id"]) is None


@pytest.mark.asyncio
async def test_quest_progress_tables(db, player):
    uid = player["user_id"]
    await db.start_quest(uid, "slime_cleanup")
    active = await db.get_active_quests(uid)
    assert active[0]["quest_id"] == "slime_cleanup"
    await db.update_quest_progress(uid, "slime_cleanup", 1, 2)
    row = await db.get_player_quest(uid, "slime_cleanup")
    assert row["stage"] == 1 and row["progress"] == 2
    await db.complete_player_quest(uid, "slime_cleanup")
    assert await db.get_active_quests(uid) == []
    assert await db.count_completed_quests(uid) == 1


@pytest.mark.asyncio
async def test_market_buy_cancel(db, player, strong_player):
    seller = strong_player
    buyer = player
    await db.add_item(seller["user_id"], "large_potion", 2)
    listing_id = await db.create_listing(seller["user_id"], "large_potion", 2, 100)
    listings = await db.get_active_listings()
    assert len(listings) == 1 and listings[0]["seller_name"] == "Champion"

    buyer_gold = int(buyer["gold"])
    result = await db.buy_listing(listing_id, buyer["user_id"])
    assert result["ok"]
    assert await db.get_item_quantity(buyer["user_id"], "large_potion") == 2
    assert int((await db.get_player(buyer["user_id"]))["gold"]) == buyer_gold - 100
    assert int((await db.get_player(seller["user_id"]))["gold"]) == int(seller["gold"]) + 100
    assert (await db.get_listing(listing_id))["active"] == 0
    assert not (await db.buy_listing(listing_id, buyer["user_id"]))["ok"]

    await db.add_item(seller["user_id"], "iron_ore", 1)
    await db.remove_item(seller["user_id"], "iron_ore", 1)
    listing2 = await db.create_listing(seller["user_id"], "iron_ore", 1, 50)
    cancel = await db.cancel_listing(listing2, seller["user_id"])
    assert cancel["ok"]
    assert await db.get_item_quantity(seller["user_id"], "iron_ore") == 1


@pytest.mark.asyncio
async def test_duel_logs_and_dump(db, player):
    uid = player["user_id"]
    await db.log_duel(uid, 999, uid, 5, "a duel happened")
    history = await db.get_duel_history(uid)
    assert history and history[0]["rounds"] == 5
    dump = await db.dump_tables()
    assert "players" in dump and "duel_logs" in dump
    assert len(dump["players"]) == 1


@pytest.mark.asyncio
async def test_memory_database_and_double_connect():
    db = Database(":memory:")
    await db.connect()
    await db.connect()
    await db.init()
    await db.init()
    p = await db.create_player(7, "mem", "Mem", "human", "warrior",
                               {"strength": 5, "agility": 5, "intellect": 5,
                                "vitality": 5, "luck": 5}, 100, 50)
    assert p["user_id"] == 7
    await db.close()
