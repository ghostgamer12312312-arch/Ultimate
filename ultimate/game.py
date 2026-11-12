"""Gameplay engine: stats, combat, gacha, progression, raids and economy."""

from __future__ import annotations

import random
from datetime import date

try:
    from . import config, data
except ImportError:
    import config
    import data

MAX_LOG_LINES = 14


def _title_bonus(player: dict) -> dict:
    title = data.TITLES.get(player.get("title") or "", {})
    return title.get("bonus", {})


def _passive_bonus(skill_ids: list[str], scale: float = 1.0) -> dict:
    bonus: dict[str, float] = {}
    for skill_id in skill_ids:
        skill = data.SKILLS.get(skill_id)
        if not skill or skill["type"] != "passive":
            continue
        for key, value in skill.get("bonus", {}).items():
            bonus[key] = bonus.get(key, 0.0) + float(value) * scale
    return bonus


def scaled_character(character: dict) -> dict:
    level = int(character.get("level", 1))
    stars = int(character.get("stars", 1))
    level_mult = 1.0 + 0.075 * (level - 1)
    star_mult = 1.0 + 0.12 * (stars - 1)
    awaken_mult = 1.06 if character.get("awakened") else 1.0
    mult = level_mult * star_mult * awaken_mult
    return {
        "hp": int(character["hp"] * mult),
        "atk": int(character["atk"] * mult),
        "def": int(character["def"] * mult),
        "spd": int(character["spd"] * mult),
        "skills": list(character.get("skills", [])),
        "element": character.get("element", "spirit"),
        "name": character.get("name", "Unknown"),
        "series": character.get("series", "dragonball"),
        "rarity": character.get("rarity", "common"),
    }


def effective_stats(db, user_id: int, main_id: str | None = None) -> dict:
    player = db.require_player(user_id)
    rank = data.rank_for_level(int(player["level"]))
    base = {
        "hp": 700 + int(player["level"]) * 115,
        "atk": 55 + int(player["level"]) * 11,
        "def": 28 + int(player["level"]) * 7,
        "spd": 20 + int(player["level"]) * 1.6,
    }
    for key in base:
        base[key] *= rank["bonus"]
    attributes = {
        "strength": int(player.get("strength", 10) or 10),
        "agility": int(player.get("agility", 10) or 10),
        "intellect": int(player.get("intellect", 10) or 10),
        "vitality": int(player.get("vitality", 10) or 10),
        "luck": int(player.get("luck", 10) or 10),
    }
    base["hp"] += attributes["vitality"] * 6
    base["atk"] += attributes["strength"] * 1.8
    base["def"] += attributes["vitality"] * 0.9
    base["spd"] += attributes["agility"] * 0.8

    characters = {character["id"]: character for character in db.characters(user_id)}
    team_ids = db.team(user_id)
    if not team_ids and player.get("equipped_char") in characters:
        team_ids = [player["equipped_char"]]
    if main_id and main_id in characters:
        main = characters[main_id]
        support = [characters[cid] for cid in team_ids if cid in characters and cid != main_id][:2]
    else:
        main = next((characters[cid] for cid in team_ids if cid in characters), None)
        support = [characters[cid] for cid in team_ids[1:] if cid in characters]

    gear_slot_ids = [player.get("weapon"), player.get("armor"), player.get("accessory")]
    gear_items = []
    for instance_id in gear_slot_ids:
        if instance_id:
            gear = db.gear_instance(user_id, int(instance_id))
            if gear:
                gear_items.append(gear)

    if main:
        main_stats = scaled_character(main)
        base["hp"] += main_stats["hp"] * 0.48
        base["atk"] += main_stats["atk"] * 0.60
        base["def"] += main_stats["def"] * 0.46
        base["spd"] += main_stats["spd"] * 0.35
    for character in support:
        stats = scaled_character(character)
        base["hp"] += stats["hp"] * 0.11
        base["atk"] += stats["atk"] * 0.13
        base["def"] += stats["def"] * 0.10
        base["spd"] += stats["spd"] * 0.08

    for gear in gear_items:
        level_mult = 1.0 + 0.06 * (int(gear.get("level", 1)) - 1)
        base["hp"] += gear.get("hp", 0) * level_mult
        base["atk"] += gear.get("atk", 0) * level_mult
        base["def"] += gear.get("def", 0) * level_mult
        base["spd"] += gear.get("spd", 0) * level_mult

    passive_scale = 1.0 if main else 0.0
    passive_ids: list[str] = []
    if main:
        passive_ids.extend(main.get("skills", []))
    for character in support:
        passive_ids.extend(character.get("skills", []))
    passives = _passive_bonus(passive_ids, passive_scale)
    for key, pct in passives.items():
        stat = {"hp_pct": "hp", "atk_pct": "atk", "def_pct": "def", "spd_pct": "spd"}.get(key)
        if stat:
            base[stat] *= 1.0 + pct
    title = _title_bonus(player)
    for key, pct in title.items():
        stat = {"hp_pct": "hp", "atk_pct": "atk", "def_pct": "def", "spd_pct": "spd"}.get(key)
        if stat:
            base[stat] *= 1.0 + pct
    pet = next((item for item in db.pets(user_id) if item.get("equipped")), None)
    if pet:
        pet_scale = 1.0 + 0.02 * (int(pet.get("level", 1)) - 1)
        for key, pct in pet.get("bonus", {}).items():
            stat = {"hp_pct": "hp", "atk_pct": "atk", "def_pct": "def", "spd_pct": "spd"}.get(key)
            if stat:
                base[stat] *= 1.0 + float(pct) * pet_scale

    active_skills = []
    if main:
        active_skills.extend(main.get("skills", []))
    active_skills.extend(skill["id"] for skill in db.skills(user_id) if skill["equipped"])
    active_skills = [skill_id for skill_id in dict.fromkeys(active_skills) if data.SKILLS.get(skill_id, {}).get("type") == "active"]
    element = main["element"] if main else data.SERIES.get(player.get("travel", "dragonball"), {}).get("emoji", "spirit")
    if main is None:
        element = "spirit"

    max_mp = max(60, int(120 + int(player["level"]) * 4 + attributes["intellect"] * 8))
    return {
        "name": main["name"] if main else (player.get("first_name") or player.get("username") or "Summoner"),
        "hp": max(1, int(base["hp"])),
        "atk": max(1, int(base["atk"])),
        "def": max(0, int(base["def"])),
        "spd": max(1, int(base["spd"])),
        "mp": max_mp,
        "max_mp": max_mp,
        "crit": min(0.65, 0.08 + attributes["luck"] * 0.0008 + passives.get("crit", 0.0) + title.get("crit", 0.0)),
        "dodge": min(0.45, 0.04 + attributes["agility"] * 0.0006 + passives.get("dodge", 0.0) + title.get("dodge", 0.0)),
        "element": element,
        "skills": active_skills,
        "series": main["series"] if main else player.get("travel", "dragonball"),
        "rank": rank["name"],
        "attributes": attributes,
    }


