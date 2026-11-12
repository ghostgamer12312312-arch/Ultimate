from __future__ import annotations

import random

import pytest

import game
from combat import (
    Fighter,
    PvEBattle,
    PvPBattle,
    WorldBossRaid,
    calculate_damage,
    fighter_from_boss,
    fighter_from_monster,
    fighter_from_player,
)
from game_data import element_multiplier


class AlwaysFleeRng(random.Random):
    def random(self) -> float:  # noqa: D401 - deterministic helper
        return 0.0

    def uniform(self, a: float, b: float) -> float:
        return (a + b) / 2


def make_fighter(uid: int, name: str, hp: int = 300, attack: int = 40,
                 defense: int = 10, speed: int = 10, element: str = "physical",
                 skills: list[str] | None = None) -> Fighter:
    return Fighter(
        uid=uid, name=name, level=5, element=element, max_hp=hp, hp=hp,
        max_mana=100, mana=100, attack=attack, defense=defense, speed=speed,
        crit_chance=0.1, skills=skills or [],
    )


def test_fighter_factories_from_catalog():
    monster = fighter_from_monster("forest_slime")
    assert monster.max_hp > 0 and monster.hp == monster.max_hp
    boss = fighter_from_boss("goblin_king")
    assert boss.max_hp > monster.max_hp
    assert boss.uid is None


def test_damage_and_element_affinity():
    fire = make_fighter(1, "Fire", element="fire")
    ice = make_fighter(2, "Ice", element="ice")
    hit = calculate_damage(fire, ice, 1.0, "fire", random.Random(42))
    assert hit["damage"] > 0
    assert hit["multiplier"] == element_multiplier("fire", "ice") > 1
    assert ice.hp < ice.max_hp

    physical = make_fighter(3, "Physical", element="physical")
    hit2 = calculate_damage(fire, physical, 1.0, "fire", random.Random(42))
    assert hit2["multiplier"] == 1.0


def test_take_damage_immunity_and_resist():
    undead = make_fighter(1, "Undead")
    undead.immune = ("poison",)
    assert undead.take_damage(50, "poison") == 0
    resistant = make_fighter(2, "Resistant")
    resistant.resist = {"fire": 0.5}
    taken = resistant.take_damage(100, "fire")
    assert taken == 50


def test_pve_battle_victory_flow(player):
    battle = PvEBattle("forest_slime", fighter_from_player(player), rng=random.Random(7))
    for _ in range(30):
        if battle.finished:
            break
        battle.player_attack()
    assert battle.finished
    assert battle.result == "win"
    assert battle.rewards["xp"] > 0
    assert battle.rewards["gold"] > 0


def test_pve_skill_mana_and_cooldown(player):
    battle = PvEBattle("goblin_scout", fighter_from_player(player), rng=random.Random(3))
    mana_before = battle.player.mana
    events = battle.player_skill("power_strike")
    assert any("Power Strike" in e for e in events)
    assert battle.player.mana < mana_before
    assert battle.player.cooldowns.get("power_strike", 0) >= 1
    blocked = battle.player_skill("power_strike")
    assert any("cooldown" in e.lower() for e in blocked)
    unknown = battle.player_skill("meteor")
    assert any("not learned" in e.lower() for e in unknown)


def test_pve_heal_and_flee():
    fighter = make_fighter(1, "Healer", hp=500, attack=30, defense=20, speed=1000)
    battle = PvEBattle("forest_slime", fighter, rng=AlwaysFleeRng(1))
    battle.player.hp = 100
    events = battle.player_heal(60)
    assert battle.player.hp > 100
    assert any("recover" in e.lower() for e in events)

    battle2 = PvEBattle("forest_slime", make_fighter(2, "Runner", speed=1000), rng=AlwaysFleeRng(2))
    events = battle2.player_flee()
    assert battle2.finished and battle2.result == "flee"
    assert any("flee" in e.lower() for e in events)


def test_pve_loss_sets_result():
    weak = make_fighter(1, "Weak", hp=1, attack=1, defense=0, speed=1)
    battle = PvEBattle("shadow_stalker", weak, rng=random.Random(5))
    battle.player_attack()
    assert battle.finished and battle.result == "lose"


async def test_world_boss_raid(db, strong_player):
    raid = WorldBossRaid("goblin_king", rng=random.Random(11))
    ok, _ = raid.join(strong_player)
    assert ok
    fighter = raid.participants[strong_player["user_id"]]
    fighter.attack = 100_000
    events = raid.attack(strong_player)
    assert raid.finished and raid.winner
    assert raid.rewards
    reward = next(iter(raid.rewards.values()))
    assert reward["gold"] > 0 and reward["xp"] > 0
    assert raid.boss.hp == 0
    assert events


async def test_world_boss_join_level_gate(db, player):
    raid = WorldBossRaid("void_titan", rng=random.Random(1))
    ok, message = raid.join(player)
    assert not ok and "level" in message.lower()


def test_pvp_round_resolution_and_flee():
    a = make_fighter(1, "Alice", hp=1000, attack=40, defense=10, speed=20)
    b = make_fighter(2, "Bob", hp=1000, attack=40, defense=10, speed=10)
    battle = PvPBattle(a, b, rng=random.Random(9))
    first = battle.submit(1, "attack")
    assert first["waiting"]
    second = battle.submit(2, "attack")
    assert not second["waiting"]
    assert battle.round == 2
    assert a.hp < 1000 or b.hp < 1000

    # Alice flees -> Bob wins.
    result = battle.submit(1, "flee")
    assert result["finished"] and battle.winner == 2


def test_pvp_skill_and_heal_and_draw():
    a = make_fighter(1, "Alice", hp=200, attack=5, defense=100, speed=5, skills=["power_strike"])
    a.mana = 100
    b = make_fighter(2, "Bob", hp=200, attack=5, defense=100, speed=4, skills=["power_strike"])
    battle = PvPBattle(a, b, rng=random.Random(2))
    assert battle.submit(1, "attack")["waiting"]
    result = battle.submit(2, "skill", skill_id="power_strike")
    assert not result["waiting"]
    assert b.mana < 100

    assert battle.submit(1, "heal", heal_amount=50)["waiting"]
    result = battle.submit(2, "heal", heal_amount=50)
    assert result["ok"]

    # Force a draw.
    battle2 = PvPBattle(make_fighter(3, "X", hp=500, attack=1, defense=500),
                        make_fighter(4, "Y", hp=500, attack=1, defense=500), rng=random.Random(3))
    for _ in range(100):
        if battle2.finished:
            break
        battle2.submit(3, "attack")
        battle2.submit(4, "attack")
    assert battle2.finished
    assert battle2.result in {"draw", "victory"}
