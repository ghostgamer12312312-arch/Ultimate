"""Turn-based battle engine with inline-button actions."""

from __future__ import annotations

import random
import time
import uuid

try:
    from . import data, game, ui
except ImportError:
    import data
    import game
    import ui

ELEMENT_EMOJI = {
    "spirit": "🔮", "fire": "🔥", "water": "💧", "earth": "🌍", "air": "🌪️",
    "lightning": "⚡", "light": "✨", "dark": "🌑", "ice": "❄️", "poison": "☠️",
}

MODES = {"hunt", "boss", "elite", "dungeon", "chapter", "summon", "world", "clanraid", "duel", "arena"}
WIN_FIELDS = {"wins", "boss_kills", "pvp_wins", "hunt", "raid_damage"}
LOSS_FIELDS = {"losses"}


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _rng() -> random.Random:
    return random.Random()


def _battle_id() -> str:
    return uuid.uuid4().hex


def _skill_cost(skill: dict) -> int:
    power = float(skill.get("power", 1.0))
    return max(6, int(8 + power * 11))


def _player_snapshot(db, user_id: int, main_id: str | None = None) -> dict:
    player = db.require_player(user_id)
    stats = game.effective_stats(db, user_id, main_id)
    max_hp = max(1, int(stats["hp"]))
    hp = max_hp
    max_mp = max(1, int(stats.get("max_mp", 200)))
    mp = max_mp
    skills = [skill_id for skill_id in stats.get("skills", []) if data.SKILLS.get(skill_id, {}).get("type") == "active"]
    return {
        "user_id": int(user_id),
        "char_id": main_id or player.get("equipped_char") or "",
        "name": stats["name"],
        "level": int(player["level"]),
        "hp": hp,
        "max_hp": max_hp,
        "mp": mp,
        "max_mp": max_mp,
        "atk": int(stats["atk"]),
        "def": int(stats["def"]),
        "spd": int(stats["spd"]),
        "crit": float(stats.get("crit", 0.08)),
        "dodge": float(stats.get("dodge", 0.04)),
        "element": stats.get("element", "spirit"),
        "skills": skills[:5],
        "cooldowns": {},
    }


def _team_snapshots(db, user_id: int) -> list[dict]:
    team_ids = db.team(user_id)
    if not team_ids:
        player = db.require_player(user_id)
        team_ids = [player["equipped_char"]] if player.get("equipped_char") else []
    snapshots = []
    for char_id in team_ids[:3]:
        try:
            snap = _player_snapshot(db, user_id, char_id)
        except Exception:
            continue
        snap["char_id"] = char_id
        snapshots.append(snap)
    return snapshots


def _enemy(name: str, stats: dict, *, level: int = 1, art: str = "npc", art_key: str = "") -> dict:
    return {
        "name": name,
        "level": int(level),
        "hp": max(1, int(stats["hp"])),
        "max_hp": max(1, int(stats["hp"])),
        "atk": max(1, int(stats["atk"])),
        "def": max(0, int(stats["def"])),
        "spd": max(1, int(stats["spd"])),
        "crit": float(stats.get("crit", 0.06)),
        "dodge": float(stats.get("dodge", 0.02)),
        "element": stats.get("element", "spirit"),
        "skills": list(stats.get("skills", []))[:4],
        "art": art,
        "art_key": art_key,
    }


def _new_battle(db, user_id: int, mode: str, title: str, enemy: dict, meta: dict, intro: str) -> dict:
    player = _player_snapshot(db, user_id)
    battle = {
        "battle_id": _battle_id(),
        "user_id": int(user_id),
        "mode": mode,
        "title": title,
        "created_at": _now(),
        "state": {
            "player": player,
            "enemy": enemy,
            "turn": 1,
            "ult": 0,
            "guard": 0,
            "transform": 0,
            "active_team": 0,
            "team": _team_snapshots(db, user_id),
            "status": "active",
            "outcome": None,
            "log": [intro],
            "rewards": {},
            "drops": {},
            "meta": meta,
            "started": int(time.time()),
        },
    }
    db.save_battle(battle)
    db.set_vitals(user_id, hp=player["hp"], mp=player["mp"])
    return battle


def _existing(db, user_id: int) -> dict | None:
    return db.active_battle(user_id)


def _resume(db, user_id: int) -> dict | None:
    battle = _existing(db, user_id)
    if battle and battle.get("state", {}).get("status") == "active":
        return battle
    if battle:
        db.clear_battle(user_id)
    return None


def _pick_boss(series: str, boss_id: str | None) -> dict | None:
    bosses = data.BOSSES.get(series, [])
    if boss_id:
        return next((boss for boss in bosses if boss["id"] == boss_id), None)
    return bosses[0] if bosses else None


