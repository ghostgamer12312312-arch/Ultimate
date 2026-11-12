from __future__ import annotations

import data


def test_ensure_player_starter(database, player):
    assert player["user_id"] == 1001
    assert player["level"] == 1
    assert player["yens"] >= 3000
    assert database.characters(1001)
    assert database.team(1001)
    assert database.items(1001)
    assert database.gear(1001)
    assert player["equipped_char"] in data.CHARACTERS


def test_gacha_duplicate_shards_and_pity(database, player):
    database.give(1001, tickets=50)
    character = data.STARTER_CHARACTERS["dragonball"]
    database.add_character(1001, character)
    shards_before = database.shards(1001, character)
    result = database.add_character(1001, character)
    assert result[0] is False
    assert database.shards(1001, character) == shards_before + 1
    database.set_field(1001, "pity", 79)
    pull = database.conn()
    with pull as c:
        c.execute("UPDATE players SET pity=79 WHERE user_id=1001")
    from game import gacha
    result = gacha(database, 1001, "multiverse", 1)
    assert result["ok"]
    assert result["pity"] == 0


def test_items_gear_and_skills(database, player):
    database.add_item(1001, "senzu_small", 2)
    assert database.item_qty(1001, "senzu_small") >= 2
    assert database.take_item(1001, "senzu_small", 2)
    gear_id = database.grant_gear(1001, "gear_univ_champion_s_blade")
    equipped = database.equip_gear(1001, gear_id)
    assert equipped["ok"]
    assert int(database.player(1001)["weapon"]) == gear_id
    enhanced = database.enhance_gear(1001, gear_id)
    assert enhanced["ok"]
    database.give(1001, skill_points=2)
    learned = database.learn_skill(1001, "kamehameha")
    assert learned["ok"]
    assert database.equip_skill(1001, "kamehameha")["ok"]


def test_clan_lifecycle(database, player):
    result = database.create_clan(1001, "Z Warriors", "ZW")
    assert result["ok"]
    info = database.clan(1001)
    assert info["name"] == "Z Warriors"
    database.ensure_player(1002, "friend", "Friend")
    assert database.join_clan(1002, "ZW")["ok"]
    assert database.clan_donate(1001, "yens", 500)["ok"]
    assert database.clan_info(info["id"])["members"]
    assert database.start_clan_raid(1001, "cr_dragonball")["ok"]
    assert database.clan_raid_current(info["id"]) is not None
    assert database.record_clan_raid_damage(1001, 5000)["ok"]
    assert database.clan_kick(1001, "1002")["ok"]
    assert database.leave_clan(1001)["ok"]
    assert database.clan(1001) is None


def test_market_lifecycle(database, player):
    database.add_item(1001, "senzu_small", 2)
    listing = database.market_list(1001, "item", "senzu_small", 1, 100)
    assert listing["ok"]
    database.ensure_player(1002, "buyer", "Buyer")
    database.give(1002, yens=1000)
    before = database.item_qty(1002, "senzu_small")
    bought = database.market_buy(1002, listing["listing_id"])
    assert bought["ok"]
    assert database.item_qty(1002, "senzu_small") == before + 1
    gear_id = database.grant_gear(1001, "gear_univ_iron_guard")
    gear_listing = database.market_list(1001, "gear", str(gear_id), 1, 500)
    assert gear_listing["ok"]
    assert database.market_cancel(1001, gear_listing["listing_id"])["ok"]


def test_quests_achievements_and_rewards(database, player):
    database.bump(1001, "total_battles", 10)
    database.bump(1001, "wins", 10)
    claimed = database.claim_quests(1001)
    assert claimed["claimed"]
    achievements = database.claim_achievements(1001)
    assert achievements["claimed"]
    titles = database.unlocked_titles(1001)
    assert "title_fighter" in titles
    assert database.equip_title(1001, "title_fighter")


def test_daily_weekly_monthly(database, player):
    assert database.claim_daily(1001)["ok"]
    assert database.claim_daily(1001)["ok"] is False
    assert database.claim_weekly(1001)["ok"]
    assert database.claim_monthly(1001)["ok"]


def test_find_player_and_reset(database, player):
    database.ensure_player(1002, "friend", "Friend")
    assert database.find_player("@friend")["user_id"] == 1002
    database.reset_player(1002)
    assert database.player(1002) is None


def test_pet_persistence_and_reset(database, player):
    new, pet = database.add_pet(1001, "pet_ranga")
    assert new and pet["name"] == "Ranga"
    assert database.equip_pet(1001, "pet_ranga")
    assert any(item["pet_id"] == "pet_ranga" and item["equipped"] for item in database.pets(1001))
    database.reset_player(1001)
    assert database.player(1001) is None
    fresh = database.ensure_player(1001, "tester", "Tester")
    assert fresh["user_id"] == 1001
    assert database.pets(1001)


def test_transfer_assets_and_trade(database, player):
    database.ensure_player(1002, "trader", "Trader")
    before = database.item_qty(1002, "senzu_small")
    sent = database.transfer_asset(1001, 1002, "item", "senzu_small", 2)
    assert sent["ok"]
    assert database.item_qty(1002, "senzu_small") == before + 2
    database.give(1002, yens=100)
    trade = database.trade_create(1001, 1002)
    assert trade["ok"]
    assert database.trade_add(1001, "yens", 100)["ok"]
    assert database.trade_add(1002, "item", "senzu_small", 1)["ok"]
    assert database.trade_confirm(1001)["ok"]
    completed = database.trade_confirm(1002)
    assert completed["ok"] and completed["completed"]
    assert database.trade_for(1001) is None


def test_admin_grant_and_clan_management(database, player):
    database.ensure_player(1002, "member", "Member")
    char_id = next(iter(data.CHARACTERS))
    assert database.grant_asset(1002, "character", char_id)["ok"]
    assert database.grant_asset(1002, "gear", "gear_univ_iron_guard")["ok"]
    assert database.grant_asset(1002, "everything", None)["ok"]
    database.give(1001, yens=10000, crystals=200)
    assert database.create_clan(1001, "Manage Clan", "MNG")["ok"]
    assert database.clan_invite(1001, "1002")["ok"]
    assert database.clan_accept(1002)["ok"]
    assert database.clan_set_description(1001, "We rule the multiverse.")["ok"]
    assert database.clan_settings(1001, open_join=False, min_level=3)["ok"]
    assert database.clan_transfer(1001, "1002")["ok"]
    assert database.clan(1002)["leader_id"] == 1002
