"""Core gameplay services: characters, XP, stats, shop, crafting, daily, quests."""

from __future__ import annotations

from typing import Any

from catalog import (
    CLASSES,
    CRAFTING_RECIPES,
    ITEMS,
    QUESTS,
    RACES,
    SLOTS,
)
from database import Database
from game_data import (
    DAILY_GEM_INTERVAL,
    MAX_LEVEL,
    STARTING_GEMS,
    STARTING_GOLD,
    STARTING_STAT_POINTS,
    STAT_POINTS_PER_LEVEL,
    apply_xp,
    daily_reward,
    derive_stats,
    today_utc,
    xp_for_level,
)


# ---------------------------------------------------------------------------
# Character helpers
# ---------------------------------------------------------------------------

async def get_equipped_items(db: Database, player_id: int) -> dict[str, dict]:
    equipment = await db.get_equipment(player_id)
    return {slot: ITEMS[item_id] for slot, item_id in equipment.items() if item_id in ITEMS}


async def load_player(db: Database, user_id: int) -> dict | None:
    player = await db.get_player(user_id)
    if player is None:
        return None
    equipment = await get_equipped_items(db, user_id)
    player["equipment"] = equipment
    player["derived"] = derive_stats(player, equipment)
    return player


def _base_stats(race_id: str, class_id: str) -> dict[str, int]:
    race = RACES[race_id]
    cls = CLASSES[class_id]
    return {
        key: int(cls["base"].get(key, 0)) + int(race["bonuses"].get(key, 0))
        for key in ("strength", "agility", "intellect", "vitality", "luck")
    }


async def create_character(
    db: Database, user_id: int, username: str | None, display_name: str,
    race_id: str, class_id: str,
) -> tuple[dict | None, str]:
    if race_id not in RACES:
        return None, "Unknown race."
    if class_id not in CLASSES:
        return None, "Unknown class."
    existing = await db.get_player(user_id)
    if existing is not None:
        return None, "You already have a character. Use /profile to view it."

    stats = _base_stats(race_id, class_id)
    preview = {
        "level": 1, "race": race_id, "class": class_id, "strength": stats["strength"],
        "agility": stats["agility"], "intellect": stats["intellect"],
        "vitality": stats["vitality"], "luck": stats["luck"],
    }
    derived = derive_stats(preview)
    player = await db.create_player(
        user_id=user_id,
        username=username,
        display_name=display_name,
        race=race_id,
        class_id=class_id,
        stats=stats,
        hp=derived["max_hp"],
        mana=derived["max_mana"],
        gold=STARTING_GOLD,
        gems=STARTING_GEMS,
        stat_points=STARTING_STAT_POINTS,
    )

    for item_id in CLASSES[class_id].get("starting_items", []):
        if item_id in ITEMS:
            await db.add_item(user_id, item_id, 1)

    for item_id in CLASSES[class_id].get("starting_items", []):
        item = ITEMS.get(item_id, {})
        if item.get("type") in ("weapon", "armor"):
            await equip_item(db, user_id, item_id, silent=True)

    loaded = await load_player(db, user_id)
    assert loaded is not None
    return loaded, ""


# ---------------------------------------------------------------------------
# XP / leveling
# ---------------------------------------------------------------------------

async def grant_xp(db: Database, player: dict, amount: int) -> dict:
    """Grant XP, handling level-ups and stat points. Mutates *player*."""
    amount = max(0, int(amount))
    result = apply_xp(int(player.get("level") or 1), int(player.get("xp") or 0), amount)
    levels_gained = result["levels_gained"]
    fields: dict[str, Any] = {"level": result["level"], "xp": result["xp"]}
    if levels_gained:
        fields["stat_points"] = int(player.get("stat_points") or 0) + levels_gained * STAT_POINTS_PER_LEVEL
    await db.update_player(int(player["user_id"]), **fields)
    player.update(fields)

    equipment = await get_equipped_items(db, int(player["user_id"]))
    derived = derive_stats(player, equipment)
    player["equipment"] = equipment
    player["derived"] = derived
    if levels_gained:
        player["hp"] = derived["max_hp"]
        player["mana"] = derived["max_mana"]
        await db.update_player(int(player["user_id"]), hp=player["hp"], mana=player["mana"])
    else:
        if int(player.get("hp") or 0) > derived["max_hp"]:
            player["hp"] = derived["max_hp"]
        if int(player.get("mana") or 0) > derived["max_mana"]:
            player["mana"] = derived["max_mana"]
        await db.update_player(int(player["user_id"]), hp=player["hp"], mana=player["mana"])
    result["player"] = player
    result["max_hp"] = derived["max_hp"]
    return result