def enemy_from_boss(boss: dict, scale: float = 1.0) -> dict:
    return {
        "name": boss["name"],
        "hp": int(boss["hp"] * scale),
        "atk": int(boss["atk"] * scale),
        "def": int(boss["def"] * scale),
        "spd": int(boss["spd"] * scale),
        "crit": 0.10,
        "dodge": 0.03,
        "element": boss.get("element", "spirit"),
        "skills": [],
    }


def enemy_from_npc(npc: dict) -> dict:
    return {
        "name": npc["name"],
        "hp": npc["hp"],
        "atk": npc["atk"],
        "def": npc["def"],
        "spd": npc["spd"],
        "crit": 0.06,
        "dodge": 0.02,
        "element": npc.get("element", "spirit"),
        "skills": [],
    }


def element_multiplier(attacker: str, defender: str) -> float:
    attack_data = data.ELEMENTS.get(attacker, {})
    defense_data = data.ELEMENTS.get(defender, {})
    if defender in attack_data.get("strong", []):
        return 1.40
    if defender in attack_data.get("weak", []):
        return 0.75
    if attacker in defense_data.get("strong", []):
        return 0.80
    return 1.0


def choose_skill(attacker: dict, turn: int, rng: random.Random) -> dict | None:
    if not attacker.get("skills"):
        return None
    if turn % 3 != 0 and rng.random() > 0.45:
        return None
    skill_id = rng.choice(attacker["skills"])
    return data.SKILLS.get(skill_id)


def attack_damage(attacker: dict, defender: dict, skill: dict | None, rng: random.Random) -> tuple[int, bool, bool]:
    if rng.random() < float(defender.get("dodge", 0.0)):
        return 0, False, True
    multiplier = float(skill["power"]) if skill else 1.0
    damage = max(1.0, float(attacker["atk"]) * multiplier - float(defender["def"]) * 0.44)
    damage *= element_multiplier(attacker.get("element", "spirit"), defender.get("element", "spirit"))
    crit = rng.random() < float(attacker.get("crit", 0.08))
    if crit:
        damage *= 1.65
    damage *= rng.uniform(0.90, 1.10)
    return max(1, int(damage)), crit, False


def simulate(player_stats: dict, enemy_stats: dict, *, seed: int | None = None, max_turns: int = 30) -> dict:
    rng = random.Random(seed)
    player = dict(player_stats)
    enemy = dict(enemy_stats)
    player_hp = int(player["hp"])
    enemy_hp = int(enemy["hp"])
    player_max = player_hp
    enemy_max = enemy_hp
    log: list[str] = []
    player_damage = 0
    enemy_damage = 0
    turn = 1
    while turn <= max_turns and player_hp > 0 and enemy_hp > 0:
        order = ["player", "enemy"] if player.get("spd", 1) >= enemy.get("spd", 1) else ["enemy", "player"]
        for actor_key in order:
            if player_hp <= 0 or enemy_hp <= 0:
                break
            if actor_key == "player":
                skill = choose_skill(player, turn, rng)
                damage, crit, dodged = attack_damage(player, enemy, skill, rng)
                if dodged:
                    log.append(f"💨 {enemy['name']} dodged {player['name']}'s attack.")
                else:
                    enemy_hp = max(0, enemy_hp - damage)
                    player_damage += damage
                    label = f"✨ {skill['name']}" if skill else "⚔️ Basic attack"
                    crit_label = " **CRITICAL**" if crit else ""
                    log.append(f"{label}: {player['name']} dealt {damage:,} to {enemy['name']}.{crit_label}")
            else:
                skill = choose_skill(enemy, turn, rng)
                damage, crit, dodged = attack_damage(enemy, player, skill, rng)
                if dodged:
                    log.append(f"💨 {player['name']} dodged {enemy['name']}'s attack.")
                else:
                    player_hp = max(0, player_hp - damage)
                    enemy_damage += damage
                    label = f"✨ {skill['name']}" if skill else "⚔️ Basic attack"
                    crit_label = " **CRITICAL**" if crit else ""
                    log.append(f"{label}: {enemy['name']} dealt {damage:,} to {player['name']}.{crit_label}")
        turn += 1
    if enemy_hp <= 0 and player_hp > 0:
        winner = "player"
    elif player_hp <= 0 and enemy_hp > 0:
        winner = "enemy"
    elif player_hp <= 0 and enemy_hp <= 0:
        winner = "draw"
    else:
        player_ratio = player_hp / max(1, player_max)
        enemy_ratio = enemy_hp / max(1, enemy_max)
        winner = "player" if player_ratio >= enemy_ratio else "enemy"
    return {
        "winner": winner,
        "turns": min(turn, max_turns),
        "log": log[-MAX_LOG_LINES:],
        "player_hp": player_hp,
        "player_max_hp": player_max,
        "enemy_hp": enemy_hp,
        "enemy_max_hp": enemy_max,
        "player_damage": player_damage,
        "enemy_damage": enemy_damage,
    }


