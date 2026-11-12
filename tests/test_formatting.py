from __future__ import annotations

import random
from types import SimpleNamespace

import game
import handlers
from combat import PvPBattle, WorldBossRaid, fighter_from_player


def test_bar_and_html_helpers():
    assert handlers.bar(0, 100).count("█") == 0
    assert handlers.bar(100, 100).count("█") == 10
    assert handlers.bar(50, 100).count("█") == 5
    assert handlers.bar(10, 0) == "██████████"

    assert handlers.fmt_msg("**Hi** <x>") == "<b>Hi</b> &lt;x&gt;"
    rendered = handlers.events_html(["You use **Power Strike**!", "<script>"])
    assert "<b>Power Strike</b>" in rendered
    assert "&lt;script&gt;" in rendered


def test_equipment_text_accepts_ids_and_dicts():
    assert "Nothing equipped" in handlers._equipment_text({})
    by_id = handlers._equipment_text({"equipment": {"weapon": {"wooden_sword": True}}})
    assert "Nothing equipped" in by_id  # malformed input is ignored gracefully
    assert "Wooden Sword" in handlers._equipment_text({"equipment": {"weapon": "wooden_sword"}})
    assert "Wooden Sword" in handlers._equipment_text({"equipment": {"weapon": handlers.ITEMS["wooden_sword"]}})


def test_item_resolution():
    assert handlers._resolve_item("wooden_sword") == "wooden_sword"
    assert handlers._resolve_item("Wooden Sword") == "wooden_sword"
    assert handlers._resolve_item("iron") == "iron_knuckles"
    assert handlers._resolve_item("") is None
    assert handlers._resolve_item("does-not-exist") is None


async def test_profile_rendering_escapes_player_names(db, player):
    player["display_name"] = "<Evil>"
    text = handlers._profile_text(player)
    assert "&lt;Evil&gt;" in text
    assert "<Evil>" not in text
    assert "Wooden Sword" in text
    assert "Cloth Robe" in text
    assert "Level 1" in text


async def test_pvp_and_raid_rendering(db, player, strong_player):
    battle = PvPBattle(
        fighter_from_player(player), fighter_from_player(strong_player), rng=random.Random(1)
    )
    view = handlers._pvp_view(battle, player["user_id"])
    assert "Duel" in view and "Opponent" in view
    assert "Champion" in view

    raid = WorldBossRaid("goblin_king", rng=random.Random(2))
    ok, _ = raid.join(strong_player)
    assert ok
    text = handlers._raid_text(raid, strong_player["user_id"])
    assert "World Boss" in text and "Goblin King" in text
    assert "Top contributors" in text


async def test_clan_text_states(db, strong_player):
    ctx = SimpleNamespace(bot_data={"db": db})
    text, clan = await handlers._clan_text(ctx, strong_player)
    assert clan is None and "not in a clan" in text

    await db.update_player(strong_player["user_id"], level=10, gold=5000)
    strong_player = await game.load_player(db, strong_player["user_id"])
    import clans
    ok, _, _ = await clans.create_clan(db, strong_player, "Test Guild", "TG")
    assert ok
    text, clan = await handlers._clan_text(ctx, strong_player)
    assert clan is not None
    assert "Test Guild" in text and "Members" in text