async def refresh_player(db: Database, player: dict) -> dict:
    equipment = await get_equipped_items(db, int(player["user_id"]))
    derived = derive_stats(player, equipment)
    player["equipment"] = equipment
    player["derived"] = derived
    hp = min(int(player.get("hp") or derived["max_hp"]), derived["max_hp"])
    mana = min(int(player.get("mana") or derived["max_mana"]), derived["max_mana"])
    player["hp"], player["mana"] = hp, mana
    await db.update_player(int(player["user_id"]), hp=hp, mana=mana)
    return player


async def heal_player(db: Database, player: dict, hp: int = 0, mana: int = 0) -> dict:
    derived = player.get("derived") or derive_stats(player)
    new_hp = min(derived["max_hp"], int(player.get("hp") or 0) + max(0, hp))
    new_mana = min(derived["max_mana"], int(player.get("mana") or 0) + max(0, mana))
    player["hp"], player["mana"] = new_hp, new_mana
    await db.update_player(int(player["user_id"]), hp=new_hp, mana=new_mana)
    return player


async def allocate_stat(db: Database, player: dict, stat: str, points: int = 1) -> tuple[bool, str]:
    if stat not in ("strength", "agility", "intellect", "vitality", "luck"):
        return False, "Unknown stat."
    points = max(1, int(points))
    available = int(player.get("stat_points") or 0)
    if available < points:
        return False, f"You only have {available} stat point(s)."
    new_value = int(player.get(stat) or 0) + points
    await db.update_player(
        int(player["user_id"]), **{stat: new_value, "stat_points": available - points}
    )
    player[stat] = new_value
    player["stat_points"] = available - points
    await refresh_player(db, player)
    return True, f"+{points} {stat.title()}."


# ---------------------------------------------------------------------------
# Rewards
# ---------------------------------------------------------------------------

async def grant_rewards(
    db: Database, player: dict, gold: int = 0, gems: int = 0, xp: int = 0,
    items: dict[str, int] | None = None,
) -> dict:
    """Grant currency/XP/items and mutate the supplied player dict."""
    gold, gems, xp = int(gold), int(gems), int(xp)
    if gold:
        await db.add_gold(int(player["user_id"]), gold)
        player["gold"] = int(player.get("gold") or 0) + gold
    if gems:
        await db.add_gems(int(player["user_id"]), gems)
        player["gems"] = int(player.get("gems") or 0) + gems
    if items:
        for item_id, qty in items.items():
            if item_id in ITEMS and qty > 0:
                await db.add_item(int(player["user_id"]), item_id, int(qty))
    if xp:
        await grant_xp(db, player, xp)
    else:
        await refresh_player(db, player)
    return player


# ---------------------------------------------------------------------------
# Daily rewards
# ---------------------------------------------------------------------------

async def claim_daily(db: Database, player: dict) -> dict:
    reward = daily_reward(player, today_utc())
    if not reward["claimable"]:
        return {"ok": False, "reward": reward, "message": "Daily reward already claimed today."}

    updates = {
        "daily_streak": reward["streak"],
        "last_daily": today_utc().isoformat(),
    }
    await db.update_player(int(player["user_id"]), **updates)
    player.update(updates)
    await grant_rewards(
        db, player, gold=reward["gold"], gems=reward["gems"],
        xp=reward["xp"], items=reward["items"],
    )
    return {"ok": True, "reward": reward, "player": player}


# ---------------------------------------------------------------------------
# Shop / inventory
# ---------------------------------------------------------------------------

