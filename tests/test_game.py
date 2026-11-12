from __future__ import annotations

from datetime import timedelta

import pytest

import game
from catalog import CLASSES, QUESTS, RACES
from game_data import (
    MAX_LEVEL,
    apply_xp,
    daily_reward,
    derive_stats,
    today_utc,
    xp_for_level,
    xp_progress,
)


def test_apply_xp_single_and_multi_level():
    result = apply_xp(1, 0, xp_for_level(1))
    assert result["level"] == 2
    assert result["levels_gained"] == 1
    assert result["xp"] == 0

    huge = apply_xp(1, 0, 100_000)
    assert huge["level"] > 5
    assert huge["levels_gained"] >= 5
    assert huge["stat_points"] == huge["levels_gained"] * 3

    capped = apply_xp(MAX_LEVEL, 0, 10_000_000)
    assert capped["level"] == MAX_LEVEL
    assert capped["xp"] == 0


def test_xp_progress_and_curve():
    current, needed, pct = xp_progress(3, 50)
    assert current == 50
    assert needed == xp_for_level(3)
    assert 0 <= pct <= 1
    assert xp_progress(1, 99999)[2] == 1.0


def test_derive_stats_and_equipment():
    player = {
        "level": 1, "race": "human", "class": "warrior",
        "strength": 7, "agility": 3, "intellect": 1, "vitality": 7, "luck": 2,
    }
    base = derive_stats(player)
    assert base["max_hp"] > 0
    assert base["max_mana"] > 0
    assert base["attack"] > 0

    equipped = {"weapon": {"attack": 100, "element": "fire", "stats": {"strength": 5}}}
    boosted = derive_stats(player, equipped)
    assert boosted["attack"] > base["attack"]
    assert boosted["element"] == "fire"


async def test_level_up_through_service(db, player):
    uid = player["user_id"]
    before_hp = player["hp"]
    await db.update_player(uid, hp=1)
    player = await game.load_player(db, uid)
    assert player["hp"] == 1
    result = await game.grant_xp(db, player, sum(xp_for_level(i) for i in range(1, 5)))
    assert result["levels_gained"] >= 3
    refreshed = await game.load_player(db, uid)
    assert refreshed["level"] == result["level"]
    assert refreshed["stat_points"] >= 5 + 3 * 3
    assert refreshed["hp"] == refreshed["derived"]["max_hp"]
    assert refreshed["hp"] >= before_hp


async def test_allocate_stats(db, player):
    uid = player["user_id"]
    ok, _ = await game.allocate_stat(db, player, "strength", 2)
    assert ok
    player = await game.load_player(db, uid)
    assert player["strength"] == 11
    assert player["stat_points"] == 3
    ok, message = await game.allocate_stat(db, player, "strength", 99)
    assert not ok and "only" in message.lower()
    ok, message = await game.allocate_stat(db, player, "charisma", 1)
    assert not ok


async def test_shop_buy_and_sell(db, player):
    uid = player["user_id"]
    gold = int(player["gold"])
    ok, message = await game.buy_item(db, player, "small_potion", 2)
    assert ok and "bought" in message.lower()
    assert int(player["gold"]) == gold - 60
    assert await db.get_item_quantity(uid, "small_potion") == 3
    ok, _ = await game.sell_item(db, player, "small_potion", 2)
    assert ok
    assert await db.get_item_quantity(uid, "small_potion") == 1
    assert int((await db.get_player(uid))["gold"]) > gold - 60
    ok, _ = await game.buy_item(db, player, "iron_ore")
    assert not ok
    ok, _ = await game.sell_item(db, player, "small_potion", 99)
    assert not ok


async def test_crafting(db, player):
    uid = player["user_id"]
    await db.add_item(uid, "herb", 4)
    before = await db.get_item_quantity(uid, "small_potion")
    ok, message = await game.craft_item(db, player, "small_potion")
    assert ok and "crafted" in message.lower()
    assert await db.get_item_quantity(uid, "small_potion") == before + 1
    assert await db.get_item_quantity(uid, "herb") == 2
    ok, message = await game.craft_item(db, player, "small_potion")
    assert ok
    ok, reason = await game.craft_item(db, player, "small_potion")
    assert not ok and "missing" in reason.lower()
    ok, reason = await game.can_craft(db, player, "dragon_greatsword")
    assert not ok


