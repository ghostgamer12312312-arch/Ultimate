from __future__ import annotations

import game


def test_effective_stats_and_power(database, player):
    stats = game.effective_stats(database, 1001)
    assert stats["hp"] > 0
    assert stats["atk"] > 0
    assert stats["spd"] > 0
    assert stats["element"] in ("fire", "water", "earth", "wind", "lightning", "ice", "light", "dark", "spirit", "void")
    assert game.power_score(stats) > 0


def test_simulation_is_deterministic():
    a = {"name": "A", "hp": 1000, "atk": 100, "def": 20, "spd": 20, "crit": 0.1, "dodge": 0.0, "element": "fire", "skills": ["flame_burst"]}
    b = {"name": "B", "hp": 900, "atk": 90, "def": 15, "spd": 15, "crit": 0.1, "dodge": 0.0, "element": "wind", "skills": []}
    first = game.simulate(a, b, seed=42)
    second = game.simulate(a, b, seed=42)
    assert first["winner"] == second["winner"]
    assert first["player_damage"] == second["player_damage"]
    assert first["log"]


def test_hunt_consumes_stamina_and_rewards(database, player):
    stamina = database.player(1001)["stamina"]
    result = game.hunt(database, 1001, "dragonball")
    assert result["ok"]
    assert result["npc"]["series"] == "dragonball"
    assert database.player(1001)["stamina"] <= stamina
    assert result["result"]["winner"] in ("player", "enemy", "draw")


def test_boss_requires_key(database, player):
    database.take_item(1001, "boss_key", database.item_qty(1001, "boss_key"))
    fail = game.fight_boss(database, 1001, "dragonball")
    assert fail["ok"] is False
    database.add_item(1001, "boss_key", 1)
    succeed = game.fight_boss(database, 1001, "dragonball")
    assert succeed["ok"]


def test_world_and_clan_raids(database, player):
    world = game.attack_world(database, 1001)
    assert world["ok"]
    assert world["damage"] > 0
    database.give(1001, yens=10000, crystals=200)
    assert database.create_clan(1001, "Raid Clan", "RAID")["ok"]
    assert database.start_clan_raid(1001, "cr_dragonball")["ok"]
    raid = game.attack_clan_raid(database, 1001)
    assert raid["ok"]
    assert raid["damage"] > 0


def test_gacha_and_wish(database, player):
    database.give(1001, tickets=20)
    result = game.gacha(database, 1001, "dragonball", 10)
    assert result["ok"]
    assert len(result["results"]) == 10
    for index in range(1, 8):
        database.add_item(1001, f"dragon_ball_{index}", 1)
    wish = game.wish(database, 1001)
    assert wish["ok"]
    assert wish["character"]["rarity"] == "divine"


def test_economy(database, player):
    buy = game.buy_shop(database, 1001, "senzu_small", 1)
    assert buy["ok"]
    sell = game.sell_item(database, 1001, "senzu_small", 1)
    assert sell["ok"]
    recipes = game.craft(database, 1001, "craft_multiverse_relic")
    assert recipes["ok"] is False
    database.give(1001, yens=5000)
    database.add_item(1001, "crystal_shard", 5)
    database.add_item(1001, "forge_core", 2)
    crafted = game.craft(database, 1001, "craft_rare_weapon")
    assert crafted["ok"]


def test_duel_and_arena(database, player):
    database.ensure_player(1002, "rival", "Rival")
    result = game.duel(database, 1001, 1002)
    assert result["ok"]
    assert database.player(1002)["arena_rating"] >= 0
    arena = game.arena(database, 1001)
    assert arena["ok"]


def test_titles_and_collection(database, player):
    collection = game.series_collection(database, 1001)
    assert sum(collection.values()) >= 1
    assert database.equip_title(1001, "title_rookie")


def test_companions(database, player):
    pets = database.pets(1001)
    assert pets and any(pet["equipped"] for pet in pets)
    before = game.effective_stats(database, 1001)["atk"]
    new, pet = database.add_pet(1001, "pet_kurama")
    assert new
    assert database.equip_pet(1001, "pet_kurama")
    after = game.effective_stats(database, 1001)["atk"]
    assert after >= before
    database.give(1001, yens=10000)
    fed = database.feed_pet(1001, "pet_kurama", 2)
    assert fed["ok"] and fed["level"] == 3


def test_pet_egg_and_side_activities(database, player):
    database.give(1001, stamina=200)
    database.add_item(1001, "pet_egg", 1)
    hatched = game.use_item(database, 1001, "pet_egg", 1)
    assert hatched["ok"] and "pet" in hatched
    stamina = database.player(1001)["stamina"]
    fished = game.fish(database, 1001)
    assert fished["ok"]
    assert database.player(1001)["stamina"] < stamina
    mined = game.mine(database, 1001)
    assert mined["ok"]
    assert mined["drops"]


def test_dungeon_flow(database, player):
    database.give(1001, stamina=200)
    result = game.dungeon(database, 1001, "dragonball")
    assert result["ok"]
    assert result["floor"]["series"] == "dragonball"
    assert result["result"]["winner"] in ("player", "enemy", "draw")


def test_persistent_boss_chapters_and_skills(database, player):
    import data as game_data

    boss = game_data.BOSSES["dragonball"][0]
    state = database.boss_state(1001, boss)
    assert state["hp"] == boss["hp"]
    damaged = database.damage_boss(1001, boss, 10)
    assert damaged["hp"] == boss["hp"] - 10
    again = database.boss_state(1001, boss)
    assert again["hp"] == boss["hp"] - 10
    database.reset_boss(1001, boss["id"])
    database.give(1001, stamina=200)
    chapter = game.chapter_fight(database, 1001, "dragonball")
    assert chapter["ok"]
    assert chapter["cleared"]
    status = game.chapter_status(database, 1001, "dragonball")
    assert status["next"]["number"] == 2
    database.give(1001, gems=1000, crystals=1000, yens=100000)
    skill = game.skill_shop("dragonball")[0]
    assert game.buy_skill(database, 1001, skill["skill"]["id"])["ok"]
    assert game.buy_skill(database, 1001, skill["skill"]["id"])["ok"] is False


def test_summon_boss_and_cards(database, player):
    import images

    database.give(1001, tickets=5, stamina=200)
    result = game.summon_boss(database, 1001, "dragonball")
    assert result["ok"]
    assert result["damage"] > 0
    assert database.summon_state(1001, {**result["boss"], "hp": max(1, int(result["boss"]["hp"] * 0.18))})["max_hp"] > 0
    path = images.character_card(database.characters(1001)[0])
    assert path.endswith(".png")
    assert (images.Path(path)).exists()