def sell_price(item_id: str) -> int:
    item = ITEMS.get(item_id, {})
    return max(1, int(item.get("price", 0) * 0.4))


async def buy_item(db: Database, player: dict, item_id: str, quantity: int = 1) -> tuple[bool, str]:
    item = ITEMS.get(item_id)
    quantity = max(1, int(quantity))
    if item is None or item.get("type") == "material" or not item.get("price"):
        return False, "That item is not for sale."
    total = int(item["price"]) * quantity
    if int(player.get("gold") or 0) < total:
        return False, f"You need {total} gold (you have {player.get('gold', 0)})."
    await db.add_gold(int(player["user_id"]), -total)
    await db.add_item(int(player["user_id"]), item_id, quantity)
    player["gold"] = int(player.get("gold") or 0) - total
    return True, f"Bought **{quantity}x {item['name']}** for {total} gold."


async def sell_item(db: Database, player: dict, item_id: str, quantity: int = 1) -> tuple[bool, str]:
    item = ITEMS.get(item_id)
    quantity = max(1, int(quantity))
    if item is None:
        return False, "Unknown item."
    if not await db.remove_item(int(player["user_id"]), item_id, quantity):
        return False, "You do not have that many."
    total = sell_price(item_id) * quantity
    await db.add_gold(int(player["user_id"]), total)
    player["gold"] = int(player.get("gold") or 0) + total
    return True, f"Sold **{quantity}x {item['name']}** for {total} gold."


async def equip_item(db: Database, user_id: int, item_id: str, silent: bool = False) -> tuple[bool, str]:
    item = ITEMS.get(item_id)
    if item is None:
        return False, "Unknown item."
    slot = item.get("slot")
    if item.get("type") not in ("weapon", "armor", "helmet", "boots", "ring", "amulet") or slot not in SLOTS:
        return False, "That item cannot be equipped."
    if not await db.has_item(user_id, item_id, 1):
        return False, "You do not own that item."
    previous = await db.set_equipment(user_id, slot, item_id)
    # Move inventory: consume new item, return old one to bag.
    await db.remove_item(user_id, item_id, 1)
    if previous:
        await db.add_item(user_id, previous, 1)
    if silent:
        return True, ""
    return True, f"Equipped **{item['name']}** in the {slot} slot."


async def unequip_item(db: Database, user_id: int, slot: str) -> tuple[bool, str]:
    previous = await db.clear_equipment_slot(user_id, slot)
    if not previous:
        return False, "Nothing is equipped in that slot."
    await db.add_item(user_id, previous, 1)
    return True, f"Unequipped **{ITEMS.get(previous, {}).get('name', previous)}**."


async def use_consumable(db: Database, player: dict, item_id: str) -> tuple[bool, str]:
    item = ITEMS.get(item_id, {})
    if item.get("type") != "consumable":
        return False, "That item cannot be used."
    if not await db.has_item(int(player["user_id"]), item_id, 1):
        return False, "You don't own that item."

    effect = item.get("effect") or {}
    derived = player.get("derived") or derive_stats(player)
    if "hp" in effect and int(player.get("hp") or 0) >= derived["max_hp"]:
        return False, "You are already at full HP."
    if "mana" in effect and int(player.get("mana") or 0) >= derived["max_mana"]:
        return False, "You are already at full mana."
    if "xp" in effect:
        pass

    if "damage" in effect and not any(
        key in effect for key in ("hp", "mana", "xp", "cleanse", "respec")
    ):
        return False, "This item can only be used in combat."

    await db.remove_item(int(player["user_id"]), item_id, 1)
    messages = []

    if effect.get("respec"):
        race = RACES.get(player.get("race") or "", {})
        cls = CLASSES.get(player.get("class") or "", {})
        base = {
            key: int(cls.get("base", {}).get(key, 0)) + int(race.get("bonuses", {}).get(key, 0))
            for key in ("strength", "agility", "intellect", "vitality", "luck")
        }
        refund = sum(max(0, int(player.get(k) or 0) - base[k]) for k in base)
        fields = dict(base)
        fields["stat_points"] = int(player.get("stat_points") or 0) + refund
        await db.update_player(int(player["user_id"]), **fields)
        player.update(fields)
        await refresh_player(db, player)
        return True, f"Respec complete. Refunded {refund} stat points."

    if "hp" in effect:
        await heal_player(db, player, hp=int(effect["hp"]))
        messages.append(f"+{effect['hp']} HP")
    if "mana" in effect:
        await heal_player(db, player, mana=int(effect["mana"]))
        messages.append(f"+{effect['mana']} mana")
    if effect.get("xp"):
        result = await grant_xp(db, player, int(effect["xp"]))
        messages.append(f"+{effect['xp']} XP")
        if result["levels_gained"]:
            messages.append(f"level up to {result['level']}")
    if effect.get("cleanse"):
        messages.append("debuffs cleansed")
    if not messages:
        messages.append("nothing happened")
    return True, f"Used **{item['name']}**: " + ", ".join(messages) + "."


