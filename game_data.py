"""Game rules, formulas and derived stat calculations.

This module is intentionally free of database / Telegram imports so every
formula can be unit-tested in isolation.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from catalog import (
    CLASSES,
    ELEMENT_MULTIPLIER_STRONG,
    ELEMENT_MULTIPLIER_WEAK,
    ELEMENT_STRENGTHS,
    ELEMENTS,
    ITEMS,
    RACES,
    RARITY_ORDER,
    SKILLS,
)

GAME_NAME = "Aetherfall RPG"
GAME_TAGLINE = "Forge your legend across the shattered realms."
VERSION = "1.0.0"

MAX_LEVEL = 100
STAT_POINTS_PER_LEVEL = 3
STARTING_GOLD = 200
STARTING_GEMS = 3
STARTING_STAT_POINTS = 5

# Clan economy
CLAN_CREATE_COST = 1000
CLAN_MIN_LEVEL = 5
CLAN_MAX_MEMBERS_BASE = 10
CLAN_MAX_MEMBERS_PER_LEVEL = 2
CLAN_UPGRADE_BASE_COST = 2000
CLAN_UPGRADE_LEVEL_MULT = 1.6
CLAN_WAR_COST = 500
CLAN_TAG_MIN = 2
CLAN_TAG_MAX = 5
CLAN_NAME_MIN = 3
CLAN_NAME_MAX = 24

# Daily rewards
DAILY_BASE_GOLD = 100
DAILY_STREAK_BONUS = 25
DAILY_MAX_STREAK_BONUS_DAYS = 7
DAILY_GEM_INTERVAL = 7

# PvP
DUEL_MIN_LEVEL = 3
DUEL_GOLD_REWARD = 100

# Combat
MAX_COMBAT_ROUNDS = 40
CRIT_MULTIPLIER = 1.75
FLEE_BASE_CHANCE = 0.45

XP_CURVE_EXPONENT = 1.55
XP_CURVE_BASE = 100


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def today_utc() -> date:
    return utcnow().date()


# ---------------------------------------------------------------------------
# XP / levels
# ---------------------------------------------------------------------------

def xp_for_level(level: int) -> int:
    """XP required to advance *from* ``level`` to ``level + 1``."""
    level = max(1, int(level))
    return int(XP_CURVE_BASE * (level ** XP_CURVE_EXPONENT))


def cumulative_xp_for_level(level: int) -> int:
    return sum(xp_for_level(i) for i in range(1, max(1, level)))


def apply_xp(level: int, xp: int, amount: int) -> dict:
    """Apply XP and return the new level/xp plus number of level-ups.

    Pure function: does not touch the database.
    """
    level = max(1, int(level))
    xp = max(0, int(xp)) + max(0, int(amount))
    levels_gained = 0
    while level < MAX_LEVEL:
        needed = xp_for_level(level)
        if xp < needed:
            break
        xp -= needed
        level += 1
        levels_gained += 1
    if level >= MAX_LEVEL:
        xp = 0
    return {
        "level": level,
        "xp": xp,
        "levels_gained": levels_gained,
        "stat_points": levels_gained * STAT_POINTS_PER_LEVEL,
    }


def xp_progress(level: int, xp: int) -> tuple[int, int, float]:
    needed = xp_for_level(level)
    pct = min(1.0, xp / needed) if needed else 1.0
    return xp, needed, pct


# ---------------------------------------------------------------------------
# Derived stats
# ---------------------------------------------------------------------------

def item_stats_bonus(equipment_items: dict[str, dict] | list[dict] | None) -> dict:
    """Aggregate flat bonuses from a mapping or list of item definitions."""
    bonus = {"attack": 0, "defense": 0, "hp": 0, "mana": 0}
    bonus.update({k: 0 for k in ("strength", "agility", "intellect", "vitality", "luck")})
    if not equipment_items:
        return bonus
    items = equipment_items.values() if isinstance(equipment_items, dict) else equipment_items
    for item in items:
        if not item:
            continue
        for key in ("attack", "defense", "hp", "mana"):
            bonus[key] += int(item.get(key, 0) or 0)
        for key in ("strength", "agility", "intellect", "vitality", "luck"):
            bonus[key] += int((item.get("stats") or {}).get(key, 0) or 0)
    return bonus


def derive_stats(player: dict, equipment_items: dict[str, dict] | list[dict] | None = None) -> dict:
    """Calculate combat statistics from a player row and equipped items."""
    level = max(1, int(player.get("level") or 1))
    base = {
        "strength": int(player.get("strength") or 0),
        "agility": int(player.get("agility") or 0),
        "intellect": int(player.get("intellect") or 0),
        "vitality": int(player.get("vitality") or 0),
        "luck": int(player.get("luck") or 0),
    }
    bonus = item_stats_bonus(equipment_items)
    attrs = {key: base[key] + bonus[key] for key in base}

    race = RACES.get(player.get("race") or "", {})
    weapon_element = None
    if isinstance(equipment_items, dict):
        weapon = equipment_items.get("weapon")
        if weapon:
            weapon_element = weapon.get("element")

    max_hp = 60 + attrs["vitality"] * 12 + level * 10 + bonus["hp"]
    max_hp = int(max_hp * (1 + race.get("hp_bonus", 0)))
    max_mana = 30 + attrs["intellect"] * 6 + level * 3 + bonus["mana"]
    max_mana = int(max_mana * (1 + race.get("mana_bonus", 0)))

    attack = 8 + attrs["strength"] * 2 + attrs["intellect"] + level * 2 + bonus["attack"]
    attack = int(attack * (1 + race.get("attack_bonus", 0)))

    defense = 3 + attrs["vitality"] + level + bonus["defense"]
    defense = int(defense * (1 + race.get("defense_bonus", 0)))

    speed = (5 + attrs["agility"] * 2) * (1 + race.get("speed_bonus", 0))
    speed = int(speed)

    crit = 0.05 + attrs["luck"] * 0.01 + race.get("crit_bonus", 0)
    crit = round(min(0.60, crit), 4)

    return {
        "max_hp": max(1, max_hp),
        "max_mana": max(0, max_mana),
        "attack": max(1, attack),
        "defense": max(0, defense),
        "speed": max(1, speed),
        "crit_chance": crit,
        "attributes": attrs,
        "element": weapon_element or CLASSES.get(player.get("class") or "", {}).get("element", "physical"),
        "lifesteal": race.get("lifesteal", 0.0),
        "healing_bonus": race.get("healing_bonus", 0.0),
        "element_damage": race.get("element_damage", {}),
        "resist": race.get("resist", {}),
        "immune": tuple(race.get("immune", ())),
        "xp_bonus": race.get("xp_bonus", 0.0),
        "race": race,
    }


# ---------------------------------------------------------------------------
# Elements / damage helpers
# ---------------------------------------------------------------------------

def element_multiplier(attacker_element: str, defender_element: str) -> float:
    attacker_element = attacker_element or "physical"
    defender_element = defender_element or "physical"
    if defender_element in ELEMENT_STRENGTHS.get(attacker_element, ()):
        return ELEMENT_MULTIPLIER_STRONG
    if attacker_element in ELEMENT_STRENGTHS.get(defender_element, ()):
        return ELEMENT_MULTIPLIER_WEAK
    return 1.0


def element_label(element: str) -> str:
    data = ELEMENTS.get(element)
    if not data:
        return element.title()
    return f"{data['emoji']} {data['name']}"


# ---------------------------------------------------------------------------
# Loot
# ---------------------------------------------------------------------------

def roll_loot(loot: list[str] | tuple[str, ...] | None, rng: random.Random | None = None,
              drop_chance: float = 0.55) -> list[str]:
    """Roll a loot table, returning item ids (possibly empty, possibly duplicate)."""
    if not loot:
        return []
    rng = rng or random.Random()
    drops: list[str] = []
    for item_id in loot:
        if rng.random() <= drop_chance:
            drops.append(item_id)
    return drops


def weighted_rarity_item(pool: list[str], rng: random.Random | None = None) -> str | None:
    if not pool:
        return None
    rng = rng or random.Random()
    weights = []
    for item_id in pool:
        item = ITEMS.get(item_id, {})
        rarity = item.get("rarity", "common")
        weights.append(RARITY_ORDER.get(rarity, 0) + 1)
    return rng.choices(pool, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Daily rewards
# ---------------------------------------------------------------------------

def daily_reward(player: dict, today: date | None = None) -> dict:
    """Calculate a daily reward without claiming it.

    Returns dict with ``claimable``, ``streak``, ``gold``, ``gems``,
    ``xp`` and ``items``.
    """
    today = today or today_utc()
    last_raw = player.get("last_daily")
    streak = int(player.get("daily_streak") or 0)

    last_date = None
    if last_raw:
        try:
            last_date = date.fromisoformat(str(last_raw)[:10])
        except ValueError:
            last_date = None

    if last_date == today:
        return {
            "claimable": False,
            "streak": streak,
            "gold": 0,
            "gems": 0,
            "xp": 0,
            "items": {},
            "reason": "already_claimed",
        }

    if last_date == today - timedelta(days=1):
        new_streak = streak + 1
    else:
        new_streak = 1

    level = max(1, int(player.get("level") or 1))
    streak_bonus_days = min(new_streak, DAILY_MAX_STREAK_BONUS_DAYS)
    gold = DAILY_BASE_GOLD + level * 12 + streak_bonus_days * DAILY_STREAK_BONUS
    xp = 40 + level * 15 + streak_bonus_days * 10

    gems = 0
    items: dict[str, int] = {}
    if new_streak % DAILY_GEM_INTERVAL == 0:
        gems = 1 + new_streak // DAILY_GEM_INTERVAL
        items["large_potion"] = 1
    if new_streak >= 3:
        items["herb"] = 2
    if new_streak >= 5:
        items["crystal"] = 1

    return {
        "claimable": True,
        "streak": new_streak,
        "gold": gold,
        "gems": gems,
        "xp": xp,
        "items": items,
        "reason": "ok",
    }


# ---------------------------------------------------------------------------
# Clan helpers
# ---------------------------------------------------------------------------

def clan_upgrade_cost(level: int) -> int:
    return int(CLAN_UPGRADE_BASE_COST * (CLAN_UPGRADE_LEVEL_MULT ** max(0, level - 1)))


def clan_member_limit(level: int) -> int:
    return CLAN_MAX_MEMBERS_BASE + max(0, level - 1) * CLAN_MAX_MEMBERS_PER_LEVEL


def clan_power(members: list[dict]) -> int:
    total = 0
    for member in members:
        derives = derive_stats(member)
        total += derives["attack"] + derives["defense"] + derives["max_hp"] // 4 + derives["speed"]
    return total


def validate_clan_name(name: str) -> tuple[bool, str]:
    name = (name or "").strip()
    if len(name) < CLAN_NAME_MIN:
        return False, f"Clan name must be at least {CLAN_NAME_MIN} characters."
    if len(name) > CLAN_NAME_MAX:
        return False, f"Clan name must be at most {CLAN_NAME_MAX} characters."
    if not all(ch.isalnum() or ch in " _-'" for ch in name):
        return False, "Clan name may only contain letters, numbers, spaces, - _ and '."
    return True, ""


def validate_clan_tag(tag: str) -> tuple[bool, str]:
    tag = (tag or "").strip()
    if not tag.isalnum():
        return False, "Clan tag must be letters and numbers only."
    if not CLAN_TAG_MIN <= len(tag) <= CLAN_TAG_MAX:
        return False, f"Clan tag must be {CLAN_TAG_MIN}-{CLAN_TAG_MAX} characters."
    return True, ""


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def skill_unlocked(skill_id: str, level: int) -> bool:
    """Skills unlock at class start; higher-tier skills require levels."""
    order = list(SKILLS.keys())
    if skill_id not in order:
        return False
    idx = order.index(skill_id)
    tier = idx % 3
    required = 1 if tier == 0 else (8 if tier == 1 else 16)
    return level >= required


def can_equip(player: dict, item: dict) -> tuple[bool, str]:
    if not item:
        return False, "Unknown item."
    if item.get("type") not in ("weapon", "armor", "helmet", "boots", "ring", "amulet"):
        return False, "That item cannot be equipped."
    min_level = int(item.get("level", 1) or 1)
    if int(player.get("level") or 1) < min_level:
        return False, f"You need level {min_level} to equip this."
    return True, ""


def player_combat_skills(player: dict) -> list[str]:
    cls = CLASSES.get(player.get("class") or "", {})
    return [sid for sid in cls.get("skills", []) if sid in SKILLS and skill_unlocked(sid, int(player.get("level") or 1))]