def _apply_battle_result(db, user_id: int, result: dict, enemy_name: str, *, win_field: str = "wins", loss_field: str = "losses") -> None:
    won = result["winner"] == "player"
    with db.conn() as c:
        c.execute(
            f"UPDATE players SET total_battles=total_battles+1, {win_field}={win_field}+?, {loss_field}={loss_field}+?, current_hp=? WHERE user_id=?",
            (1 if won else 0, 0 if won else 1, max(1, int(result.get("player_max_hp", 1))), int(user_id)),
        )
    db.bump(user_id, "total_battles", 1)
    db.bump(user_id, "wins" if won else "losses", 1)
    db.battle_record(user_id, enemy_name, result["winner"], result["player_damage"])


def _reward_items(db, user_id: int, drops: dict[str, int]) -> None:
    for item_id, qty in drops.items():
        if qty > 0:
            db.add_item(user_id, item_id, qty)


def _drop_for_rarity(rarity: str) -> str:
    return {
        "common": "shard_common",
        "rare": "shard_rare",
        "epic": "shard_epic",
        "legendary": "shard_legendary",
        "mythic": "shard_mythic",
        "divine": "shard_divine",
    }.get(rarity, "shard_common")


def hunt(db, user_id: int, series: str | None = None) -> dict:
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    if int(player["stamina"]) < 8:
        return {"ok": False, "reason": "Not enough stamina. You need 8."}
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    if series not in data.SERIES:
        series = "dragonball"
    npcs = data.NPCS[series]
    limit = max(1, min(len(npcs), 1 + int(player["level"]) // 12))
    npc = random.choice(npcs[:limit])
    stats = effective_stats(db, user_id)
    enemy = enemy_from_npc(npc)
    result = simulate(stats, enemy)
    db.spend(user_id, stamina=8)
    _apply_battle_result(db, user_id, result, npc["name"])
    db.bump(user_id, "hunt", 1)
    rewards = {}
    drops = {}
    if result["winner"] == "player":
        player_row = db.require_player(user_id)
        streak = int(player_row["npc_streak"]) + 1
        best = max(int(player_row["best_streak"]), streak)
        db.set_field(user_id, "npc_streak", streak)
        db.set_field(user_id, "best_streak", best)
        db.bump(user_id, "npc_streak", 1)
        rewards = {"yens": npc["yens"], "exp": npc["exp"], "gems": npc["gems"]}
        if npc.get("drop") and random.random() < 0.40:
            drops[npc["drop"]] = 1
        if random.random() < 0.025:
            drops[f"dragon_ball_{db.dragon_ball_count(user_id) % 7 + 1}"] = 1
        db.grant_rewards(user_id, rewards)
        _reward_items(db, user_id, drops)
    else:
        db.set_field(user_id, "npc_streak", 0)
        db.grant_rewards(user_id, {"exp": max(10, npc["exp"] // 5)})
    return {"ok": True, "series": series, "npc": npc, "result": result, "rewards": rewards, "drops": drops}


def fight_boss(db, user_id: int, series: str | None = None, boss_id: str | None = None) -> dict:
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    if int(player["stamina"]) < 15:
        return {"ok": False, "reason": "Not enough stamina. You need 15."}
    if db.item_qty(user_id, "boss_key") < 1:
        return {"ok": False, "reason": "You need a Boss Key. Buy one with /shop."}
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    bosses = data.BOSSES.get(series, [])
    if not bosses:
        return {"ok": False, "reason": "No boss found for that series."}
    if boss_id:
        boss = next((item for item in bosses if item["id"] == boss_id), None)
    else:
        index = max(0, min(len(bosses) - 1, int(player["level"]) // 22))
        boss = bosses[index]
    if boss is None:
        return {"ok": False, "reason": "Unknown boss."}
    state = db.boss_state(user_id, boss)
    if state.get("status") == "defeated":
        db.reset_boss(user_id, boss["id"])
        state = db.boss_state(user_id, boss)
    stats = effective_stats(db, user_id)
    enemy = enemy_from_boss(boss, 0.42)
    enemy["hp"] = max(1, int(state["hp"]))
    result = simulate(stats, enemy)
    db.spend(user_id, stamina=15)
    db.take_item(user_id, "boss_key", 1)
    damage = max(0, int(result["player_damage"]))
    state = db.damage_boss(user_id, boss, damage)
    _apply_battle_result(db, user_id, result, boss["name"], win_field="boss_kills")
    rewards = {}
    drops = {}
    killed = int(state["hp"]) <= 0
    if killed:
        rewards = {"yens": boss["yens"], "exp": boss["exp"], "gems": boss["gems"], "crystals": boss["crystals"]}
        drops[boss["drop"]] = 1
        if random.random() < 0.08:
            drops[f"dragon_ball_{db.dragon_ball_count(user_id) % 7 + 1}"] = 1
        db.grant_rewards(user_id, rewards)
        _reward_items(db, user_id, drops)
        db.reset_boss(user_id, boss["id"])
    elif result["winner"] != "player":
        db.grant_rewards(user_id, {"exp": max(30, boss["exp"] // 6)})
    return {"ok": True, "series": series, "boss": boss, "state": state, "result": result, "rewards": rewards, "drops": drops, "killed": killed, "damage": damage}


def fight_elite(db, user_id: int, series: str | None = None) -> dict:
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    if int(player["stamina"]) < 12:
        return {"ok": False, "reason": "Not enough stamina. You need 12."}
    if db.item_qty(user_id, "elite_key") < 1:
        return {"ok": False, "reason": "You need an Elite Key. Buy one with /shop."}
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    npcs = data.NPCS[series]
    npc = npcs[max(0, min(len(npcs) - 1, int(player["level"]) // 18))]
    elite = dict(npc)
    elite.update({
        "id": npc["id"] + "_elite",
        "name": "Elite " + npc["name"],
        "hp": int(npc["hp"] * 1.8),
        "atk": int(npc["atk"] * 1.35),
        "def": int(npc["def"] * 1.35),
        "spd": int(npc["spd"] * 1.2),
        "exp": int(npc["exp"] * 2.5),
        "yens": int(npc["yens"] * 2.5),
    })
    stats = effective_stats(db, user_id)
    result = simulate(stats, enemy_from_npc(elite))
    db.spend(user_id, stamina=12)
    db.take_item(user_id, "elite_key", 1)
    _apply_battle_result(db, user_id, result, elite["name"], win_field="boss_kills")
    rewards = {}
    drops = {}
    if result["winner"] == "player":
        rewards = {"yens": elite["yens"], "exp": elite["exp"], "gems": 5, "crystals": 2}
        drops["shard_rare"] = 2
        drops["forge_core"] = 1
        if random.random() < 0.05:
            drops["awakening_stone"] = 1
        db.grant_rewards(user_id, rewards)
        _reward_items(db, user_id, drops)
    return {"ok": True, "series": series, "npc": elite, "result": result, "rewards": rewards, "drops": drops}


def attack_world(db, user_id: int) -> dict:
    boss = db.world_boss_current()
    if not boss:
        return {"ok": False, "reason": "No world boss is active."}
    if boss.get("hp", 0) <= 0:
        return {"ok": False, "reason": "The world boss is already defeated. Return tomorrow."}
    if db.item_qty(user_id, "raid_token") < 1:
        if not db.spend(user_id, stamina=25):
            return {"ok": False, "reason": "Need 1 Raid Token or 25 stamina."}
    else:
        db.take_item(user_id, "raid_token", 1)
    stats = effective_stats(db, user_id)
    boss_info = boss["boss"]
    result = simulate(stats, enemy_from_boss(boss_info, 0.12), max_turns=30)
    damage = max(1, result["player_damage"])
    state = db.record_world_damage(user_id, damage)
    rewards = {
        "yens": max(80, damage * 2),
        "exp": max(60, damage // 3),
        "gems": 2 if damage > 2500 else 0,
    }
    db.grant_rewards(user_id, rewards)
    if result["winner"] == "player":
        rewards["crystals"] = 2
        db.grant_rewards(user_id, {"crystals": 2})
    if random.random() < 0.10:
        db.add_dragon_ball(user_id)
    _apply_battle_result(db, user_id, result, boss_info["name"])
    return {"ok": True, "boss": boss_info, "state": state, "result": result, "damage": damage, "rewards": rewards}


def attack_clan_raid(db, user_id: int) -> dict:
    clan = db.clan(user_id)
    if clan is None:
        return {"ok": False, "reason": "Join a clan first."}
    raid_row = db.clan_raid_current(clan["id"])
    if raid_row is None:
        return {"ok": False, "reason": "Your clan has no active raid. The leader can start one."}
    if raid_row["hp"] <= 0:
        return {"ok": False, "reason": "The clan raid boss is already defeated."}
    if db.item_qty(user_id, "raid_token") < 1:
        if not db.spend(user_id, stamina=20):
            return {"ok": False, "reason": "Need 1 Raid Token or 20 stamina."}
    else:
        db.take_item(user_id, "raid_token", 1)
    info = data.CLAN_RAID_BY_ID.get(raid_row["raid_id"], data.CLAN_RAIDS[0])
    boss = {
        "name": info["name"],
        "hp": info["hp"],
        "atk": info["atk"],
        "def": info["def"],
        "spd": info["spd"],
        "element": info["element"],
    }
    stats = effective_stats(db, user_id)
    result = simulate(stats, enemy_from_boss(boss, 0.16), max_turns=30)
    damage = max(1, result["player_damage"])
    state = db.record_clan_raid_damage(user_id, damage)
    rewards = {"yens": max(100, damage * 2), "exp": max(80, damage // 3), "gems": 2}
    db.grant_rewards(user_id, rewards)
    _apply_battle_result(db, user_id, result, info["name"])
    return {"ok": True, "raid": info, "state": state, "result": result, "damage": damage, "rewards": rewards}


def duel(db, user_id: int, opponent_id: int) -> dict:
    if int(user_id) == int(opponent_id):
        return {"ok": False, "reason": "You cannot duel yourself."}
    db.refresh_stamina(user_id)
    if not db.spend(user_id, stamina=15):
        return {"ok": False, "reason": "Need 15 stamina to duel."}
    opponent = db.require_player(opponent_id)
    if opponent.get("banned"):
        return {"ok": False, "reason": "That player is banned."}
    a = effective_stats(db, user_id)
    b = effective_stats(db, opponent_id)
    result = simulate(a, b)
    won = result["winner"] == "player"
    rating_change = random.randint(14, 25)
    if won:
        with db.conn() as c:
            c.execute("UPDATE players SET arena_rating=arena_rating+?, pvp_wins=pvp_wins+1 WHERE user_id=?", (rating_change, int(user_id)))
            c.execute("UPDATE players SET arena_rating=MAX(0, arena_rating-?) WHERE user_id=?", (max(5, rating_change // 2), int(opponent_id)))
        db.bump(user_id, "pvp_wins", 1)
    else:
        with db.conn() as c:
            c.execute("UPDATE players SET arena_rating=MAX(0, arena_rating-?) WHERE user_id=?", (rating_change, int(user_id)))
            c.execute("UPDATE players SET arena_rating=arena_rating+? WHERE user_id=?", (max(3, rating_change // 2), int(opponent_id)))
    _apply_battle_result(db, user_id, result, opponent.get("first_name") or opponent.get("username") or "Opponent")
    db.duel_record(user_id, opponent_id, int(user_id) if won else int(opponent_id), rating_change if won else -rating_change)
    rewards = {"yens": 280 if won else 80, "exp": 180 if won else 45, "gems": 8 if won else 1}
    db.grant_rewards(user_id, rewards)
    return {"ok": True, "opponent": opponent, "result": result, "won": won, "rating_change": rating_change, "rewards": rewards}


def arena(db, user_id: int) -> dict:
    opponent = db.random_opponent(user_id)
    if opponent is None:
        return {"ok": False, "reason": "No arena opponents found yet."}
    return duel(db, user_id, int(opponent["user_id"]))


def _pick_rarity(rng: random.Random, pity: int) -> str:
    if pity >= config.GACHA_PITY - 1:
        return rng.choices(["mythic", "divine"], weights=[5, 1])[0]
    rarities = data.RARITY_ORDER
    weights = [data.RARITIES[rarity]["weight"] for rarity in rarities]
    return rng.choices(rarities, weights=weights)[0]


def _pick_character(series: str, rarity: str, banner: dict, rng: random.Random) -> str | None:
    if series == "all":
        pool = data.CHARACTERS_BY_RARITY.get(rarity, [])
    else:
        pool = [cid for cid in data.CHARACTERS_BY_SERIES.get(series, []) if data.CHARACTERS[cid]["rarity"] == rarity]
    if not pool:
        pool = [cid for cid in data.CHARACTERS if series == "all" or data.CHARACTERS[cid]["series"] == series]
    if not pool:
        pool = list(data.CHARACTERS)
    featured = [cid for cid in banner.get("featured", []) if cid in pool]
    if featured and rng.random() < float(banner.get("boost", 0.25)):
        return rng.choice(featured)
    return rng.choice(pool)


def gacha(db, user_id: int, banner_id: str = "dragonball", count: int = 1) -> dict:
    banner = data.GACHA_BANNERS.get(banner_id)
    if banner is None:
        return {"ok": False, "reason": "Unknown banner."}
    count = 10 if int(count) >= 10 else 1
    player = db.require_player(user_id)
    if count == 10:
        if int(player["tickets"]) >= 10:
            db.spend(user_id, tickets=10)
            payment = "10 tickets"
        elif db.spend(user_id, gems=config.GACHA_MULTI_COST_GEMS):
            payment = f"{config.GACHA_MULTI_COST_GEMS} gems"
        else:
            return {"ok": False, "reason": f"Need 10 tickets or {config.GACHA_MULTI_COST_GEMS} gems for a 10x summon."}
    else:
        if int(player["tickets"]) >= 1:
            db.spend(user_id, tickets=1)
            payment = "1 ticket"
        elif db.spend(user_id, gems=config.GACHA_COST_GEMS):
            payment = f"{config.GACHA_COST_GEMS} gems"
        else:
            return {"ok": False, "reason": f"Need 1 ticket or {config.GACHA_COST_GEMS} gems."}

    results = []
    rng = random.Random()
    pity = int(player["pity"])
    for _ in range(count):
        rarity = _pick_rarity(rng, pity)
        char_id = _pick_character(banner["series"], rarity, banner, rng)
        if char_id is None:
            continue
        new, base = db.add_character(user_id, char_id)
        if new:
            shards = 0
            gems = 0
        else:
            shards = 5 if base["rarity"] in ("common", "rare") else 3
            db.add_shards(user_id, char_id, shards)
            gems = data.RARITIES[base["rarity"]]["gem_dup"]
            db.give(user_id, gems=gems)
        actual_rarity = base["rarity"]
        results.append({"character": base, "new": new, "shards": shards, "gems": gems, "rarity": actual_rarity})
        if actual_rarity in ("mythic", "divine"):
            pity = 0
        else:
            pity += 1
        db.bump(user_id, "gacha_pulls", 1)
    with db.conn() as c:
        c.execute("UPDATE players SET gacha_pulls=gacha_pulls+? WHERE user_id=?", (len(results), int(user_id)))
    db.set_field(user_id, "pity", pity)
    return {"ok": True, "banner": banner, "results": results, "payment": payment, "pity": pity}


def wish(db, user_id: int, series: str | None = None) -> dict:
    if not db.consume_dragon_balls(user_id):
        return {"ok": False, "reason": "You need all 7 Dragon Balls."}
    series = series if series in data.SERIES else "all"
    pool = [
        cid for cid in data.CHARACTERS
        if data.CHARACTERS[cid]["rarity"] == "divine"
        and (series == "all" or data.CHARACTERS[cid]["series"] == series)
    ] or [cid for cid in data.CHARACTERS if data.CHARACTERS[cid]["rarity"] == "divine"]
    char_id = random.choice(pool)
    new, base = db.add_character(user_id, char_id)
    if not new:
        db.add_shards(user_id, char_id, 10)
    return {"ok": True, "character": base, "new": new}


def use_item(db, user_id: int, item_id: str, qty: int = 1) -> dict:
    item = data.ITEMS.get(item_id)
    if item is None:
        return {"ok": False, "reason": "Unknown item."}
    qty = max(1, int(qty))
    kind = item["kind"]
    if kind in ("key_elite", "key_boss", "raid", "awaken", "craft", "material", "shard", "dragonball"):
        return {"ok": False, "reason": "This item is used automatically or from its own command."}
    if not db.take_item(user_id, item_id, qty):
        return {"ok": False, "reason": "You do not have that many."}
    player = db.require_player(user_id)
    value = int(item["value"]) * qty
    if kind == "heal":
        stats = effective_stats(db, user_id)
        current = min(stats["hp"], int(player["current_hp"]) + value)
        db.set_field(user_id, "current_hp", current)
        return {"ok": True, "message": f"Restored {value:,} HP.", "item": item}
    if kind == "stamina":
        with db.conn() as c:
            c.execute("UPDATE players SET stamina=MIN(max_stamina, stamina+?) WHERE user_id=?", (value, int(user_id)))
        return {"ok": True, "message": f"Restored {value} stamina.", "item": item}
    if kind == "exp":
        result = db.add_exp(user_id, value)
        return {"ok": True, "message": f"Gained {value:,} EXP. Level {result['level']}.", "item": item, "level_up": result["level_up"]}
    if kind == "ticket":
        db.add_currency(user_id, "tickets", value)
        return {"ok": True, "message": f"Added {value} summon ticket(s).", "item": item}
    if kind == "wish":
        return wish(db, user_id)
    if kind == "pet":
        hatched = db.random_pet(user_id, premium=int(item.get("value", 1)) >= 2)
        return {"ok": True, "message": f"Hatched {hatched['pet']['name']}!", "item": item, "pet": hatched["pet"], "new": hatched["new"]}
    return {"ok": True, "message": "Item used.", "item": item}


def shop_catalog(category: str = "all") -> list[dict]:
    entries: list[dict] = []
    for item_id, item in data.ITEMS.items():
        if item["currency"] == "none" or item["price"] <= 0:
            continue
        if category == "gear":
            continue
        kind = item["kind"]
        group = "potions" if kind in ("heal", "stamina") else "summon" if kind in ("ticket", "key_elite", "key_boss", "raid") else "materials"
        if category not in ("all", group):
            continue
        entries.append({"id": item_id, "name": item["name"], "emoji": item["emoji"], "price": item["price"], "currency": item["currency"], "kind": "item", "desc": item["desc"]})
    if category in ("all", "gear"):
        for gear_id, gear in data.GEAR.items():
            entries.append({"id": gear_id, "name": gear["name"], "emoji": data.RARITIES[gear["rarity"]]["emoji"], "price": gear["price"], "currency": gear["currency"], "kind": "gear", "desc": gear["desc"]})
    return entries


def buy_shop(db, user_id: int, item_id: str, qty: int = 1) -> dict:
    qty = max(1, min(99, int(qty)))
    item = data.ITEMS.get(item_id)
    gear = data.GEAR.get(item_id)
    if item is None and gear is None:
        return {"ok": False, "reason": "That item is not in the shop."}
    if item:
        price = int(item["price"]) * qty
        currency = item["currency"]
        if currency == "none":
            return {"ok": False, "reason": "That item cannot be bought."}
        if not db.spend(user_id, **{currency: price}):
            return {"ok": False, "reason": f"Not enough {currency}."}
        db.add_item(user_id, item_id, qty)
        return {"ok": True, "name": item["name"], "qty": qty, "price": price, "currency": currency, "kind": "item"}
    price = int(gear["price"])
    currency = gear["currency"]
    if qty != 1:
        return {"ok": False, "reason": "Gear can only be bought one at a time."}
    if not db.spend(user_id, **{currency: price}):
        return {"ok": False, "reason": f"Not enough {currency}."}
    instance = db.grant_gear(user_id, item_id)
    return {"ok": True, "name": gear["name"], "qty": 1, "price": price, "currency": currency, "kind": "gear", "instance_id": instance}


def sell_item(db, user_id: int, item_id: str, qty: int = 1) -> dict:
    item = data.ITEMS.get(item_id)
    qty = max(1, int(qty))
    if item is None or item["kind"] in ("dragonball", "wish"):
        return {"ok": False, "reason": "That item cannot be sold."}
    if not db.take_item(user_id, item_id, qty):
        return {"ok": False, "reason": "You do not have that many."}
    value = max(1, int(item["price"] * 0.35)) * qty
    db.add_currency(user_id, "yens", value)
    return {"ok": True, "name": item["name"], "qty": qty, "yens": value}


def daily_shop(db) -> list[dict]:
    seed = int(date.today().strftime("%Y%m%d"))
    pool = list(data.DAILY_SHOP_POOL)
    picks = []
    for offset in range(6):
        item_id = pool[(seed + offset * 7) % len(pool)]
        item = data.ITEMS.get(item_id)
        if item is None:
            continue
        discount = 0.15 + (offset % 3) * 0.05
        price = max(1, int(item["price"] * (1 - discount)))
        picks.append({
            "slot": offset + 1, "id": item_id, "name": item["name"], "emoji": item["emoji"],
            "price": price, "currency": item["currency"], "discount": discount, "desc": item["desc"],
        })
    return picks


def buy_daily(db, user_id: int, slot: int) -> dict:
    shop = daily_shop(db)
    offer = next((item for item in shop if item["slot"] == int(slot)), None)
    if offer is None:
        return {"ok": False, "reason": "Invalid daily shop slot."}
    if not db.spend(user_id, **{offer["currency"]: offer["price"]}):
        return {"ok": False, "reason": f"Not enough {offer['currency']}."}
    db.add_item(user_id, offer["id"], 1)
    return {"ok": True, "offer": offer}


def craft(db, user_id: int, recipe_id: str) -> dict:
    recipe = next((item for item in data.CRAFTING_RECIPES if item["id"] == recipe_id), None)
    if recipe is None:
        return {"ok": False, "reason": "Unknown recipe."}
    item_costs = {key: value for key, value in recipe["cost"].items() if key in data.ITEMS}
    yens = int(recipe["cost"].get("yens", 0))
    player = db.require_player(user_id)
    if int(player["yens"]) < yens:
        return {"ok": False, "reason": f"Need {yens:,} yens."}
    for item_id, qty in item_costs.items():
        if db.item_qty(user_id, item_id) < int(qty):
            return {"ok": False, "reason": f"Need {qty}x {data.ITEMS[item_id]['name']}."}
    if yens:
        db.spend(user_id, yens=yens)
    for item_id, qty in item_costs.items():
        db.take_item(user_id, item_id, int(qty))
    instance = db.grant_gear(user_id, recipe["result"])
    return {"ok": True, "gear": data.GEAR[recipe["result"]], "instance_id": instance}


def chapter_status(db, user_id: int, series: str | None = None) -> dict:
    player = db.require_player(user_id)
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    chapters = data.CHAPTERS.get(series, [])
    cleared = db.chapter_progress(user_id, series)
    next_chapter = next((chapter for chapter in chapters if int(chapter["number"]) not in cleared), None)
    return {"series": series, "chapters": chapters, "cleared": cleared, "next": next_chapter}


def chapter_fight(db, user_id: int, series: str | None = None, chapter: int | None = None) -> dict:
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    chapters = data.CHAPTERS.get(series, [])
    if not chapters:
        return {"ok": False, "reason": "No chapters found for that series."}
    cleared = db.chapter_progress(user_id, series)
    if chapter is None:
        chapter_data = next((item for item in chapters if int(item["number"]) not in cleared), None)
        if chapter_data is None:
            return {"ok": False, "reason": "Every chapter is cleared. Switch series for a new story."}
    else:
        number = max(1, int(chapter))
        chapter_data = next((item for item in chapters if int(item["number"]) == number), None)
        if chapter_data is None:
            return {"ok": False, "reason": "Unknown chapter."}
    number = int(chapter_data["number"])
    if number in cleared:
        return {"ok": False, "reason": "That chapter is already cleared."}
    if number > 1 and number - 1 not in cleared:
        return {"ok": False, "reason": f"Clear chapter {number - 1} first."}
    if not db.spend(user_id, stamina=15):
        return {"ok": False, "reason": "Need 15 stamina to fight this chapter."}
    enemy = enemy_from_npc(chapter_data["enemy"])
    result = simulate(effective_stats(db, user_id), enemy)
    _apply_battle_result(db, user_id, result, chapter_data["enemy"]["name"])
    rewards = {}
    drops = {}
    if result["winner"] == "player":
        db.clear_chapter(user_id, series, number)
        rewards = dict(chapter_data["rewards"])
        drops[chapter_data["drop"]] = 1
        db.grant_rewards(user_id, rewards)
        _reward_items(db, user_id, drops)
    else:
        rewards = {"exp": max(20, int(chapter_data["rewards"].get("exp", 0)) // 8)}
        db.grant_rewards(user_id, rewards)
    return {"ok": True, "series": series, "chapter": chapter_data, "result": result, "rewards": rewards, "drops": drops, "cleared": number in db.chapter_progress(user_id, series)}


def summon_boss(db, user_id: int, series: str | None = None, boss_id: str | None = None) -> dict:
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    pool = data.SUMMON_BOSSES_BY_SERIES.get(series, data.SUMMON_BOSSES)
    if boss_id:
        boss = next((item for item in data.SUMMON_BOSSES if item["id"] == boss_id), None)
    else:
        boss = random.choice(pool)
    if boss is None:
        return {"ok": False, "reason": "Unknown summon boss."}
    scaled = dict(boss)
    scaled["hp"] = max(1, int(boss["hp"] * 0.18))
    state = db.summon_state(user_id, scaled)
    if int(state["hp"]) <= 0:
        state = db.summon_state(user_id, scaled)
    if int(player["tickets"]) >= 1:
        db.spend(user_id, tickets=1)
        payment = "1 ticket"
    elif db.spend(user_id, gems=15):
        payment = "15 gems"
    elif db.spend(user_id, stamina=20):
        payment = "20 stamina"
    else:
        return {"ok": False, "reason": "Need 1 ticket, 15 gems, or 20 stamina to summon."}
    enemy = enemy_from_boss(scaled, 0.55)
    enemy["hp"] = max(1, int(state["hp"]))
    result = simulate(effective_stats(db, user_id), enemy, max_turns=30)
    damage = max(0, int(result["player_damage"]))
    state = db.damage_summon(user_id, scaled, damage)
    _apply_battle_result(db, user_id, result, boss["name"])
    rewards = {}
    drops = {}
    killed = int(state["hp"]) <= 0
    if killed:
        rewards = dict(boss.get("reward", {}))
        drops[boss.get("drop", "shard_epic")] = 2
        db.grant_rewards(user_id, rewards)
        _reward_items(db, user_id, drops)
        if random.random() < 0.20:
            db.give(user_id, skill_points=1)
            rewards["skill_points"] = 1
    return {"ok": True, "series": series, "boss": boss, "state": state, "result": result, "damage": damage, "rewards": rewards, "drops": drops, "killed": killed, "payment": payment}


def skill_cost(skill: dict) -> tuple[int, str]:
    power = float(skill.get("power", 1.0))
    if power >= 2.4:
        return int(30 + power * 12), "crystals"
    if power >= 1.8:
        return int(25 + power * 8), "gems"
    return int(1200 + power * 1600), "yens"


def skill_shop(series: str = "all") -> list[dict]:
    skill_ids = []
    if series in data.SKILLS_BY_SERIES:
        skill_ids = data.SKILLS_BY_SERIES[series]
    else:
        for ids in data.SKILLS_BY_SERIES.values():
            skill_ids.extend(ids)
    rows = []
    for skill_id in skill_ids:
        skill = data.SKILLS.get(skill_id)
        if skill is None or skill.get("type") != "active":
            continue
        cost, currency = skill_cost(skill)
        rows.append({"skill": skill, "cost": cost, "currency": currency})
    return rows


def buy_skill(db, user_id: int, skill_id: str) -> dict:
    skill = data.SKILLS.get(skill_id)
    if skill is None or skill.get("type") != "active":
        return {"ok": False, "reason": "Unknown active skill."}
    if any(item["id"] == skill_id for item in db.skills(user_id)):
        return {"ok": False, "reason": "You already know that skill."}
    cost, currency = skill_cost(skill)
    if not db.spend(user_id, **{currency: cost}):
        return {"ok": False, "reason": f"Need {cost:,} {currency}."}
    with db.conn() as c:
        c.execute("INSERT INTO skills(user_id, skill_id, level, equipped) VALUES(?,?,1,0)", (int(user_id), skill_id))
    return {"ok": True, "skill": skill, "cost": cost, "currency": currency}



def travel(db, user_id: int, series: str) -> dict:
    if series not in data.SERIES:
        return {"ok": False, "reason": "Unknown series."}
    db.set_field(user_id, "travel", series)
    return {"ok": True, "series": data.SERIES[series]}


def power_score(stats: dict) -> int:
    return int(stats["hp"] * 0.15 + stats["atk"] * 3.2 + stats["def"] * 2.1 + stats["spd"] * 1.4)


def best_team_power(db, user_id: int) -> tuple[int, str]:
    characters = db.characters(user_id)
    if not characters:
        return 0, "No hero"
    best = max(characters, key=lambda c: c["power"] + c["level"] * 3 + c["stars"] * 12)
    return int(best["power"] * 10 + best["level"] * 40 + best["stars"] * 80), best["name"]


def series_collection(db, user_id: int) -> dict[str, int]:
    counts = {series: 0 for series in data.SERIES}
    for character in db.characters(user_id):
        counts[character["series"]] = counts.get(character["series"], 0) + 1
    return counts


def fish(db, user_id: int) -> dict:
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    if not db.spend(user_id, stamina=5):
        return {"ok": False, "reason": "Need 5 stamina to fish."}
    roll = random.random()
    drops = {}
    if roll < 0.62:
        drops["fish_common"] = random.randint(1, 3)
    elif roll < 0.90:
        drops["fish_rare"] = 1
    elif roll < 0.97:
        drops["crystal_shard"] = 1
    else:
        drops["treasure_map"] = 1
    rewards = {"yens": random.randint(40, 120), "exp": random.randint(20, 60)}
    db.grant_rewards(user_id, rewards)
    _reward_items(db, user_id, drops)
    return {"ok": True, "rewards": rewards, "drops": drops}


def mine(db, user_id: int) -> dict:
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    if not db.spend(user_id, stamina=8):
        return {"ok": False, "reason": "Need 8 stamina to mine."}
    roll = random.random()
    drops = {"ore_iron": random.randint(1, 3)}
    if roll < 0.70:
        pass
    elif roll < 0.92:
        drops["ore_gold"] = 1
    elif roll < 0.98:
        drops["crystal_shard"] = 2
    else:
        drops["forge_core"] = 1
    if random.random() < 0.10:
        drops["dragon_ball_" + str(db.dragon_ball_count(user_id) % 7 + 1)] = 1
    rewards = {"yens": random.randint(60, 160), "exp": random.randint(30, 80)}
    db.grant_rewards(user_id, rewards)
    _reward_items(db, user_id, drops)
    return {"ok": True, "rewards": rewards, "drops": drops}


def dungeon(db, user_id: int, series: str | None = None) -> dict:
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    floors = data.DUNGEONS.get(series, [])
    if not floors:
        return {"ok": False, "reason": "No dungeon found for that series."}
    if not db.spend(user_id, stamina=25):
        return {"ok": False, "reason": "Need 25 stamina to enter the dungeon."}
    index = max(0, min(len(floors) - 1, int(player["level"]) // 20))
    floor = floors[index]
    stats = effective_stats(db, user_id)
    result = simulate(stats, enemy_from_boss(floor, 0.70))
    _apply_battle_result(db, user_id, result, floor["name"], win_field="boss_kills")
    rewards = {}
    drops = {}
    if result["winner"] == "player":
        rewards = {"yens": floor["yens"], "exp": floor["exp"], "gems": floor["gems"], "crystals": floor["crystals"]}
        drops[floor["drop"]] = 2
        drops["forge_core"] = 1
        if random.random() < 0.20:
            drops["awakening_stone"] = 1
        db.grant_rewards(user_id, rewards)
        _reward_items(db, user_id, drops)
    else:
        db.grant_rewards(user_id, {"exp": max(50, floor["exp"] // 8)})
    return {"ok": True, "series": series, "floor": floor, "result": result, "rewards": rewards, "drops": drops}