# ---------------------------------------------------------------------------
# Crafting
# ---------------------------------------------------------------------------

async def can_craft(db: Database, player: dict, item_id: str) -> tuple[bool, str]:
    recipe = CRAFTING_RECIPES.get(item_id)
    if not recipe:
        return False, "No recipe for that item."
    if int(player.get("level") or 1) < int(recipe.get("level", 1)):
        return False, f"You need level {recipe['level']} to craft this."
    if int(player.get("gold") or 0) < int(recipe.get("gold", 0)):
        return False, f"You need {recipe['gold']} gold."
    for material, qty in recipe["materials"].items():
        owned = await db.get_item_quantity(int(player["user_id"]), material)
        if owned < qty:
            return False, f"Missing {qty - owned}x {ITEMS.get(material, {}).get('name', material)}."
    return True, ""


async def craft_item(db: Database, player: dict, item_id: str) -> tuple[bool, str]:
    ok, reason = await can_craft(db, player, item_id)
    if not ok:
        return False, reason
    recipe = CRAFTING_RECIPES[item_id]
    user_id = int(player["user_id"])

    async with db._lock:  # transaction: consume materials + gold atomically
        for material, qty in recipe["materials"].items():
            cur = await db.conn.execute(
                "SELECT quantity FROM inventory WHERE player_id = ? AND item_id = ?",
                (user_id, material),
            )
            row = await cur.fetchone()
            if row is None or row["quantity"] < qty:
                await db.conn.rollback()
                return False, "Missing materials."
            if row["quantity"] == qty:
                await db.conn.execute(
                    "DELETE FROM inventory WHERE player_id = ? AND item_id = ?",
                    (user_id, material),
                )
            else:
                await db.conn.execute(
                    "UPDATE inventory SET quantity = quantity - ? WHERE player_id = ? AND item_id = ?",
                    (qty, user_id, material),
                )
        await db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ?",
            (int(recipe.get("gold", 0)), user_id),
        )
        await db.conn.execute(
            """INSERT INTO inventory (player_id, item_id, quantity) VALUES (?, ?, 1)
               ON CONFLICT(player_id, item_id)
               DO UPDATE SET quantity = quantity + 1""",
            (user_id, item_id),
        )
        await db.conn.commit()

    player["gold"] = int(player.get("gold") or 0) - int(recipe.get("gold", 0))
    return True, f"Crafted **{ITEMS[item_id]['name']}**!"


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------

async def list_market_item(
    db: Database, player: dict, item_id: str, quantity: int, price: int,
) -> tuple[bool, str]:
    quantity = max(1, int(quantity))
    price = max(1, int(price))
    if item_id not in ITEMS:
        return False, "Unknown item."
    if price > 10_000_000:
        return False, "Price is too high."
    if not await db.remove_item(int(player["user_id"]), item_id, quantity):
        return False, "You do not own that many."
    await db.create_listing(int(player["user_id"]), item_id, quantity, price)
    return True, f"Listed **{quantity}x {ITEMS[item_id]['name']}** for {price} gold."


