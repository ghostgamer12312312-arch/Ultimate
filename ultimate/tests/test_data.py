from __future__ import annotations

import data


def test_five_series_and_large_roster():
    assert len(data.SERIES) == 5
    assert set(data.SERIES) == set(data.SERIES_ORDER)
    assert len(data.CHARACTERS) >= 300
    for series in data.SERIES_ORDER:
        assert len(data.CHARACTERS_BY_SERIES[series]) >= 60


def test_character_integrity():
    for char_id, character in data.CHARACTERS.items():
        assert character["id"] == char_id
        assert character["series"] in data.SERIES
        assert character["element"] in data.ELEMENTS
        assert character["rarity"] in data.RARITIES
        assert character["hp"] > 0 and character["atk"] > 0 and character["def"] >= 0 and character["spd"] > 0
        for skill_id in character["skills"]:
            assert skill_id in data.SKILLS
        assert character["base_id"] in data.CHARACTERS


def test_gear_skills_items_integrity():
    for gear in data.GEAR.values():
        assert gear["slot"] in ("weapon", "armor", "accessory")
        assert gear["rarity"] in data.RARITIES
        assert gear["element"] in data.ELEMENTS
    for skill in data.SKILLS.values():
        assert skill["element"] in data.ELEMENTS
        assert skill["type"] in ("active", "passive")
    for recipe in data.CRAFTING_RECIPES:
        assert recipe["result"] in data.GEAR
        for item_id in recipe["cost"]:
            assert item_id == "yens" or item_id in data.ITEMS
    for banner in data.GACHA_BANNERS.values():
        assert banner["series"] in (*data.SERIES_ORDER, "all")
        for char_id in banner["featured"]:
            assert char_id in data.CHARACTERS


def test_starters_and_bosses():
    for series in data.SERIES_ORDER:
        assert data.STARTER_CHARACTERS[series] in data.CHARACTERS
        assert len(data.NPCS[series]) >= 8
        assert len(data.BOSSES[series]) >= 4
    assert len(data.WORLD_BOSSES) == 5
    assert len(data.CLAN_RAIDS) == 5


def test_quests_achievements_titles():
    assert len(data.QUESTS) >= 12
    assert len(data.ACHIEVEMENTS) >= 40
    for quest in data.QUESTS:
        assert quest["type"] in ("daily", "weekly", "monthly")
        assert quest["target"] > 0
        for key in quest["rewards"]:
            assert key in ("yens", "gems", "crystals", "tickets", "exp", "clan_exp") or key in data.ITEMS
    for title in data.TITLES.values():
        assert "bonus" in title


def test_pets_dungeons_and_materials():
    assert len(data.PETS) >= 10
    assert data.STARTER_PET in data.PETS
    for pet in data.PETS.values():
        assert pet["series"] in data.SERIES
        assert pet["rarity"] in data.RARITIES
        assert pet["element"] in data.ELEMENTS
    for series in data.SERIES_ORDER:
        assert len(data.DUNGEONS[series]) == len(data.BOSSES[series])
    for item_id in ("fish_common", "fish_rare", "ore_iron", "ore_gold", "treasure_map", "pet_egg", "pet_egg_premium"):
        assert item_id in data.ITEMS
