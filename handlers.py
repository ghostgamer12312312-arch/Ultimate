"""Telegram command and inline-keyboard handlers."""

from __future__ import annotations

import asyncio
import html
import random
import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

import clans as clan_service
import config
import game
from backup import perform_backup
from catalog import (
    BOSSES,
    CLASSES,
    CRAFTING_RECIPES,
    ELEMENTS,
    EQUIPMENT_SLOT_NAMES,
    ITEMS,
    MONSTERS,
    QUESTS,
    RACES,
    RARITY_EMOJI,
    SKILLS,
    SLOTS,
)
from combat import (
    PvEBattle,
    PvPBattle,
    WorldBossRaid,
    fighter_from_player,
)
from game_data import (
    CLAN_CREATE_COST,
    CLAN_MIN_LEVEL,
    CLAN_UPGRADE_BASE_COST,
    DAILY_GEM_INTERVAL,
    DUEL_GOLD_REWARD,
    DUEL_MIN_LEVEL,
    GAME_NAME,
    MAX_LEVEL,
    STAT_POINTS_PER_LEVEL,
    VERSION,
    clan_member_limit,
    clan_power,
    clan_upgrade_cost,
    daily_reward,
    derive_stats,
    element_label,
    player_combat_skills,
    xp_for_level,
    xp_progress,
)

PAGE_SIZE = 8

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def esc(value) -> str:
    return html.escape(str(value), quote=False)


def bar(current: int | float, maximum: int | float, length: int = 10,
        filled: str = "█", empty: str = "░") -> str:
    maximum = max(1, float(maximum or 1))
    ratio = max(0.0, min(1.0, float(current) / maximum))
    count = int(round(ratio * length))
    return filled * count + empty * (length - count)


def fmt_int(value: int | float) -> str:
    return f"{int(value):,}"


def events_html(events: list[str]) -> str:
    rendered = []
    for event in events:
        line = esc(event)
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        rendered.append(line)
    return "\n".join(rendered)