async def buy_market_listing(db: Database, player: dict, listing_id: int) -> tuple[bool, str]:
    result = await db.buy_listing(int(listing_id), int(player["user_id"]))
    if not result["ok"]:
        return False, result["reason"]
    listing = result["listing"]
    player["gold"] = int(player.get("gold") or 0) - int(listing["price"])
    return True, f"Bought **{listing['quantity']}x {ITEMS.get(listing['item_id'], {}).get('name', listing['item_id'])}** for {listing['price']} gold."


# ---------------------------------------------------------------------------
# Quests
# ---------------------------------------------------------------------------

def _stage_for(quest: dict, index: int) -> dict | None:
    stages = quest.get("stages") or []
    if 0 <= index < len(stages):
        return stages[index]
    return None


def _objective_matches(stage: dict, objective: str, target: str | None) -> bool:
    if stage.get("objective") != objective:
        return False
    required_target = stage.get("target")
    if required_target in (None, "any"):
        return True
    return target is not None and required_target == target


async def progress_quests(
    db: Database, player: dict, objective: str, target: str | None = None, amount: int = 1,
) -> list[str]:
    """Advance matching active quests. Returns human-readable notices."""
    notices: list[str] = []
    active = await db.get_active_quests(int(player["user_id"]))
    for row in active:
        quest = QUESTS.get(row["quest_id"])
        if not quest:
            continue
        stage_index = int(row["stage"])
        stage = _stage_for(quest, stage_index)
        if not stage or not _objective_matches(stage, objective, target):
            continue

        new_progress = int(row["progress"]) + max(1, int(amount))
        needed = int(stage.get("count", 1))
        if new_progress < needed:
            await db.update_quest_progress(
                int(player["user_id"]), row["quest_id"], stage_index, new_progress
            )
            continue

        reward = stage.get("reward", {})
        await grant_rewards(
            db, player,
            gold=int(reward.get("gold", 0)),
            xp=int(reward.get("xp", 0)),
            gems=int(reward.get("gems", 0)),
            items=reward.get("items") or {},
        )
        notices.append(
            f"✅ Quest stage complete: **{quest['name']}** — {stage.get('text', '')}"
        )

        next_index = stage_index + 1
        if next_index >= len(quest["stages"]):
            await db.complete_player_quest(int(player["user_id"]), row["quest_id"])
            notices.append(f"🏆 Quest completed: **{quest['name']}**!")
        else:
            await db.update_quest_progress(
                int(player["user_id"]), row["quest_id"], next_index, 0
            )
            notices.append(f"➡️ Next stage: {quest['stages'][next_index].get('text', '')}")
    return notices


async def start_quest(db: Database, player: dict, quest_id: str) -> tuple[bool, str]:
    quest = QUESTS.get(quest_id)
    if not quest:
        return False, "Unknown quest."
    if int(player.get("level") or 1) < int(quest.get("min_level", 1)):
        return False, f"You need level {quest['min_level']}."
    existing = await db.get_player_quest(int(player["user_id"]), quest_id)
    if existing and existing["active"]:
        return False, "Quest already active."
    if existing and not existing["active"]:
        return False, "Quest already completed."
    await db.start_quest(int(player["user_id"]), quest_id)
    return True, f"Started quest **{quest['name']}**."


async def quest_status(db: Database, player: dict, quest_id: str) -> dict | None:
    row = await db.get_player_quest(int(player["user_id"]), quest_id)
    if not row:
        return None
    quest = QUESTS.get(quest_id, {})
    stage = _stage_for(quest, int(row["stage"]))
    return {"row": row, "quest": quest, "stage": stage}


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def power_rating(player: dict) -> int:
    derived = player.get("derived") or derive_stats(player, player.get("equipment"))
    return int(
        derived["attack"] * 2 + derived["defense"] * 2
        + derived["max_hp"] / 4 + derived["speed"] + int(player.get("level") or 1) * 10
    )


async def level_up_test_hook(db: Database, player: dict, amount: int) -> dict:
    """Convenience wrapper used by tests/tools."""
    return await grant_xp(db, player, amount)