def _dragonball_drop(db, user_id: int, chance: float) -> dict:
    if random.random() < chance:
        return {f"dragon_ball_{db.dragon_ball_count(user_id) % 7 + 1}": 1}
    return {}


def start_hunt(db, user_id: int, series: str | None = None, npc_id: str | None = None) -> dict:
    battle = _resume(db, user_id)
    if battle:
        return {"ok": True, "battle": battle, "resumed": True}
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    if int(player["stamina"]) < 8:
        return {"ok": False, "reason": "Not enough stamina. You need 8."}
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    npcs = data.NPCS.get(series) or data.NPCS["dragonball"]
    limit = max(1, min(len(npcs), 1 + int(player["level"]) // 12))
    npc = next((item for item in npcs if item["id"] == npc_id), None) if npc_id else None
    if npc is None:
        npc = random.choice(npcs[:limit])
    db.spend(user_id, stamina=8)
    enemy = _enemy(npc["name"], game.enemy_from_npc(npc), level=npc["level"], art="npc", art_key=npc["id"])
    rewards = {"yens": npc["yens"], "exp": npc["exp"], "gems": npc["gems"]}
    drops = {}
    if npc.get("drop") and random.random() < 0.40:
        drops[npc["drop"]] = 1
    drops.update(_dragonball_drop(db, user_id, 0.025))
    meta = {"kind": "hunt", "series": series, "npc_id": npc["id"], "rewards": rewards, "drops": drops}
    return {"ok": True, "battle": _new_battle(db, user_id, "hunt", f"⚔️ Hunt — {npc['name']}", enemy, meta, f"A wild {npc['name']} appears!")}


def start_boss(db, user_id: int, series: str | None = None, boss_id: str | None = None) -> dict:
    battle = _resume(db, user_id)
    if battle:
        return {"ok": True, "battle": battle, "resumed": True}
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    if int(player["stamina"]) < 15:
        return {"ok": False, "reason": "Not enough stamina. You need 15."}
    if db.item_qty(user_id, "boss_key") < 1:
        return {"ok": False, "reason": "You need a Boss Key. Buy one with /shop."}
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    boss = _pick_boss(series, boss_id)
    if boss is None:
        return {"ok": False, "reason": "Unknown boss."}
    state = db.boss_state(user_id, boss)
    if state.get("status") == "defeated":
        db.reset_boss(user_id, boss["id"])
        state = db.boss_state(user_id, boss)
    db.spend(user_id, stamina=15)
    db.take_item(user_id, "boss_key", 1)
    scaled = game.enemy_from_boss(boss, 0.42)
    enemy = _enemy(boss["name"], scaled, level=boss["level"], art="boss", art_key=boss["id"])
    enemy["hp"] = max(1, int(state["hp"]))
    enemy["max_hp"] = max(1, int(state["max_hp"]))
    drops = {boss.get("drop", "shard_rare"): 2}
    if random.random() < 0.15:
        drops["awakening_stone"] = 1
    meta = {
        "kind": "boss", "series": series, "boss": boss, "persistent": "boss",
        "rewards": dict(boss.get("reward", {})), "drops": drops, "win_field": "boss_kills",
    }
    return {"ok": True, "battle": _new_battle(db, user_id, "boss", f"👹 Boss — {boss['name']}", enemy, meta, f"{boss['name']} blocks your path!")}


def start_elite(db, user_id: int, series: str | None = None) -> dict:
    battle = _resume(db, user_id)
    if battle:
        return {"ok": True, "battle": battle, "resumed": True}
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    if int(player["stamina"]) < 12:
        return {"ok": False, "reason": "Not enough stamina. You need 12."}
    if db.item_qty(user_id, "elite_key") < 1:
        return {"ok": False, "reason": "You need an Elite Key. Buy one with /shop."}
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    npcs = data.NPCS.get(series) or data.NPCS["dragonball"]
    npc = npcs[max(0, min(len(npcs) - 1, int(player["level"]) // 18))]
    elite = dict(npc)
    elite.update({
        "id": npc["id"] + "_elite", "name": "Elite " + npc["name"],
        "hp": int(npc["hp"] * 1.8), "atk": int(npc["atk"] * 1.35),
        "def": int(npc["def"] * 1.35), "spd": int(npc["spd"] * 1.2),
        "exp": int(npc["exp"] * 2.5), "yens": int(npc["yens"] * 2.5),
    })
    db.spend(user_id, stamina=12)
    db.take_item(user_id, "elite_key", 1)
    enemy = _enemy(elite["name"], game.enemy_from_npc(elite), level=elite["level"], art="boss", art_key=elite["id"])
    drops = {"shard_rare": 2, "forge_core": 1}
    if random.random() < 0.05:
        drops["awakening_stone"] = 1
    meta = {
        "kind": "elite", "series": series, "npc_id": elite["id"], "win_field": "boss_kills",
        "rewards": {"yens": elite["yens"], "exp": elite["exp"], "gems": 5, "crystals": 2}, "drops": drops,
    }
    return {"ok": True, "battle": _new_battle(db, user_id, "elite", f"💀 Elite — {elite['name']}", enemy, meta, f"Elite {npc['name']} challenges you!")}


def start_dungeon(db, user_id: int, series: str | None = None) -> dict:
    battle = _resume(db, user_id)
    if battle:
        return {"ok": True, "battle": battle, "resumed": True}
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
    enemy = _enemy(floor["name"], game.enemy_from_boss(floor, 0.70), level=floor["level"], art="boss", art_key=floor["id"])
    drops = {floor["drop"]: 2, "forge_core": 1}
    if random.random() < 0.20:
        drops["awakening_stone"] = 1
    meta = {
        "kind": "dungeon", "series": series, "floor": floor, "win_field": "boss_kills",
        "rewards": {"yens": floor["yens"], "exp": floor["exp"], "gems": floor["gems"], "crystals": floor["crystals"]},
        "drops": drops,
    }
    return {"ok": True, "battle": _new_battle(db, user_id, "dungeon", f"🏰 {floor['name']}", enemy, meta, f"You enter {floor['name']}.")}


def start_chapter(db, user_id: int, series: str | None = None, chapter: int | None = None) -> dict:
    battle = _resume(db, user_id)
    if battle:
        return {"ok": True, "battle": battle, "resumed": True}
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
        chapter_data = next((item for item in chapters if int(item["number"]) == int(chapter)), None)
        if chapter_data is None:
            return {"ok": False, "reason": "Unknown chapter."}
    number = int(chapter_data["number"])
    if number in cleared:
        return {"ok": False, "reason": "That chapter is already cleared."}
    if number > 1 and number - 1 not in cleared:
        return {"ok": False, "reason": f"Clear chapter {number - 1} first."}
    if not db.spend(user_id, stamina=15):
        return {"ok": False, "reason": "Need 15 stamina to fight this chapter."}
    enemy = _enemy(
        chapter_data["enemy"]["name"], game.enemy_from_npc(chapter_data["enemy"]),
        level=chapter_data["enemy"].get("level", 1), art="npc", art_key=chapter_data["enemy"].get("id", ""),
    )
    meta = {
        "kind": "chapter", "series": series, "chapter": chapter_data, "win_field": "boss_kills",
        "rewards": dict(chapter_data["rewards"]), "drops": {chapter_data["drop"]: 1},
    }
    return {"ok": True, "battle": _new_battle(db, user_id, "chapter", f"📖 Chapter {number} — {chapter_data['name']}", enemy, meta, chapter_data.get("intro") or "The story battle begins!")}


def start_summon(db, user_id: int, series: str | None = None, boss_id: str | None = None) -> dict:
    battle = _resume(db, user_id)
    if battle:
        return {"ok": True, "battle": battle, "resumed": True}
    db.refresh_stamina(user_id)
    player = db.require_player(user_id)
    series = series if series in data.SERIES else player.get("travel", "dragonball")
    pool = data.SUMMON_BOSSES_BY_SERIES.get(series, data.SUMMON_BOSSES)
    boss = next((item for item in data.SUMMON_BOSSES if item["id"] == boss_id), None) if boss_id else random.choice(pool)
    if boss is None:
        return {"ok": False, "reason": "Unknown summon boss."}
    scaled = dict(boss)
    scaled["hp"] = max(1, int(boss["hp"] * 0.18))
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
    enemy = _enemy(boss["name"], game.enemy_from_boss(scaled, 0.55), level=boss["level"], art="summon", art_key=boss["id"])
    enemy["hp"] = max(1, int(state["hp"]))
    enemy["max_hp"] = max(1, int(state["max_hp"]))
    meta = {
        "kind": "summon", "series": series, "boss": scaled, "persistent": "summon", "win_field": "boss_kills",
        "rewards": dict(boss.get("reward", {})), "drops": {boss.get("drop", "shard_epic"): 2}, "payment": payment,
    }
    return {"ok": True, "battle": _new_battle(db, user_id, "summon", f"🌌 Summon — {boss['name']}", enemy, meta, f"{boss['name']} answers your call!")}


def start_world(db, user_id: int) -> dict:
    battle = _resume(db, user_id)
    if battle:
        return {"ok": True, "battle": battle, "resumed": True}
    boss = db.world_boss_current()
    if not boss or not boss.get("boss"):
        return {"ok": False, "reason": "No world boss is active right now."}
    if int(boss.get("hp", 0)) <= 0:
        return {"ok": False, "reason": "The world boss is already defeated. Return tomorrow."}
    if db.item_qty(user_id, "raid_token") < 1:
        if not db.spend(user_id, stamina=25):
            return {"ok": False, "reason": "Need 1 Raid Token or 25 stamina."}
    else:
        db.take_item(user_id, "raid_token", 1)
    info = boss["boss"]
    enemy = _enemy(info["name"], game.enemy_from_boss(info, 0.12), level=info["level"], art="world", art_key=info["id"])
    enemy["hp"] = max(1, int(boss["hp"]))
    enemy["max_hp"] = max(1, int(boss["max_hp"]))
    meta = {"kind": "world", "series": info.get("series"), "shared": "world", "boss": info, "damage": 0}
    return {"ok": True, "battle": _new_battle(db, user_id, "world", f"🌍 World Boss — {info['name']}", enemy, meta, f"The world boss {info['name']} looms over the battlefield!")}


def start_clanraid(db, user_id: int) -> dict:
    battle = _resume(db, user_id)
    if battle:
        return {"ok": True, "battle": battle, "resumed": True}
    clan = db.clan(user_id)
    if clan is None:
        return {"ok": False, "reason": "Join a clan first."}
    raid_row = db.clan_raid_current(clan["id"])
    if raid_row is None:
        return {"ok": False, "reason": "Your clan has no active raid. The leader can start one."}
    if int(raid_row["hp"]) <= 0:
        return {"ok": False, "reason": "The clan raid boss is already defeated."}
    if db.item_qty(user_id, "raid_token") < 1:
        if not db.spend(user_id, stamina=20):
            return {"ok": False, "reason": "Need 1 Raid Token or 20 stamina."}
    else:
        db.take_item(user_id, "raid_token", 1)
    info = data.CLAN_RAID_BY_ID.get(raid_row["raid_id"], data.CLAN_RAIDS[0])
    boss = {"name": info["name"], "hp": info["hp"], "atk": info["atk"], "def": info["def"], "spd": info["spd"], "element": info["element"]}
    enemy = _enemy(info["name"], game.enemy_from_boss(boss, 0.16), level=info.get("level", 1), art="world", art_key=info["id"])
    enemy["hp"] = max(1, int(raid_row["hp"]))
    enemy["max_hp"] = max(1, int(raid_row["max_hp"]))
    meta = {"kind": "clanraid", "series": info.get("series"), "shared": "clanraid", "raid": info, "damage": 0}
    return {"ok": True, "battle": _new_battle(db, user_id, "clanraid", f"🏯 Clan Raid — {info['name']}", enemy, meta, f"Your clan strikes {info['name']}!")}


def start_duel(db, user_id: int, opponent_id: int, *, arena: bool = False) -> dict:
    battle = _resume(db, user_id)
    if battle:
        return {"ok": True, "battle": battle, "resumed": True}
    if int(user_id) == int(opponent_id):
        return {"ok": False, "reason": "You cannot duel yourself."}
    db.refresh_stamina(user_id)
    if not db.spend(user_id, stamina=15):
        return {"ok": False, "reason": "Need 15 stamina to duel."}
    opponent = db.require_player(opponent_id)
    if opponent.get("banned"):
        return {"ok": False, "reason": "That player is banned."}
    stats = game.effective_stats(db, opponent_id)
    name = opponent.get("first_name") or opponent.get("username") or "Opponent"
    enemy = _enemy(name, stats, level=int(opponent["level"]), art="character", art_key=opponent.get("equipped_char") or "")
    rating_change = random.randint(14, 25)
    meta = {
        "kind": "duel", "arena": arena, "opponent_id": int(opponent_id), "rating_change": rating_change,
        "win_field": "pvp_wins", "rewards": {"yens": 280, "exp": 180, "gems": 8},
        "loss_rewards": {"yens": 80, "exp": 45, "gems": 1},
    }
    title = f"🏟️ {'Arena' if arena else 'Duel'} — {name}"
    return {"ok": True, "battle": _new_battle(db, user_id, "duel", title, enemy, meta, f"{name} accepts your challenge!")}


def start_arena(db, user_id: int) -> dict:
    opponent = db.random_opponent(user_id)
    if opponent is None:
        return {"ok": False, "reason": "No arena opponents found yet."}
    return start_duel(db, user_id, int(opponent["user_id"]), arena=True)


def start(db, user_id: int, mode: str, **kwargs) -> dict:
    mode = (mode or "").lower()
    if mode == "hunt":
        return start_hunt(db, user_id, kwargs.get("series"), kwargs.get("npc_id"))
    if mode == "boss":
        return start_boss(db, user_id, kwargs.get("series"), kwargs.get("boss_id"))
    if mode == "elite":
        return start_elite(db, user_id, kwargs.get("series"))
    if mode == "dungeon":
        return start_dungeon(db, user_id, kwargs.get("series"))
    if mode == "chapter":
        return start_chapter(db, user_id, kwargs.get("series"), kwargs.get("chapter"))
    if mode == "summon":
        return start_summon(db, user_id, kwargs.get("series"), kwargs.get("boss_id"))
    if mode == "world":
        return start_world(db, user_id)
    if mode == "clanraid":
        return start_clanraid(db, user_id)
    if mode == "arena":
        return start_arena(db, user_id)
    if mode == "duel":
        return start_duel(db, user_id, int(kwargs["opponent_id"]))
    return {"ok": False, "reason": "Unknown battle mode."}


def _damage_enemy(db, user_id: int, battle: dict, damage: int) -> None:
    state = battle["state"]
    enemy = state["enemy"]
    meta = state["meta"]
    damage = max(0, int(damage))
    enemy["hp"] = max(0, int(enemy["hp"]) - damage)
    if meta.get("shared") == "world":
        result = db.record_world_damage(user_id, damage)
        if result.get("ok"):
            enemy["hp"] = int(result["hp"])
            enemy["max_hp"] = int(result["max_hp"])
            meta["shared_defeated"] = bool(result.get("defeated"))
        meta["damage"] = int(meta.get("damage", 0)) + damage
    elif meta.get("shared") == "clanraid":
        result = db.record_clan_raid_damage(user_id, damage)
        if result.get("ok"):
            enemy["hp"] = int(result["hp"])
            enemy["max_hp"] = int(result["max_hp"])
            meta["shared_defeated"] = bool(result.get("defeated"))
        meta["damage"] = int(meta.get("damage", 0)) + damage
    elif meta.get("persistent") == "boss":
        result = db.damage_boss(user_id, meta["boss"], damage)
        enemy["hp"] = int(result["hp"])
        enemy["max_hp"] = int(result["max_hp"])
    elif meta.get("persistent") == "summon":
        result = db.damage_summon(user_id, meta["boss"], damage)
        enemy["hp"] = int(result["hp"])
        enemy["max_hp"] = int(result["max_hp"])


def _heal_items(db, user_id: int) -> list[dict]:
    return [item for item in db.items(user_id) if item.get("kind") == "heal" and int(item.get("qty", 0)) > 0][:3]


def _grant(db, user_id: int, rewards: dict, drops: dict) -> None:
    if rewards:
        db.grant_rewards(user_id, rewards)
    for item_id, qty in (drops or {}).items():
        if qty > 0 and item_id in data.ITEMS:
            db.add_item(user_id, item_id, int(qty))


def _record(db, user_id: int, battle: dict, won: bool) -> None:
    state = battle["state"]
    meta = state["meta"]
    player = state["player"]
    win_field = meta.get("win_field", "wins")
    if win_field not in WIN_FIELDS:
        win_field = "wins"
    with db.conn() as c:
        c.execute(
            f"UPDATE players SET total_battles=total_battles+1, {win_field}={win_field}+?, losses=losses+?, "
            "current_hp=?, mp=? WHERE user_id=?",
            (1 if won else 0, 0 if won else 1, max(1, int(player["hp"])), max(0, int(player["mp"])), int(user_id)),
        )
    db.bump(user_id, "total_battles", 1)
    db.bump(user_id, "wins" if won else "losses", 1)
    db.battle_record(user_id, state["enemy"]["name"], "win" if won else "loss", int(meta.get("damage", 0)))
    if battle["mode"] == "hunt":
        if won:
            player_row = db.require_player(user_id)
            streak = int(player_row["npc_streak"]) + 1
            db.set_field(user_id, "npc_streak", streak)
            db.set_field(user_id, "best_streak", max(int(player_row["best_streak"]), streak))
            db.bump(user_id, "npc_streak", 1)
        else:
            db.set_field(user_id, "npc_streak", 0)
    if meta.get("kind") == "chapter" and won:
        chapter = meta["chapter"]
        db.clear_chapter(user_id, meta["series"], int(chapter["number"]))
        db.bump(user_id, "chapter", 1)
    if battle["mode"] == "duel":
        opponent_id = int(meta["opponent_id"])
        change = int(meta["rating_change"])
        if won:
            with db.conn() as c:
                c.execute("UPDATE players SET arena_rating=arena_rating+?, pvp_wins=pvp_wins+1 WHERE user_id=?", (change, int(user_id)))
                c.execute("UPDATE players SET arena_rating=MAX(0, arena_rating-?) WHERE user_id=?", (max(5, change // 2), opponent_id))
            db.duel_record(user_id, opponent_id, int(user_id), change)
        else:
            with db.conn() as c:
                c.execute("UPDATE players SET arena_rating=MAX(0, arena_rating-?) WHERE user_id=?", (change, int(user_id)))
                c.execute("UPDATE players SET arena_rating=arena_rating+? WHERE user_id=?", (max(3, change // 2), opponent_id))
            db.duel_record(user_id, opponent_id, opponent_id, -change)


def _finish(db, user_id: int, battle: dict, outcome: str) -> dict:
    state = battle["state"]
    meta = state["meta"]
    won = outcome == "victory"
    rewards = dict(meta.get("rewards") or {}) if won else dict(meta.get("loss_rewards") or {})
    drops = dict(meta.get("drops") or {}) if won else {}
    if outcome == "fled":
        rewards, drops = {}, {}
    kind = meta.get("kind")
    if won:
        if kind == "world":
            rewards = {"yens": max(80, int(meta.get("damage", 0)) * 2), "exp": max(60, int(meta.get("damage", 0)) // 3), "gems": 2}
            drops.update(_dragonball_drop(db, user_id, 0.10))
        elif kind == "clanraid":
            rewards = {"yens": max(100, int(meta.get("damage", 0)) * 2), "exp": max(80, int(meta.get("damage", 0)) // 3), "gems": 2}
        elif kind == "summon" and random.random() < 0.20:
            rewards["skill_points"] = 1
    else:
        if kind in ("hunt", "chapter", "elite", "dungeon", "boss", "summon"):
            rewards = {"exp": max(10, int((meta.get("rewards") or {}).get("exp", 30)) // 6)}
        elif kind in ("world", "clanraid"):
            rewards = {"exp": max(20, int(meta.get("damage", 0)) // 8)}
    if won and meta.get("persistent") == "boss":
        db.reset_boss(user_id, meta["boss"]["id"])
    _grant(db, user_id, rewards, drops)
    _record(db, user_id, battle, won)
    state["status"] = "finished"
    state["outcome"] = outcome
    state["rewards"] = rewards
    state["drops"] = drops
    restored = _player_snapshot(db, user_id)
    state["player"]["hp"] = int(restored["max_hp"])
    state["player"]["mp"] = int(restored["max_mp"])
    db.set_vitals(user_id, hp=restored["hp"], mp=restored["mp"])
    db.save_battle(battle)
    return battle


def _enemy_attack(db, user_id: int, battle: dict, rng: random.Random) -> None:
    state = battle["state"]
    player = state["player"]
    enemy = state["enemy"]
    if int(enemy["hp"]) <= 0 or int(player["hp"]) <= 0:
        return
    skill = game.choose_skill(enemy, int(state["turn"]), rng)
    if state.get("guard"):
        if rng.random() < 0.60:
            state["log"].append(f"💨 {player['name']} dodged {enemy['name']}'s attack!")
            state["guard"] = 0
            return
    damage, crit, dodged = game.attack_damage(enemy, player, skill, rng)
    if dodged:
        state["log"].append(f"💨 {player['name']} dodged {enemy['name']}'s attack!")
    else:
        if state.get("guard"):
            damage = max(1, int(damage * 0.40))
        player["hp"] = max(0, int(player["hp"]) - damage)
        label = f"✨ {skill['name']}" if skill else "⚔️ Enemy attack"
        crit_label = " **CRITICAL**" if crit else ""
        state["log"].append(f"{label}: {enemy['name']} dealt {damage:,} to {player['name']}.{crit_label}")
        state["ult"] = min(100, int(state.get("ult", 0)) + 15)
    state["guard"] = 0


def act(db, user_id: int, battle_id: str, action: str, payload: str | None = None) -> dict:
    battle = db.active_battle(user_id)
    if battle is None or battle.get("battle_id") != battle_id:
        return {"ok": False, "reason": "That battle is no longer active.", "stale": True}
    state = battle["state"]
    if state.get("status") != "active":
        return {"ok": True, "battle": battle, "finished": True}
    player = state["player"]
    enemy = state["enemy"]
    meta = state["meta"]
    rng = _rng()
    action = (action or "attack").lower()
    if action == "flee":
        chance = min(0.90, 0.20 + float(player["spd"]) / max(1.0, float(player["spd"]) + float(enemy["spd"])) * 0.70)
        if rng.random() < chance:
            state["log"].append("🏃 You escaped the battle.")
            return {"ok": True, "battle": _finish(db, user_id, battle, "fled"), "finished": True}
        state["log"].append("❌ Escape failed!")
        _enemy_attack(db, user_id, battle, rng)
    elif action == "potion":
        item = data.ITEMS.get(payload or "")
        if item is None or item.get("kind") != "heal":
            return {"ok": False, "reason": "That is not a healing item."}
        if not db.take_item(user_id, payload, 1):
            return {"ok": False, "reason": "You do not have that item."}
        heal = int(item.get("value", 0))
        before = int(player["hp"])
        player["hp"] = min(int(player["max_hp"]), before + heal)
        state["log"].append(f"{item['emoji']} Used {item['name']} and restored {player['hp'] - before:,} HP.")
        _enemy_attack(db, user_id, battle, rng)
    elif action in ("guard", "dodge"):
        state["guard"] = 1
        state["ult"] = min(100, int(state.get("ult", 0)) + 20)
        player["mp"] = min(int(player["max_mp"]), int(player["mp"]) + max(4, int(player["max_mp"]) * 0.06))
        state["log"].append("🛡️ You take a defensive stance.")
        _enemy_attack(db, user_id, battle, rng)
    elif action == "switch":
        team = state.get("team") or []
        if len(team) < 2:
            return {"ok": False, "reason": "You need at least two heroes on your team to switch."}
        index = (int(state.get("active_team", 0)) + 1) % len(team)
        target = dict(team[index])
        ratio = float(player["hp"]) / max(1, int(player["max_hp"]))
        player.update({
            "char_id": target.get("char_id", ""),
            "name": target["name"], "level": target["level"],
            "max_hp": target["max_hp"], "hp": max(1, int(target["max_hp"] * ratio)),
            "max_mp": target["max_mp"], "mp": min(int(target["max_mp"]), int(player["mp"])),
            "atk": target["atk"], "def": target["def"], "spd": target["spd"],
            "crit": target["crit"], "dodge": target["dodge"], "element": target["element"],
            "skills": target.get("skills", []),
        })
        state["active_team"] = index
        state["log"].append(f"🔄 Switched to {player['name']}!")
        _enemy_attack(db, user_id, battle, rng)
    elif action == "transform":
        if int(state.get("ult", 0)) < 50:
            return {"ok": False, "reason": "You need 50% ultimate gauge to transform."}
        state["ult"] = int(state.get("ult", 0)) - 50
        state["transform"] = 3
        state["log"].append("🌟 Transformation activated! Attack power increased for 3 turns.")
        _enemy_attack(db, user_id, battle, rng)
    else:
        skill = None
        cooldowns = player.setdefault("cooldowns", {})
        for skill_id in list(cooldowns):
            cooldowns[skill_id] = max(0, int(cooldowns[skill_id]) - 1)
        if action == "skill":
            try:
                index = int(payload or "0")
            except ValueError:
                index = 0
            skill_id = player["skills"][index] if 0 <= index < len(player["skills"]) else None
            skill = data.SKILLS.get(skill_id)
            if skill is None:
                return {"ok": False, "reason": "That skill is not equipped."}
            if int(cooldowns.get(skill_id, 0)) > 0:
                return {"ok": False, "reason": f"{skill['name']} is still on cooldown."}
            cost = _skill_cost(skill)
            if int(player["mp"]) < cost:
                return {"ok": False, "reason": f"Not enough MP. {skill['name']} costs {cost} MP."}
            player["mp"] = int(player["mp"]) - cost
            cooldowns[skill_id] = 2
            state["ult"] = min(100, int(state.get("ult", 0)) + 15)
        elif action == "ultimate":
            if int(state.get("ult", 0)) < 100:
                return {"ok": False, "reason": "Your ultimate gauge is not full."}
            skill = {"name": "Ultimate Burst", "power": 2.8, "type": "active"}
            state["ult"] = 0
            state["log"].append("🌟 Ultimate unleashed!")
        else:
            state["ult"] = min(100, int(state.get("ult", 0)) + 10)
        attacker = player
        if int(state.get("transform", 0)) > 0:
            attacker = dict(player)
            attacker["atk"] = int(float(player["atk"]) * 1.30)
        damage, crit, dodged = game.attack_damage(attacker, enemy, skill, rng)
        if dodged:
            state["log"].append(f"💨 {enemy['name']} dodged your attack!")
        else:
            _damage_enemy(db, user_id, battle, damage)
            label = f"✨ {skill['name']}" if skill else "⚔️ Basic attack"
            crit_label = " **CRITICAL**" if crit else ""
            state["log"].append(f"{label}: you dealt {damage:,} damage.{crit_label}")
        if int(enemy["hp"]) > 0:
            _enemy_attack(db, user_id, battle, rng)
    if action != "transform" and int(state.get("transform", 0)) > 0:
        state["transform"] = int(state["transform"]) - 1
    state["turn"] = int(state.get("turn", 1)) + 1
    if int(player["hp"]) <= 0:
        state["log"].append("💀 You were defeated!")
        return {"ok": True, "battle": _finish(db, user_id, battle, "defeat"), "finished": True}
    if int(enemy["hp"]) <= 0:
        state["log"].append(f"🏆 {enemy['name']} defeated!")
        return {"ok": True, "battle": _finish(db, user_id, battle, "victory"), "finished": True}
    db.set_vitals(user_id, hp=player["hp"], mp=player["mp"])
    db.save_battle(battle)
    return {"ok": True, "battle": battle, "finished": False}


def render(battle: dict) -> str:
    state = battle["state"]
    player = state["player"]
    enemy = state["enemy"]
    meta = state["meta"]
    lines = [f"<b>{ui.esc(battle['title'])}</b>", ""]
    lines.append(f"👤 <b>{ui.esc(player['name'])}</b> Lv.{player['level']}")
    lines.append(f"❤️ {ui.percent_bar(player['hp'], player['max_hp'], 12)} {ui.fmt(player['hp'])}/{ui.fmt(player['max_hp'])}")
    lines.append(f"🔵 {ui.percent_bar(player['mp'], player['max_mp'], 12)} {ui.fmt(player['mp'])}/{ui.fmt(player['max_mp'])} MP")
    lines.append(f"🌟 ULT {ui.percent_bar(state.get('ult', 0), 100, 10)} {state.get('ult', 0)}%")
    if int(state.get("transform", 0)) > 0:
        lines.append(f"🔥 Transformation: <b>{state['transform']}</b> turns left")
    team = state.get("team") or []
    if len(team) > 1:
        lines.append("👥 Team: " + " • ".join(
            f"{'▶️' if index == int(state.get('active_team', 0)) else ''}{ui.esc(member['name'])}"
            for index, member in enumerate(team)
        ))
    lines.append("")
    element = ELEMENT_EMOJI.get(enemy.get("element"), "🔮")
    lines.append(f"{element} <b>{ui.esc(enemy['name'])}</b> Lv.{enemy.get('level', 1)}")
    lines.append(f"❤️ {ui.percent_bar(enemy['hp'], enemy['max_hp'], 12)} {ui.fmt(enemy['hp'])}/{ui.fmt(enemy['max_hp'])}")
    if meta.get("shared"):
        lines.append("💥 Damage this fight: <b>{}</b>".format(ui.fmt(meta.get("damage", 0))))
    lines.append(f"🔄 Turn <b>{state.get('turn', 1)}</b>")
    lines.append("")
    for entry in state.get("log", [])[-8:]:
        lines.append(f"• {ui.esc(entry)}")
    if state.get("status") == "finished":
        lines.append("")
        outcome = state.get("outcome")
        if outcome == "victory":
            lines.append("🏆 <b>VICTORY!</b>")
        elif outcome == "defeat":
            lines.append("💀 <b>DEFEAT</b> — HP restored for your next battle.")
        else:
            lines.append("🏃 <b>ESCAPED</b>")
        rewards = state.get("rewards") or {}
        if rewards:
            lines.append("Rewards: " + " • ".join(f"{key} +{ui.fmt(value)}" for key, value in rewards.items() if value))
        drops = state.get("drops") or {}
        if drops:
            names = [f"{data.ITEMS.get(key, {}).get('emoji', '📦')} {data.ITEMS.get(key, {}).get('name', key)} x{qty}" for key, qty in drops.items()]
            lines.append("Loot: " + ", ".join(names))
    return "\n".join(lines)


def keyboard(battle: dict, potions: list[dict] | None = None):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    state = battle["state"]
    bid = battle["battle_id"]
    if state.get("status") == "finished":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Profile", callback_data="menu:profile"), InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")],
        ])
    player = state["player"]
    rows = [[
        InlineKeyboardButton("⚔️ Attack", callback_data=f"btl:a:{bid}"),
        InlineKeyboardButton("🛡️ Guard", callback_data=f"btl:g:{bid}"),
    ]]
    skill_buttons = []
    for index, skill_id in enumerate(player.get("skills", [])[:4]):
        skill = data.SKILLS.get(skill_id)
        if not skill:
            continue
        cooldown = int(player.get("cooldowns", {}).get(skill_id, 0))
        label = f"✨ {skill['name']}"
        if cooldown:
            label += f" ({cooldown})"
        else:
            label += f" ({_skill_cost(skill)} MP)"
        skill_buttons.append(InlineKeyboardButton(label, callback_data=f"btl:s:{index}:{bid}"))
    if skill_buttons:
        rows.append(skill_buttons[:2])
        if len(skill_buttons) > 2:
            rows.append(skill_buttons[2:4])
    extra = []
    if int(state.get("ult", 0)) >= 100:
        extra.append(InlineKeyboardButton("🌟 Ultimate", callback_data=f"btl:u:{bid}"))
    if int(state.get("ult", 0)) >= 50:
        extra.append(InlineKeyboardButton("🔥 Transform", callback_data=f"btl:t:{bid}"))
    if len(state.get("team") or []) > 1:
        extra.append(InlineKeyboardButton("🔄 Switch", callback_data=f"btl:x:{bid}"))
    if extra:
        rows.append(extra)
    potion_buttons = [
        InlineKeyboardButton(f"{item['emoji']} {item['name']} x{item['qty']}", callback_data=f"btl:p:{item['item_id']}:{bid}")
        for item in (potions or [])[:2]
    ]
    if potion_buttons:
        rows.append(potion_buttons)
    rows.append([InlineKeyboardButton("🏃 Flee", callback_data=f"btl:f:{bid}")])
    return InlineKeyboardMarkup(rows)


def potions(db, user_id: int) -> list[dict]:
    return _heal_items(db, user_id)
