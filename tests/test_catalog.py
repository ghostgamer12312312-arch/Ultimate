from __future__ import annotations

from catalog import (
    BOSSES,
    CLASSES,
    CRAFTING_RECIPES,
    ELEMENTS,
    ITEMS,
    MONSTERS,
    QUESTS,
    RACES,
    SKILLS,
    STAT_KEYS,
)
from game_data import (
    clan_member_limit,
    clan_upgrade_cost,
    element_multiplier,
    player_combat_skills,
    skill_unlocked,
    validate_clan_name,
    validate_clan_tag,
    xp_for_level,
)


def test_races_have_complete_bonuses():
    for race_id, race in RACES.items():
        assert race["name"]
        assert race["element"] in ELEMENTS
        assert set(race["bonuses"]) == set(STAT_KEYS), race_id
        assert race["passive"]


def test_classes_reference_valid_skills_and_items():
    for class_id, cls in CLASSES.items():
        assert cls["name"]
        assert cls["element"] in ELEMENTS
        assert set(cls["base"]) == set(STAT_KEYS), class_id
        for skill_id in cls["skills"]:
            assert skill_id in SKILLS, (class_id, skill_id)
        for item_id in cls["starting_items"]:
            assert item_id in ITEMS, (class_id, item_id)


def test_skills_have_required_fields():
    for skill_id, skill in SKILLS.items():
        assert skill["name"]
        assert skill["type"] in {"damage", "heal", "buff", "debuff"}, skill_id
        assert skill["element"] in ELEMENTS, skill_id
        assert int(skill["mana"]) >= 0
        assert int(skill["cooldown"]) >= 1
        assert skill["description"]


def test_all_item_references_exist():
    for item_id, item in ITEMS.items():
        assert item["name"], item_id
        assert item["type"] in {"weapon", "armor", "helmet", "boots", "ring", "amulet", "consumable", "material"}
        assert item.get("rarity") in {"common", "uncommon", "rare", "epic", "legendary"}
        if item["type"] in {"weapon", "armor", "helmet", "boots", "ring", "amulet"}:
            assert item["slot"] == item["type"]
    for monster in MONSTERS.values():
        for drop in monster["loot"]:
            assert drop in ITEMS, drop
    for boss in BOSSES.values():
        for drop in boss["loot"]:
            assert drop in ITEMS, drop


def test_crafting_recipes_are_valid():
    for result_id, recipe in CRAFTING_RECIPES.items():
        assert result_id in ITEMS, result_id
        assert recipe["gold"] >= 0
        assert recipe["level"] >= 1
        for material, qty in recipe["materials"].items():
            assert material in ITEMS, material
            assert qty > 0


def test_quests_are_valid():
    valid_objectives = {"kill", "boss", "duel", "hunt"}
    for quest_id, quest in QUESTS.items():
        assert quest["name"], quest_id
        assert quest["stages"], quest_id
        for stage in quest["stages"]:
            assert stage["objective"] in valid_objectives, quest_id
            assert int(stage["count"]) > 0
            if stage["objective"] == "kill":
                assert stage["target"] in MONSTERS, (quest_id, stage["target"])
            if stage["objective"] == "boss":
                assert stage["target"] in BOSSES, (quest_id, stage["target"])
            reward = stage.get("reward", {})
            for item_id in (reward.get("items") or {}):
                assert item_id in ITEMS, item_id


def test_element_affinity_rules():
    assert element_multiplier("fire", "ice") > 1
    assert element_multiplier("ice", "fire") < 1
    assert element_multiplier("physical", "physical") == 1
    assert element_multiplier("shadow", "holy") > 1
    assert element_multiplier("holy", "shadow") > 1


def test_xp_curve_and_skill_unlocks():
    assert xp_for_level(1) > 0
    assert xp_for_level(10) > xp_for_level(5)
    assert skill_unlocked("power_strike", 1)
    assert player_combat_skills({"class": "warrior", "level": 1})
    assert player_combat_skills({"class": "berserker", "level": 30})


def test_clan_validation_and_costs():
    assert validate_clan_name("Dragon Order")[0]
    assert not validate_clan_name("x")[0]
    assert validate_clan_name("bad<script>")[0] is False
    assert validate_clan_tag("DGN")[0]
    assert not validate_clan_tag("A")[0]
    assert clan_upgrade_cost(2) > clan_upgrade_cost(1)
    assert clan_member_limit(2) > clan_member_limit(1)