async def test_consumables_and_respec(db, player):
    uid = player["user_id"]
    await db.update_player(uid, hp=10)
    player = await game.load_player(db, uid)
    ok, message = await game.use_consumable(db, player, "small_potion")
    assert ok and "hp" in message.lower()
    player = await game.load_player(db, uid)
    assert player["hp"] > 10
    ok, _ = await game.use_consumable(db, player, "small_potion")
    assert not ok

    await game.allocate_stat(db, player, "strength", 2)
    await db.add_item(uid, "respec_stone", 1)
    player = await game.load_player(db, uid)
    ok, message = await game.use_consumable(db, player, "respec_stone")
    assert ok and "refund" in message.lower()
    player = await game.load_player(db, uid)
    base = (
        CLASSES["warrior"]["base"]["strength"]
        + RACES["human"]["bonuses"]["strength"]
    )
    assert player["strength"] == base
    assert player["stat_points"] == 5


async def test_equip_unequip_flow(db, player):
    uid = player["user_id"]
    await db.add_item(uid, "iron_sword", 1)
    ok, message = await game.equip_item(db, uid, "iron_sword")
    assert ok
    assert (await db.get_equipment(uid))["weapon"] == "iron_sword"
    assert await db.get_item_quantity(uid, "wooden_sword") == 1
    ok, _ = await game.unequip_item(db, uid, "weapon")
    assert ok
    assert "weapon" not in await db.get_equipment(uid)
    ok, _ = await game.equip_item(db, uid, "large_potion")
    assert not ok


def test_daily_reward_calculation():
    today = today_utc()
    fresh = {"level": 5, "daily_streak": 0, "last_daily": None}
    reward = daily_reward(fresh, today)
    assert reward["claimable"] and reward["streak"] == 1

    claimed = {"level": 5, "daily_streak": 1, "last_daily": today.isoformat()}
    assert not daily_reward(claimed, today)["claimable"]

    yesterday = {"level": 5, "daily_streak": 4, "last_daily": (today - timedelta(days=1)).isoformat()}
    streak = daily_reward(yesterday, today)
    assert streak["claimable"] and streak["streak"] == 5

    broken = {"level": 5, "daily_streak": 9, "last_daily": (today - timedelta(days=3)).isoformat()}
    assert daily_reward(broken, today)["streak"] == 1

    seventh = {"level": 5, "daily_streak": 6, "last_daily": (today - timedelta(days=1)).isoformat()}
    weekly = daily_reward(seventh, today)
    assert weekly["streak"] == 7 and weekly["gems"] > 0


async def test_daily_claim_once(db, player):
    uid = player["user_id"]
    first = await game.claim_daily(db, player)
    assert first["ok"]
    gold = int((await db.get_player(uid))["gold"])
    second = await game.claim_daily(db, player)
    assert not second["ok"]
    assert int((await db.get_player(uid))["gold"]) == gold


async def test_quest_progress_and_rewards(db, player):
    uid = player["user_id"]
    ok, _ = await game.start_quest(db, player, "slime_cleanup")
    assert ok
    ok, _ = await game.start_quest(db, player, "slime_cleanup")
    assert not ok

    gold_before = int(player["gold"])
    notices = await game.progress_quests(db, player, "kill", "forest_slime", 3)
    assert notices and "stage complete" in notices[0].lower()
    assert int(player["gold"]) > gold_before
    row = await db.get_player_quest(uid, "slime_cleanup")
    assert row["stage"] == 1

    notices = await game.progress_quests(db, player, "kill", "wild_wolf", 2)
    assert any("completed" in n.lower() for n in notices)
    row = await db.get_player_quest(uid, "slime_cleanup")
    assert row["active"] == 0

    ok, _ = await game.start_quest(db, player, "dragon_slayer")
    assert not ok


async def test_marketplace_helpers(db, player, strong_player):
    seller = strong_player
    buyer = player
    await db.add_item(seller["user_id"], "iron_sword", 2)
    ok, _ = await game.list_market_item(db, seller, "iron_sword", 1, 150)
    assert ok
    listings = await db.get_active_listings()
    assert listings
    ok, _ = await game.list_market_item(db, seller, "iron_sword", 5, 150)
    assert not ok
    ok, message = await game.buy_market_listing(db, buyer, listings[0]["id"])
    assert ok
    assert await db.get_item_quantity(buyer["user_id"], "iron_sword") == 1


async def test_rewards_and_power(db, player):
    uid = player["user_id"]
    xp_before = int(player["xp"])
    gold_before = int(player["gold"])
    await game.grant_rewards(db, player, gold=50, gems=2, xp=10, items={"herb": 2})
    assert int(player["gold"]) == gold_before + 50
    assert int(player["gems"]) == 5
    assert await db.get_item_quantity(uid, "herb") == 2
    assert int(player["xp"]) == xp_before + 10
    assert game.power_rating(player) > 0