def fmt_msg(text: str) -> str:
    """Escape a service message and convert **bold** markers to HTML."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text))


def _xp_line(player: dict) -> str:
    _, needed, pct = xp_progress(int(player["level"]), int(player["xp"]))
    return f"{bar(player['xp'], needed)} {int(pct * 100)}%  ({fmt_int(player['xp'])}/{fmt_int(needed)} XP)"


def _hp_line(player: dict) -> str:
    d = player.get("derived") or derive_stats(player)
    return f"❤️ {bar(player.get('hp', 0), d['max_hp'])} {player.get('hp', 0)}/{d['max_hp']}"


def _mana_line(player: dict) -> str:
    d = player.get("derived") or derive_stats(player)
    return f"💧 {bar(player.get('mana', 0), d['max_mana'])} {player.get('mana', 0)}/{d['max_mana']}"


def _equipment_text(player: dict) -> str:
    equipment = player.get("equipment") or {}
    lines = []
    for slot in SLOTS:
        value = equipment.get(slot)
        if isinstance(value, dict) and value.get("name"):
            item = value
        else:
            item = ITEMS.get(value) if isinstance(value, str) else None
        if item:
            lines.append(
                f"{EQUIPMENT_SLOT_NAMES[slot]}: "
                f"{RARITY_EMOJI.get(item.get('rarity'), '')} {esc(item['name'])}"
            )
    return "\n".join(lines) if lines else "Nothing equipped."


def _player_header(player: dict) -> str:
    race = RACES.get(player.get("race") or "", {})
    cls = CLASSES.get(player.get("class") or "", {})
    return (
        f"{race.get('emoji', '')} {esc(player.get('display_name') or 'Hero')} "
        f"— Lv.{player['level']} {cls.get('emoji', '')} {esc(cls.get('name', player.get('class')))}"
    )


def _profile_text(player: dict) -> str:
    d = player.get("derived") or derive_stats(player)
    clan = player.get("clan_name")
    lines = [
        f"<b>{_player_header(player)}</b>",
        f"{RACES.get(player.get('race'), {}).get('emoji', '')} {esc(RACES.get(player.get('race'), {}).get('name', player.get('race')))}"
        f" · {esc(RACES.get(player.get('race'), {}).get('passive', ''))}",
        "",
        f"⭐ Level {player['level']} / {MAX_LEVEL}",
        f"📊 {_xp_line(player)}",
        _hp_line(player),
        _mana_line(player),
        "",
        f"⚔️ Attack: <b>{d['attack']}</b>   🛡️ Defense: <b>{d['defense']}</b>",
        f"💨 Speed: <b>{d['speed']}</b>   🎯 Crit: <b>{d['crit_chance'] * 100:.1f}%</b>",
        f"🔥 Element: {element_label(d['element'])}",
        "",
        f"💪 STR {player['strength']}  🏃 AGI {player['agility']}  🧠 INT {player['intellect']}  ❤️ VIT {player['vitality']}  🍀 LUK {player['luck']}",
        f"🪙 Gold: <b>{fmt_int(player['gold'])}</b>   💎 Gems: <b>{player['gems']}</b>   🎁 Stat points: <b>{player['stat_points']}</b>",
    ]
    if clan:
        lines.append(f"🏰 Clan: <b>[{esc(clan['tag'])}] {esc(clan['name'])}</b>")
    lines.append("")
    lines.append(f"<b>Equipment</b>\n{_equipment_text(player)}")
    return "\n".join(lines)


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("⚔️ Hunt", callback_data="menu:hunt"),
         InlineKeyboardButton("🐉 World Boss", callback_data="menu:boss")],
        [InlineKeyboardButton("👤 Profile", callback_data="menu:profile"),
         InlineKeyboardButton("🎒 Inventory", callback_data="menu:inventory")],
        [InlineKeyboardButton("🛒 Shop", callback_data="menu:shop"),
         InlineKeyboardButton("🔨 Craft", callback_data="menu:craft")],
        [InlineKeyboardButton("🏰 Clan", callback_data="menu:clan"),
         InlineKeyboardButton("📜 Quests", callback_data="menu:quest")],
        [InlineKeyboardButton("🎁 Daily", callback_data="menu:daily"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="menu:leaderboard")],
        [InlineKeyboardButton("❓ Help", callback_data="menu:help")],
    ]
    return InlineKeyboardMarkup(rows)


def _back_button(target: str = "menu:main") -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ Back", callback_data=target)


def _register_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ Create Character", callback_data="reg:start")]])


# ---------------------------------------------------------------------------
# Sending / state helpers
# ---------------------------------------------------------------------------

async def _show(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str,
                keyboard: InlineKeyboardMarkup | None = None) -> None:
    query = update.callback_query
    kwargs = {"text": text, "parse_mode": ParseMode.HTML, "disable_web_page_preview": True}
    if keyboard is not None:
        kwargs["reply_markup"] = keyboard
    if query and query.message:
        try:
            await query.edit_message_text(**kwargs)
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
        try:
            await context.bot.send_message(chat_id=query.message.chat_id, **kwargs)
            return
        except TelegramError:
            pass
    if update.effective_message:
        await update.effective_message.reply_text(**kwargs)


async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str,
                 keyboard: InlineKeyboardMarkup | None = None) -> None:
    kwargs = {"text": text, "parse_mode": ParseMode.HTML, "disable_web_page_preview": True}
    if keyboard is not None:
        kwargs["reply_markup"] = keyboard
    await context.bot.send_message(chat_id=update.effective_chat.id, **kwargs)


async def _send_to(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str,
                   keyboard: InlineKeyboardMarkup | None = None) -> bool:
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
            reply_markup=keyboard, disable_web_page_preview=True,
        )
        return True
    except TelegramError:
        return False


async def _load(update: Update, context: ContextTypes.DEFAULT_TYPE,
                notify: bool = True) -> dict | None:
    user = update.effective_user
    if user is None:
        return None
    player = await game.load_player(context.bot_data["db"], user.id)
    if player is None and notify:
        await _show(
            update, context,
            "You don't have a character yet.\n\n"
            "Use /register to choose a race and class, then begin your adventure.",
            _register_keyboard(),
        )
    return player


def _db(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["db"]


# ---------------------------------------------------------------------------
# /start, /help, registration
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    player = await game.load_player(_db(context), user.id)
    if player is None:
        text = (
            f"<b>⚔️ Welcome to {GAME_NAME}!</b>\n\n"
            f"{esc(config.GAME_NAME)} is a persistent Telegram RPG. Choose a race and class, "
            "hunt monsters, raid world bosses, duel other players, build a clan and forge "
            "your legend.\n\n"
            "Use /register to create your character."
        )
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=_register_keyboard()
        )
        return
    text = (
        f"<b>⚔️ Welcome back, {esc(player.get('display_name') or user.first_name)}!</b>\n\n"
        f"⭐ Level {player['level']} · 🪙 {fmt_int(player['gold'])} gold · 💎 {player['gems']} gems\n"
        f"{_hp_line(player)}\n\n"
        "What will you do today?"
    )
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=_main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        f"<b>📖 {GAME_NAME} — Command Guide</b>\n\n"
        "<b>Character</b>\n"
        "/register — create your hero\n"
        "/profile /stats — stats, gear and upgrades\n"
        "/daily — claim daily streak rewards\n"
        "/quest — start and track quests\n\n"
        "<b>Combat</b>\n"
        "/hunt — turn-based PvE battles\n"
        "/boss — join a world-boss raid\n"
        "/duel @username — challenge a player\n\n"
        "<b>Items</b>\n"
        "/inventory — bag and equipment\n"
        "/equip <item> — equip gear\n"
        "/shop — browse the shop\n"
        "/buy <item> [qty] — buy from shop\n"
        "/sell <item> [qty] — sell for gold\n"
        "/craft — craft gear and potions\n"
        "/market [list|buy|cancel] — player marketplace\n\n"
        "<b>Social</b>\n"
        "/clan — clan menu and management\n"
        "/leaderboard — top players and clans\n\n"
        "<b>Admin</b>\n"
        "/myid — show your Telegram ID (for ADMIN_IDS)\n"
        "/backup — export JSON and SQLite backups\n"
        "/broadcast <text> — message every player\n\n"
        f"<i>v{VERSION} · {esc(config.GAME_NAME)}</i>"
    )
    await _show(update, context, text, InlineKeyboardMarkup([[_back_button()]]))


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await _show(
        update, context,
        f"🆔 Your Telegram user ID is <code>{user_id}</code>\n\n"
        "To enable admin commands, put this number in <code>ADMIN_IDS</code> in your .env file "
        "and restart the bot.",
        InlineKeyboardMarkup([[_back_button()]]),
    )


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await game.load_player(_db(context), update.effective_user.id)
    if player:
        await _show(update, context, "You already have a character!", _main_menu_keyboard())
        return
    context.user_data.pop("reg_race", None)
    await _show_race_select(update, context)


async def _show_race_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = []
    row = []
    for race_id, race in RACES.items():
        row.append(InlineKeyboardButton(
            f"{race['emoji']} {race['name']}", callback_data=f"reg:race:{race_id}"
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    lines = ["<b>🧬 Choose your race</b>\n"]
    for race in RACES.values():
        bonuses = ", ".join(f"+{v} {k[:3].upper()}" for k, v in race["bonuses"].items() if v)
        lines.append(
            f"{race['emoji']} <b>{esc(race['name'])}</b> — {esc(race['description'])}\n"
            f"   <i>{esc(bonuses)}</i> · Passive: {esc(race['passive'])}"
        )
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


async def _show_class_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    race_id = context.user_data.get("reg_race")
    if not race_id or race_id not in RACES:
        await _show_race_select(update, context)
        return
    race = RACES[race_id]
    rows = []
    row = []
    for class_id, cls in CLASSES.items():
        row.append(InlineKeyboardButton(
            f"{cls['emoji']} {cls['name']}", callback_data=f"reg:class:{class_id}"
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    lines = [
        f"<b>🧬 Race: {race['emoji']} {esc(race['name'])}</b>\n",
        "<b>⚔️ Choose your class</b>\n",
    ]
    for cls in CLASSES.values():
        skills = ", ".join(SKILLS[s]["name"] for s in cls["skills"] if s in SKILLS)
        lines.append(
            f"{cls['emoji']} <b>{esc(cls['name'])}</b> — {esc(cls['description'])}\n"
            f"   Skills: <i>{esc(skills)}</i>"
        )
    rows.append([InlineKeyboardButton("⬅️ Change race", callback_data="reg:back")])
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


async def _create_character(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            class_id: str) -> None:
    race_id = context.user_data.get("reg_race")
    if not race_id or class_id not in CLASSES:
        await _show_race_select(update, context)
        return
    user = update.effective_user
    display = user.full_name or user.first_name or f"Hero{user.id}"
    player, error = await game.create_character(
        _db(context), user.id, user.username, display, race_id, class_id
    )
    if error:
        await _show(update, context, f"⚠️ {esc(error)}", _main_menu_keyboard())
        return
    context.user_data.pop("reg_race", None)
    assert player is not None
    text = (
        f"<b>🎉 Character created!</b>\n\n{_profile_text(player)}\n\n"
        "Your journey begins. Use /hunt to find your first monster!"
    )
    await _show(update, context, text, _main_menu_keyboard())


# ---------------------------------------------------------------------------
# Profile / stats
# ---------------------------------------------------------------------------

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    clan = await _db(context).get_player_clan(player["user_id"])
    player["clan_name"] = clan["name"] if clan else None
    player["clan_tag"] = clan["tag"] if clan else None
    keyboard = _profile_keyboard(player)
    await _show(update, context, _profile_text(player), keyboard)


def _profile_keyboard(player: dict) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("➕ STR", callback_data="profile:alloc:strength"),
            InlineKeyboardButton("➕ AGI", callback_data="profile:alloc:agility"),
            InlineKeyboardButton("➕ INT", callback_data="profile:alloc:intellect"),
        ],
        [
            InlineKeyboardButton("➕ VIT", callback_data="profile:alloc:vitality"),
            InlineKeyboardButton("➕ LUK", callback_data="profile:alloc:luck"),
            InlineKeyboardButton("🔄 Refresh", callback_data="profile:refresh"),
        ],
        [
            InlineKeyboardButton("⚔️ Hunt", callback_data="menu:hunt"),
            InlineKeyboardButton("🎒 Inventory", callback_data="menu:inventory"),
            _back_button(),
        ],
    ]
    return InlineKeyboardMarkup(rows)


async def _allocate(update: Update, context: ContextTypes.DEFAULT_TYPE, stat: str) -> None:
    player = await game.load_player(_db(context), update.effective_user.id)
    if not player:
        return
    ok, message = await game.allocate_stat(_db(context), player, stat, 1)
    player = await game.load_player(_db(context), update.effective_user.id)
    clan = await _db(context).get_player_clan(player["user_id"])
    player["clan_name"] = clan["name"] if clan else None
    player["clan_tag"] = clan["tag"] if clan else None
    text = _profile_text(player)
    if not ok:
        text = f"⚠️ {fmt_msg(message)}\n\n{text}"
    await _show(update, context, text, _profile_keyboard(player))


# ---------------------------------------------------------------------------
# Hunting (PvE)
# ---------------------------------------------------------------------------

def _eligible_monsters(player: dict) -> list[str]:
    level = int(player.get("level") or 1)
    pool = [mid for mid, m in MONSTERS.items() if int(m["level"]) <= level + 4]
    pool.sort(key=lambda mid: MONSTERS[mid]["level"])
    if not pool:
        pool = ["forest_slime"]
    return pool[-8:]


async def hunt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    await _show_hunt_menu(update, context, player)


async def _show_hunt_menu(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          player: dict) -> None:
    rows = []
    lines = ["<b>⚔️ Hunting Grounds</b>\n", "Choose your prey. Victory grants XP, gold and loot.\n"]
    for monster_id in _eligible_monsters(player):
        monster = MONSTERS[monster_id]
        locked = int(monster["level"]) > int(player["level"]) + 2
        tag = " ⚠️" if locked else ""
        lines.append(
            f"{monster['emoji']} <b>{esc(monster['name'])}</b> (Lv.{monster['level']}){tag}\n"
            f"   HP {monster['hp']} · ATK {monster['attack']} · DEF {monster['defense']} · "
            f"XP {monster['xp']} · 🪙 {monster['gold']}"
        )
        rows.append([InlineKeyboardButton(
            f"{monster['emoji']} {monster['name']} (Lv.{monster['level']})",
            callback_data=f"hunt:start:{monster_id}",
        )])
    rows.append([_back_button()])
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


def _battle_text(battle: PvEBattle, events: list[str] | None = None) -> str:
    player, monster = battle.player, battle.monster
    lines = [
        f"<b>⚔️ Battle vs {esc(monster.name)}</b>",
        f"Round {battle.round}",
        "",
        f"👹 {esc(monster.name)}  Lv.{monster.level}",
        f"❤️ {bar(monster.hp, monster.max_hp)} {monster.hp}/{monster.max_hp}",
        "",
        f"🧑 {esc(player.name)}  Lv.{player.level}",
        f"❤️ {bar(player.hp, player.max_hp)} {player.hp}/{player.max_hp}",
        f"💧 {bar(player.mana, player.max_mana)} {player.mana}/{player.max_mana}",
        f"⚔️ ATK {int(player.effective_attack)}  🛡️ DEF {int(player.effective_defense)}  💨 SPD {int(player.effective_speed)}",
    ]
    if events:
        lines += ["", "<b>Combat log</b>", events_html(events[-8:])]
    return "\n".join(lines)


def _battle_keyboard(battle: PvEBattle) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚔️ Attack", callback_data="battle:attack"),
            InlineKeyboardButton("✨ Skill", callback_data="battle:skillmenu"),
        ],
        [
            InlineKeyboardButton("🧪 Heal", callback_data="battle:heal"),
            InlineKeyboardButton("🏃 Flee", callback_data="battle:flee"),
        ],
    ])


async def _start_hunt(update: Update, context: ContextTypes.DEFAULT_TYPE, monster_id: str) -> None:
    player = await _load(update, context)
    if not player:
        return
    if monster_id not in MONSTERS:
        await _show(update, context, "Unknown monster.", _main_menu_keyboard())
        return
    uid = int(player["user_id"])
    hunts = context.bot_data.setdefault("hunts", {})
    if uid in hunts:
        await _show(update, context, "You are already in a battle. Finish it first!", _battle_keyboard(hunts[uid]))
        return
    battle = PvEBattle(monster_id, fighter_from_player(player), rng=random.Random())
    hunts[uid] = battle
    await _show(update, context, _battle_text(battle), _battle_keyboard(battle))


async def _battle_action(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         action: str, arg: str | None = None) -> None:
    player = await game.load_player(_db(context), update.effective_user.id)
    if not player:
        return
    uid = int(player["user_id"])
    hunts = context.bot_data.setdefault("hunts", {})
    battle = hunts.get(uid)
    if not battle:
        await _show(update, context, "No active battle. Use /hunt to find a monster.", _main_menu_keyboard())
        return

    if action == "skillmenu":
        rows = []
        for skill_id in battle.player.skills:
            skill = SKILLS[skill_id]
            cd = battle.player.cooldowns.get(skill_id, 0)
            status = f" (CD {cd})" if cd else f" ({skill['mana']} MP)"
            rows.append([InlineKeyboardButton(
                f"{skill['name']}{status}", callback_data=f"battle:skill:{skill_id}"
            )])
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="battle:back")])
        await _show(update, context, "<b>✨ Choose a skill</b>", InlineKeyboardMarkup(rows))
        return

    if action == "back":
        await _show(update, context, _battle_text(battle), _battle_keyboard(battle))
        return

    events: list[str] = []
    if action == "attack":
        events = battle.player_attack()
    elif action == "skill" and arg:
        events = battle.player_skill(arg)
    elif action == "heal":
        potion, heal_amount = await _consume_heal_potion(context, uid, battle.player.hp, battle.player.max_hp)
        if potion == "__full__":
            events = ["You are already at full HP."]
        elif potion is None:
            events = ["You have no healing potions!"]
        else:
            events = battle.player_heal(heal_amount)
    elif action == "flee":
        events = battle.player_flee()
    else:
        events = ["Unknown action."]

    await _db(context).update_player(
        uid, hp=max(0, battle.player.hp), mana=max(0, battle.player.mana)
    )

    if battle.finished:
        del hunts[uid]
        await _finish_hunt(update, context, uid, battle, events)
        return

    await _show(update, context, _battle_text(battle, events), _battle_keyboard(battle))


async def _consume_heal_potion(context: ContextTypes.DEFAULT_TYPE, uid: int,
                               current_hp: int, max_hp: int) -> tuple[str | None, int]:
    db = _db(context)
    if current_hp >= max_hp:
        return "__full__", 0
    missing = max_hp - current_hp
    for item_id in ("large_potion", "small_potion", "elixir"):
        if await db.has_item(uid, item_id, 1):
            effect = ITEMS[item_id].get("effect", {})
            amount = int(effect.get("hp", 0))
            if item_id == "elixir" and missing < 100:
                continue
            await db.remove_item(uid, item_id, 1)
            return item_id, amount
    return None, 0


async def _finish_hunt(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int,
                       battle: PvEBattle, events: list[str]) -> None:
    db = _db(context)
    player = await game.load_player(db, uid)
    if not player:
        return
    lines = [f"<b>{'🏆 Victory!' if battle.result == 'win' else '💀 Defeat' if battle.result == 'lose' else '🏃 Escaped'}</b>"]
    player_hp = max(1, battle.player.hp) if battle.result == "lose" else max(1, battle.player.hp)
    await db.update_player(uid, hp=player_hp, mana=max(0, battle.player.mana))
    player = await game.load_player(db, uid)

    if battle.result == "win" and battle.rewards:
        rewards = battle.rewards
        lines.append(
            f"\nSlain: {esc(battle.monster.name)}\n"
            f"+{rewards['xp']} XP · +{rewards['gold']} gold"
        )
        drops = rewards.get("items") or []
        await game.grant_rewards(
            db, player, gold=rewards["gold"], xp=rewards["xp"],
            items={item_id: 1 for item_id in drops},
        )
        if drops:
            lines.append("Loot: " + ", ".join(
                f"{RARITY_EMOJI.get(ITEMS[i].get('rarity'), '')} {esc(ITEMS[i]['name'])}" for i in drops
            ))
        notices = await game.progress_quests(
            db, player, "kill", target=battle.monster_id, amount=1
        )
        if notices:
            lines.append("\n" + "\n".join(fmt_msg(n) for n in notices))
    elif battle.result == "lose":
        loss = min(int(player["gold"]), max(10, int(player["gold"]) * 0.10))
        if loss:
            await db.add_gold(uid, -int(loss))
            lines.append(f"\nYou lost {int(loss)} gold and barely escaped with your life.")
        await db.update_player(uid, hp=1)
    elif battle.result == "flee":
        lines.append("\nYou escaped with your life.")

    player = await game.load_player(db, uid)
    lines += [
        "",
        _hp_line(player),
        f"📊 {_xp_line(player)}",
        f"🪙 {fmt_int(player['gold'])} gold",
    ]
    if events:
        lines += ["", "<b>Last round</b>", events_html(events[-6:])]
    await _show(
        update, context, "\n".join(lines),
        InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ Hunt again", callback_data="menu:hunt"),
             InlineKeyboardButton("👤 Profile", callback_data="menu:profile")],
            [_back_button()],
        ]),
    )


# ---------------------------------------------------------------------------
# World bosses
# ---------------------------------------------------------------------------

async def boss_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    rows = []
    lines = ["<b>🐉 World Boss Raids</b>\n", "Join forces with other players to bring down colossal foes.\n"]
    for boss_id, boss in BOSSES.items():
        locked = int(player["level"]) < int(boss.get("min_level", 1))
        lines.append(
            f"{boss['emoji']} <b>{esc(boss['name'])}</b> (Lv.{boss['level']})"
            f"{' 🔒' if locked else ''}\n"
            f"   HP {fmt_int(boss['hp'])} · XP {fmt_int(boss['xp'])} · 🪙 {fmt_int(boss['gold'])} · 💎 {boss['gems']}\n"
            f"   <i>{esc(boss['description'])}</i>"
        )
        if not locked:
            rows.append([InlineKeyboardButton(
                f"{boss['emoji']} {boss['name']}", callback_data=f"boss:join:{boss_id}"
            )])
    if not rows:
        lines.append("\nLevel up to unlock your first world boss.")
    rows.append([_back_button()])
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


def _raid_text(raid: WorldBossRaid, uid: int | None = None) -> str:
    boss = raid.boss
    lines = [
        f"<b>🌍 World Boss: {esc(boss.name)}</b>",
        f"Round {raid.round} · Participants: {len(raid.participants)}",
        "",
        f"❤️ {bar(boss.hp, boss.max_hp, 14)} {fmt_int(boss.hp)}/{fmt_int(boss.max_hp)}",
        f"⚔️ ATK {boss.attack} · 🛡️ DEF {boss.defense} · {element_label(boss.element)}",
        "",
    ]
    if uid is not None and uid in raid.participants:
        fighter = raid.participants[uid]
        lines += [
            f"<b>Your fighter</b>",
            f"❤️ {bar(fighter.hp, fighter.max_hp)} {fighter.hp}/{fighter.max_hp}",
            f"💧 {bar(fighter.mana, max(1, fighter.max_mana))} {fighter.mana}/{fighter.max_mana}",
            f"Damage dealt: <b>{fmt_int(raid.contributions.get(uid, 0))}</b>",
            "",
        ]
    lines.append("<b>Top contributors</b>")
    ranking = raid.leaderboard(5)
    if ranking:
        for idx, (contributor_id, damage) in enumerate(ranking, 1):
            fighter = raid.participants.get(contributor_id)
            name = fighter.name if fighter else f"Player {contributor_id}"
            lines.append(f"{idx}. {esc(name)} — {fmt_int(damage)} dmg")
    else:
        lines.append("No damage dealt yet.")
    return "\n".join(lines)


def _raid_keyboard(boss_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚔️ Attack", callback_data=f"raid:attack:{boss_id}"),
            InlineKeyboardButton("✨ Skill", callback_data=f"raid:skill:{boss_id}"),
        ],
        [
            InlineKeyboardButton("🧪 Heal", callback_data=f"raid:heal:{boss_id}"),
            InlineKeyboardButton("🏃 Flee", callback_data=f"raid:flee:{boss_id}"),
        ],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"raid:refresh:{boss_id}")],
        [_back_button("menu:boss")],
    ])


async def _join_boss(update: Update, context: ContextTypes.DEFAULT_TYPE, boss_id: str) -> None:
    player = await _load(update, context)
    if not player:
        return
    if boss_id not in BOSSES:
        await _show(update, context, "Unknown world boss.", _main_menu_keyboard())
        return
    raids = context.bot_data.setdefault("raids", {})
    raid = raids.get(boss_id)
    if raid is None or raid.finished:
        raid = WorldBossRaid(boss_id, rng=random.Random())
        raids[boss_id] = raid
    ok, message = raid.join(player)
    if not ok:
        await _show(update, context, f"⚠️ {fmt_msg(message)}", _main_menu_keyboard())
        return
    await _show(update, context, _raid_text(raid, int(player["user_id"])), _raid_keyboard(boss_id))


async def _raid_action(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       action: str, boss_id: str) -> None:
    player = await game.load_player(_db(context), update.effective_user.id)
    if not player:
        return
    raids = context.bot_data.setdefault("raids", {})
    raid = raids.get(boss_id)
    if raid is None or raid.finished:
        if raid and raid.finished:
            await _show(update, context, "This raid has already ended.", _main_menu_keyboard())
        else:
            await _join_boss(update, context, boss_id)
        return

    uid = int(player["user_id"])
    if uid not in raid.participants:
        joined, join_message = raid.join(player)
        if not joined:
            await _show(update, context, f"⚠️ {esc(join_message)}", _main_menu_keyboard())
            return
    if action == "refresh":
        await _show(update, context, _raid_text(raid, uid), _raid_keyboard(boss_id))
        return
    if action == "flee":
        raid.participants.pop(uid, None)
        raid.contributions.pop(uid, None)
        await _show(
            update, context,
            "🏃 You retreat from the world boss. Your contribution is lost.",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🐉 Boss list", callback_data="menu:boss")],
                [_back_button()],
            ]),
        )
        return

    if action == "heal":
        potion, amount = await _consume_heal_potion(
            context, uid,
            raid.participants.get(uid).hp if uid in raid.participants else 0,
            raid.participants.get(uid).max_hp if uid in raid.participants else 1,
        )
        if potion == "__full__":
            await _show(update, context, "You are already at full HP.", _raid_keyboard(boss_id))
            return
        if potion is None:
            await _show(update, context, "You have no usable healing potions.", _raid_keyboard(boss_id))
            return
        events = raid.attack(player, heal_amount=amount)
    elif action == "skill":
        fighter = raid.participants.get(uid)
        skill_id = None
        if fighter:
            for candidate in fighter.skills:
                ready, _ = fighter.skill_ready(candidate)
                if ready and SKILLS[candidate].get("type") != "heal":
                    skill_id = candidate
                    break
        if not skill_id:
            await _show(update, context, "No offensive skill is ready.", _raid_keyboard(boss_id))
            return
        events = raid.attack(player, skill_id=skill_id)
    else:
        events = raid.attack(player)

    fighter = raid.participants.get(uid)
    if fighter:
        await _db(context).update_player(
            uid, hp=max(0, fighter.hp), mana=max(0, fighter.mana)
        )

    if raid.finished:
        await _finish_raid(update, context, boss_id, raid, events)
        return

    text = _raid_text(raid, uid) + "\n\n<b>Combat log</b>\n" + events_html(events[-8:])
    await _show(update, context, text, _raid_keyboard(boss_id))


async def _finish_raid(update: Update, context: ContextTypes.DEFAULT_TYPE, boss_id: str,
                       raid: WorldBossRaid, events: list[str]) -> None:
    db = _db(context)
    raids = context.bot_data.setdefault("raids", {})
    raids.pop(boss_id, None)
    boss = raid.boss_data
    lines = []
    if raid.winner:
        lines.append(f"<b>🏆 {esc(boss['name'])} defeated!</b>")
    else:
        lines.append(f"<b>💨 The raid against {esc(boss['name'])} failed.</b>")
    lines.append("")

    for participant_id, fighter in raid.participants.items():
        await db.update_player(participant_id, hp=max(1, fighter.hp), mana=max(0, fighter.mana))
        reward = raid.rewards.get(participant_id)
        if not reward:
            continue
        member = await game.load_player(db, participant_id)
        if not member:
            continue
        await game.grant_rewards(
            db, member, gold=reward["gold"], gems=reward["gems"], xp=reward["xp"],
            items={item_id: 1 for item_id in reward["items"]},
        )
        if raid.winner:
            await db.increment_boss_kills(participant_id, 1)
            notices = await game.progress_quests(
                db, member, "boss", target=boss_id, amount=1
            )
        else:
            notices = []
        loot_names = ", ".join(
            ITEMS[i]["name"] for i in reward["items"] if i in ITEMS
        ) or "—"
        message = (
            f"<b>🐉 Raid result: {esc(boss['name'])}</b>\n"
            f"Rank #{reward['rank']} · {fmt_int(reward['damage'])} damage "
            f"({reward['share'] * 100:.1f}%)\n"
            f"+{fmt_int(reward['xp'])} XP · +{fmt_int(reward['gold'])} gold"
            + (f" · +{reward['gems']} gems" if reward["gems"] else "")
            + f"\nLoot: {esc(loot_names)}"
        )
        if notices:
            message += "\n\n" + "\n".join(fmt_msg(n) for n in notices)
        await _send_to(context, participant_id, message)

    lines.append(f"Total damage: {fmt_int(raid.total_contribution())}")
    for idx, (participant_id, damage) in enumerate(raid.leaderboard(5), 1):
        fighter = raid.participants.get(participant_id)
        name = fighter.name if fighter else str(participant_id)
        lines.append(f"{idx}. {esc(name)} — {fmt_int(damage)} dmg")
    if events:
        lines += ["", "<b>Final blows</b>", events_html(events[-5:])]
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup([
        [InlineKeyboardButton("🐉 Boss list", callback_data="menu:boss"),
         InlineKeyboardButton("👤 Profile", callback_data="menu:profile")],
        [_back_button()],
    ]))


# ---------------------------------------------------------------------------
# PvP duels
# ---------------------------------------------------------------------------

async def duel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    if int(player["level"]) < DUEL_MIN_LEVEL:
        await _show(update, context, f"You need level {DUEL_MIN_LEVEL} to duel.", _main_menu_keyboard())
        return

    target = None
    if context.args:
        target = await _db(context).get_player_by_username(context.args[0])
    elif update.message and update.message.reply_to_message:
        replied = update.message.reply_to_message.from_user
        if replied and not replied.is_bot:
            target = await _db(context).get_player(replied.id)
    if target is None:
        await _show(
            update, context,
            "Usage: <code>/duel @username</code> (or reply to a registered player's message).",
            _main_menu_keyboard(),
        )
        return
    if int(target["user_id"]) == int(player["user_id"]):
        await _show(update, context, "You cannot duel yourself.", _main_menu_keyboard())
        return
    if int(target["level"]) < DUEL_MIN_LEVEL:
        await _show(update, context, f"{esc(target['display_name'])} is below level {DUEL_MIN_LEVEL}.", _main_menu_keyboard())
        return

    requests = context.bot_data.setdefault("duel_requests", {})
    requests[int(target["user_id"])] = int(player["user_id"])
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚔️ Accept", callback_data=f"pvp:accept:{player['user_id']}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"pvp:decline:{player['user_id']}"),
    ]])
    sent = await _send_to(
        context, int(target["user_id"]),
        f"<b>⚔️ Duel challenge!</b>\n\n{esc(player['display_name'])} (Lv.{player['level']}) "
        f"challenges you to a duel!",
        keyboard,
    )
    if sent:
        await _show(update, context, f"Challenge sent to <b>{esc(target['display_name'])}</b>.", _main_menu_keyboard())
    else:
        await _show(update, context, "Could not message that player. They must start the bot first.", _main_menu_keyboard())


def _pvp_key(a: int, b: int) -> str:
    return f"{min(int(a), int(b))}_{max(int(a), int(b))}"


def _pvp_view(battle: PvPBattle, uid: int, header: str = "") -> str:
    self_f = battle.fighter(uid)
    other = battle.opponent_of(uid)
    lines = []
    if header:
        lines += [header, ""]
    lines += [
        f"<b>⚔️ Duel — Round {battle.round}</b>",
        "",
        f"🧑 <b>You</b> — {esc(self_f.name)} Lv.{self_f.level}",
        f"❤️ {bar(self_f.hp, self_f.max_hp)} {self_f.hp}/{self_f.max_hp}",
        f"💧 {bar(self_f.mana, max(1, self_f.max_mana))} {self_f.mana}/{self_f.max_mana}",
        "",
        f"👤 <b>Opponent</b> — {esc(other.name)} Lv.{other.level}",
        f"❤️ {bar(other.hp, other.max_hp)} {other.hp}/{other.max_hp}",
        f"💧 {bar(other.mana, max(1, other.max_mana))} {other.mana}/{other.max_mana}",
    ]
    return "\n".join(lines)


def _pvp_keyboard(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Attack", callback_data=f"pvp:act:{key}:attack"),
         InlineKeyboardButton("✨ Skill", callback_data=f"pvp:skill:{key}")],
        [InlineKeyboardButton("🧪 Heal", callback_data=f"pvp:act:{key}:heal"),
         InlineKeyboardButton("🏃 Flee", callback_data=f"pvp:act:{key}:flee")],
    ])


async def _pvp_accept(update: Update, context: ContextTypes.DEFAULT_TYPE, challenger_id: int) -> None:
    target = await game.load_player(_db(context), update.effective_user.id)
    challenger = await game.load_player(_db(context), challenger_id)
    if not target or not challenger:
        await _show(update, context, "That challenge is no longer valid.", _main_menu_keyboard())
        return
    requests = context.bot_data.setdefault("duel_requests", {})
    requests.pop(int(target["user_id"]), None)
    pvps = context.bot_data.setdefault("pvp", {})
    key = _pvp_key(target["user_id"], challenger["user_id"])
    for active in pvps.values():
        if (int(target["user_id"]) in active.fighters
                or int(challenger["user_id"]) in active.fighters):
            await _show(update, context, "One of you already has an active duel.", _main_menu_keyboard())
            return
    if key in pvps:
        await _show(update, context, "You already have an active duel.", _main_menu_keyboard())
        return
    battle = PvPBattle(fighter_from_player(challenger), fighter_from_player(target), rng=random.Random())
    pvps[key] = battle
    for uid in (int(challenger["user_id"]), int(target["user_id"])):
        await _send_to(context, uid, _pvp_view(battle, uid, "⚔️ <b>The duel begins!</b>"),
                       _pvp_keyboard(key))
    await _show(update, context, "Duel accepted! Check the battle message above.", _main_menu_keyboard())


async def _pvp_decline(update: Update, context: ContextTypes.DEFAULT_TYPE, challenger_id: int) -> None:
    requests = context.bot_data.setdefault("duel_requests", {})
    requests.pop(int(update.effective_user.id), None)
    if challenger_id:
        await _send_to(context, challenger_id, "❌ Your duel challenge was declined.")
    await _show(update, context, "Challenge declined.", _main_menu_keyboard())


async def _pvp_action(update: Update, context: ContextTypes.DEFAULT_TYPE,
                      key: str, action: str, skill_id: str | None = None) -> None:
    pvps = context.bot_data.setdefault("pvp", {})
    battle = pvps.get(key)
    if battle is None:
        await _show(update, context, "That duel is no longer active.", _main_menu_keyboard())
        return
    uid = int(update.effective_user.id)
    if uid not in battle.fighters:
        await _show(update, context, "You are not a participant in this duel.", _main_menu_keyboard())
        return
    if action == "skill" and not skill_id:
        fighter = battle.fighter(uid)
        rows = []
        for sid in fighter.skills:
            skill = SKILLS[sid]
            cd = fighter.cooldowns.get(sid, 0)
            rows.append([InlineKeyboardButton(
                f"{skill['name']} ({'CD ' + str(cd) if cd else str(skill['mana']) + ' MP'})",
                callback_data=f"pvp:sk:{key}:{sid}",
            )])
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"pvp:refresh:{key}")])
        await _show(update, context, "<b>✨ Choose a skill</b>", InlineKeyboardMarkup(rows))
        return
    if action == "refresh":
        await _show(update, context, _pvp_view(battle, uid), _pvp_keyboard(key))
        return

    heal_amount = 0
    if action == "heal":
        potion, heal_amount = await _consume_heal_potion(
            context, uid, battle.fighter(uid).hp, battle.fighter(uid).max_hp
        )
        if potion == "__full__":
            await _show(update, context, _pvp_view(battle, uid) + "\n\nYou are already at full HP.", _pvp_keyboard(key))
            return
        if potion is None:
            await _show(update, context, _pvp_view(battle, uid) + "\n\nYou have no healing potions.", _pvp_keyboard(key))
            return

    result = battle.submit(uid, action, skill_id=skill_id, heal_amount=heal_amount)
    if not result["ok"]:
        await _show(update, context, events_html(result["events"]), _pvp_keyboard(key))
        return
    if result["waiting"]:
        await _show(update, context, _pvp_view(battle, uid) + "\n\n⏳ " + events_html(result["events"]), _pvp_keyboard(key))
        return

    if result["finished"]:
        pvps.pop(key, None)
        await _finish_pvp(context, battle, result["events"])
        return

    events = events_html(result["events"])
    for participant_id in battle.fighters:
        await _send_to(
            context, participant_id,
            _pvp_view(battle, participant_id, f"<b>Round {battle.round - 1} resolved</b>\n{events}"),
            _pvp_keyboard(key),
        )


async def _finish_pvp(context: ContextTypes.DEFAULT_TYPE, battle: PvPBattle,
                      events: list[str]) -> None:
    db = _db(context)
    log_text = "\n".join(events)
    winner_id = battle.winner
    loser_id = None
    if winner_id is not None:
        for uid in battle.fighters:
            if uid != int(winner_id):
                loser_id = uid
                break

    for uid, fighter in battle.fighters.items():
        await db.update_player(uid, hp=max(1, fighter.hp), mana=max(0, fighter.mana))

    if winner_id is not None and loser_id is not None and battle.result in {"victory", "flee"}:
        await db.increment_pvp(winner_id, True)
        await db.increment_pvp(loser_id, False)
        winner = await game.load_player(db, winner_id)
        loser = await game.load_player(db, loser_id)
        if winner and loser:
            if battle.result == "victory":
                reward = min(int(loser["gold"]), DUEL_GOLD_REWARD + int(loser["level"]) * 10)
                await db.add_gold(loser_id, -reward)
                xp_reward = 50 + int(loser["level"]) * 10
                await game.grant_rewards(db, winner, gold=reward, xp=xp_reward)
            else:
                reward = 0
                xp_reward = 15
                await game.grant_rewards(db, winner, xp=xp_reward)
            notices = await game.progress_quests(db, winner, "duel", target="any", amount=1)
            await db.log_duel(
                int(winner["user_id"]), int(loser["user_id"]), int(winner["user_id"]),
                battle.round, log_text,
            )
            if battle.result == "victory":
                headline = f"<b>🏆 {esc(winner['display_name'])} wins the duel!</b>"
                detail = (
                    f"+{fmt_int(reward)} gold · +{xp_reward} XP\n"
                    f"{esc(loser['display_name'])} loses {fmt_int(reward)} gold."
                )
                loser_text = f"<b>💀 Defeat</b>\nYou lost {fmt_int(reward)} gold."
            else:
                headline = f"<b>🏆 {esc(winner['display_name'])} wins the duel!</b>"
                detail = f"{esc(loser['display_name'])} fled the duel. +{xp_reward} XP."
                loser_text = "<b>🏃 You fled the duel.</b>"
            summary = headline + "\n" + detail
            if notices:
                summary += "\n" + "\n".join(fmt_msg(n) for n in notices)
            await _send_to(context, winner_id, summary + "\n\n<b>Final log</b>\n" + events_html(events[-6:]))
            await _send_to(context, loser_id, loser_text + "\n\n<b>Final log</b>\n" + events_html(events[-6:]))
        return

    await db.log_duel(
        list(battle.fighters)[0], list(battle.fighters)[1], None, battle.round, log_text
    )
    summary = "<b>🤝 The duel ends in a draw.</b>\n\n" + events_html(events[-6:])
    for uid in battle.fighters:
        await _send_to(context, uid, summary)


# ---------------------------------------------------------------------------
# Inventory / equipment
# ---------------------------------------------------------------------------

async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    await _show_inventory(update, context, player)


async def _show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE, player: dict) -> None:
    db = _db(context)
    items = await db.get_inventory(int(player["user_id"]))
    equipped = player.get("equipment") or {}
    rows = []
    lines = [f"<b>🎒 Inventory</b> — 🪙 {fmt_int(player['gold'])} gold\n"]
    if not items:
        lines.append("Your bag is empty. Visit /shop or hunt monsters for loot.")
    for row in items:
        item = ITEMS.get(row["item_id"])
        if not item:
            continue
        qty = row["quantity"]
        emoji = RARITY_EMOJI.get(item.get("rarity"), "")
        lines.append(f"{emoji} <b>{esc(item['name'])}</b> ×{qty} <i>({item['type']})</i>")
        if item["type"] in ("weapon", "armor", "helmet", "boots", "ring", "amulet"):
            rows.append([InlineKeyboardButton(
                f"Equip {item['name']}", callback_data=f"inv:equip:{row['item_id']}"
            )])
        elif item["type"] == "consumable":
            rows.append([InlineKeyboardButton(
                f"Use {item['name']}", callback_data=f"inv:use:{row['item_id']}"
            )])
    lines += ["", "<b>⚙️ Equipped</b>", _equipment_text(player)]
    equip_rows = []
    for slot in SLOTS:
        if slot in equipped:
            equip_rows.append(InlineKeyboardButton(
                f"Unequip {EQUIPMENT_SLOT_NAMES[slot]}", callback_data=f"inv:unequip:{slot}"
            ))
    for idx in range(0, len(equip_rows), 2):
        rows.append(equip_rows[idx:idx + 2])
    rows.append([InlineKeyboardButton("🛒 Shop", callback_data="menu:shop"),
                 InlineKeyboardButton("🔄 Refresh", callback_data="inv:refresh")])
    rows.append([_back_button()])
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


async def _inventory_action(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            action: str, item_id: str) -> None:
    db = _db(context)
    uid = int(update.effective_user.id)
    player = await game.load_player(db, uid)
    if not player:
        return
    if action == "equip":
        ok, message = await game.equip_item(db, uid, item_id)
    elif action == "use":
        ok, message = await game.use_consumable(db, player, item_id)
    elif action == "unequip":
        ok, message = await game.unequip_item(db, uid, item_id)
    else:
        ok, message = False, "Unknown action."
    player = await game.load_player(db, uid)
    prefix = "" if ok else "⚠️ "
    await _show(update, context, f"{prefix}{fmt_msg(message)}\n\n" + _profile_text(player), _profile_keyboard(player))


async def equip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    if not context.args:
        await _show(update, context, "Usage: <code>/equip item name or id</code>", _main_menu_keyboard())
        return
    item_id = _resolve_item(" ".join(context.args))
    if not item_id:
        await _show(update, context, "Item not found.", _main_menu_keyboard())
        return
    ok, message = await game.equip_item(_db(context), int(player["user_id"]), item_id)
    player = await game.load_player(_db(context), int(player["user_id"]))
    await _show(update, context, ("" if ok else "⚠️ ") + fmt_msg(message), _profile_keyboard(player))


def _resolve_item(query: str) -> str | None:
    query = (query or "").strip().lower()
    if not query:
        return None
    if query in ITEMS:
        return query
    for item_id, item in ITEMS.items():
        if item["name"].lower() == query:
            return item_id
    for item_id, item in ITEMS.items():
        if query in item["name"].lower() or query in item_id:
            return item_id
    return None


# ---------------------------------------------------------------------------
# Shop
# ---------------------------------------------------------------------------

def _shop_items() -> list[str]:
    return [item_id for item_id, item in ITEMS.items()
            if item.get("type") != "material" and int(item.get("price", 0)) > 0]


async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    await _show_shop(update, context, player, 0)


async def _show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     player: dict, page: int) -> None:
    items = _shop_items()
    pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    lines = [f"<b>🛒 Shop</b> — Page {page + 1}/{pages}", f"🪙 You have {fmt_int(player['gold'])} gold.\n"]
    rows = []
    for item_id in chunk:
        item = ITEMS[item_id]
        stat = ""
        if item.get("attack"):
            stat = f" · ATK +{item['attack']}"
        elif item.get("defense"):
            stat = f" · DEF +{item['defense']}"
        elif item.get("effect", {}).get("hp"):
            stat = f" · +{item['effect']['hp']} HP"
        lines.append(f"{RARITY_EMOJI.get(item.get('rarity'), '')} <b>{esc(item['name'])}</b> — {fmt_int(item['price'])}g{stat}")
        rows.append([InlineKeyboardButton(
            f"Buy {item['name']} ({item['price']}g)", callback_data=f"shop:buy:{item_id}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"shop:page:{page - 1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"shop:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🎒 Inventory", callback_data="menu:inventory"), _back_button()])
    lines.append("\nSell items with <code>/sell item [qty]</code>.")
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


async def _shop_buy(update: Update, context: ContextTypes.DEFAULT_TYPE, item_id: str) -> None:
    db = _db(context)
    uid = int(update.effective_user.id)
    player = await game.load_player(db, uid)
    if not player:
        return
    ok, message = await game.buy_item(db, player, item_id, 1)
    player = await game.load_player(db, uid)
    await _show(update, context, ("" if ok else "⚠️ ") + fmt_msg(message), InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Shop", callback_data="menu:shop"),
         InlineKeyboardButton("🎒 Inventory", callback_data="menu:inventory")],
        [_back_button()],
    ]))


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    if not context.args:
        await _show(update, context, "Usage: <code>/buy item name [qty]</code>", _main_menu_keyboard())
        return
    args = list(context.args)
    qty = 1
    if args[-1].isdigit():
        qty = max(1, int(args.pop()))
    item_id = _resolve_item(" ".join(args))
    if not item_id:
        await _show(update, context, "Item not found.", _main_menu_keyboard())
        return
    ok, message = await game.buy_item(_db(context), player, item_id, qty)
    await _show(update, context, ("" if ok else "⚠️ ") + fmt_msg(message), _main_menu_keyboard())


async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    if not context.args:
        await _show(update, context, "Usage: <code>/sell item name [qty]</code>", _main_menu_keyboard())
        return
    args = list(context.args)
    qty = 1
    if args[-1].isdigit():
        qty = max(1, int(args.pop()))
    item_id = _resolve_item(" ".join(args))
    if not item_id:
        await _show(update, context, "Item not found.", _main_menu_keyboard())
        return
    ok, message = await game.sell_item(_db(context), player, item_id, qty)
    await _show(update, context, ("" if ok else "⚠️ ") + fmt_msg(message), _main_menu_keyboard())


# ---------------------------------------------------------------------------
# Crafting
# ---------------------------------------------------------------------------

async def craft_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    rows = []
    lines = ["<b>🔨 Crafting</b>\n", "Combine materials and gold into powerful gear.\n"]
    for item_id, recipe in CRAFTING_RECIPES.items():
        item = ITEMS[item_id]
        materials = ", ".join(
            f"{ITEMS[m]['name']} ×{q}" for m, q in recipe["materials"].items()
        )
        locked = int(player["level"]) < int(recipe.get("level", 1))
        status = " 🔒" if locked else ""
        lines.append(
            f"{RARITY_EMOJI.get(item.get('rarity'), '')} <b>{esc(item['name'])}</b>{status}\n"
            f"   {esc(materials)} + {recipe.get('gold', 0)}g · requires Lv.{recipe.get('level', 1)}"
        )
        if not locked:
            rows.append([InlineKeyboardButton(
                f"Craft {item['name']}", callback_data=f"craft:make:{item_id}"
            )])
    rows.append([_back_button()])
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


async def _craft_item(update: Update, context: ContextTypes.DEFAULT_TYPE, item_id: str) -> None:
    db = _db(context)
    uid = int(update.effective_user.id)
    player = await game.load_player(db, uid)
    if not player:
        return
    ok, message = await game.craft_item(db, player, item_id)
    player = await game.load_player(db, uid)
    await _show(update, context, ("" if ok else "⚠️ ") + fmt_msg(message), InlineKeyboardMarkup([
        [InlineKeyboardButton("🔨 Craft more", callback_data="menu:craft"),
         InlineKeyboardButton("🎒 Inventory", callback_data="menu:inventory")],
        [_back_button()],
    ]))


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------

async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    db = _db(context)
    args = context.args or []
    if args and args[0].lower() == "list":
        if len(args) < 2:
            await _show(update, context, "Usage: <code>/market list item qty price</code>", _main_menu_keyboard())
            return
        tokens = list(args[1:])
        price = 0
        qty = 1
        if tokens and tokens[-1].isdigit():
            price = int(tokens.pop())
        if tokens and tokens[-1].isdigit():
            qty = int(tokens.pop())
        item_id = _resolve_item(" ".join(tokens))
        if not item_id:
            await _show(update, context, "Item not found.", _main_menu_keyboard())
            return
        qty = max(1, qty)
        if price <= 0:
            price = max(1, int(ITEMS.get(item_id, {}).get("price", 10)))
        ok, message = await game.list_market_item(db, player, item_id, qty, price)
        await _show(update, context, ("" if ok else "⚠️ ") + fmt_msg(message), _main_menu_keyboard())
        return
    if args and args[0].lower() == "cancel":
        if len(args) < 2 or not args[1].isdigit():
            await _show(update, context, "Usage: <code>/market cancel listing_id</code>", _main_menu_keyboard())
            return
        result = await db.cancel_listing(int(args[1]), int(player["user_id"]))
        message = "Listing cancelled." if result["ok"] else result["reason"]
        await _show(update, context, ("" if result["ok"] else "⚠️ ") + fmt_msg(message), _main_menu_keyboard())
        return

    listings = await db.get_active_listings(limit=10)
    lines = ["<b>🏪 Player Marketplace</b>\n"]
    rows = []
    if not listings:
        lines.append("No active listings. Create one with <code>/market list item qty price</code>.")
    for listing in listings:
        item = ITEMS.get(listing["item_id"], {"name": listing["item_id"]})
        lines.append(
            f"#{listing['id']} {esc(item['name'])} ×{listing['quantity']} — "
            f"<b>{fmt_int(listing['price'])}g</b> · seller {esc(listing.get('seller_name') or '?')}"
        )
        rows.append([InlineKeyboardButton(
            f"Buy #{listing['id']} ({listing['price']}g)",
            callback_data=f"market:buy:{listing['id']}",
        )])
    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="market:refresh")])
    rows.append([_back_button()])
    lines.append("\nCreate: <code>/market list item qty price</code>\nCancel: <code>/market cancel id</code>")
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


# ---------------------------------------------------------------------------
# Clan
# ---------------------------------------------------------------------------

def _clan_keyboard(clan: dict | None) -> InlineKeyboardMarkup:
    if clan is None:
        rows = [
            [InlineKeyboardButton("🏆 Clan rankings", callback_data="lb:clans")],
            [_back_button()],
        ]
        return InlineKeyboardMarkup(rows)
    rows = [
        [InlineKeyboardButton("🪙 Donate 100", callback_data="clan:donate:100"),
         InlineKeyboardButton("🪙 Donate 500", callback_data="clan:donate:500"),
         InlineKeyboardButton("🪙 Donate 1k", callback_data="clan:donate:1000")],
        [InlineKeyboardButton("⬆️ Upgrade", callback_data="clan:upgrade"),
         InlineKeyboardButton("🏆 Rankings", callback_data="lb:clans"),
         InlineKeyboardButton("🔄 Refresh", callback_data="clan:refresh")],
        [InlineKeyboardButton("🚪 Leave", callback_data="clan:leave")],
        [_back_button()],
    ]
    return InlineKeyboardMarkup(rows)


async def _clan_text(context: ContextTypes.DEFAULT_TYPE, player: dict) -> tuple[str, dict | None]:
    db = _db(context)
    clan = await db.get_player_clan(int(player["user_id"]))
    if clan is None:
        invites = await db.get_clan_invites(int(player["user_id"]))
        text = (
            "<b>🏰 Clans</b>\n\nYou are not in a clan.\n\n"
            f"<b>Create</b> (Lv.{CLAN_MIN_LEVEL}+, {CLAN_CREATE_COST}g):\n"
            "<code>/clan create Name TAG</code>\n\n"
            "<b>Join</b>:\n<code>/clan join ClanName</code>\n\n"
            "<b>Accept invite</b>:\n<code>/clan accept</code>"
        )
        if invites:
            text += "\n\n<b>Your invitations</b>\n" + "\n".join(
                f"• [{esc(i['clan_tag'])}] {esc(i['clan_name'])}" for i in invites
            )
        return text, None
    members = await db.get_clan_members(int(clan["id"]))
    wars = await db.get_clan_wars(int(clan["id"]), 3)
    lines = [
        f"<b>🏰 [{esc(clan['tag'])}] {esc(clan['name'])}</b>",
        f"Level {clan['level']} · XP {fmt_int(clan['xp'])} · Role: {esc(clan['member_role'])}",
        f"🪙 Bank: {fmt_int(clan['bank_gold'])} · 👥 Members: {len(members)}/{clan_member_limit(clan['level'])}",
        f"🏆 Record: {clan['wins']}W / {clan['losses']}L",
        "",
        "<b>Members</b>",
    ]
    for member in members[:15]:
        lines.append(
            f"• {esc(member['display_name'])} — Lv.{member['level']} "
            f"{esc(member['role'])} · {fmt_int(member['contribution'])}g donated"
        )
    if clan["description"]:
        lines += ["", f"<i>{esc(clan['description'])}</i>"]
    if wars:
        lines += ["", "<b>Recent wars</b>"]
        for war in wars:
            won = war["winner_id"] == clan["id"]
            lines.append(
                f"• vs #{war['defender_id'] if war['attacker_id'] == clan['id'] else war['attacker_id']}: "
                f"{'Win' if won else 'Loss'} ({war['attacker_score']} - {war['defender_score']})"
            )
    upgrade_cost = clan_upgrade_cost(int(clan["level"]))
    lines += [
        "",
        f"💡 Upgrade cost: {fmt_int(upgrade_cost)}g · member cap +2",
        "Commands: <code>/clan donate N</code>, <code>/clan invite @user</code>, "
        "<code>/clan war ClanName</code>, <code>/clan upgrade</code>",
    ]
    return "\n".join(lines), clan


async def clan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    db = _db(context)
    args = list(context.args or [])
    sub = args[0].lower() if args else ""

    async def _result(ok: bool, message: str) -> None:
        player2 = await game.load_player(db, int(player["user_id"]))
        clan = await db.get_player_clan(int(player2["user_id"]))
        text, _ = await _clan_text(context, player2)
        await _show(update, context, ("" if ok else "⚠️ ") + message + "\n\n" + text, _clan_keyboard(clan))

    if sub == "create":
        if len(args) < 3:
            await _show(update, context, "Usage: <code>/clan create ClanName TAG</code>", _main_menu_keyboard())
            return
        name = " ".join(args[1:-1])
        tag = args[-1]
        ok, message, _ = await clan_service.create_clan(db, player, name, tag)
        await _result(ok, fmt_msg(message))
        return
    if sub == "join":
        if len(args) < 2:
            await _show(update, context, "Usage: <code>/clan join ClanName</code>", _main_menu_keyboard())
            return
        ok, message, _ = await clan_service.join_clan(db, player, " ".join(args[1:]))
        await _result(ok, fmt_msg(message))
        return
    if sub == "accept":
        ok, message, _ = await clan_service.accept_invite(db, player)
        await _result(ok, fmt_msg(message))
        return
    if sub == "invite":
        if len(args) < 2:
            await _show(update, context, "Usage: <code>/clan invite @username</code>", _main_menu_keyboard())
            return
        ok, message = await clan_service.invite_player(db, player, args[1])
        await _result(ok, fmt_msg(message))
        return
    if sub == "leave":
        ok, message = await clan_service.leave_clan(db, player)
        await _result(ok, fmt_msg(message))
        return
    if sub == "disband":
        ok, message = await clan_service.disband_clan(db, player)
        await _result(ok, fmt_msg(message))
        return
    if sub == "donate":
        if len(args) < 2 or not args[1].isdigit():
            await _show(update, context, "Usage: <code>/clan donate Amount</code>", _main_menu_keyboard())
            return
        ok, message = await clan_service.donate(db, player, int(args[1]))
        await _result(ok, fmt_msg(message))
        return
    if sub == "upgrade":
        ok, message, _ = await clan_service.upgrade_clan(db, player)
        await _result(ok, fmt_msg(message))
        return
    if sub == "war":
        if len(args) < 2:
            await _show(update, context, "Usage: <code>/clan war ClanName</code>", _main_menu_keyboard())
            return
        ok, message, _ = await clan_service.declare_war(db, player, " ".join(args[1:]))
        await _result(ok, fmt_msg(message))
        return
    if sub == "kick":
        target = await db.get_player_by_username(args[1]) if len(args) > 1 else None
        if not target:
            await _show(update, context, "Player not found.", _main_menu_keyboard())
            return
        ok, message = await clan_service.kick_member(db, player, int(target["user_id"]))
        await _result(ok, fmt_msg(message))
        return

    text, clan = await _clan_text(context, player)
    await _show(update, context, text, _clan_keyboard(clan))


async def _clan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         action: str, arg: str | None = None) -> None:
    db = _db(context)
    uid = int(update.effective_user.id)
    player = await game.load_player(db, uid)
    if not player:
        return
    if action == "donate" and arg and arg.isdigit():
        ok, message = await clan_service.donate(db, player, int(arg))
    elif action == "upgrade":
        ok, message, _ = await clan_service.upgrade_clan(db, player)
    elif action == "leave":
        ok, message = await clan_service.leave_clan(db, player)
    elif action == "refresh":
        ok, message = True, ""
    elif action == "war":
        return
    else:
        ok, message = False, "Unknown clan action."
    player = await game.load_player(db, uid)
    clan = await db.get_player_clan(uid)
    text, _ = await _clan_text(context, player)
    prefix = "" if ok else "⚠️ "
    if message:
        text = f"{prefix}{fmt_msg(message)}\n\n{text}"
    await _show(update, context, text, _clan_keyboard(clan))


# ---------------------------------------------------------------------------
# Quests / daily
# ---------------------------------------------------------------------------

async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    await _show_quests(update, context, player)


async def _show_quests(update: Update, context: ContextTypes.DEFAULT_TYPE, player: dict) -> None:
    db = _db(context)
    rows = []
    lines = ["<b>📜 Quest Log</b>\n"]
    active = await db.get_player_quests(int(player["user_id"]))
    active_by_id = {q["quest_id"]: q for q in active}
    showed_any = False
    for quest_id, quest in QUESTS.items():
        row = active_by_id.get(quest_id)
        if row and row["active"]:
            stage = quest["stages"][int(row["stage"])] if int(row["stage"]) < len(quest["stages"]) else None
            lines.append(f"🔸 <b>{esc(quest['name'])}</b>")
            if stage:
                lines.append(
                    f"   Stage {int(row['stage']) + 1}/{len(quest['stages'])}: {esc(stage['text'])} "
                    f"({row['progress']}/{stage['count']})"
                )
            showed_any = True
        elif row and not row["active"]:
            lines.append(f"✅ <s>{esc(quest['name'])}</s> — completed")
            showed_any = True
    if not showed_any:
        lines.append("No active quests.\n")
    lines += ["", "<b>Available quests</b>"]
    for quest_id, quest in QUESTS.items():
        row = active_by_id.get(quest_id)
        if row:
            continue
        if int(player["level"]) < int(quest.get("min_level", 1)):
            continue
        lines.append(
            f"{quest['emoji']} <b>{esc(quest['name'])}</b> (Lv.{quest['min_level']})\n"
            f"   {esc(quest['description'])}"
        )
        rows.append([InlineKeyboardButton(
            f"Start {quest['name']}", callback_data=f"quest:start:{quest_id}"
        )])
    rows.append([_back_button()])
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


async def _quest_start(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: str) -> None:
    db = _db(context)
    player = await game.load_player(db, int(update.effective_user.id))
    if not player:
        return
    ok, message = await game.start_quest(db, player, quest_id)
    player = await game.load_player(db, int(player["user_id"]))
    text = ("" if ok else "⚠️ ") + fmt_msg(message)
    if ok:
        quest = QUESTS[quest_id]
        text += f"\n\n{quest['emoji']} <b>{esc(quest['name'])}</b>\n" + "\n".join(
            f"{i}. {esc(stage['text'])}" for i, stage in enumerate(quest["stages"], 1)
        )
    await _show(update, context, text, InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Quest log", callback_data="menu:quest")],
        [_back_button()],
    ]))


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context)
    if not player:
        return
    reward = daily_reward(player)
    lines = [
        "<b>🎁 Daily Reward</b>\n",
        f"Current streak: <b>{player['daily_streak']}</b> day(s)",
        f"Next reward: 🪙 {reward['gold']} gold · ⭐ {reward['xp']} XP"
        + (f" · 💎 {reward['gems']} gems" if reward["gems"] else ""),
    ]
    if reward["items"]:
        lines.append("Items: " + ", ".join(f"{ITEMS[i]['name']} ×{q}" for i, q in reward["items"].items()))
    lines.append(f"\nStreak bonus peaks after {7} days. Gem reward every {DAILY_GEM_INTERVAL} days.")
    if not reward["claimable"]:
        lines.append("\n✅ Already claimed today. Come back tomorrow!")
        keyboard = InlineKeyboardMarkup([[_back_button()]])
    else:
        lines.append("\nTap below to claim.")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎁 Claim daily", callback_data="daily:claim"),
            _back_button(),
        ]])
    await _show(update, context, "\n".join(lines), keyboard)


async def _daily_claim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db(context)
    player = await game.load_player(db, int(update.effective_user.id))
    if not player:
        return
    result = await game.claim_daily(db, player)
    if not result["ok"]:
        await _show(update, context, "⚠️ " + esc(result["message"]), _main_menu_keyboard())
        return
    reward = result["reward"]
    player = await game.load_player(db, int(player["user_id"]))
    lines = [
        "<b>🎁 Daily reward claimed!</b>\n",
        f"🔥 Streak: <b>{reward['streak']}</b> days",
        f"+{fmt_int(reward['gold'])} gold · +{reward['xp']} XP"
        + (f" · +{reward['gems']} gems" if reward["gems"] else ""),
    ]
    if reward["items"]:
        lines.append("Items: " + ", ".join(f"{ITEMS[i]['name']} ×{q}" for i, q in reward["items"].items()))
    lines += ["", _hp_line(player), f"📊 {_xp_line(player)}"]
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Hunt", callback_data="menu:hunt"),
         InlineKeyboardButton("👤 Profile", callback_data="menu:profile")],
        [_back_button()],
    ]))


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await _load(update, context, notify=False)
    await _show_leaderboard(update, context, "level", bool(player))


async def _show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            tab: str, registered: bool | None = None) -> None:
    db = _db(context)
    if tab == "clans":
        clans = await db.get_clan_leaderboard(10)
        lines = ["<b>🏆 Top Clans</b>\n"]
        if not clans:
            lines.append("No clans have been founded yet.")
        for idx, clan in enumerate(clans, 1):
            lines.append(
                f"{idx}. <b>[{esc(clan['tag'])}] {esc(clan['name'])}</b> — Lv.{clan['level']} · "
                f"{clan['member_count']} members · {fmt_int(clan['bank_gold'])}g · "
                f"{clan['wins']}W/{clan['losses']}L"
            )
    else:
        column = {"level": "level", "gold": "gold", "pvp": "wins", "boss": "boss_kills"}.get(tab, "level")
        labels = {
            "level": ("⭐ Top Heroes by Level", "level"),
            "gold": ("🪙 Richest Players", "gold"),
            "pvp": ("⚔️ PvP Champions", "wins"),
            "boss": ("🐉 Boss Slayers", "boss_kills"),
        }
        title, _ = labels.get(tab, labels["level"])
        players = await db.get_top_players(column, 10)
        lines = [f"<b>{title}</b>\n"]
        if not players:
            lines.append("No players registered yet.")
        for idx, row in enumerate(players, 1):
            cls = CLASSES.get(row.get("class") or "", {})
            if tab == "gold":
                metric = f"🪙 {fmt_int(row['gold'])}"
            elif tab == "pvp":
                metric = f"⚔️ {row['wins']}W / {row['losses']}L"
            elif tab == "boss":
                metric = f"🐉 {row['boss_kills']} kills"
            else:
                metric = f"Lv.{row['level']} · {fmt_int(row['xp'])} XP"
            lines.append(
                f"{idx}. {cls.get('emoji', '')} <b>{esc(row['display_name'])}</b> — {metric}"
            )
    rows = [
        [InlineKeyboardButton("⭐ Level", callback_data="lb:level"),
         InlineKeyboardButton("🪙 Gold", callback_data="lb:gold")],
        [InlineKeyboardButton("⚔️ PvP", callback_data="lb:pvp"),
         InlineKeyboardButton("🐉 Bosses", callback_data="lb:boss")],
        [InlineKeyboardButton("🏰 Clans", callback_data="lb:clans")],
        [_back_button()],
    ]
    await _show(update, context, "\n".join(lines), InlineKeyboardMarkup(rows))


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not config.is_admin(user.id):
        await _show(update, context, "⛔ Admin only.", _main_menu_keyboard())
        return
    message = await update.effective_message.reply_text("📦 Creating backup...")
    try:
        result = await perform_backup(_db(context), config.BACKUP_DIR)
    except Exception as exc:  # noqa: BLE001 - surface any backup failure to admin
        await message.edit_text(f"❌ Backup failed: {esc(exc)}", parse_mode=ParseMode.HTML)
        return
    text = (
        f"✅ <b>Backup complete</b>\n"
        f"Players: {result['players']}\n"
        f"Size: {result['bytes'] / 1024:.1f} KB\n"
        f"Time: {result['seconds']}s"
    )
    await message.edit_text(text, parse_mode=ParseMode.HTML)
    try:
        with open(result["json"], "rb") as fh:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=InputFile(fh, filename=Path(result["json"]).name),
                caption="JSON backup",
            )
        if result["sqlite"]:
            with open(result["sqlite"], "rb") as fh:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=InputFile(fh, filename=Path(result["sqlite"]).name),
                    caption="SQLite backup",
                )
    except (TelegramError, OSError) as exc:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ Files saved locally but upload failed: {esc(exc)}",
            parse_mode=ParseMode.HTML,
        )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not config.is_admin(user.id):
        await _show(update, context, "⛔ Admin only.", _main_menu_keyboard())
        return
    text = " ".join(context.args or []).strip()
    if not text:
        await _show(update, context, "Usage: <code>/broadcast message</code>", _main_menu_keyboard())
        return
    db = _db(context)
    players = await db.get_all_players()
    sent = failed = 0
    notice = (
        f"<b>📢 Announcement from {GAME_NAME}</b>\n\n{esc(text)}"
    )
    for index, player in enumerate(players):
        ok = await _send_to(context, int(player["user_id"]), notice)
        if ok:
            sent += 1
        else:
            failed += 1
        if index % 25 == 24:
            await asyncio.sleep(1)
    await _show(
        update, context,
        f"📢 Broadcast complete.\n✅ Delivered: {sent}\n❌ Failed: {failed}",
        _main_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# Main menu callbacks
# ---------------------------------------------------------------------------

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    if action in ("main", "start"):
        player = await game.load_player(_db(context), update.effective_user.id)
        if not player:
            await start(update, context)
            return
        text = (
            f"<b>⚔️ {GAME_NAME}</b>\n\n"
            f"{_player_header(player)}\n{_hp_line(player)}\n"
            f"🪙 {fmt_int(player['gold'])} gold · 💎 {player['gems']} gems\n\n"
            "Choose an action."
        )
        await _show(update, context, text, _main_menu_keyboard())
        return
    if action == "help":
        await help_command(update, context)
        return
    player = await _load(update, context)
    if not player:
        return
    if action == "profile":
        await profile_command(update, context)
    elif action == "hunt":
        await _show_hunt_menu(update, context, player)
    elif action == "boss":
        await boss_command(update, context)
    elif action == "inventory":
        await _show_inventory(update, context, player)
    elif action == "shop":
        await _show_shop(update, context, player, 0)
    elif action == "craft":
        await craft_command(update, context)
    elif action == "clan":
        text, clan = await _clan_text(context, player)
        await _show(update, context, text, _clan_keyboard(clan))
    elif action == "quest":
        await _show_quests(update, context, player)
    elif action == "daily":
        await daily_command(update, context)
    elif action == "leaderboard":
        await _show_leaderboard(update, context, "level")
    elif action == "market":
        await market_command(update, context)
    else:
        await _show(update, context, "Unknown menu action.", _main_menu_keyboard())


# ---------------------------------------------------------------------------
# Callback router
# ---------------------------------------------------------------------------

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    try:
        await query.answer()
    except TelegramError:
        pass
    data = query.data or ""
    parts = data.split(":")
    prefix = parts[0]

    try:
        if prefix == "menu":
            await menu_callback(update, context, parts[1] if len(parts) > 1 else "main")
        elif prefix == "reg":
            action = parts[1] if len(parts) > 1 else ""
            if action == "start":
                await _show_race_select(update, context)
            elif action == "back":
                await _show_race_select(update, context)
            elif action == "race" and len(parts) > 2:
                context.user_data["reg_race"] = parts[2]
                await _show_class_select(update, context)
            elif action == "class" and len(parts) > 2:
                await _create_character(update, context, parts[2])
        elif prefix == "profile":
            action = parts[1] if len(parts) > 1 else ""
            if action == "alloc" and len(parts) > 2:
                await _allocate(update, context, parts[2])
            elif action == "refresh":
                await profile_command(update, context)
        elif prefix == "hunt":
            action = parts[1] if len(parts) > 1 else ""
            if action == "start" and len(parts) > 2:
                await _start_hunt(update, context, parts[2])
            elif action == "menu":
                player = await _load(update, context)
                if player:
                    await _show_hunt_menu(update, context, player)
        elif prefix == "battle":
            action = parts[1] if len(parts) > 1 else ""
            arg = parts[2] if len(parts) > 2 else None
            await _battle_action(update, context, action, arg)
        elif prefix == "boss":
            action = parts[1] if len(parts) > 1 else ""
            if action == "join" and len(parts) > 2:
                await _join_boss(update, context, parts[2])
            elif action == "list":
                await boss_command(update, context)
        elif prefix == "raid":
            action = parts[1] if len(parts) > 1 else ""
            boss_id = parts[2] if len(parts) > 2 else ""
            await _raid_action(update, context, action, boss_id)
        elif prefix == "pvp":
            action = parts[1] if len(parts) > 1 else ""
            if action == "accept" and len(parts) > 2:
                await _pvp_accept(update, context, int(parts[2]))
            elif action == "decline" and len(parts) > 2:
                await _pvp_decline(update, context, int(parts[2]))
            elif action == "act" and len(parts) > 3:
                await _pvp_action(update, context, parts[2], parts[3])
            elif action == "skill" and len(parts) > 2:
                await _pvp_action(update, context, parts[2], "skill")
            elif action == "sk" and len(parts) > 3:
                await _pvp_action(update, context, parts[2], "skill", parts[3])
            elif action == "refresh" and len(parts) > 2:
                await _pvp_action(update, context, parts[2], "refresh")
        elif prefix == "inv":
            action = parts[1] if len(parts) > 1 else ""
            if action == "refresh":
                player = await game.load_player(_db(context), update.effective_user.id)
                if player:
                    await _show_inventory(update, context, player)
            elif len(parts) > 2:
                await _inventory_action(update, context, action, parts[2])
        elif prefix == "shop":
            action = parts[1] if len(parts) > 1 else ""
            if action == "buy" and len(parts) > 2:
                await _shop_buy(update, context, parts[2])
            elif action == "page" and len(parts) > 2:
                player = await _load(update, context)
                if player:
                    await _show_shop(update, context, player, int(parts[2]))
        elif prefix == "craft":
            action = parts[1] if len(parts) > 1 else ""
            if action == "make" and len(parts) > 2:
                await _craft_item(update, context, parts[2])
        elif prefix == "market":
            action = parts[1] if len(parts) > 1 else ""
            if action == "buy" and len(parts) > 2:
                db = _db(context)
                player = await game.load_player(db, update.effective_user.id)
                if player:
                    ok, message = await game.buy_market_listing(db, player, int(parts[2]))
                    player = await game.load_player(db, update.effective_user.id)
                    await _show(update, context, ("" if ok else "⚠️ ") + fmt_msg(message), InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏪 Market", callback_data="market:refresh")],
                        [_back_button()],
                    ]))
            elif action == "refresh":
                await market_command(update, context)
        elif prefix == "clan":
            action = parts[1] if len(parts) > 1 else ""
            arg = parts[2] if len(parts) > 2 else None
            await _clan_callback(update, context, action, arg)
        elif prefix == "quest":
            action = parts[1] if len(parts) > 1 else ""
            if action == "start" and len(parts) > 2:
                await _quest_start(update, context, parts[2])
            elif action == "list":
                await quest_command(update, context)
        elif prefix == "daily":
            if len(parts) > 1 and parts[1] == "claim":
                await _daily_claim(update, context)
        elif prefix == "lb":
            tab = parts[1] if len(parts) > 1 else "level"
            await _show_leaderboard(update, context, tab)
    except Exception as exc:  # noqa: BLE001 - never let a callback crash the bot
        import logging
        logging.getLogger(__name__).exception("Callback failed for %s", data)
        try:
            await query.message.reply_text(
                f"⚠️ Something went wrong: {esc(exc)}", parse_mode=ParseMode.HTML
            )
        except TelegramError:
            pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    import logging
    logger = logging.getLogger(__name__)
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning("Telegram network hiccup: %s", context.error)
        return
    logger.exception("Update caused an exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ An unexpected error occurred. Please try again.",
            )
        except TelegramError:
            pass
