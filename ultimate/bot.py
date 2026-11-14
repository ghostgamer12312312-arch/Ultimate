"""Telegram interface for Dragon Ball: Multiverse Legends."""

from __future__ import annotations

import asyncio
import logging
import random
import shutil
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

try:
    from . import battle, config, data, game, ui
    from .db import Database
except ImportError:
    import battle
    import config
    import data
    import game
    import ui
    from db import Database

logger = logging.getLogger(__name__)

SERIES_ALIASES = {}
for _series, _info in data.SERIES.items():
    SERIES_ALIASES[_series] = _series
    SERIES_ALIASES[_info["name"].lower()] = _series
    SERIES_ALIASES[_info["short"].lower()] = _series
    SERIES_ALIASES[_info["home"].lower()] = _series


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


def parse_series(value: str | None) -> str | None:
    if not value:
        return None
    return SERIES_ALIASES.get(value.strip().lower())


def chunks(text: str, size: int = 3800) -> list[str]:
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    current = ""
    for line in lines:
        if len(current) + len(line) > size and current:
            result.append(current)
            current = ""
        current += line
    if current:
        result.append(current)
    return result or [text[:size]]


async def respond(update: Update, text: str, keyboard=None) -> None:
    try:
        if update.callback_query is not None:
            try:
                await update.callback_query.edit_message_text(
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                return
            except BadRequest as exc:
                if "not modified" in str(exc).lower():
                    return
        message = update.effective_message
        if message is None:
            return
        parts = chunks(text)
        await message.reply_text(parts[0], reply_markup=keyboard, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        for part in parts[1:]:
            await message.reply_text(part, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except (BadRequest, TelegramError) as exc:
        logger.warning("Could not send response: %s", exc)


async def show_battle(update: Update, context: ContextTypes.DEFAULT_TYPE, battle_data: dict) -> None:
    db = get_db(context)
    user_id = update.effective_user.id
    await respond(update, battle.render(battle_data), battle.keyboard(battle_data, battle.potions(db, user_id)))


async def start_battle(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str, **kwargs) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    result = battle.start(db, update.effective_user.id, mode, **kwargs)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    if result.get("resumed"):
        await respond(update, "⚔️ Resuming your active battle.")
    await show_battle(update, context, result["battle"])


def replied_user(update: Update):
    message = update.effective_message
    if message is not None and message.reply_to_message is not None:
        return message.reply_to_message.from_user
    return None


def resolve_player_target(db: Database, update: Update, query: str | None) -> dict | None:
    user = replied_user(update)
    if user is not None and not query:
        return db.player(user.id) or db.ensure_player(user.id, user.username, user.first_name)
    if not query:
        return None
    return db.find_player(query)


def resolve_owned_character(db: Database, user_id: int, query: str) -> dict | None:
    query = query.strip()
    owned = db.characters(user_id)
    return next((char for char in owned if char["id"].lower() == query.lower()), None) or next((char for char in owned if query.lower() in char["name"].lower()), None)


def resolve_any_character(query: str) -> dict | None:
    query = query.strip()
    return data.CHARACTERS.get(query) or next((char for char in data.CHARACTERS.values() if query.lower() in char["name"].lower()), None)


def resolve_owned_pet(db: Database, user_id: int, query: str) -> dict | None:
    query = query.strip()
    pets = db.pets(user_id)
    return next((pet for pet in pets if pet["id"].lower() == query.lower()), None) or next((pet for pet in pets if query.lower() in pet["name"].lower()), None)


def resolve_item(query: str) -> dict | None:
    query = query.strip()
    return data.ITEMS.get(query) or next((item for item in data.ITEMS.values() if query.lower() in item["name"].lower()), None)


def parse_offer(kind: str, tokens: list[str]) -> tuple[str, object, int] | None:
    kind = {"char": "character", "chars": "character", "weapon": "gear", "armor": "gear", "sp": "skill_points", "spirit": "skill_points"}.get(kind.lower(), kind.lower())
    if kind in ("yens", "gems", "crystals", "tickets", "stamina", "skill_points"):
        if not tokens or not tokens[0].lstrip("-").isdigit():
            return None
        return kind, int(tokens[0]), 1
    if not tokens:
        return None
    qty = int(tokens[1]) if len(tokens) > 1 and tokens[1].isdigit() else 1
    return kind, tokens[0], qty


def asset_from_tokens(db: Database, user_id: int, kind: str, tokens: list[str], *, owned: bool = True, any_series: bool = False) -> tuple[str, object, int] | None:
    parsed = parse_offer(kind, tokens)
    if parsed is None:
        return None
    kind, asset, qty = parsed
    if kind in ("yens", "gems", "crystals", "tickets", "stamina", "skill_points"):
        return kind, asset, 1
    if kind == "item":
        item = resolve_item(str(asset))
        return ("item", item["id"], qty) if item else None
    if kind == "character":
        char = resolve_owned_character(db, user_id, str(asset)) if owned else resolve_any_character(str(asset))
        return ("character", char["id"], qty) if char else None
    if kind == "gear":
        if not str(asset).isdigit():
            return None
        return ("gear", int(asset), 1)
    if kind == "pet":
        if any_series:
            pet = data.PETS.get(str(asset)) or next((p for p in data.PETS.values() if str(asset).lower() in p["name"].lower()), None)
        else:
            pet = resolve_owned_pet(db, user_id, str(asset))
        return ("pet", pet["id"], qty) if pet else None
    if kind == "shard":
        char = resolve_owned_character(db, user_id, str(asset)) if owned else resolve_any_character(str(asset))
        return ("shard", char["id"], qty) if char else None
    if kind == "title":
        return ("title", str(asset), 1)
    return None

async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    user = update.effective_user
    if user is None:
        return None
    db = get_db(context)
    player = db.ensure_player(user.id, user.username, user.first_name)
    if player.get("banned") and not config.is_admin(user.id):
        await respond(update, "🚫 <b>You are banned from this bot.</b>")
        return None
    return player


async def guard_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    player = await guard(update, context)
    if player is None:
        return None
    if not config.is_admin(update.effective_user.id):
        await respond(update, "⛔ <b>Admin only.</b>")
        return None
    return player


def series_name(series: str) -> str:
    info = data.SERIES.get(series)
    return f"{info['emoji']} {info['name']}" if info else series


def display_name(player: dict | None, fallback: str = "Summoner") -> str:
    if not player:
        return fallback
    return player.get("first_name") or player.get("username") or str(player.get("user_id", fallback))


def trade_keyboard(trade: dict) -> InlineKeyboardMarkup:
    trade_id = int(trade["id"])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🐾 Offer a Pet", callback_data=f"trade:petmenu:{trade_id}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"trade:view:{trade_id}"), InlineKeyboardButton("✅ Confirm", callback_data=f"trade:confirm:{trade_id}")],
        [InlineKeyboardButton("❌ Cancel Trade", callback_data=f"trade:cancel:{trade_id}")],
    ])


async def notify_user(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str, keyboard=None) -> bool:
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return True
    except (BadRequest, TelegramError) as exc:
        logger.info("Could not notify user %s: %s", user_id, exc)
        return False


def main_menu_text(player: dict) -> str:
    return (
        f"🐉 <b>{ui.esc(config.GAME_NAME)}</b>\n"
        f"<i>Five worlds. One multiverse. Become the ultimate legend.</i>\n\n"
        f"👤 <b>{ui.esc(player.get('first_name') or player.get('username') or 'Summoner')}</b>\n"
        f"🏅 Rank: <b>{ui.esc(player['rank'])}</b> • Level <b>{player['level']}</b>\n"
        f"🌍 Home: <b>{series_name(player.get('travel', 'dragonball'))}</b>\n\n"
        f"⚡ Stamina: {ui.percent_bar(player['stamina'], player['max_stamina'])}\n"
        f"💠 {ui.fmt(player['yens'])} Yens • 💎 {ui.fmt(player['gems'])} Gems\n"
        f"🔮 {ui.fmt(player['crystals'])} Crystals • 🎟️ {player['tickets']} Tickets\n\n"
        f"Use the menu below or /help for all commands."
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    text = (
        f"🐉 <b>WELCOME TO {ui.esc(config.GAME_NAME)}</b> 🐉\n\n"
        f"Choose your home series and begin your journey. Each week brings new banners, "
        f"raids, bosses, and clan wars across <b>Dragon Ball</b>, <b>Naruto</b>, "
        f"<b>Bleach</b>, <b>Jujutsu Kaisen</b>, and <b>Tempest</b>.\n\n"
        f"• Collect {len(data.CHARACTERS)} heroes and forms\n"
        f"• Summon by series with pity protection\n"
        f"• Hunt NPCs, bosses, world raids, and clan raids\n"
        f"• Build clans, trade, duel, and rule the arena\n\n"
        f"Pick a series to set your home world, then open the menu."
    )
    await respond(update, text, ui.series_keyboard("startseries"))


async def cmd_starter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    result = db.claim_starter_pack(update.effective_user.id)
    if not result.get("ok"):
        await respond(update, f"🎁 {ui.esc(result.get('reason', 'You already claimed your starter pack.'))}", ui.back_keyboard())
        return
    character = data.CHARACTERS.get(result["starter"], {})
    rarity = data.RARITIES.get(character.get("rarity", "common"), {})
    lines = [
        "🎁 <b>STARTER PACK CLAIMED!</b>",
        "",
        f"{rarity.get('emoji', '⚪')} <b>{ui.esc(character.get('name', result['starter']))}</b> — {ui.esc(rarity.get('name', 'Common'))}",
        f"💠 {ui.fmt(result['yens'])} Yens • 💎 {ui.fmt(result['gems'])} Gems • 🔮 {ui.fmt(result['crystals'])} Crystals",
        "",
        "Your new hero is already set as your main. Use /team to build your squad.",
    ]
    await respond(update, "\n".join(lines), ui.back_keyboard())


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    await respond(update, main_menu_text(player), ui.main_menu_keyboard())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 <b>COMMAND GUIDE</b>\n\n"
        "<b>⚔️ Combat & Progression</b>\n"
        "/hunt [series] — preview an NPC, then Battle or Flee\n/npc [series] — view NPC zones\n"
        "/boss [series] — choose a persistent series boss\n/elite — elite hunt\n/streak — NPC streak\n"
        "/raid or /global — world boss info\n/attack — attack the world boss\n"
        "/summonboss [series|boss_id] — summon and damage a persistent boss\n"
        "/clanraid [start|attack|info] — clan raid\n/arena — random PvP duel\n/duel &lt;id|@user&gt; — challenge a player\n\n"
        "<b>🎴 Heroes & Summoning</b>\n"
        "/gacha — banners by series\n/pull &lt;series|multiverse&gt; [10]\n/summon — alias for pull\n/wish [series] — use 7 Dragon Balls\n/starter — one-time starter hero and rewards\n/redeem &lt;code&gt; — claim a redeem code\n"
        "/characters [series] [rarity] [page]\n/character &lt;name/id&gt;\n/team &lt;id1&gt; &lt;id2&gt; &lt;id3&gt;\n"
        "/equipchar &lt;id&gt; • /levelup &lt;id&gt; [n]\n/awaken &lt;id&gt; • /fuse &lt;id&gt;\n"
        "/skills • /learn &lt;skill_id&gt; • /skill_equip &lt;skill_id&gt;\n"
        "/skillshop [series] • /skillbuy &lt;skill_id&gt;\n\n"
        "<b>🎒 Gear & Economy</b>\n"
        "/inventory • /use &lt;item&gt; [qty]\n/gear • /equip &lt;instance_id&gt; • /unequip &lt;slot&gt;\n"
        "/shop [potions|summon|materials|gear]\n/buy &lt;item_or_gear_id&gt; [qty]\n/sell &lt;item_id&gt; [qty]\n"
        "/daily_shop • /dailybuy &lt;slot&gt;\n/forge [recipe_id] • /craft [recipe_id] • /enhance &lt;slot|instance_id&gt;\n"
        "/market [page] • /market_sell &lt;item_id&gt; &lt;qty&gt; &lt;price&gt;\n/market_buy &lt;listing_id&gt; • /market_cancel &lt;listing_id&gt;\n"
        "/give &lt;user&gt; &lt;kind&gt; &lt;id|amount&gt; [qty] — send assets (or reply)\n"
        "/trade &lt;user|reply&gt; — pet trading with buttons • /trade add/remove/view/confirm/cancel\n\n"
        "<b>🏯 Clans & Quests</b>\n"
        "/clan • /clan_create &lt;name&gt; &lt;tag&gt; • /clan_join &lt;name|tag&gt; • /clan_leave\n"
        "/clan_info • /clan_donate &lt;yens|gems|crystals&gt; &lt;amount&gt;\n"
        "/clan_kick &lt;user&gt; • /clan_promote &lt;user&gt; • /clan_demote &lt;user&gt;\n"
        "/clan_announce &lt;text&gt; • /clan_disband\n"
        "/clan_invite &lt;user&gt; • /clan_add &lt;user&gt; • /clan_accept • /clan_transfer &lt;user&gt;\n"
        "/clan desc &lt;text&gt; • /clan open on|off • /clan minlevel &lt;level&gt;\n"
        "/clanraid_start &lt;raid_id&gt; • /clanraid_attack\n"
        "/quests [daily|weekly|monthly] • /claim [type]\n"
        "/achievements • /claimach • /titles • /title &lt;title_id&gt;\n\n"
        "<b>🌍 World & Profile</b>\n"
        "/profile • /stats • /daily • /weekly • /monthly\n"
        "/leaderboard [wealth|players|arena|clans|raid] — wealth/collection is page 1\n/wealth — shortcuts to wealth leaderboard • /collection — per-series collection progress\n"
        "/travel &lt;series&gt; or /switch &lt;series&gt; • /series • /codex • /events\n"
        "/chapters [series] • /chapter [series] [number] — story battles\n"
        "/explore — tap-through battle map • /heal — heal from a menu\n/stamina — restore stamina with drinks and crystals\n"
        "/inv — inventory buttons • /top — rankings • /unstuck — clear a stuck battle\n"
        "/pity — gacha pity • /petsummon [1|10|50] — gem companion summon\n/element — element chart • /crown — avatars and clan hall\n"
        "/banner • /settings • /about • /myid • /userid @user (or reply)\n\n"
    )
    if config.is_admin(update.effective_user.id):
        text += (
            "<b>🛠 Admin</b>\n"
            "/admin or /admin_help • /grant • /ban • /unban • /broadcast • /backup\n"
            "/crownart — hidden custom art manager • /upload TYPE NAME\n/createcode CODE rewards [uses=] [days=] — create redeem code\n/codes — list redeem codes\n"
            "/setlevel &lt;user&gt; &lt;level&gt; • /admin_heal &lt;user&gt; • /resetplayer &lt;user&gt;\n\n"
        )
    text += "<i>Most actions are also available as inline buttons.</i>"
    await respond(update, text, ui.back_keyboard())


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        f"🐉 <b>{ui.esc(config.GAME_NAME)}</b> v{config.GAME_VERSION}\n\n"
        f"A five-series anime RPG with <b>{len(data.CHARACTERS)}</b> collectible heroes and forms, "
        f"<b>{len(data.GEAR)}</b> gear pieces, <b>{len(data.SKILLS)}</b> skills, "
        f"<b>{len(data.BOSSES['dragonball']) * len(data.SERIES)}</b> series bosses, "
        f"world bosses, clan raids, quests, achievements, trading, and arena PvP.\n\n"
        f"Series: Dragon Ball • Naruto • Bleach • Jujutsu Kaisen • Tempest\n"
        f"Built for async Telegram with SQLite persistence."
    )
    await respond(update, text, ui.back_keyboard())


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        await respond(update, f"🆔 Your Telegram user ID: <code>{user.id}</code>")


async def cmd_userid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    reply = replied_user(update)
    query = context.args[0] if context.args else None
    if reply is not None:
        target = db.ensure_player(reply.id, reply.username, reply.first_name)
    elif query:
        target = db.find_player(query)
        if target is None:
            await respond(update, "❌ No player found with that ID or username.")
            return
    else:
        user = update.effective_user
        if user is None:
            return
        target = db.ensure_player(user.id, user.username, user.first_name)
    text = "\n".join([
        "🆔 <b>PLAYER LOOKUP</b>",
        "",
        f"👤 Name: <b>{ui.esc(display_name(target))}</b>",
        f"🔗 Username: {('@' + ui.esc(target['username'])) if target.get('username') else 'None'}",
        f"🆔 User ID: <code>{int(target['user_id'])}</code>",
        f"🏅 Rank: <b>{ui.esc(target.get('rank', 'Unknown'))}</b> • Level <b>{int(target.get('level', 1))}</b>",
        "",
        "Tip: /give or /trade also accept this ID or @username.",
    ])
    await respond(update, text, ui.back_keyboard())


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    series = parse_series(context.args[0]) if context.args else None
    if series is None:
        await respond(update, "Choose your home series:", ui.series_keyboard("startseries"))
        return
    db = get_db(context)
    before = db.characters(update.effective_user.id)
    player = db.register(update.effective_user.id, series, update.effective_user.username, update.effective_user.first_name)
    if len(before) == 1 and before[0]["series"] != series:
        starter = data.STARTER_CHARACTERS[series]
        db.add_character(update.effective_user.id, starter, level=5, stars=1)
        db.set_team(update.effective_user.id, [starter])
    await respond(
        update,
        f"✅ Home series set to {series_name(series)}.\nYour journey begins in <b>{data.SERIES[series]['home']}</b>.",
        ui.main_menu_keyboard(),
    )


def profile_text(db: Database, user_id: int) -> str:
    player = db.require_player(user_id)
    stats = game.effective_stats(db, user_id)
    characters = db.characters(user_id)
    team = db.team(user_id)
    by_id = {character["id"]: character for character in characters}
    team_names = " • ".join(ui.esc(by_id[cid]["name"]) for cid in team if cid in by_id) or "None"
    title = data.TITLES.get(player.get("title") or "", {})
    clan = db.clan(user_id)
    next_exp = db.exp_needed(int(player["level"]))
    collection = game.series_collection(db, user_id)
    collection_text = " • ".join(f"{data.SERIES[s]['emoji']}{collection.get(s, 0)}" for s in data.SERIES_ORDER)
    avatar = game.avatar_for(player)
    return (
        f"{avatar['icon']} <b>{ui.esc(player.get('first_name') or player.get('username') or 'Summoner')}</b>\n"
        f"🏅 {ui.esc(player['rank'])} • Level <b>{player['level']}</b>\n"
        f"✨ EXP: {ui.percent_bar(player['exp'], next_exp)} ({ui.fmt(player['exp'])}/{ui.fmt(next_exp)})\n"
        f"🌍 Home: {series_name(player.get('travel', 'dragonball'))}\n"
        f"⚡ Stamina: {ui.percent_bar(player['stamina'], player['max_stamina'])}\n\n"
        f"⚔️ <b>Combat Power</b> — {ui.fmt(game.power_score(stats))}\n"
        f"❤️ HP {ui.fmt(player.get('current_hp', stats['hp']))}/{ui.fmt(stats['hp'])} • 🔵 MP {ui.fmt(player.get('mp', stats['max_mp']))}/{ui.fmt(stats['max_mp'])}\n"
        f"⚔️ ATK {ui.fmt(stats['atk'])} • 🛡️ DEF {ui.fmt(stats['def'])} • 💨 SPD {ui.fmt(stats['spd'])}\n"
        f"💪 STR {stats['attributes']['strength']} • 🏃 AGI {stats['attributes']['agility']} • 🧠 INT {stats['attributes']['intellect']}\n"
        f"❤️‍🔥 VIT {stats['attributes']['vitality']} • 🍀 LUK {stats['attributes']['luck']} • 🎯 Stat Points: {player.get('stat_points', 0)}\n"
        f"🔮 Element: {data.ELEMENTS[stats['element']]['emoji']} {data.ELEMENTS[stats['element']]['name']}\n\n"
        f"🦸 Main: <b>{ui.esc(stats['name'])}</b>\n"
        f"👥 Team: {team_names}\n"
        f"👑 Avatar: {avatar['icon']} <b>{ui.esc(avatar['name'])}</b>\n"
        f"🏷️ Title: <b>{ui.esc(title.get('name', 'None'))}</b>\n"
        f"🐾 Companion: <b>{ui.esc(next((p['name'] for p in db.pets(user_id) if p.get('equipped')), 'None'))}</b>\n"
        f"🏯 Clan: <b>{ui.esc(clan['name'] if clan else 'None')}</b>\n\n"
        f"💠 {ui.fmt(player['yens'])} Yens • 💎 {ui.fmt(player['gems'])} Gems\n"
        f"🔮 {ui.fmt(player['crystals'])} Crystals • 🎟️ {player['tickets']} Tickets • 🧠 {player['skill_points']} SP\n"
        f"🎴 Collection: {len(characters)} heroes — {collection_text}\n"
        f"🎯 Pity: {player['pity']}/{config.GACHA_PITY} • ⚔️ {player['wins']}W/{player['losses']}L • 🏟️ {player['arena_rating']} rating"
    )


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    rows = [
        [InlineKeyboardButton("🎴 Summon", callback_data="menu:gacha"), InlineKeyboardButton("⚔️ Hunt", callback_data="menu:hunt")],
        [InlineKeyboardButton("💚 Heal", callback_data="menu:heal"), InlineKeyboardButton("🧭 Explore", callback_data="menu:explore")],
        [InlineKeyboardButton("📜 Quests", callback_data="menu:quests"), InlineKeyboardButton("🏆 Rankings", callback_data="menu:leaderboard")],
    ]
    if int(player.get("stat_points", 0) or 0) > 0:
        stat_buttons = [
            InlineKeyboardButton("+STR", callback_data="stat:strength"),
            InlineKeyboardButton("+AGI", callback_data="stat:agility"),
            InlineKeyboardButton("+INT", callback_data="stat:intellect"),
            InlineKeyboardButton("+VIT", callback_data="stat:vitality"),
            InlineKeyboardButton("+LUK", callback_data="stat:luck"),
        ]
        for index in range(0, len(stat_buttons), 2):
            rows.append(stat_buttons[index:index + 2])
    rows.append([InlineKeyboardButton("👑 Crown", callback_data="crown:view"), InlineKeyboardButton("🎴 Heroes", callback_data="chars:all:all:1")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    keyboard = InlineKeyboardMarkup(rows)
    player = db.require_player(update.effective_user.id)
    stats = game.effective_stats(db, update.effective_user.id)
    await respond(update, profile_text(db, update.effective_user.id), keyboard)


async def characters_view(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    series = None
    rarity = None
    page = 1
    for arg in args:
        token = arg.lower()
        if token.isdigit():
            page = max(1, int(token))
        elif token in data.SERIES:
            series = token
        elif token in data.RARITIES:
            rarity = token
        else:
            parsed = parse_series(token)
            if parsed:
                series = parsed
    owned = db.characters(update.effective_user.id)
    filtered = [c for c in owned if (not series or c["series"] == series) and (not rarity or c["rarity"] == rarity)]
    filtered.sort(key=lambda c: (-data.RARITY_INDEX[c["rarity"]], -c["power"], -c["level"], c["name"]))
    total_pages = max(1, (len(filtered) + 9) // 10)
    page = min(page, total_pages)
    page_items = filtered[(page - 1) * 10: page * 10]
    rarity_counts: dict[str, int] = {}
    for character in filtered:
        rarity_counts[character["rarity"]] = rarity_counts.get(character["rarity"], 0) + 1
    lines = [
        f"🎴 <b>YOUR HEROES</b> — {len(owned)} owned",
        f"📺 {series_name(series) if series else 'All series'} • "
        f"🏅 {data.RARITIES[rarity]['name'] if rarity else 'All rarity ranks'} • "
        f"Showing <b>{len(filtered)}</b>",
        "",
    ]
    if not page_items:
        lines.append("No heroes match this filter. Summon more with /gacha.")
    last_rarity = None
    for character in page_items:
        rarity_info = data.RARITIES[character["rarity"]]
        element_info = data.ELEMENTS[character["element"]]
        if character["rarity"] != last_rarity:
            if last_rarity is not None:
                lines.append("")
            lines.append(f"{rarity_info['emoji']} <b>{rarity_info['name'].upper()}</b> — {rarity_counts.get(character['rarity'], 0)} heroes")
            last_rarity = character["rarity"]
        power = game.power_score(game.scaled_character(character))
        lines.append(
            f"{rarity_info['emoji']} {element_info['emoji']} <b>{ui.esc(character['name'])}</b> "
            f"Lv.{character['level']} ⭐{character['stars']}"
        )
        lines.append(
            f"   ⚔️ Power <b>{ui.fmt(power)}</b> • 📺 {ui.esc(data.SERIES[character['series']]['name'])}\n"
            f"   🆔 <code>{character['id']}</code>"
        )
    lines.extend(["", f"Page {page}/{total_pages} • Use /character &lt;id&gt; for details."])
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    series_buttons = [InlineKeyboardButton("🌐 All Series", callback_data=f"chars:all:{rarity or 'all'}:1")]
    series_buttons.extend(
        InlineKeyboardButton(
            f"{data.SERIES[s]['emoji']} {data.SERIES[s]['short']}",
            callback_data=f"chars:{s}:{rarity or 'all'}:1",
        )
        for s in data.SERIES_ORDER
    )
    for index in range(0, len(series_buttons), 3):
        keyboard_rows.append(series_buttons[index:index + 3])
    rarity_buttons = [InlineKeyboardButton("🏅 All Ranks", callback_data=f"chars:{series or 'all'}:all:1")]
    rarity_buttons.extend(
        InlineKeyboardButton(
            f"{data.RARITIES[r]['emoji']} {data.RARITIES[r]['name']}",
            callback_data=f"chars:{series or 'all'}:{r}:1",
        )
        for r in reversed(data.RARITY_ORDER)
    )
    for index in range(0, len(rarity_buttons), 4):
        keyboard_rows.append(rarity_buttons[index:index + 4])
    for character in page_items:
        keyboard_rows.append([InlineKeyboardButton(
            f"{data.RARITIES[character['rarity']]['emoji']} {character['name']} • Lv.{character['level']}",
            callback_data=f"char:view:{character['id']}",
        )])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"chars:{series or 'all'}:{rarity or 'all'}:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"chars:{series or 'all'}:{rarity or 'all'}:{page + 1}"))
    if nav:
        keyboard_rows.append(nav)
    keyboard_rows.append([InlineKeyboardButton("👥 Team", callback_data="team:view"), InlineKeyboardButton("👑 Crown", callback_data="crown:view")])
    keyboard_rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(keyboard_rows))


async def cmd_characters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await characters_view(update, context, context.args)


async def character_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    owned = db.characters(update.effective_user.id)
    found = next((c for c in owned if c["id"].lower() == query.lower()), None)
    if found is None:
        found = next((c for c in owned if query.lower() in c["name"].lower()), None)
    if found is None:
        await respond(update, "Hero not found in your roster. Use /characters to browse.")
        return
    stats = game.scaled_character(found)
    element = data.ELEMENTS[found["element"]]
    rarity = data.RARITIES[found["rarity"]]
    skills = ", ".join(ui.esc(data.SKILLS[sid]["name"]) for sid in found["skills"] if sid in data.SKILLS)
    shards = db.shards(update.effective_user.id, found["id"])
    text = (
        f"{rarity['emoji']} <b>{ui.esc(found['name'])}</b>\n"
        f"{element['emoji']} {element['name']} • {rarity['name']} • {series_name(found['series'])}\n"
        f"Form: {ui.esc(found['form'])} • Base power {found['power']}\n\n"
        f"⭐ Stars: {found['stars']}/6 • Level: {found['level']}/100\n"
        f"❤️ HP {ui.fmt(stats['hp'])} • 🗡️ ATK {ui.fmt(stats['atk'])}\n"
        f"🛡️ DEF {ui.fmt(stats['def'])} • 💨 SPD {ui.fmt(stats['spd'])}\n"
        f"🧩 Shards: {shards}\n"
        f"✨ Skills: {skills or 'None'}\n\n"
        f"<code>{found['id']}</code>"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Equip", callback_data=f"char:equip:{found['id']}"), InlineKeyboardButton("⬆️ Level Up", callback_data=f"char:level:{found['id']}")],
        [InlineKeyboardButton("⭐ Awaken", callback_data=f"char:awaken:{found['id']}"), InlineKeyboardButton("🎒 Heroes", callback_data="chars:all:all:1")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ])
    await respond(update, text, keyboard)


async def cmd_character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await characters_view(update, context, [])
        return
    await character_detail(update, context, " ".join(context.args))


async def team_view(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    series: str | None = None,
    rarity: str | None = None,
    page: int = 1,
) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    characters = db.characters(update.effective_user.id)
    by_id = {character["id"]: character for character in characters}
    team = [cid for cid in db.team(update.effective_user.id) if cid in by_id]
    lines = ["👥 <b>ACTIVE BATTLE TEAM</b>", f"Slots: <b>{len(team)}/{config.MAX_TEAM}</b>", ""]
    combined_power = 0
    for slot in range(config.MAX_TEAM):
        if slot < len(team):
            character = by_id[team[slot]]
            combined_power += game.power_score(game.scaled_character(character))
            marker = "🟢" if slot == 0 else "🔵"
            role = " (Main)" if slot == 0 else ""
            lines.append(
                f"{marker} <b>Slot {slot + 1}{role}</b>\n"
                f"   {data.RARITIES[character['rarity']]['emoji']} <b>{ui.esc(character['name'])}</b> "
                f"Lv.{character['level']} ⭐{character['stars']} • ⚔️ {ui.fmt(game.power_score(game.scaled_character(character)))}"
            )
        else:
            lines.append(f"⚫ <b>Slot {slot + 1}</b> — <i>Empty</i>")
    lines.append("")
    lines.append(f"⚔️ <b>Combined Power:</b> {ui.fmt(combined_power)}")
    lines.append("Use ⬆️ and ⬇️ to swap slots. Slot 1 is your main hero.")
    lines.append("")
    lines.append(
        f"📋 <b>Your Heroes</b> — {series_name(series) if series else 'All series'} • "
        f"{data.RARITIES[rarity]['name'] if rarity else 'All ranks'}"
    )
    rows = []
    for index, cid in enumerate(team, 1):
        name = by_id[cid]["name"]
        if index > 1:
            rows.append([
                InlineKeyboardButton("⬆️", callback_data=f"team:up:{cid}"),
                InlineKeyboardButton(f"Slot {index}", callback_data=f"team:view:{cid}"),
                InlineKeyboardButton("➖", callback_data=f"team:remove:{cid}"),
            ])
        else:
            rows.append([
                InlineKeyboardButton("⭐ Main", callback_data="team:view"),
                InlineKeyboardButton("⬇️", callback_data=f"team:down:{cid}"),
                InlineKeyboardButton("➖", callback_data=f"team:remove:{cid}"),
            ])
    available = [
        c for c in characters
        if c["id"] not in team
        and (not series or c["series"] == series)
        and (not rarity or c["rarity"] == rarity)
    ]
    available.sort(key=lambda c: (-data.RARITY_INDEX[c["rarity"]], -c["power"], -c["level"], c["name"]))
    series_buttons = [InlineKeyboardButton("🌐 All Series", callback_data=f"team:filter:all:{rarity or 'all'}")]
    series_buttons.extend(
        InlineKeyboardButton(
            f"{data.SERIES[s]['emoji']} {data.SERIES[s]['short']}",
            callback_data=f"team:filter:{s}:{rarity or 'all'}",
        )
        for s in data.SERIES_ORDER
    )
    for index in range(0, len(series_buttons), 3):
        rows.append(series_buttons[index:index + 3])
    rarity_buttons = [InlineKeyboardButton("🏅 All Ranks", callback_data=f"team:filter:{series or 'all'}:all")]
    rarity_buttons.extend(
        InlineKeyboardButton(
            f"{data.RARITIES[r]['emoji']} {data.RARITIES[r]['name']}",
            callback_data=f"team:filter:{series or 'all'}:{r}",
        )
        for r in reversed(data.RARITY_ORDER)
    )
    for index in range(0, len(rarity_buttons), 4):
        rows.append(rarity_buttons[index:index + 4])
    total_pages = max(1, (len(available) + 19) // 20)
    page = min(max(1, page), total_pages)
    page_items = available[(page - 1) * 20:page * 20]
    lines.append(f"<i>Page {page}/{total_pages} • {len(available)} available</i>")
    add_buttons = [
        InlineKeyboardButton(
            f"➕ {c['name']} Lv.{c['level']}",
            callback_data=f"team:add:{c['id']}",
        )
        for c in page_items
    ]
    for index in range(0, len(add_buttons), 2):
        rows.append(add_buttons[index:index + 2])
    if not available:
        lines.append("<i>No available heroes match this filter.</i>")
    else:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"team:filter:{series or 'all'}:{rarity or 'all'}:{page - 1}"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"team:filter:{series or 'all'}:{rarity or 'all'}:{page + 1}"))
        if nav:
            rows.append(nav)
    rows.append([InlineKeyboardButton("🧹 Clear Team", callback_data="team:clear"), InlineKeyboardButton("🎴 Heroes", callback_data="chars:all:all:1")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    if not context.args:
        await team_view(update, context)
        return
    result = db.set_team(update.effective_user.id, context.args[: config.MAX_TEAM])
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    names = ", ".join(ui.esc(next(c["name"] for c in db.characters(update.effective_user.id) if c["id"] == cid)) for cid in result["team"])
    await respond(update, f"✅ Team updated: {names}", ui.main_menu_keyboard())


PICK_TITLES = {
    "setmain": "⚔️ Choose your main hero",
    "level": "⬆️ Choose a hero to level up",
    "awaken": "⭐ Choose a hero to awaken",
}


async def hero_picker(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action: str,
    title: str,
    series: str | None = None,
    rarity: str | None = None,
    page: int = 1,
) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    characters = db.characters(update.effective_user.id)
    if not characters:
        await respond(update, "You have no heroes yet. Summon with /gacha.")
        return
    filtered = [c for c in characters if (not series or c["series"] == series) and (not rarity or c["rarity"] == rarity)]
    filtered.sort(key=lambda c: (-data.RARITY_INDEX[c["rarity"]], -c["power"], -c["level"], c["name"]))
    total_pages = max(1, (len(filtered) + 19) // 20)
    page = min(max(1, page), total_pages)
    page_items = filtered[(page - 1) * 20:page * 20]
    lines = [
        title,
        f"📺 {series_name(series) if series else 'All series'} • "
        f"🏅 {data.RARITIES[rarity]['name'] if rarity else 'All rarity ranks'} • "
        f"Showing <b>{len(filtered)}</b> • Page {page}/{total_pages}",
        "",
    ]
    if not page_items:
        lines.append("No heroes match this filter.")
    else:
        last_rarity = None
        for character in page_items:
            if character["rarity"] != last_rarity:
                if last_rarity is not None:
                    lines.append("")
                info = data.RARITIES[character["rarity"]]
                lines.append(f"{info['emoji']} <b>{info['name'].upper()}</b>")
                last_rarity = character["rarity"]
            lines.append(
                f"• {data.RARITIES[character['rarity']]['emoji']} <b>{ui.esc(character['name'])}</b> "
                f"Lv.{character['level']} ⭐{character['stars']}"
            )
    lines.append("")
    lines.append("Tap a hero below. Use the filters to browse by series and rarity rank.")
    rows: list[list[InlineKeyboardButton]] = []
    for character in page_items:
        rows.append([InlineKeyboardButton(
            f"{data.RARITIES[character['rarity']]['emoji']} {character['name']} Lv.{character['level']}",
            callback_data=f"char:{action}:{character['id']}",
        )])
    series_buttons = [InlineKeyboardButton("🌐 All Series", callback_data=f"pick:{action}:all:{rarity or 'all'}:1")]
    series_buttons.extend(
        InlineKeyboardButton(
            f"{data.SERIES[s]['emoji']} {data.SERIES[s]['short']}",
            callback_data=f"pick:{action}:{s}:{rarity or 'all'}:1",
        )
        for s in data.SERIES_ORDER
    )
    for index in range(0, len(series_buttons), 3):
        rows.append(series_buttons[index:index + 3])
    rarity_buttons = [InlineKeyboardButton("🏅 All Ranks", callback_data=f"pick:{action}:{series or 'all'}:all:1")]
    rarity_buttons.extend(
        InlineKeyboardButton(
            f"{data.RARITIES[r]['emoji']} {data.RARITIES[r]['name']}",
            callback_data=f"pick:{action}:{series or 'all'}:{r}:1",
        )
        for r in reversed(data.RARITY_ORDER)
    )
    for index in range(0, len(rarity_buttons), 4):
        rows.append(rarity_buttons[index:index + 4])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"pick:{action}:{series or 'all'}:{rarity or 'all'}:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"pick:{action}:{series or 'all'}:{rarity or 'all'}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🎴 All Heroes", callback_data="chars:all:all:1"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_equipchar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if not context.args:
        await hero_picker(update, context, "setmain", "⚔️ Choose your main hero")
        return
    db = get_db(context)
    if db.equip_character(update.effective_user.id, context.args[0]):
        await respond(update, f"✅ Main hero set to <code>{ui.esc(context.args[0])}</code>.")
    else:
        await respond(update, "❌ You do not own that hero.")


async def cmd_levelup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if not context.args:
        await hero_picker(update, context, "level", "⬆️ Choose a hero to level up")
        return
    db = get_db(context)
    levels = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
    result = db.level_character(update.effective_user.id, context.args[0], levels)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"⬆️ Hero reached level <b>{result['level']}</b> for 💠 {ui.fmt(result['cost'])} yens.")


async def cmd_awaken(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if not context.args:
        await hero_picker(update, context, "awaken", "⭐ Choose a hero to awaken")
        return
    db = get_db(context)
    result = db.awaken_character(update.effective_user.id, context.args[0])
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"⭐ Hero awakened to <b>{result['stars']} stars</b>! Used {result['cost']} shards.")


async def cmd_skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    learned = db.skills(update.effective_user.id)
    equipped_count = sum(1 for skill in learned if skill["equipped"])
    lines = [
        "🧠 <b>SKILL CODEX</b>",
        f"🔹 Skill Points: <b>{player['skill_points']}</b> • ✅ Equipped: <b>{equipped_count}/3</b> • 📚 Learned: <b>{len(learned)}</b>",
        "",
    ]

    def add_grouped(skills: list[dict], title: str) -> None:
        if not skills:
            return
        lines.append(title)
        grouped: dict[str, list[dict]] = {tag: [] for tag in game.SKILL_TAG_ORDER}
        for skill in skills:
            tags = game.skill_tags(skill)
            grouped.setdefault(tags[0], []).append(skill)
        tag_icons = {
            "REGENERATION": "💚", "DEFENSE": "🛡️", "LUCK": "🍀",
            "DROP RATE": "💰", "PULL RATE": "🎟️", "ATTACK": "⚔️",
        }
        for tag in game.SKILL_TAG_ORDER:
            group = grouped.get(tag, [])
            if not group:
                continue
            lines.append(f"{tag_icons.get(tag, '•')} <b>{tag}</b>")
            for skill in group:
                status = "✅" if skill.get("equipped") else "⚪"
                cost = int(skill.get("cost", 0) or 0)
                cost_text = f" • {cost} MP" if skill.get("type") == "active" and cost else ""
                all_tags = " • ".join(game.skill_tags(skill))
                lines.append(
                    f"{status} <b>{ui.esc(skill['name'])}</b> "
                    f"[{ui.esc(str(skill['element']).upper())}]{cost_text} • {ui.esc(all_tags)}\n"
                    f"   {ui.esc(game.skill_effect(skill))} • <code>{skill['id']}</code>"
                )
            lines.append("")

    add_grouped(learned, "📖 <b>Your Learned Skills</b>")
    if not learned:
        lines.append("No skills learned yet. Learn one from the catalog below.")
        lines.append("")
    learned_ids = {skill["id"] for skill in learned}
    catalog = [skill for skill in data.SKILLS.values() if skill.get("type") == "active" and skill["id"] not in learned_ids]
    sample: list[dict] = []
    seen_tags: set[str] = set()
    for skill in catalog:
        primary = game.skill_tags(skill)[0]
        if primary not in seen_tags:
            sample.append(skill)
            seen_tags.add(primary)
        if len(sample) >= 8:
            break
    if len(sample) < 8:
        for skill in catalog:
            if skill not in sample:
                sample.append(skill)
            if len(sample) >= 8:
                break
    add_grouped(sample, "📚 <b>Skill Catalog</b> — tap to learn")
    lines.append("At most <b>3</b> active skills can be equipped for battle.")
    rows = []
    equip_buttons = [
        InlineKeyboardButton(
            ("✅ " if skill["equipped"] else "⚪ ") + skill["name"],
            callback_data=f"skill:equip:{skill['id']}",
        )
        for skill in learned
    ]
    for index in range(0, len(equip_buttons), 2):
        rows.append(equip_buttons[index:index + 2])
    learn_buttons = [
        InlineKeyboardButton(f"📚 {skill['name']}", callback_data=f"skill:learn:{skill['id']}")
        for skill in sample
    ]
    for index in range(0, len(learn_buttons), 2):
        rows.append(learn_buttons[index:index + 2])
    rows.append([InlineKeyboardButton("🛒 Skill Shop", callback_data="menu:skillshop"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_learn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args:
        if player:
            await respond(update, "Usage: /learn &lt;skill_id&gt;")
        return
    db = get_db(context)
    result = db.learn_skill(update.effective_user.id, context.args[0])
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"✅ Learned <b>{ui.esc(result['skill']['name'])}</b>!")


async def cmd_skill_equip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if not context.args:
        await cmd_skills(update, context)
        return
    db = get_db(context)
    result = db.equip_skill(update.effective_user.id, context.args[0])
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"{'✅ Equipped' if result['equipped'] else '⚪ Unequipped'} skill.")


async def inventory_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    items = db.items(update.effective_user.id)
    gear = db.gear(update.effective_user.id)
    lines = ["🎒 <b>INVENTORY</b>", ""]
    lines.append(f"💠 {ui.fmt(player['yens'])} Yens • 💎 {ui.fmt(player['gems'])} Gems • 🔮 {ui.fmt(player['crystals'])} Crystals")
    lines.append("")
    lines.append("🧪 <b>Items</b>")
    if items:
        for item in items[:20]:
            lines.append(f"{item['emoji']} {ui.esc(item['name'])} x{item['qty']} — <code>{item['item_id']}</code>")
    else:
        lines.append("No items.")
    lines.extend(["", "⚙️ <b>Gear</b>"])
    if gear:
        for item in gear[:12]:
            slot = f" [equipped: {item['equipped_slot']}]" if item.get("equipped_slot") else ""
            lines.append(f"{data.RARITIES[item['rarity']]['emoji']} {ui.esc(item['name'])} Lv.{item['level']}{slot} — <code>{item['instance_id']}</code>")
    else:
        lines.append("No gear.")
    pets = db.pets(update.effective_user.id)
    lines.extend(["", "🐾 <b>Companions</b>"])
    if pets:
        for pet in pets[:8]:
            lines.append(f"{pet['emoji']} {ui.esc(pet['name'])} Lv.{pet['level']}{' • equipped' if pet.get('equipped') else ''}")
    else:
        lines.append("No companions. Hatch one with /pet_summon.")
    lines.append("\nTap an item to use or sell, or tap gear to equip. Commands still work: /use &lt;item_id&gt;, /equip &lt;instance_id&gt;.")
    rows = []
    for item in items[:8]:
        rows.append([
            InlineKeyboardButton(f"{item['emoji']} Use {item['name']}", callback_data=f"inv:use:{item['item_id']}"),
            InlineKeyboardButton("💠 Sell", callback_data=f"inv:sell:{item['item_id']}"),
        ])
    for item in gear[:8]:
        label = f"⚙️ {item['name']} Lv.{item['level']}"
        if item.get("equipped_slot"):
            rows.append([InlineKeyboardButton(f"⚪ Unequip {item['name']}", callback_data=f"inv:unequip:{item['equipped_slot']}")])
        else:
            rows.append([InlineKeyboardButton(label, callback_data=f"inv:equip:{item['instance_id']}")])
    rows.append([InlineKeyboardButton("🛒 Shop", callback_data="menu:shop"), InlineKeyboardButton("💚 Heal", callback_data="menu:heal")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await inventory_view(update, context)


async def cmd_use(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args:
        if player:
            await respond(update, "Usage: /use &lt;item_id&gt; [qty]")
        return
    db = get_db(context)
    qty = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
    result = game.use_item(db, update.effective_user.id, context.args[0], qty)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"{result.get('item', {}).get('emoji', '✅')} {ui.esc(result.get('message', 'Item used.'))}")


async def cmd_gear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await inventory_view(update, context)


async def cmd_equip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args:
        if player:
            await respond(update, "Usage: /equip &lt;gear_instance_id&gt;")
        return
    db = get_db(context)
    if not context.args[0].isdigit():
        await respond(update, "Gear instance IDs are numbers shown in /inventory.")
        return
    result = db.equip_gear(update.effective_user.id, int(context.args[0]))
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"✅ Equipped <b>{ui.esc(result['item']['name'])}</b> in {result['slot']} slot.")


async def cmd_unequip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args:
        if player:
            await respond(update, "Usage: /unequip &lt;weapon|armor|accessory&gt;")
        return
    db = get_db(context)
    if db.unequip_gear(update.effective_user.id, context.args[0].lower()):
        await respond(update, "✅ Gear unequipped.")
    else:
        await respond(update, "❌ Invalid slot.")


async def gacha_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    lines = [
        "🎴 <b>SUMMON BANNERS</b>",
        f"🎟️ Tickets: {player['tickets']} • 💎 Gems: {ui.fmt(player['gems'])} • 🎯 Pity: {player['pity']}/{config.GACHA_PITY}",
        "",
    ]
    for banner in data.GACHA_BANNERS.values():
        featured = ", ".join(ui.esc(data.CHARACTERS[cid]["name"]) for cid in banner["featured"][:3] if cid in data.CHARACTERS)
        lines.append(f"{banner['emoji']} <b>{ui.esc(banner['name'])}</b>\n   Featured: {featured or 'Mixed pool'}")
    lines.append("\nTap a banner or use /pull &lt;series&gt; [10].")
    await respond(update, "\n".join(lines), ui.gacha_keyboard())


async def cmd_gacha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await gacha_view(update, context)


async def banner_view(update: Update, context: ContextTypes.DEFAULT_TYPE, series: str) -> None:
    banner = data.GACHA_BANNERS.get(series)
    if banner is None:
        await respond(update, "Unknown banner.", ui.gacha_keyboard())
        return
    lines = [
        f"{banner['emoji']} <b>{ui.esc(banner['name'])}</b>",
        f"<i>{ui.esc(banner['description'])}</i>",
        "",
        "⭐ Featured:",
    ]
    for char_id in banner["featured"]:
        character = data.CHARACTERS.get(char_id)
        if not character:
            continue
        rarity = data.RARITIES[character["rarity"]]
        lines.append(f"{rarity['emoji']} {ui.esc(character['name'])} — {character['rarity'].title()}")
    lines.extend([
        "",
        f"🎯 Pity: {config.GACHA_PITY} pulls guarantees Mythic or Divine.",
        f"Cost: 1 ticket or {config.GACHA_COST_GEMS} gems; 10x = 10 tickets or {config.GACHA_MULTI_COST_GEMS} gems.",
    ])
    await respond(update, "\n".join(lines), ui.banner_keyboard(series))


async def do_pull(update: Update, context: ContextTypes.DEFAULT_TYPE, series: str, count: int) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    series = parse_series(series) or series
    if series not in data.GACHA_BANNERS:
        await respond(update, "Unknown banner. Use /gacha.")
        return
    result = game.gacha(db, update.effective_user.id, series, count)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    lines = [f"{result['banner']['emoji']} <b>{ui.esc(result['banner']['name'])}</b>", f"Paid with {result['payment']}.", ""]
    for item in result["results"]:
        character = item["character"]
        rarity = data.RARITIES[character["rarity"]]
        tag = "🆕 NEW" if item["new"] else f"💠 +{item['gems']} gems, +{item['shards']} shards"
        lines.append(f"{rarity['emoji']} <b>{ui.esc(character['name'])}</b> — {rarity['name']} · {tag}")
    lines.extend(["", f"🎯 Pity: {result['pity']}/{config.GACHA_PITY}"])
    await respond(update, "\n".join(lines), ui.banner_keyboard(series))
    if result["results"]:
        card = result["results"][0]["character"]


async def cmd_pull(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    series = parse_series(context.args[0]) if context.args else "multiverse"
    count = 10 if len(context.args) > 1 and context.args[1].lower() in ("10", "x10", "multi") else 1
    if not context.args:
        await gacha_view(update, context)
        return
    await do_pull(update, context, series or context.args[0], count)


async def cmd_summon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_pull(update, context)


async def cmd_wish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    series = parse_series(context.args[0]) if context.args else None
    result = game.wish(db, update.effective_user.id, series)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}\nDragon Balls: {db.dragon_ball_count(update.effective_user.id)}/7")
        return
    character = result["character"]
    await respond(update, f"🐉 <b>SHENRON GRANTS YOUR WISH!</b>\n\n{ui.char_summary({**character, 'level': 1, 'stars': 1})}\n{'🆕 New hero!' if result['new'] else 'Duplicate converted into shards.'}", ui.main_menu_keyboard())


async def shop_view(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str = "all", page: int = 1) -> None:
    player = await guard(update, context)
    if player is None:
        return
    category = (category or "all").lower()
    if category == "daily":
        offers = game.daily_shop(get_db(context))
        lines = ["🌅 <b>DAILY SHOP</b>", ""]
        rows = []
        for offer in offers:
            lines.append(f"{offer['slot']}. {offer['emoji']} <b>{ui.esc(offer['name'])}</b> — {ui.fmt(offer['price'])} {offer['currency']} (-{int(offer['discount'] * 100)}%)")
            rows.append([InlineKeyboardButton(f"{offer['emoji']} Buy {offer['name']} — {ui.fmt(offer['price'])} {offer['currency']}", callback_data=f"shop:dailybuy:{offer['slot']}")])
        rows.extend(ui.shop_keyboard().inline_keyboard)
        await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))
        return
    labels = {"all": "All Items", "potions": "Potions", "summon": "Summoning", "materials": "Materials", "gear": "Gear"}
    if category not in labels:
        category = "all"
    entries = game.shop_catalog(category)
    per_page = 8
    total_pages = max(1, (len(entries) + per_page - 1) // per_page)
    page = max(1, min(int(page or 1), total_pages))
    start_index = (page - 1) * per_page
    page_entries = entries[start_index:start_index + per_page]
    lines = [f"🛒 <b>SHOP — {labels[category].upper()}</b>", f"Page <b>{page}/{total_pages}</b> • {len(entries)} items", ""]
    if not page_entries:
        lines.append("No items in this category.")
    for entry in page_entries:
        lines.append(f"{entry['emoji']} <b>{ui.esc(entry['name'])}</b> — {ui.fmt(entry['price'])} {entry['currency']}\n   <code>{entry['id']}</code> • {ui.esc(entry['desc'])}")
    lines.append("\nTap an item to choose quantity, or use /buy &lt;id&gt; [qty].")
    rows = []
    for entry in page_entries:
        rows.append([InlineKeyboardButton(f"{entry['emoji']} {entry['name']} — {ui.fmt(entry['price'])} {entry['currency']}", callback_data=f"shop:item:{entry['id']}:{category}:{page}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"shop:page:{category}:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"shop:page:{category}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.extend(ui.shop_keyboard().inline_keyboard)
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def show_shop_item(update: Update, context: ContextTypes.DEFAULT_TYPE, item_id: str, category: str = "all", page: int = 1) -> None:
    player = await guard(update, context)
    if player is None:
        return
    entry = next((row for row in game.shop_catalog("all") if row["id"] == item_id), None)
    if entry is None:
        await respond(update, "❌ Item not found.", ui.back_keyboard("menu:shop"))
        return
    lines = [
        f"{entry['emoji']} <b>{ui.esc(entry['name'])}</b>",
        f"💰 {ui.fmt(entry['price'])} {entry['currency']} each",
        f"📦 {ui.esc(entry['desc'])}",
        "",
        "Choose a quantity:",
    ]
    rows = []
    quantities = [1] if entry["kind"] == "gear" else [1, 10, 50]
    for qty in quantities:
        rows.append([InlineKeyboardButton(f"🛒 Buy {qty}", callback_data=f"shop:buy:{item_id}:{qty}")])
    rows.append([InlineKeyboardButton("⬅️ Back to Shop", callback_data=f"shop:page:{category}:{page}")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    category = context.args[0].lower() if context.args else "all"
    page = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
    await shop_view(update, context, category, page)


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args:
        if player:
            await respond(update, "Usage: /buy &lt;item_or_gear_id&gt; [qty]")
        return
    db = get_db(context)
    qty = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
    result = game.buy_shop(db, update.effective_user.id, context.args[0], qty)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"✅ Bought <b>{ui.esc(result['name'])}</b> x{result['qty']} for {ui.fmt(result['price'])} {result['currency']}.")


async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args:
        if player:
            await respond(update, "Usage: /sell &lt;item_id&gt; [qty]")
        return
    db = get_db(context)
    qty = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
    result = game.sell_item(db, update.effective_user.id, context.args[0], qty)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"✅ Sold {ui.esc(result['name'])} x{result['qty']} for 💠 {ui.fmt(result['yens'])} yens.")


async def cmd_daily_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await shop_view(update, context, "daily")


async def cmd_dailybuy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args or not context.args[0].isdigit():
        if player:
            await respond(update, "Usage: /dailybuy &lt;slot 1-6&gt;")
        return
    result = game.buy_daily(get_db(context), update.effective_user.id, int(context.args[0]))
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    offer = result["offer"]
    await respond(update, f"✅ Bought {offer['emoji']} <b>{ui.esc(offer['name'])}</b> for {ui.fmt(offer['price'])} {offer['currency']}.")


async def forge_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    lines = ["⚙️ <b>FORGE RECIPES</b>", ""]
    for recipe in data.CRAFTING_RECIPES:
        gear = data.GEAR[recipe["result"]]
        cost = ", ".join(f"{qty}x {data.ITEMS[key]['name'] if key in data.ITEMS else key}" for key, qty in recipe["cost"].items())
        lines.append(f"• <b>{ui.esc(gear['name'])}</b> — <code>{recipe['id']}</code>\n   Cost: {ui.esc(cost)}")
    lines.append("\nUse /forge &lt;recipe_id&gt; or /craft &lt;recipe_id&gt;.")
    await respond(update, "\n".join(lines), ui.back_keyboard())


async def cmd_forge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await forge_view(update, context)
        return
    player = await guard(update, context)
    if player is None:
        return
    result = game.craft(get_db(context), update.effective_user.id, context.args[0])
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"⚙️ Forged <b>{ui.esc(result['gear']['name'])}</b>! Instance #{result['instance_id']}.")


async def cmd_craft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_forge(update, context)


async def cmd_enhance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args:
        if player:
            await respond(update, "Usage: /enhance &lt;weapon|armor|accessory|gear_instance_id&gt;")
        return
    db = get_db(context)
    value = context.args[0].lower()
    if value in ("weapon", "armor", "accessory"):
        field = player.get(value)
        if not field:
            await respond(update, "❌ No gear equipped in that slot.")
            return
        instance_id = int(field)
    elif value.isdigit():
        instance_id = int(value)
    else:
        await respond(update, "Usage: /enhance &lt;slot|instance_id&gt;")
        return
    result = db.enhance_gear(update.effective_user.id, instance_id)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"⚙️ Gear enhanced to level <b>{result['level']}</b> for 💠 {ui.fmt(result['cost'])} yens.")


def hunt_candidate(db: Database, user_id: int, series: str, npc_query: str | None = None) -> dict:
    player = db.require_player(user_id)
    npcs = data.NPCS.get(series) or data.NPCS["dragonball"]
    if npc_query:
        found = next((npc for npc in npcs if npc["id"].lower() == npc_query.lower()), None)
        found = found or next((npc for npc in npcs if npc_query.lower() in npc["name"].lower()), None)
        if found is not None:
            return found
    limit = max(1, min(len(npcs), 1 + int(player["level"]) // 12))
    return random.choice(npcs[:limit])


async def hunt_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    args = list(context.args)
    series = parse_series(args[0]) if args and parse_series(args[0]) else player.get("travel", "dragonball")
    npc_query = args[1] if args and parse_series(args[0]) and len(args) > 1 else (args[0] if args and not parse_series(args[0]) else None)
    npc = hunt_candidate(db, update.effective_user.id, series, npc_query)
    info = data.SERIES[series]
    stamina = int(player["stamina"])
    lines = [
        f"{info['emoji']} <b>HUNT — {ui.esc(info['home'])}</b>",
        "",
        f"👹 <b>{ui.esc(npc['name'])}</b> Lv.{npc['level']}",
        f"{data.ELEMENTS[npc['element']]['emoji']} Element: {npc['element'].title()}",
        f"❤️ HP: {ui.fmt(npc['hp'])} • ⚔️ ATK: {ui.fmt(npc['atk'])} • 🛡️ DEF: {ui.fmt(npc['def'])}",
        f"🎁 Reward: {ui.fmt(npc['exp'])} EXP • {ui.fmt(npc['yens'])} yens • {npc['gems']} gems",
        "",
        f"⚡ Stamina: {stamina}/{player['max_stamina']} • Cost: 8",
        "",
        "Do you want to battle this NPC?",
    ]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Battle NPC", callback_data=f"hunt:fight:{series}:{npc['id']}")],
        [InlineKeyboardButton("🎲 Find Another", callback_data=f"hunt:reroll:{series}"), InlineKeyboardButton("🏃 Flee", callback_data="hunt:flee")],
        [InlineKeyboardButton("👹 Bosses", callback_data=f"boss:view:{series}"), InlineKeyboardButton("🌍 Travel", callback_data="menu:travel")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ])
    await respond(update, "\n".join(lines), keyboard)


async def cmd_hunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and context.args[0].lower() in ("start", "fight", "random"):
        context.args = context.args[1:]
        series = parse_series(context.args[0]) if context.args else None
        await start_battle(update, context, "hunt", series=series)
        return
    await hunt_view(update, context)


async def cmd_adventure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_hunt(update, context)


async def cmd_npc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    series = parse_series(context.args[0]) if context.args else "dragonball"
    if series not in data.SERIES:
        series = "dragonball"
    lines = [f"🗺️ <b>{series_name(series)} Hunting Zones</b>", ""]
    for npc in data.NPCS[series]:
        lines.append(f"👹 <b>{ui.esc(npc['name'])}</b> — Lv.{npc['level']} • {data.ELEMENTS[npc['element']]['emoji']} • {ui.fmt(npc['hp'])} HP")
    lines.append("\nUse /hunt &lt;series&gt; to preview a zone enemy, then tap Battle or Flee.")
    await respond(update, "\n".join(lines), ui.back_keyboard())


async def boss_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    args = list(context.args)
    series = parse_series(args[0]) if args and parse_series(args[0]) else player.get("travel", "dragonball")
    bosses = data.BOSSES.get(series, [])
    info = data.SERIES[series]
    lines = [
        f"{info['emoji']} <b>BOSSES — {ui.esc(info['home'])}</b>",
        "",
        f"⚡ Stamina: {player['stamina']} • Boss Key required: {get_db(context).item_qty(update.effective_user.id, 'boss_key')}",
        "",
        "Choose a boss to inspect, or flee from the hunt.",
    ]
    rows = []
    for boss in bosses[:6]:
        lines.append(f"👹 <b>{ui.esc(boss['name'])}</b> Lv.{boss['level']} • {data.ELEMENTS[boss['element']]['emoji']}")
        rows.append([InlineKeyboardButton(f"⚔️ Battle {boss['name']} Lv.{boss['level']}", callback_data=f"boss:fight:{series}:{boss['id']}")])
    rows.append([InlineKeyboardButton("🏃 Flee", callback_data="boss:flee"), InlineKeyboardButton("🌍 Travel", callback_data="menu:travel")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_boss(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and context.args[0].lower() in ("start", "fight", "random"):
        context.args = context.args[1:]
        series = parse_series(context.args[0]) if context.args else None
        await start_battle(update, context, "boss", series=series)
        return
    await boss_view(update, context)


async def cmd_elite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    series = parse_series(context.args[0]) if context.args else None
    await start_battle(update, context, "elite", series=series)


async def cmd_streak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    await respond(
        update,
        f"🔥 <b>NPC Hunt Streak</b>\nCurrent: <b>{player['npc_streak']}</b>\nBest: <b>{player['best_streak']}</b>\n\nWin hunts to build your streak. A loss resets it.",
        ui.back_keyboard(),
    )


async def raid_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    boss = db.world_boss_current()
    if not boss or not boss.get("boss"):
        await respond(update, "No world boss is active right now.")
        return
    info = boss["boss"]
    leaders = db.world_boss_leaderboard(5)
    lines = [
        f"{data.SERIES[info['series']]['emoji']} <b>WORLD BOSS — {ui.esc(info['name'])}</b>",
        f"{data.ELEMENTS[info['element']]['emoji']} Level {info['level']} • {series_name(info['series'])}",
        f"❤️ {ui.percent_bar(boss['hp'], boss['max_hp'], 16)}",
        f"HP: {ui.fmt(boss['hp'])} / {ui.fmt(boss['max_hp'])}",
        f"Status: <b>{boss['status'].title()}</b>",
        "",
        "🏆 <b>Top Damage</b>",
    ]
    if leaders:
        for index, row in enumerate(leaders, 1):
            lines.append(f"{index}. {ui.esc(row.get('first_name') or row.get('username') or 'Summoner')} — {ui.fmt(row['damage'])}")
    else:
        lines.append("No damage recorded yet.")
    lines.extend(["", "Attack with /attack (uses 1 Raid Token or 25 stamina).", f"Your Raid Tokens: {db.item_qty(update.effective_user.id, 'raid_token')}"])
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 Attack World Boss", callback_data="world:attack")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ])
    await respond(update, "\n".join(lines), keyboard)


async def cmd_raid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await raid_view(update, context)


async def cmd_global(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await raid_view(update, context)


async def cmd_worldboss(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await raid_view(update, context)


async def cmd_attack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_battle(update, context, "world")


async def cmd_clanraid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    clan = db.clan(update.effective_user.id)
    if clan is None:
        await respond(update, "Join a clan first with /clan_join &lt;name&gt;.")
        return
    action = context.args[0].lower() if context.args else "info"
    if action == "start":
        if len(context.args) < 2:
            lines = ["🏯 <b>Clan Raids</b>", ""]
            for raid in data.CLAN_RAIDS:
                lines.append(f"• {ui.esc(raid['name'])} — <code>{raid['id']}</code> • {ui.fmt(raid['hp'])} HP")
            lines.append("\nUsage: /clanraid start &lt;raid_id&gt;")
            await respond(update, "\n".join(lines), ui.back_keyboard("menu:clan"))
            return
        result = db.start_clan_raid(update.effective_user.id, context.args[1])
        if not result["ok"]:
            await respond(update, f"❌ {ui.esc(result['reason'])}")
            return
        raid = result["info"]
        await respond(update, f"🏯 Clan raid <b>{ui.esc(raid['name'])}</b> started! HP {ui.fmt(raid['hp'])}.\nMembers can use /clanraid attack.", ui.back_keyboard("menu:clan"))
        return
    if action == "attack":
        await start_battle(update, context, "clanraid")
        return
    raid = db.clan_raid_current(clan["id"])
    if raid is None:
        await respond(update, "No active clan raid. Leaders can start one with /clanraid start &lt;raid_id&gt;.", ui.back_keyboard("menu:clan"))
        return
    info = data.CLAN_RAID_BY_ID.get(raid["raid_id"], data.CLAN_RAIDS[0])
    leaders = db.clan_raid_leaderboard(raid["id"])
    lines = [
        f"🏯 <b>CLAN RAID — {ui.esc(info['name'])}</b>",
        f"❤️ {ui.percent_bar(raid['hp'], raid['max_hp'], 16)}",
        f"HP: {ui.fmt(raid['hp'])} / {ui.fmt(raid['max_hp'])} • Status: {raid['status'].title()}",
        "",
        "🏆 <b>Damage Leaders</b>",
    ]
    for index, row in enumerate(leaders, 1):
        lines.append(f"{index}. {ui.esc(row.get('first_name') or row.get('username') or 'Member')} — {ui.fmt(row['damage'])}")
    if not leaders:
        lines.append("No damage yet.")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Attack Clan Raid", callback_data="clanraid:attack")],
        [InlineKeyboardButton("⬅️ Clan", callback_data="menu:clan")],
    ])
    await respond(update, "\n".join(lines), keyboard)


async def cmd_clanraid_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["start", *context.args]
    await cmd_clanraid(update, context)


async def cmd_clanraid_attack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["attack"]
    await cmd_clanraid(update, context)


async def cmd_duel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    target = None
    if context.args:
        target = db.find_player(context.args[0])
    elif update.effective_message and update.effective_message.reply_to_message:
        replied = update.effective_message.reply_to_message.from_user
        target = db.find_player(str(replied.id)) if replied else None
    if target is None:
        await respond(update, "Usage: /duel &lt;user_id|@username&gt; or reply to a player's message.")
        return
    await start_battle(update, context, "duel", opponent_id=int(target["user_id"]))


async def cmd_arena(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_battle(update, context, "arena")


async def leaderboard_view(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str = "wealth") -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    category = category.lower()
    lines = []
    if category in ("wealth", "page1", "economy"):
        boards = db.leaderboard_wealth(5)
        total_characters = len(data.CHARACTERS)
        lines.append("📊 <b>MULTIVERSE LEADERBOARD — PAGE 1</b>")
        lines.append("<i>Wealth and collection rankings</i>")
        lines.append("")
        sections = [
            ("💰", "TOP YENS", "yens", lambda row: f"{ui.fmt(row['amount'])} yens"),
            ("💎", "TOP GEMS", "gems", lambda row: f"{ui.fmt(row['amount'])} gems"),
            ("🔮", "TOP CRYSTALS", "crystals", lambda row: f"{ui.fmt(row['amount'])} crystals"),
            ("🎴", "TOP COLLECTIONS", "characters", lambda row: f"{row['amount']}/{total_characters} heroes ({row['amount'] * 100 / total_characters:.0f}%)"),
        ]
        for icon, title, key, formatter in sections:
            lines.append(f"{icon} <b>{title}</b>")
            rows = boards.get(key, [])
            if not rows:
                lines.append("No entries yet.")
            for index, row in enumerate(rows, 1):
                name = ui.esc(row.get("first_name") or row.get("username") or "Summoner")
                lines.append(f"{index}. {name} — {formatter(row)}")
            lines.append("")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏆 Rankings — Page 2", callback_data="lb:players")],
            [InlineKeyboardButton("👤 Players", callback_data="lb:players"), InlineKeyboardButton("🏟️ Arena", callback_data="lb:arena")],
            [InlineKeyboardButton("🏯 Clans", callback_data="lb:clans"), InlineKeyboardButton("🌍 Raid", callback_data="lb:raid")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
        ])
        await respond(update, "\n".join(lines).rstrip(), keyboard)
        return
    if category == "clans":
        rows = db.clan_leaderboard(10)
        lines.append("🏯 <b>TOP CLANS</b>")
        for index, row in enumerate(rows, 1):
            lines.append(f"{index}. <b>{ui.esc(row['name'])}</b> [{ui.esc(row['tag'])}] — Lv.{row['level']} • {row['members']} members • {ui.fmt(row['exp'])} exp")
    elif category == "raid":
        rows = db.world_boss_leaderboard(10)
        lines.append("🌍 <b>WORLD BOSS DAMAGE</b>")
        for index, row in enumerate(rows, 1):
            lines.append(f"{index}. {ui.esc(row.get('first_name') or row.get('username') or 'Summoner')} — {ui.fmt(row['damage'])}")
    else:
        order = "arena" if category == "arena" else "level"
        rows = db.leaderboard_players(10, order)
        lines.append(f"🏆 <b>TOP PLAYERS — {category.title()}</b>")
        for index, row in enumerate(rows, 1):
            if category == "arena":
                score = f"{row['arena_rating']} rating"
            else:
                score = f"Lv.{row['level']} • {ui.fmt(row['wins'])} wins"
            lines.append(f"{index}. {ui.esc(row.get('first_name') or row.get('username') or 'Summoner')} — {score}")
    if len(lines) == 1:
        lines.append("No entries yet.")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Wealth — Page 1", callback_data="lb:wealth")],
        [InlineKeyboardButton("👤 Players", callback_data="lb:players"), InlineKeyboardButton("🏟️ Arena", callback_data="lb:arena")],
        [InlineKeyboardButton("🏯 Clans", callback_data="lb:clans"), InlineKeyboardButton("🌍 Raid", callback_data="lb:raid")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ])
    await respond(update, "\n".join(lines), keyboard)


async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    category = context.args[0].lower() if context.args else "wealth"
    await leaderboard_view(update, context, category)


async def clan_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    clan = db.clan(update.effective_user.id)
    if clan is None:
        text = (
            "🏯 <b>CLANS</b>\n\nYou are not in a clan.\n\n"
            f"Create one: /clan_create &lt;name&gt; &lt;tag&gt; (costs {config.CLAN_CREATE_YENS:,} yens + {config.CLAN_CREATE_CRYSTALS} crystals)\n"
            "Join one: /clan_join &lt;name or tag&gt;\n"
            "Browse: /leaderboard clans"
        )
        await respond(update, text, ui.main_menu_keyboard())
        return
    info = db.clan_info(clan["id"])
    if info is None:
        await respond(update, "Clan data unavailable.")
        return
    members = info["members"]
    lines = [
        f"🏯 <b>{ui.esc(info['name'])}</b> [{ui.esc(info['tag'])}]",
        f"Level {info['level']} • EXP {ui.fmt(info['exp'])} • {len(members)}/30 members",
        f"💰 Treasury: 💠 {ui.fmt(info['treasury_yens'])} • 💎 {ui.fmt(info['treasury_gems'])} • 🔮 {ui.fmt(info['treasury_crystals'])}",
        f"📢 {ui.esc(info['announcement'] or 'No announcement.')}",
        f"📝 {ui.esc(info.get('description') or 'No description yet.')}",
        f"⚙️ Join: {'Open' if info.get('open_join', 1) else 'Invite only'} • Min level {info.get('min_level', 1)}",
        "",
        "👥 <b>Members</b>",
    ]
    for member in members[:15]:
        name = member.get("first_name") or member.get("username") or "Summoner"
        lines.append(f"• {ui.esc(name)} — {member['role'].title()} • Lv.{member['level']} • {ui.fmt(member['donation'])} donated")
    lines.extend([
        "",
        "Commands: /clan_info /clan_donate /clanraid /clan_leave",
        "Leaders: /clan_kick /clan_promote /clan_demote /clan_announce /clan_disband",
        "Manage: /clan invite &lt;user&gt; • /clan add &lt;user&gt; • /clan accept • /clan transfer &lt;user&gt;",
        "Settings: /clan desc &lt;text&gt; • /clan open on|off • /clan minlevel &lt;level&gt;",
    ])
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏯 Clan Raid", callback_data="menu:clanraid"), InlineKeyboardButton("🏆 Top Clans", callback_data="lb:clans")],
        [InlineKeyboardButton("💠 Donate 100", callback_data="clan:donate:100"), InlineKeyboardButton("💠 Donate 1,000", callback_data="clan:donate:1000"), InlineKeyboardButton("💠 Donate 10,000", callback_data="clan:donate:10000")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="clan:settings"), InlineKeyboardButton("🚪 Leave Clan", callback_data="clan:leave_request")],
        [InlineKeyboardButton("🖼️ Clan Card", callback_data="menu:clanpic"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ])
    await respond(update, "\n".join(lines), keyboard)
    leader_name = next((m.get("first_name") or m.get("username") or str(m["user_id"]) for m in members if m["role"] == "leader"), "")


async def clan_leave_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    clan = db.clan(update.effective_user.id)
    member = db.clan_member(update.effective_user.id)
    if clan is None or member is None:
        await respond(update, "❌ You are not in a clan.", ui.back_keyboard("menu:clan"))
        return
    if member["role"] == "leader":
        text = (
            f"⚠️ <b>You are the leader of {ui.esc(clan['name'])}.</b>\n\n"
            "A leader cannot leave without transferring leadership or disbanding the clan.\n"
            "Choose an option below."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 Promote New Leader", callback_data="clan:promote_menu")],
            [InlineKeyboardButton("💥 Disband Clan", callback_data="clan:disband_yes")],
            [InlineKeyboardButton("❌ Cancel", callback_data="clan:leave_no")],
        ])
    else:
        text = (
            f"🚪 <b>Leave {ui.esc(clan['name'])}?</b>\n\n"
            "Your donation history stays with the clan, but you will lose access to clan raids and chat."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Leave", callback_data="clan:leave_yes"), InlineKeyboardButton("❌ Cancel", callback_data="clan:leave_no")],
        ])
    await respond(update, text, keyboard)


async def cmd_clan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if not context.args:
        await clan_view(update, context)
        return
    db = get_db(context)
    sub = context.args[0].lower()
    rest = context.args[1:]
    if sub == "create":
        if len(rest) < 2:
            await respond(update, "Usage: /clan create &lt;name&gt; &lt;tag&gt;")
            return
        result = db.create_clan(update.effective_user.id, " ".join(rest[:-1]), rest[-1])
        if not result["ok"]:
            await respond(update, f"❌ {ui.esc(result['reason'])}")
        else:
            await respond(update, f"🏯 Clan <b>{ui.esc(result['name'])}</b> [{ui.esc(result['tag'])}] created!", ui.back_keyboard("menu:clan"))
        return
    if sub == "join":
        result = db.join_clan(update.effective_user.id, " ".join(rest))
        await respond(update, f"✅ Joined <b>{ui.esc(result['clan']['name'])}</b>!" if result["ok"] else f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:clan"))
        return
    if sub == "leave":
        await clan_leave_request(update, context)
        return
    if sub == "donate":
        if len(rest) < 2 or not rest[1].isdigit():
            await respond(update, "Usage: /clan donate &lt;yens|gems|crystals&gt; &lt;amount&gt;")
            return
        result = db.clan_donate(update.effective_user.id, rest[0].lower(), int(rest[1]))
        await respond(update, f"✅ Donated {ui.fmt(result['amount'])} {result['currency']}." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub == "kick":
        result = db.clan_kick(update.effective_user.id, " ".join(rest))
        await respond(update, "✅ Member kicked." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub == "promote":
        result = db.clan_set_role(update.effective_user.id, " ".join(rest), "officer")
        await respond(update, "✅ Member promoted to officer." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub == "demote":
        result = db.clan_set_role(update.effective_user.id, " ".join(rest), "member")
        await respond(update, "✅ Member demoted." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub in ("invite", "inv"):
        result = db.clan_invite(update.effective_user.id, " ".join(rest))
        await respond(update, f"📨 Invited <b>{ui.esc(result['target'].get('first_name') or result['target'].get('username') or result['target']['user_id'])}</b>." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub in ("add", "recruit"):
        result = db.clan_add(update.effective_user.id, " ".join(rest))
        await respond(update, f"✅ Added <b>{ui.esc(result['target'].get('first_name') or result['target'].get('username') or result['target']['user_id'])}</b> to the clan." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub == "accept":
        result = db.clan_accept(update.effective_user.id, " ".join(rest))
        await respond(update, f"✅ Joined <b>{ui.esc(result['clan']['name'])}</b>!" if result["ok"] else f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:clan"))
        return
    if sub == "transfer":
        result = db.clan_transfer(update.effective_user.id, " ".join(rest))
        await respond(update, "👑 Leadership transferred." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub in ("desc", "description"):
        result = db.clan_set_description(update.effective_user.id, " ".join(rest))
        await respond(update, "📝 Clan description updated." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub == "open":
        value = (rest[0].lower() if rest else "").strip()
        if value not in ("on", "off", "true", "false", "1", "0"):
            await respond(update, "Usage: /clan open on|off")
            return
        result = db.clan_settings(update.effective_user.id, open_join=value in ("on", "true", "1"))
        await respond(update, "⚙️ Clan join setting updated." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub in ("minlevel", "min_level"):
        if not rest or not rest[0].isdigit():
            await respond(update, "Usage: /clan minlevel &lt;level&gt;")
            return
        result = db.clan_settings(update.effective_user.id, min_level=int(rest[0]))
        await respond(update, f"⚙️ Minimum join level set to {rest[0]}." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub == "announce":
        result = db.clan_announce(update.effective_user.id, " ".join(rest))
        await respond(update, "📢 Announcement updated." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    if sub == "disband":
        result = db.clan_disband(update.effective_user.id)
        await respond(update, "🏯 Clan disbanded." if result["ok"] else f"❌ {ui.esc(result['reason'])}")
        return
    await clan_view(update, context)


async def cmd_clan_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["create", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["join", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await clan_leave_request(update, context)


async def cmd_clan_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await clan_view(update, context)


async def cmd_clan_donate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["donate", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["kick", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_promote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["promote", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_demote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["demote", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_announce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["announce", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_disband(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["disband"]
    await cmd_clan(update, context)


async def cmd_clan_invite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["invite", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["add", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["accept", *context.args]
    await cmd_clan(update, context)


async def cmd_clan_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = ["transfer", *context.args]
    await cmd_clan(update, context)


async def quests_view(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_type: str | None = None) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    quest_type = (quest_type or "daily").lower()
    if quest_type not in ("daily", "weekly", "monthly"):
        quest_type = "daily"
    lines = [f"📜 <b>{quest_type.title()} QUESTS</b>", ""]
    for quest in data.QUESTS:
        if quest["type"] != quest_type:
            continue
        progress = db.quest_progress(update.effective_user.id, quest)
        claimed = db.quest_claimed(update.effective_user.id, quest)
        status = "✅" if claimed else "🎁" if progress >= quest["target"] else "⏳"
        lines.append(
            f"{status} <b>{ui.esc(quest['name'])}</b> — {ui.fmt(min(progress, quest['target']))}/{ui.fmt(quest['target'])}\n"
            f"   {ui.reward_text(quest['rewards'])}"
        )
    lines.extend(["", "Use /claim " + quest_type + " to collect completed rewards.", "Use /quests daily|weekly|monthly to switch."])
    await respond(update, "\n".join(lines), ui.quest_keyboard())


async def cmd_quests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await quests_view(update, context, context.args[0] if context.args else "daily")


async def cmd_claim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    quest_type = context.args[0].lower() if context.args and context.args[0].lower() in ("daily", "weekly", "monthly") else None
    result = get_db(context).claim_quests(update.effective_user.id, quest_type)
    await respond(update, claim_text(result), ui.back_keyboard("menu:quests"))


def claim_text(result: dict) -> str:
    if not result["claimed"]:
        return "No completed quests to claim yet. Keep battling!"
    lines = ["🎁 <b>QUEST REWARDS CLAIMED</b>", ""]
    for name in result["claimed"]:
        lines.append(f"✅ {ui.esc(name)}")
    reward = ui.reward_text(result.get("earned"), result.get("items"))
    if reward:
        lines.extend(["", f"🎁 {reward}"])
    return "\n".join(lines)


async def achievements_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    lines = ["🏅 <b>ACHIEVEMENTS</b>", ""]
    for achievement in data.ACHIEVEMENTS:
        progress = db.achievement_progress(update.effective_user.id, achievement)
        claimed = db.achievement_claimed(update.effective_user.id, achievement)
        status = "✅" if claimed else "🎁" if progress >= achievement["target"] else "⏳"
        lines.append(f"{status} <b>{ui.esc(achievement['name'])}</b> — {ui.fmt(min(progress, achievement['target']))}/{ui.fmt(achievement['target'])}\n   {ui.reward_text(achievement['rewards'])}")
    lines.append("\nTap below to claim every completed achievement.")
    rows = [[InlineKeyboardButton("🎁 Claim Completed", callback_data="ach:claim")], [InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")]]
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await achievements_view(update, context)


async def cmd_claimach(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    result = get_db(context).claim_achievements(update.effective_user.id)
    if not result["claimed"]:
        await respond(update, "No completed achievements to claim yet.")
        return
    reward = ui.reward_text(result.get("earned"))
    await respond(update, "🏅 <b>Achievements claimed:</b>\n" + "\n".join(f"✅ {ui.esc(name)}" for name in result["claimed"]) + (f"\n\n🎁 {reward}" if reward else ""), ui.back_keyboard())


async def cmd_titles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    unlocked = set(db.unlocked_titles(update.effective_user.id))
    lines = ["🏷️ <b>TITLES</b>", ""]
    for title_id, title in data.TITLES.items():
        status = "✅" if title_id in unlocked else "🔒"
        equipped = " • EQUIPPED" if player.get("title") == title_id else ""
        requirement = title.get("requirement")
        req = f"Requires {requirement[1]:,} {requirement[0]}" if requirement else "Starter title"
        lines.append(f"{status} <b>{ui.esc(title['name'])}</b> — <code>{title_id}</code>{equipped}\n   {ui.esc(title['desc'])} • {req}")
    lines.append("\nTap an unlocked title to equip it.")
    rows = []
    for title_id, title in data.TITLES.items():
        if title_id in unlocked:
            rows.append([InlineKeyboardButton(("✅ " if player.get("title") == title_id else "🏷️ ") + title["name"], callback_data=f"title:equip:{title_id}")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if not context.args:
        await cmd_titles(update, context)
        return
    if get_db(context).equip_title(update.effective_user.id, context.args[0]):
        title = data.TITLES.get(context.args[0], {})
        await respond(update, f"🏷️ Equipped title: <b>{ui.esc(title.get('name', context.args[0]))}</b>.")
    else:
        await respond(update, "❌ Title is locked. Check /titles.")


async def market_view(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    page = max(1, int(page))
    listings = db.market_listings(10, (page - 1) * 10)
    total = db.market_count()
    lines = [f"🏪 <b>MARKET</b> — {total} listings", ""]
    if not listings:
        lines.append("No listings yet. Use /market_sell to list an item.")
    for listing in listings:
        meta = f" Lv.{listing['meta'].get('level')}" if listing["kind"] == "gear" else ""
        lines.append(
            f"#{listing['id']} {listing['emoji']} <b>{ui.esc(listing['name'])}</b>{meta} x{listing['qty']} — 💠 {ui.fmt(listing['price'])} yens\n"
            f"   Seller: {ui.esc(listing.get('first_name') or listing.get('username') or 'Summoner')}"
        )
    lines.extend(["", "Buy: /market_buy &lt;id&gt; • Cancel: /market_cancel &lt;id&gt;", "Sell: /market_sell &lt;item_id&gt; &lt;qty&gt; &lt;price&gt;"])
    rows = []
    for listing in listings[:8]:
        if int(listing["seller_id"]) == int(update.effective_user.id):
            rows.append([InlineKeyboardButton(f"❌ Cancel #{listing['id']} {listing['name']}", callback_data=f"market:cancel:{listing['id']}")])
        else:
            rows.append([InlineKeyboardButton(f"🛒 Buy #{listing['id']} {listing['name']} — {ui.fmt(listing['price'])} yens", callback_data=f"market:buy:{listing['id']}")])
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"market:{page - 1}"))
    if page * 10 < total:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"market:{page + 1}"))
    if buttons:
        rows.append(buttons)
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    page = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
    await market_view(update, context, page)


async def cmd_market_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if len(context.args) < 3 or not context.args[1].isdigit() or not context.args[2].isdigit():
        await respond(update, "Usage: /market_sell &lt;item_id&gt; &lt;qty&gt; &lt;price&gt;")
        return
    kind = "item"
    item_id = context.args[0]
    if item_id.isdigit():
        kind = "gear"
    result = get_db(context).market_list(update.effective_user.id, kind, item_id, int(context.args[1]), int(context.args[2]))
    await respond(update, f"🏪 Listing created: #{result['listing_id']}." if result["ok"] else f"❌ {ui.esc(result['reason'])}")


async def cmd_market_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args or not context.args[0].isdigit():
        if player:
            await respond(update, "Usage: /market_buy &lt;listing_id&gt;")
        return
    result = get_db(context).market_buy(update.effective_user.id, int(context.args[0]))
    await respond(update, f"✅ Purchased for 💠 {ui.fmt(result['price'])} yens." if result["ok"] else f"❌ {ui.esc(result['reason'])}")


async def cmd_market_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args or not context.args[0].isdigit():
        if player:
            await respond(update, "Usage: /market_cancel &lt;listing_id&gt;")
        return
    result = get_db(context).market_cancel(update.effective_user.id, int(context.args[0]))
    await respond(update, "✅ Listing cancelled and item returned." if result["ok"] else f"❌ {ui.esc(result['reason'])}")


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    result = get_db(context).claim_daily(update.effective_user.id)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"📅 <b>Daily reward claimed!</b>\n🔥 Streak: {result['streak']}\n🎁 {ui.reward_text(result['rewards'])}", ui.main_menu_keyboard())


async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    result = get_db(context).claim_weekly(update.effective_user.id)
    await respond(update, f"🗓️ <b>Weekly reward claimed!</b>\n🎁 {ui.reward_text(result['rewards'])}" if result["ok"] else f"❌ {ui.esc(result['reason'])}")


async def cmd_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    result = get_db(context).claim_monthly(update.effective_user.id)
    await respond(update, f"🌕 <b>Monthly reward claimed!</b>\n🎁 {ui.reward_text(result['rewards'])}" if result["ok"] else f"❌ {ui.esc(result['reason'])}")


async def cmd_travel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if not context.args:
        await respond(update, "Usage: /travel &lt;dragonball|naruto|bleach|jujutsu|tempest&gt;")
        return
    series = parse_series(context.args[0])
    if series is None:
        await respond(update, "Unknown series.", ui.back_keyboard())
        return
    result = game.travel(get_db(context), update.effective_user.id, series)
    await respond(update, f"🌍 Traveled to {series_name(series)} — <b>{data.SERIES[series]['home']}</b>.", ui.main_menu_keyboard())


async def travel_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    lines = [f"🌍 <b>TRAVEL</b>", f"Current home: <b>{series_name(player.get('travel', 'dragonball'))}</b>", "", "Choose a world to explore:"]
    rows = []
    for series in data.SERIES_ORDER:
        info = data.SERIES[series]
        rows.append([InlineKeyboardButton(f"{info['emoji']} {info['name']} — {info['home']}", callback_data=f"travel:{series}")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_series(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["🌌 <b>FIVE SERIES, ONE MULTIVERSE</b>", ""]
    for series in data.SERIES_ORDER:
        info = data.SERIES[series]
        total = len(data.CHARACTERS_BY_SERIES[series])
        lines.append(f"{info['emoji']} <b>{info['name']}</b> — {total} heroes\n   Home: {info['home']}\n   {info['lore']}\n")
    lines.append("Set your home world with /travel &lt;series&gt;.")
    await respond(update, "\n".join(lines), ui.series_keyboard("seriesinfo", include_all=False))


async def cmd_codex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    collection = game.series_collection(db, update.effective_user.id)
    lines = ["📖 <b>MULTIVERSE CODEX</b>", ""]
    for series in data.SERIES_ORDER:
        total = len(data.CHARACTERS_BY_SERIES[series])
        owned = collection.get(series, 0)
        lines.append(f"{data.SERIES[series]['emoji']} <b>{data.SERIES[series]['name']}</b> — {owned}/{total} owned\n   {ui.percent_bar(owned, total, 12)}")
    lines.append(f"\n🎴 Total: {len(db.characters(update.effective_user.id))}/{len(data.CHARACTERS)} heroes")
    await respond(update, "\n".join(lines), ui.back_keyboard())


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["🎉 <b>ROTATING SERIES EVENTS</b>", ""]
    for event in data.EVENTS:
        lines.append(f"{event['emoji']} <b>{ui.esc(event['name'])}</b> — {series_name(event['series'])}\n   Bonus: {ui.esc(event['bonus'])}")
    lines.append("\nEvents rotate with daily resets. Hunt and raid for boosted rewards.")
    await respond(update, "\n".join(lines), ui.back_keyboard())


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    await respond(
        update,
        f"⚙️ <b>Settings</b>\n\n🏠 Home series: {series_name(player.get('travel', 'dragonball'))}\n"
        f"🏷️ Title: {ui.esc(data.TITLES.get(player.get('title', ''), {}).get('name', 'None'))}\n"
        f"🆔 User ID: <code>{player['user_id']}</code>\n\n"
        "Change home: /travel &lt;series&gt;\nChange title: /title &lt;title_id&gt;\n"
        "Your preferences are stored automatically.",
        ui.back_keyboard(),
    )


async def pets_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    pets = db.pets(update.effective_user.id)
    lines = ["🐾 <b>COMPANIONS</b>", ""]
    if not pets:
        lines.append("No companions yet. Summon one with gems using /petsummon, or hatch an egg.")
    for pet in pets:
        equipped = " • EQUIPPED" if pet.get("equipped") else ""
        bonus = ", ".join(f"{key.replace('_pct', '')} +{int(value * 100)}%" for key, value in pet.get("bonus", {}).items())
        lines.append(f"{pet['emoji']} <b>{ui.esc(pet['name'])}</b> Lv.{pet['level']}{equipped}\n   {ui.esc(pet['desc'])} • {bonus}")
    lines.extend([
        "",
        "🌟 <b>Gem Summon</b> — /petsummon [1|10|50]",
        "💎 1 summon: 1,000 gems • 10: 10,000 • 50: 50,000",
        f"Pity: {player.get('pet_pity', 0)}/{config.PET_SUMMON_PITY} • Divine guaranteed at full pity.",
        "",
        "Tap a button below. Commands: /pet_equip &lt;pet_id&gt; • /pet_feed &lt;pet_id&gt;",
    ])
    rows = []
    for pet in pets[:10]:
        if pet.get("equipped"):
            rows.append([InlineKeyboardButton(f"🍖 Feed {pet['name']} +1", callback_data=f"pet:feed:{pet['id']}:1")])
        else:
            rows.append([
                InlineKeyboardButton(f"🐾 Equip {pet['name']}", callback_data=f"pet:equip:{pet['id']}"),
                InlineKeyboardButton("🍖 Feed +1", callback_data=f"pet:feed:{pet['id']}:1"),
            ])
    rows.append([
        InlineKeyboardButton("🌟 ×1 (1,000💎)", callback_data="petsummon:1"),
        InlineKeyboardButton("×10 (10,000💎)", callback_data="petsummon:10"),
        InlineKeyboardButton("×50 (50,000💎)", callback_data="petsummon:50"),
    ])
    rows.append([InlineKeyboardButton("🥚 Hatch Egg", callback_data="pet:hatch:pet_egg"), InlineKeyboardButton("🌟 Hatch Premium", callback_data="pet:hatch:pet_egg_premium")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_pets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await pets_view(update, context)


async def cmd_pet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await pets_view(update, context)


async def cmd_pet_equip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args:
        if player:
            await respond(update, "Usage: /pet_equip &lt;pet_id&gt;")
        return
    if get_db(context).equip_pet(update.effective_user.id, context.args[0]):
        await respond(update, "🐾 Companion equipped.")
    else:
        await respond(update, "❌ You do not own that companion.")


async def cmd_pet_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None or not context.args:
        if player:
            await respond(update, "Usage: /pet_feed &lt;pet_id&gt; [levels]")
        return
    levels = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
    result = get_db(context).feed_pet(update.effective_user.id, context.args[0], levels)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"🐾 Companion reached level <b>{result['level']}</b> for 💠 {ui.fmt(result['cost'])} yens.")


async def cmd_pet_summon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    item_id = "pet_egg_premium" if context.args and context.args[0].lower() in ("premium", "rare") else "pet_egg"
    result = game.use_item(db, update.effective_user.id, item_id, 1)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    pet = result.get("pet", {})
    await respond(update, f"🥚 Hatched {pet.get('emoji', '🐾')} <b>{ui.esc(pet.get('name', 'Companion'))}</b>!\n{'🆕 New companion!' if result.get('new') else 'Duplicate companion reached a higher level.'}", ui.back_keyboard())


def _parse_redeem_rewards(tokens: list[str]) -> tuple[list[dict], dict, str]:
    options: dict[str, int] = {}
    reward_tokens: list[str] = []
    for token in tokens:
        lower = token.lower()
        if lower.startswith("uses=") or lower.startswith("uses:"):
            value = token.split("=", 1)[-1].split(":", 1)[-1]
            if not value.isdigit() or int(value) < 1:
                return [], {}, "uses must be a positive number."
            options["uses"] = int(value)
        elif lower.startswith("days=") or lower.startswith("days:"):
            value = token.split("=", 1)[-1].split(":", 1)[-1]
            if not value.isdigit() or int(value) < 1:
                return [], {}, "days must be a positive number."
            options["days"] = int(value)
        else:
            reward_tokens.append(token)
    chunks = [chunk for chunk in " ".join(reward_tokens).replace(",", " ").replace(";", " ").split() if chunk]
    if not chunks:
        return [], options, "Add at least one reward, e.g. gems:500,crystals:50,yens:5000."
    aliases = {"sp": "skill_points", "spirit": "skill_points", "char": "character", "hero": "character", "shards": "shard"}
    rewards: list[dict] = []
    for chunk in chunks:
        separator = ":" if ":" in chunk else "=" if "=" in chunk else None
        if separator is None:
            return [], options, f"Invalid reward '{chunk}'. Use TYPE:VALUE, e.g. gems:500."
        parts = [part.strip() for part in chunk.split(separator)]
        kind = aliases.get(parts[0].lower(), parts[0].lower())
        if kind in ("yens", "gems", "crystals", "tickets", "stamina", "skill_points", "exp"):
            if len(parts) < 2 or not parts[1].isdigit() or int(parts[1]) < 1:
                return [], options, f"{kind} needs a positive amount."
            rewards.append({"kind": kind, "qty": int(parts[1])})
        elif kind in ("item", "character", "pet", "gear", "shard", "title"):
            if len(parts) < 2 or not parts[1]:
                return [], options, f"{kind} needs an id."
            asset_id = parts[1]
            qty = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() and int(parts[2]) > 0 else 1
            catalog = {
                "item": data.ITEMS, "character": data.CHARACTERS, "pet": data.PETS,
                "gear": data.GEAR, "shard": data.CHARACTERS, "title": data.TITLES,
            }[kind]
            if asset_id not in catalog:
                return [], options, f"Unknown {kind} id '{asset_id}'."
            rewards.append({"kind": kind, "id": asset_id, "qty": qty})
        else:
            return [], options, f"Unknown reward type '{kind}'."
    return rewards, options, ""


async def cmd_createcode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard_admin(update, context)
    if player is None:
        return
    if len(context.args) < 2:
        await respond(
            update,
            "🎟️ <b>Create Redeem Code</b>\n"
            "Usage: <code>/createcode CODE rewards [uses=100] [days=30]</code>\n\n"
            "Reward examples:\n"
            "<code>gems:500,crystals:50,yens:5000</code>\n"
            "<code>character:db_black_frieza,item:senzu_large:5</code>\n"
            "<code>pet:pet_ranga,gear:gear_univ_iron_guard:5,title:title_god</code>\n\n"
            "Kinds: yens, gems, crystals, tickets, stamina, skill_points, exp, item, character, pet, gear, shard, title.",
            ui.back_keyboard("admin:menu"),
        )
        return
    code = context.args[0]
    rewards, options, error = _parse_redeem_rewards(context.args[1:])
    if error:
        await respond(update, f"❌ {ui.esc(error)}", ui.back_keyboard("admin:menu"))
        return
    expires_at = None
    if options.get("days"):
        expires_at = (datetime.utcnow() + timedelta(days=options["days"])).isoformat(timespec="seconds")
    result = get_db(context).redeem_code_create(player["user_id"], code, rewards, options.get("uses", 1), expires_at)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("admin:menu"))
        return
    reward_text = " • ".join(
        f"{reward['kind']} {ui.esc(str(reward.get('id', reward.get('qty', ''))))}" + (f" x{reward['qty']}" if reward.get("id") else "")
        for reward in rewards
    )
    await respond(
        update,
        f"✅ <b>Code created:</b> <code>{ui.esc(result['code'])}</code>\n"
        f"🎁 {ui.esc(reward_text)}\n"
        f"Uses: <b>{result['max_uses']:,}</b>" + (f" • Expires: <b>{ui.esc(result['expires_at'])}</b>" if result.get("expires_at") else ""),
        ui.back_keyboard("admin:menu"),
    )


async def cmd_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if not context.args:
        await respond(update, "🎟️ Usage: <code>/redeem CODE</code>", ui.back_keyboard())
        return
    result = get_db(context).redeem_code_claim(update.effective_user.id, context.args[0])
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard())
        return
    lines = [f"🎉 <b>CODE REDEEMED — {ui.esc(result['code'])}</b>", ""]
    for reward in result["rewards"]:
        kind = reward["kind"]
        asset_id = reward.get("id", "")
        if kind == "item":
            name = data.ITEMS.get(asset_id, {}).get("name", asset_id)
        elif kind == "character":
            name = data.CHARACTERS.get(asset_id, {}).get("name", asset_id)
        elif kind == "pet":
            name = data.PETS.get(asset_id, {}).get("name", asset_id)
        elif kind == "gear":
            name = data.GEAR.get(asset_id, {}).get("name", asset_id)
        elif kind == "shard":
            name = data.CHARACTERS.get(asset_id, {}).get("name", asset_id) + " shards"
        elif kind == "title":
            name = data.TITLES.get(asset_id, {}).get("name", asset_id)
        else:
            name = kind.replace("_", " ").title()
        qty = reward.get("qty", 1)
        lines.append(f"• {ui.esc(name)}" + (f" x{ui.fmt(qty)}" if qty != 1 or reward.get("id") else ""))
    await respond(update, "\n".join(lines), ui.back_keyboard())


async def pet_summon_result(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int = 1) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    result = game.pet_summon(db, update.effective_user.id, count)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:pets"))
        return
    lines = [
        f"🌟 <b>COMPANION SUMMON ×{result['count']}</b>",
        f"💎 Cost: {ui.fmt(result['cost'])} gems • Pity: <b>{result['pity']}/{config.PET_SUMMON_PITY}</b>",
        "",
    ]
    for entry in result["results"]:
        pet = entry["pet"]
        rarity = data.RARITIES.get(entry["rarity"], {})
        lines.append(
            f"{rarity.get('emoji', '⚪')} {pet.get('emoji', '🐾')} <b>{ui.esc(pet.get('name', 'Companion'))}</b> "
            f"— {ui.esc(rarity.get('name', str(entry['rarity']).title()))} {'🆕' if entry['new'] else '⭐ level up'}"
        )
    lines.extend(["", f"Rates: Common 62% • Rare 28% • Epic 7.8% • Legendary 1.8% • Mythic 0.35% • Divine 0.05%", f"Pity at {config.PET_SUMMON_PITY} guarantees a Divine companion."])
    best = max(result["results"], key=lambda entry: data.RARITY_INDEX.get(entry["rarity"], 0))
    pet = best["pet"]
    await respond(update, "\n".join(lines), InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 Summon ×1 (1,000💎)", callback_data="petsummon:1"), InlineKeyboardButton("×10 (10,000💎)", callback_data="petsummon:10"), InlineKeyboardButton("×50 (50,000💎)", callback_data="petsummon:50")],
        [InlineKeyboardButton("🐾 Pets", callback_data="menu:pets"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ]))


async def cmd_petsummon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    count = 1
    if context.args and context.args[0].isdigit():
        requested = int(context.args[0])
        if requested in config.PET_SUMMON_COSTS:
            count = requested
        else:
            await respond(update, "Choose <b>1</b>, <b>10</b>, or <b>50</b> summons: /petsummon 10", ui.back_keyboard("menu:pets"))
            return
    await pet_summon_result(update, context, count)


async def cmd_wealth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await leaderboard_view(update, context, "wealth")


async def cmd_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    owned = game.series_collection(db, update.effective_user.id)
    total_owned = sum(owned.values())
    total_all = len(data.CHARACTERS)
    lines = ["🎴 <b>COLLECTION PROGRESS</b>", f"Overall: <b>{total_owned}/{total_all}</b> heroes ({total_owned * 100 / total_all:.1f}%)", ""]
    for series in data.SERIES_ORDER:
        info = data.SERIES[series]
        have = owned.get(series, 0)
        total = len(data.CHARACTERS_BY_SERIES[series])
        bar = ui.percent_bar(have, total, 10)
        lines.append(f"{info['emoji']} <b>{ui.esc(info['name'])}</b> — {have}/{total}\n{bar}")
    await respond(update, "\n".join(lines), ui.back_keyboard())


async def cmd_codes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard_admin(update, context)
    if player is None:
        return
    rows = get_db(context).redeem_codes_list(20)
    lines = ["🎟️ <b>REDEEM CODES</b>", ""]
    if not rows:
        lines.append("No codes created yet. Use /createcode.")
    for row in rows:
        reward_text = ", ".join(f"{reward.get('kind')}:{reward.get('id', reward.get('qty', ''))}" for reward in row.get("rewards", []))
        expiry = f" • expires {row['expires_at']}" if row.get("expires_at") else ""
        lines.append(f"• <code>{ui.esc(row['code'])}</code> — {row['used_count']}/{row['max_uses']} used{expiry}\n   {ui.esc(reward_text)}")
    await respond(update, "\n".join(lines), ui.back_keyboard("admin:menu"))


async def cmd_dungeon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    series = parse_series(context.args[0]) if context.args else None
    await start_battle(update, context, "dungeon", series=series)


async def cmd_fish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    result = game.fish(get_db(context), update.effective_user.id)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"🎣 <b>Fishing Trip</b>\n🎁 {ui.reward_text(result['rewards'], result['drops'])}", ui.main_menu_keyboard())


async def cmd_mine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    result = game.mine(get_db(context), update.effective_user.id)
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"⛏️ <b>Mining Trip</b>\n🎁 {ui.reward_text(result['rewards'], result['drops'])}", ui.main_menu_keyboard())


async def cmd_banner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await gacha_view(update, context)


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard_admin(update, context)
    if player is None:
        return
    db = get_db(context)
    text = (
        "🛠 <b>ADMIN PANEL</b>\n\n"
        f"👥 Players: {db.player_count()}\n"
        f"🎴 Characters owned: {sum(len(db.characters(row['user_id'])) for row in db.all_players(500))}\n"
        f"🏯 Clans: {len(db.clan_leaderboard(999))}\n\n"
        "/grant &lt;user_id|@user&gt; &lt;kind&gt; &lt;id|amount&gt; [qty]\n"
        "   Kinds: currencies, exp, level, character, gear, item, pet, shard, title, everything\n"
        "/give &lt;user_id|@user&gt; &lt;kind&gt; &lt;id|amount&gt; [qty] — players send owned assets\n"
        "/ban &lt;user_id&gt; • /unban &lt;user_id&gt;\n"
        "/setlevel &lt;user_id&gt; &lt;level&gt;\n"
        "/resetplayer &lt;user_id&gt;\n"
        "/broadcast &lt;text&gt;\n"
        "/backup"
    )
    await respond(update, text, ui.back_keyboard())


async def cmd_give(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    args = list(context.args)
    reply = replied_user(update)
    if reply is not None:
        target = db.ensure_player(reply.id, reply.username, reply.first_name)
        tokens = args
    else:
        if len(args) < 3:
            await respond(update, "Usage: /give &lt;user_id|@user&gt; &lt;yens|gems|crystals|tickets|stamina|skill_points|item|character|gear|pet|shard&gt; &lt;id|amount&gt; [qty]\nOr reply to a player with: /give &lt;kind&gt; &lt;id|amount&gt; [qty]")
            return
        target = db.find_player(args[0])
        tokens = args[1:]
    if target is None:
        await respond(update, "❌ Player not found. Use their numeric ID, @username, or reply to them.")
        return
    if int(target["user_id"]) == int(player["user_id"]):
        await respond(update, "❌ You cannot give assets to yourself.")
        return
    if not tokens:
        await respond(update, "Usage: /give &lt;kind&gt; &lt;id|amount&gt; [qty]")
        return
    asset = asset_from_tokens(db, player["user_id"], tokens[0], tokens[1:])
    if asset is None:
        await respond(update, "❌ Unknown asset or you do not own it. Use /give &lt;kind&gt; &lt;id&gt; [qty].")
        return
    result = db.transfer_asset(player["user_id"], target["user_id"], *asset)
    if not result.get("ok"):
        await respond(update, f"❌ {ui.esc(result.get('reason', 'Transfer failed.'))}")
        return
    label = result.get("label", "asset")
    target_name = display_name(target, str(target["user_id"]))
    giver_name = display_name(player, str(player["user_id"]))
    notified = await notify_user(
        context,
        int(target["user_id"]),
        "🎁 <b>YOU RECEIVED A GIFT!</b>\n\n"
        f"👤 From: <b>{ui.esc(giver_name)}</b>\n"
        f"🆔 ID: <code>{int(player['user_id'])}</code>\n\n"
        f"🎁 You received: <b>{ui.esc(label)}</b>\n\n"
        "Check /inventory to see your new items.",
        ui.main_menu_keyboard(),
    )
    note = "They have been notified in DM." if notified else "They must start the bot once to receive DM notifications."
    await respond(update, f"✅ <b>Gift sent!</b>\n🎁 {ui.esc(label)} → <b>{ui.esc(target_name)}</b>\n{note}")


async def cmd_grant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = await guard_admin(update, context)
    if admin is None:
        return
    db = get_db(context)
    args = list(context.args)
    reply = replied_user(update)
    if reply is not None:
        target = db.ensure_player(reply.id, reply.username, reply.first_name)
        tokens = args
    else:
        if len(args) < 2:
            await respond(update, "Usage: /grant &lt;user_id|@user&gt; &lt;kind&gt; &lt;id|amount&gt; [qty]\nKinds: yens, gems, crystals, tickets, stamina, skill_points, exp, level, character, gear, item, pet, shard, title, everything")
            return
        target = db.find_player(args[0])
        tokens = args[1:]
    if target is None:
        await respond(update, "❌ Player not found.")
        return
    if not tokens:
        await respond(update, "Usage: /grant &lt;user&gt; &lt;kind&gt; &lt;id|amount&gt; [qty]")
        return
    kind = tokens[0].lower()
    rest = tokens[1:]
    qty = int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 1
    asset_id = rest[0] if rest else None
    if kind in ("yens", "gems", "crystals", "tickets", "stamina", "skill_points", "exp", "level"):
        if not rest or not rest[0].lstrip("-").isdigit():
            await respond(update, f"Usage: /grant &lt;user&gt; {kind} &lt;amount&gt;")
            return
    elif kind in ("character", "char"):
        char = resolve_any_character(rest[0]) if rest else None
        if char is None:
            await respond(update, "❌ Unknown character.")
            return
        kind, asset_id = "character", char["id"]
    elif kind == "gear":
        gear = data.GEAR.get(rest[0]) if rest else None
        if gear is None and rest:
            gear = next((item for item in data.GEAR.values() if rest[0].lower() in item["name"].lower()), None)
        if gear is None:
            await respond(update, "❌ Unknown gear.")
            return
        kind, asset_id, qty = "gear", gear["id"], int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 1
    elif kind == "item":
        item = resolve_item(rest[0]) if rest else None
        if item is None:
            await respond(update, "❌ Unknown item.")
            return
        item_key = next((key for key, value in data.ITEMS.items() if value is item), None)
        kind, asset_id, qty = "item", item_key, int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 1
    elif kind == "pet":
        pet = data.PETS.get(rest[0]) if rest else None
        if pet is None and rest:
            pet = next((item for item in data.PETS.values() if rest[0].lower() in item["name"].lower()), None)
        if pet is None:
            await respond(update, "❌ Unknown companion.")
            return
        kind, asset_id, qty = "pet", pet["id"], int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 1
    elif kind in ("shard", "shards"):
        char = resolve_any_character(rest[0]) if rest else None
        if char is None:
            await respond(update, "❌ Unknown character.")
            return
        kind, asset_id, qty = "shard", char["id"], int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 1
    elif kind == "title":
        if not rest or rest[0] not in data.TITLES:
            await respond(update, "❌ Unknown title.")
            return
        asset_id = rest[0]
    elif kind in ("all", "everything", "bundle"):
        kind, asset_id = "everything", None
    else:
        await respond(update, "❌ Unknown grant kind.")
        return
    result = db.grant_asset(target["user_id"], kind, asset_id, qty)
    if not result.get("ok"):
        await respond(update, f"❌ {ui.esc(result.get('reason', 'Grant failed.'))}")
        return
    message = result.get("message", "Grant complete.")
    notified = await notify_user(
        context,
        int(target["user_id"]),
        "🎁 <b>ADMIN GRANT RECEIVED</b>\n\n"
        f"👤 From: <b>{ui.esc(display_name(admin, 'Admin'))}</b>\n\n"
        f"🎁 {ui.esc(message)}\n\n"
        "Use /inventory or /profile to view your account.",
        ui.main_menu_keyboard(),
    )
    note = "Recipient notified in DM." if notified else "Recipient must start the bot once to receive DM notifications."
    await respond(update, f"✅ {ui.esc(message)}\n{note}")


def _offer_label(db: Database, trade: dict, side: str, offer: dict) -> str:
    kind = offer["kind"]
    qty = int(offer.get("qty", 1))
    if kind == "item":
        label = data.ITEMS.get(offer["id"], {}).get("name", offer["id"])
    elif kind == "character":
        label = data.CHARACTERS.get(offer["id"], {}).get("name", offer["id"])
    elif kind == "gear":
        owner = int(trade["initiator_id"] if side == "initiator" else trade["target_id"])
        gear = db.gear_instance(owner, int(offer["id"]))
        base_gear = data.GEAR.get(offer.get("gear_id") or "", {})
        label = f"{gear['name']} Lv.{gear['level']}" if gear else base_gear.get("name", f"Gear #{offer['id']}")
    elif kind == "pet":
        base = data.PETS.get(offer["id"], {})
        label = f"{base.get('emoji', '🐾')} {base.get('name', offer['id'])}"
    elif kind == "shard":
        label = f"Shards: {data.CHARACTERS.get(offer['id'], {}).get('name', offer['id'])}"
    else:
        label = str(offer["id"])
    if kind in ("yens", "gems", "crystals", "tickets", "stamina", "skill_points"):
        return f"{ui.fmt(offer['id'])} {kind}"
    return f"{label} x{qty}"


def trade_summary(db: Database, trade: dict, offers: dict | None = None) -> str:
    offers = offers or db._trade_offers(trade)
    initiator = db.player(int(trade["initiator_id"])) or {}
    target = db.player(int(trade["target_id"])) or {}
    lines = [f"🤝 <b>TRADE #{trade['id']}</b>", f"{ui.esc(display_name(initiator))} ↔ {ui.esc(display_name(target))}", ""]
    for side in ("initiator", "target"):
        title = display_name(initiator if side == "initiator" else target)
        lines.append(f"<b>{ui.esc(title)} offers:</b>")
        if not offers[side]:
            lines.append("  • Nothing yet")
        for offer in offers[side]:
            lines.append(f"  • {ui.esc(_offer_label(db, trade, side, offer))}")
        lines.append(f"Confirmed: {'✅' if trade.get(f'{side}_ok') else '⏳'}")
        lines.append("")
    lines.append("Both players must add at least one item and press Confirm. Nothing is exchanged until both sides confirm.")
    return "\n".join(lines)


def trade_complete_text(db: Database, trade: dict, offers: dict) -> str:
    initiator = db.player(int(trade["initiator_id"])) or {}
    target = db.player(int(trade["target_id"])) or {}
    lines = ["✅ <b>TRADE COMPLETE!</b>", f"Trade #{trade['id']} finished fairly.", ""]
    for side, giver, receiver in (
        ("initiator", initiator, target),
        ("target", target, initiator),
    ):
        for offer in offers.get(side, []):
            lines.append(f"🎁 {ui.esc(display_name(giver))} → {ui.esc(display_name(receiver))}: {ui.esc(_offer_label(db, trade, side, offer))}")
    return "\n".join(lines)


async def _notify_trade_other(context: ContextTypes.DEFAULT_TYPE, db: Database, trade: dict, user_id: int, text: str, *, show_buttons: bool = True) -> None:
    other_id = int(trade["target_id"]) if int(trade["initiator_id"]) == int(user_id) else int(trade["initiator_id"])
    await notify_user(context, other_id, text, trade_keyboard(trade) if show_buttons else None)


async def _start_trade(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database, player: dict, target: dict) -> None:
    result = db.trade_create(player["user_id"], target["user_id"])
    if not result.get("ok"):
        await respond(update, f"❌ {ui.esc(result.get('reason', 'Could not create trade.'))}")
        return
    trade = result["trade"]
    summary = trade_summary(db, trade)
    keyboard = trade_keyboard(trade)
    await respond(update, f"🤝 <b>Trade started with {ui.esc(display_name(target))}</b>\n\n{summary}", keyboard)
    await notify_user(
        context,
        int(target["user_id"]),
        f"🔔 <b>NEW TRADE REQUEST</b>\nFrom <b>{ui.esc(display_name(player))}</b>\n\n{summary}",
        keyboard,
    )


async def cmd_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    args = list(context.args)
    reply = replied_user(update)
    if not args:
        if reply is not None:
            target = db.ensure_player(reply.id, reply.username, reply.first_name)
            await _start_trade(update, context, db, player, target)
            return
        trade = db.trade_for(player["user_id"])
        if trade is None:
            await respond(update, "Usage: /trade &lt;user_id|@user&gt; or reply to a message — start a trade\n/trade add &lt;kind&gt; &lt;id|amount&gt; [qty]\n/trade remove &lt;kind&gt; [id]\n/trade confirm • /trade cancel • /trade view")
        else:
            await respond(update, trade_summary(db, trade), trade_keyboard(trade))
        return
    sub = args[0].lower()
    if sub in ("add", "remove"):
        if len(args) < 2:
            await respond(update, f"Usage: /trade {sub} &lt;kind&gt; &lt;id|amount&gt; [qty]")
            return
        if sub == "remove":
            result = db.trade_remove(player["user_id"], args[1], args[2] if len(args) > 2 else None)
        else:
            asset = asset_from_tokens(db, player["user_id"], args[1], args[2:])
            if asset is None:
                await respond(update, "❌ Unknown asset or you do not own it.")
                return
            kind, asset_id, qty = asset
            result = db.trade_add(player["user_id"], kind, asset_id, qty)
        if not result.get("ok"):
            await respond(update, f"❌ {ui.esc(result.get('reason', 'Could not update the trade.'))}")
            return
        trade = result["trade"]
        await respond(update, trade_summary(db, trade), trade_keyboard(trade))
        await _notify_trade_other(context, db, trade, player["user_id"], f"🔔 <b>Trade updated</b> by {ui.esc(display_name(player))}.\n\n{trade_summary(db, trade)}")
        return
    if sub in ("confirm", "accept"):
        result = db.trade_confirm(player["user_id"])
        if not result.get("ok"):
            await respond(update, f"❌ {ui.esc(result.get('reason', 'Confirm failed.'))}")
        elif result.get("completed"):
            text = trade_complete_text(db, result["trade"], result["offers"])
            await respond(update, text)
            await _notify_trade_other(context, db, result["trade"], player["user_id"], text, show_buttons=False)
        else:
            trade = result["trade"]
            await respond(update, f"✅ Your side is confirmed. Waiting for {ui.esc(display_name(db.player(int(trade['target_id']) if int(trade['initiator_id']) == int(player['user_id']) else int(trade['initiator_id']))))} to confirm.\n\n{trade_summary(db, trade)}", trade_keyboard(trade))
            await _notify_trade_other(context, db, trade, player["user_id"], f"🔔 <b>{ui.esc(display_name(player))} confirmed the trade.</b> Confirm when you are ready.\n\n{trade_summary(db, trade)}")
        return
    if sub == "cancel":
        trade = db.trade_for(player["user_id"])
        result = db.trade_cancel(player["user_id"])
        if result.get("ok"):
            await respond(update, "✅ Trade cancelled.")
            if trade:
                await _notify_trade_other(context, db, trade, player["user_id"], f"❌ <b>Trade cancelled</b> by {ui.esc(display_name(player))}.", show_buttons=False)
        else:
            await respond(update, f"❌ {ui.esc(result.get('reason', 'No active trade.'))}")
        return
    if sub in ("view", "info"):
        trade = db.trade_for(player["user_id"])
        await respond(update, trade_summary(db, trade) if trade else "❌ No active trade.", trade_keyboard(trade) if trade else None)
        return
    if reply is not None:
        target = db.ensure_player(reply.id, reply.username, reply.first_name)
    else:
        target = db.find_player(args[0])
    if target is None:
        await respond(update, "❌ Player not found. Use their ID, @username, or reply to them.")
        return
    await _start_trade(update, context, db, player, target)


async def handle_trade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    player = await guard(update, context)
    if player is None:
        return
    action = parts[1] if len(parts) > 1 else "view"
    db = get_db(context)
    trade = db.trade_for(player["user_id"])
    if trade is None:
        await respond(update, "❌ You have no active trade.", ui.back_keyboard())
        return
    if len(parts) > 2 and parts[2].isdigit() and int(parts[2]) != int(trade["id"]):
        await respond(update, "❌ That trade is no longer active.", ui.back_keyboard())
        return
    if action == "view":
        await respond(update, trade_summary(db, trade), trade_keyboard(trade))
        return
    if action == "petmenu":
        side = db._trade_side(trade, player["user_id"])
        offers = db._trade_offers(trade)
        offered = {str(offer["id"]) for offer in offers.get(side or "", []) if offer.get("kind") == "pet"}
        pets = [pet for pet in db.pets(player["user_id"]) if str(pet["pet_id"]) not in offered]
        if not pets:
            await respond(update, "🐾 You have no unoffered companions to trade.", trade_keyboard(trade))
            return
        rows = []
        for pet in pets[:30]:
            rows.append([InlineKeyboardButton(f"{pet['emoji']} {pet['name']} Lv.{pet['level']}", callback_data=f"trade:petadd:{trade['id']}:{pet['pet_id']}")])
        rows.append([InlineKeyboardButton("⬅️ Back to Trade", callback_data=f"trade:view:{trade['id']}")])
        await respond(update, "🐾 <b>Choose a companion to offer</b>\nTap one pet to add it to your side.", InlineKeyboardMarkup(rows))
        return
    if action == "petadd":
        if len(parts) < 4:
            await respond(update, "❌ Invalid companion.", trade_keyboard(trade))
            return
        result = db.trade_add(player["user_id"], "pet", parts[3], 1)
        if not result.get("ok"):
            await respond(update, f"❌ {ui.esc(result.get('reason', 'Could not offer that companion.'))}", trade_keyboard(trade))
            return
        trade = result["trade"]
        await respond(update, trade_summary(db, trade), trade_keyboard(trade))
        await _notify_trade_other(context, db, trade, player["user_id"], f"🔔 <b>Trade updated</b> by {ui.esc(display_name(player))}.\n\n{trade_summary(db, trade)}")
        return
    if action == "confirm":
        result = db.trade_confirm(player["user_id"])
        if not result.get("ok"):
            await respond(update, f"❌ {ui.esc(result.get('reason', 'Confirm failed.'))}", trade_keyboard(trade))
        elif result.get("completed"):
            text = trade_complete_text(db, result["trade"], result["offers"])
            await respond(update, text)
            await _notify_trade_other(context, db, result["trade"], player["user_id"], text, show_buttons=False)
        else:
            trade = result["trade"]
            await respond(update, f"✅ Confirmed. Waiting for the other player.\n\n{trade_summary(db, trade)}", trade_keyboard(trade))
            await _notify_trade_other(context, db, trade, player["user_id"], f"🔔 <b>{ui.esc(display_name(player))} confirmed the trade.</b> Confirm when ready.\n\n{trade_summary(db, trade)}")
        return
    if action == "cancel":
        result = db.trade_cancel(player["user_id"])
        await respond(update, "✅ Trade cancelled." if result.get("ok") else f"❌ {ui.esc(result.get('reason', 'No active trade.'))}")
        if result.get("ok"):
            await _notify_trade_other(context, db, trade, player["user_id"], f"❌ <b>Trade cancelled</b> by {ui.esc(display_name(player))}.", show_buttons=False)
        return
    await respond(update, trade_summary(db, trade), trade_keyboard(trade))


async def cmd_chapters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    series = parse_series(context.args[0]) if context.args else player.get("travel", "dragonball")
    status = game.chapter_status(db, player["user_id"], series)
    lines = [f"📖 <b>{series_name(series)} STORY</b>", ""]
    for chapter in status["chapters"]:
        number = int(chapter["number"])
        mark = "✅" if number in status["cleared"] else "▶️" if status["next"] and number == status["next"]["number"] else "🔒"
        lines.append(f"{mark} <b>Chapter {number}: {ui.esc(chapter['name'])}</b> — Lv.{chapter['level']}")
    lines.append("\nUse /chapter to fight the next chapter.")
    await respond(update, "\n".join(lines), ui.back_keyboard("menu:main"))


async def cmd_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    args = list(context.args)
    series = None
    number = None
    if args:
        parsed = parse_series(args[0])
        if parsed:
            series = parsed
            args = args[1:]
        if args and args[0].isdigit():
            number = int(args[0])
    await start_battle(update, context, "chapter", series=series, chapter=number)


async def cmd_switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_travel(update, context)


async def cmd_skillshop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    series = parse_series(context.args[0]) if context.args else player.get("travel", "dragonball")
    rows = game.skill_shop(series)
    lines = [f"🧠 <b>SKILL SHOP — {series_name(series)}</b>", f"Skill points: {player['skill_points']} • Buy with /skillbuy &lt;skill_id&gt;", ""]
    keyboard_rows = []
    for row in rows:
        skill = row["skill"]
        lines.append(f"• <b>{ui.esc(skill['name'])}</b> — {ui.fmt(row['cost'])} {row['currency']} • power x{skill['power']}\n   <code>{skill['id']}</code> • {ui.esc(skill['description'])}")
        keyboard_rows.append([InlineKeyboardButton(f"🛒 Buy {skill['name']} — {ui.fmt(row['cost'])} {row['currency']}", callback_data=f"skill:buy:{skill['id']}")])
    keyboard_rows.append([InlineKeyboardButton("🧠 My Skills", callback_data="menu:skills"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(keyboard_rows))


async def cmd_skillbuy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    if not context.args:
        await respond(update, "Usage: /skillbuy &lt;skill_id&gt;")
        return
    result = game.buy_skill(get_db(context), player["user_id"], context.args[0])
    if not result["ok"]:
        await respond(update, f"❌ {ui.esc(result['reason'])}")
        return
    await respond(update, f"✅ Learned <b>{ui.esc(result['skill']['name'])}</b> for {ui.fmt(result['cost'])} {result['currency']}!\nUse /skill_equip {result['skill']['id']} to equip it.")


async def cmd_summonboss(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args)
    series = None
    boss_id = None
    if args:
        possible = parse_series(args[0])
        if possible:
            series = possible
        else:
            boss_id = args[0]
    await start_battle(update, context, "summon", series=series, boss_id=boss_id)


async def cmd_summonattack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_summonboss(update, context)

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = await guard_admin(update, context)
    if admin is None or not context.args or not context.args[0].isdigit():
        if admin:
            await respond(update, "Usage: /ban &lt;user_id&gt;")
        return
    get_db(context).ban(int(context.args[0]), True)
    await respond(update, "🚫 Player banned.")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = await guard_admin(update, context)
    if admin is None or not context.args or not context.args[0].isdigit():
        if admin:
            await respond(update, "Usage: /unban &lt;user_id&gt;")
        return
    get_db(context).ban(int(context.args[0]), False)
    await respond(update, "✅ Player unbanned.")


async def cmd_setlevel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = await guard_admin(update, context)
    if admin is None:
        return
    if len(context.args) < 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await respond(update, "Usage: /setlevel &lt;user_id&gt; &lt;level&gt;")
        return
    target = int(context.args[0])
    level = max(1, min(100, int(context.args[1])))
    db = get_db(context)
    if db.player(target) is None:
        await respond(update, "Player not found.")
        return
    db.set_field(target, "level", level)
    db.set_field(target, "rank", data.rank_for_level(level)["name"])
    db.bump(target, "level", level)
    await respond(update, f"✅ Set <code>{target}</code> to level {level}.")


async def cmd_resetplayer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = await guard_admin(update, context)
    if admin is None or not context.args or not context.args[0].isdigit():
        if admin:
            await respond(update, "Usage: /resetplayer &lt;user_id&gt;")
        return
    get_db(context).reset_player(int(context.args[0]))
    await respond(update, "♻️ Player reset.")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = await guard_admin(update, context)
    if admin is None:
        return
    text = " ".join(context.args).strip()
    if not text:
        await respond(update, "Usage: /broadcast &lt;text&gt;")
        return
    db = get_db(context)
    sent = 0
    failed = 0
    for row in db.all_players(10000):
        try:
            await context.bot.send_message(row["user_id"], f"📢 <b>ANNOUNCEMENT</b>\n\n{ui.esc(text)}", parse_mode=ParseMode.HTML)
            sent += 1
        except TelegramError:
            failed += 1
    await respond(update, f"📢 Broadcast sent to {sent} players. Failed: {failed}.")


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = await guard_admin(update, context)
    if admin is None:
        return
    db = get_db(context)
    backup_dir = Path(config.BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"ultimate-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.db"
    source = sqlite3.connect(db.path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    await respond(update, f"💾 Backup created: <code>{ui.esc(target)}</code>")


ART_TYPES = ("character", "npc", "boss", "summon", "world", "clanraid", "pet", "map", "chapter", "clan", "profile")


def _art_catalog(db: Database | None = None) -> dict[str, dict[str, dict]]:
    catalog: dict[str, dict[str, dict]] = {key: {} for key in ART_TYPES}
    for char_id, char in data.CHARACTERS.items():
        catalog["character"][char_id] = {"name": char["name"], "id": char_id}
    for series, npcs in data.NPCS.items():
        for npc in npcs:
            catalog["npc"][npc["id"]] = {"name": npc["name"], "id": npc["id"]}
    for series, bosses in data.BOSSES.items():
        for boss in bosses:
            catalog["boss"][boss["id"]] = {"name": boss["name"], "id": boss["id"]}
    for boss in data.SUMMON_BOSSES:
        catalog["summon"][boss["id"]] = {"name": boss["name"], "id": boss["id"]}
    for boss in data.WORLD_BOSSES:
        catalog["world"][boss["id"]] = {"name": boss["name"], "id": boss["id"]}
    for raid in data.CLAN_RAIDS:
        catalog["clanraid"][raid["id"]] = {"name": raid["name"], "id": raid["id"]}
    for pet_id, pet in data.PETS.items():
        catalog["pet"][pet_id] = {"name": pet["name"], "id": pet_id}
    for series, floors in data.DUNGEONS.items():
        for floor in floors:
            catalog["map"][floor["id"]] = {"name": floor["name"], "id": floor["id"]}
        info = data.SERIES[series]
        catalog["map"][f"{series}_home"] = {"name": info["home"], "id": f"{series}_home"}
    for series, chapters in data.CHAPTERS.items():
        for chapter in chapters:
            catalog["chapter"][chapter["id"]] = {"name": chapter["name"], "id": chapter["id"]}
    for avatar_id, avatar in data.PROFILE_AVATARS.items():
        catalog["profile"][f"avatar_{avatar_id}"] = {"name": f"{avatar['name']} Avatar", "id": avatar_id}
    if db is not None:
        for clan in db.clan_leaderboard(500):
            key = str(clan.get("tag") or clan["id"]).lower()
            catalog["clan"][key] = {"name": f"{clan['name']} [{clan['tag']}]", "id": key}
    return catalog


def _resolve_art_target(query: str, forced_type: str | None = None, db: Database | None = None) -> tuple[str, str, str] | None:
    query = query.strip()
    if not query:
        return None
    catalog = _art_catalog(db)
    types = [forced_type] if forced_type in catalog else list(catalog)
    variants = [query]
    for separator in ("—", "–", " - "):
        if separator in query:
            variants = [part.strip() for part in query.split(separator) if part.strip()]
            break

    def normalize(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    for candidate in variants:
        key = candidate.lower().replace(" ", "_")
        normalized = normalize(candidate)
        for entity_type in types:
            entries = catalog[entity_type]
            if key in entries:
                return entity_type, key, entries[key]["name"]
            for entity_key, entry in entries.items():
                if normalize(entity_key) == normalized or normalize(entry["name"]) == normalized:
                    return entity_type, entity_key, entry["name"]
        for entity_type in types:
            entries = catalog[entity_type]
            for entity_key, entry in entries.items():
                lowered = entry["name"].lower()
                if candidate.lower() in lowered or lowered in candidate.lower():
                    return entity_type, entity_key, entry["name"]
    return None


async def cmd_explore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    series = parse_series(context.args[0]) if context.args else player.get("travel", "dragonball")
    if series is None:
        await respond(update, "❌ Unknown series. Use /explore dragonball|naruto|bleach|jujutsu|tempest.", ui.back_keyboard("menu:main"))
        return
    info = data.SERIES[series]
    npcs = data.NPCS[series]
    stamina = player["stamina"]
    lines = [
        f"{info['emoji']} <b>EXPLORE — {ui.esc(info['home'])}</b>",
        f"<i>{ui.esc(info['lore'])}</i>",
        "",
        f"⚡ Stamina: {stamina}/{player['max_stamina']} • Hunt cost: 8",
        "👹 <b>Nearby enemies</b>",
    ]
    for npc in npcs[:6]:
        lines.append(f"• {ui.esc(npc['name'])} — Lv.{npc['level']} • {data.ELEMENTS[npc['element']]['emoji']} • {ui.fmt(npc['hp'])} HP")
    lines.append("\nTap Hunt Preview to inspect an enemy and choose Battle or Flee.")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Hunt Preview", callback_data=f"hunt:reroll:{series}"), InlineKeyboardButton("🗺️ NPC List", callback_data="menu:npc")],
        [InlineKeyboardButton("🌍 Travel", callback_data="menu:travel"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ])
    await respond(update, "\n".join(lines), keyboard)


def heal_text(db: Database, user_id: int) -> str:
    player = db.require_player(user_id)
    stats = game.effective_stats(db, user_id)
    potions = battle.potions(db, user_id)
    lines = [
        "💚 <b>HEALING CAMP</b>",
        f"❤️ HP: {ui.percent_bar(player.get('current_hp', stats['hp']), stats['hp'], 14)} {ui.fmt(player.get('current_hp', 0))}/{ui.fmt(stats['hp'])}",
        f"🔵 MP: {ui.percent_bar(player.get('mp', stats['max_mp']), stats['max_mp'], 14)} {ui.fmt(player.get('mp', 0))}/{ui.fmt(stats['max_mp'])}",
        "",
        "Use a healing item below or buy more from /shop potions.",
    ]
    if potions:
        for item in potions:
            lines.append(f"{item['emoji']} {ui.esc(item['name'])} x{item['qty']} — restores {ui.fmt(item['value'])} HP")
    else:
        lines.append("No healing items. Buy potions in the shop.")
    return "\n".join(lines)


async def cmd_heal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    db.refresh_stamina(update.effective_user.id)
    rows = [[InlineKeyboardButton(f"{item['emoji']} Use {item['name']} x{item['qty']}", callback_data=f"heal:use:{item['item_id']}")] for item in battle.potions(db, update.effective_user.id)[:4]]
    rows.append([InlineKeyboardButton("🛒 Potions Shop", callback_data="shop:potions"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, heal_text(db, update.effective_user.id), InlineKeyboardMarkup(rows))


async def cmd_stamina(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    db.refresh_stamina(update.effective_user.id)
    player = db.require_player(update.effective_user.id)
    items = [item for item in db.items(update.effective_user.id) if item.get("kind") == "stamina" and int(item.get("qty", 0)) > 0]
    lines = [
        "⚡ <b>STAMINA STATION</b>",
        f"Stamina: {ui.percent_bar(player['stamina'], player['max_stamina'], 16)} {player['stamina']}/{player['max_stamina']}",
        f"Regenerates every {config.STAMINA_REGEN_SECONDS // 60} minutes.",
        "",
    ]
    rows = []
    if items:
        for item in items[:5]:
            lines.append(f"{item['emoji']} {ui.esc(item['name'])} x{item['qty']} — restores {ui.fmt(item['value'])} stamina")
            rows.append([InlineKeyboardButton(f"{item['emoji']} Use {item['name']} x{item['qty']}", callback_data=f"stamina:use:{item['item_id']}")])
    else:
        lines.append("No stamina items. Buy them from the shop below.")
    lines.append("\nShop: /shop potions — Stamina Drink, Stamina Crystal, Feast of Tempest.")
    rows.append([InlineKeyboardButton("🛒 Buy Stamina Items", callback_data="shop:potions"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_pity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    pity = int(player["pity"])
    lines = [
        "🎯 <b>GACHA PITY</b>",
        f"Progress: {ui.percent_bar(pity, config.GACHA_PITY, 16)} {pity}/{config.GACHA_PITY}",
        f"🎟️ Tickets: {player['tickets']} • 💎 Gems: {ui.fmt(player['gems'])}",
        "",
        f"At {config.GACHA_PITY} pulls you are guaranteed a Mythic or Divine hero.",
        "Pity carries across banners. Summon with /gacha or the buttons below.",
    ]
    await respond(update, "\n".join(lines), InlineKeyboardMarkup([
        [InlineKeyboardButton("🎴 Summon Banners", callback_data="menu:gacha"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ]))


async def cmd_element(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["🌀 <b>ELEMENT CHART</b>", ""]
    for element, info in data.ELEMENTS.items():
        strong = ", ".join(data.ELEMENTS[key]["name"] for key in info["strong"])
        weak = ", ".join(data.ELEMENTS[key]["name"] for key in info["weak"])
        lines.append(f"{info['emoji']} <b>{info['name']}</b>\n   Strong vs: {strong}\n   Weak vs: {weak}")
    lines.extend(["", "Element multipliers: strong x1.40 • weak x0.75."])
    await respond(update, "\n".join(lines), ui.back_keyboard())


async def cmd_unstuck(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    stats = game.effective_stats(db, update.effective_user.id)
    db.clear_battle(update.effective_user.id)
    db.set_vitals(update.effective_user.id, hp=stats["hp"], mp=stats["max_mp"])
    db.set_field(update.effective_user.id, "npc_streak", 0)
    with db.conn() as c:
        c.execute("DELETE FROM summon_bosses WHERE user_id=?", (int(update.effective_user.id),))
    await respond(update, "🧹 Stuck state cleared. HP/MP restored, NPC streak reset, and saved summon-boss HP reset.", ui.main_menu_keyboard())


async def cmd_crown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    user_id = update.effective_user.id
    level = int(player.get("level", 1))
    avatar = game.avatar_for(player)
    unlocked = [key for key, item in data.PROFILE_AVATARS.items() if level >= int(item["level"])]
    clan = db.clan(user_id)
    all_clans = db.clan_leaderboard(20)
    joinable = [
        item for item in all_clans
        if (not clan or int(item["id"]) != int(clan["id"]))
        and level >= int(item.get("min_level", 1))
        and (int(item.get("open_join", 1)) or db.clan_invite_pending(int(item["id"]), int(user_id)))
    ]
    lines = [
        "👑 <b>CROWN — PROFILE & CLAN HALL</b>",
        f"{avatar['icon']} Avatar: <b>{ui.esc(avatar['name'])}</b> • Unlocked: <b>{len(unlocked)}/{len(data.PROFILE_AVATARS)}</b>",
        f"🏯 Clan: <b>{ui.esc(clan['name']) if clan else 'None'}</b>"
        + (f" • {ui.esc(game.clan_bonus_text(clan))}" if clan else ""),
        f"🚪 Joinable clans: <b>{len(joinable)}</b>",
        "",
        "🎭 <b>AVATARS</b> — tap to equip",
    ]
    for key, item in data.PROFILE_AVATARS.items():
        unlocked_avatar = level >= int(item["level"])
        selected = key == (player.get("avatar") or "rookie")
        marker = "✅" if selected else ("🔓" if unlocked_avatar else "🔒")
        requirement = f" • Lv.{item['level']}" if not unlocked_avatar else ""
        lines.append(f"{marker} {item['icon']} <b>{ui.esc(item['name'])}</b>{requirement}")
    lines.extend(["", "🏯 <b>CLANS</b>"])
    if clan:
        info = db.clan_info(int(clan["id"]))
        members = len(info["members"]) if info else 0
        lines.append(f"✅ <b>{ui.esc(clan['name'])}</b> [{ui.esc(clan['tag'])}] • Lv.{clan.get('level', 1)} • {members}/30 members")
    else:
        lines.append("<i>You are not in a clan yet.</i>")
    if joinable:
        for item in joinable[:5]:
            lines.append(
                f"• <b>{ui.esc(item['name'])}</b> [{ui.esc(item['tag'])}] • Lv.{item.get('level', 1)} • "
                f"{item.get('members', 0)}/30 • {ui.esc(game.clan_bonus_text(item))}"
            )
    elif not clan:
        lines.append("<i>No open clans match your level. Create one below.</i>")
    rows = []
    avatar_buttons = [
        InlineKeyboardButton(
            ("✅ " if key == (player.get("avatar") or "rookie") else ("🔓 " if level >= int(item["level"]) else "🔒 ")) + f"{item['icon']} {item['name']}",
            callback_data=f"crown:avatar:{key}",
        )
        for key, item in data.PROFILE_AVATARS.items()
    ]
    for index in range(0, len(avatar_buttons), 2):
        rows.append(avatar_buttons[index:index + 2])
    for item in joinable[:4]:
        rows.append([InlineKeyboardButton(
            f"🏯 Join {item['name']} [{item['tag']}]",
            callback_data=f"crown:clan:{item['tag']}",
        )])
    rows.append([InlineKeyboardButton("🏯 Clan Menu", callback_data="menu:clan"), InlineKeyboardButton("🎴 Heroes", callback_data="chars:all:all:1")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def crown_art_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_admin(update.effective_user.id if update.effective_user else None):
        await respond(update, "🔒 Custom art tools are available to admins only.")
        return
    player = await guard(update, context)
    if player is None:
        return
    db = get_db(context)
    catalog = _art_catalog(db)
    labels = {
        "character": "🎴 Heroes", "npc": "👹 NPCs", "boss": "👑 Bosses", "summon": "🌌 Summons",
        "world": "🌍 World Bosses", "clanraid": "🏯 Clan Raids", "pet": "🐾 Pets", "map": "🗺️ Maps",
        "chapter": "📖 Chapters", "clan": "🏯 Clans", "profile": "👤 Profiles",
    }
    lines = ["👑 <b>CROWN ART — DYNAMIC ART MANAGER</b>", "Add or replace custom art for any entity.", ""]
    for entity_type, entries in catalog.items():
        uploaded = len(db.art_keys(entity_type))
        if entries:
            lines.append(f"{labels.get(entity_type, entity_type.title())}: <b>{uploaded}</b> uploaded • {len(entries)} slots")
    lines.extend([
        "",
        "Reply to a photo with: <code>/upload NAME</code>",
        "Example: <code>/upload Frieza</code> or <code>/upload boss Frieza</code>",
        "Custom art saves are kept for compatibility but images are no longer sent.",
    ])
    art_buttons = [
        InlineKeyboardButton(labels.get(entity_type, entity_type.title()), callback_data=f"art:list:{entity_type}")
        for entity_type in ART_TYPES
    ]
    rows = []
    for index in range(0, len(art_buttons), 2):
        rows.append(art_buttons[index:index + 2])
    rows.append([InlineKeyboardButton("⬅️ Crown Art", callback_data="crownart:view"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def cmd_crownart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await crown_art_view(update, context)


async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    player = await guard_admin(update, context)
    if player is None:
        return
    db = get_db(context)
    message = update.effective_message
    if message is None:
        return
    source = getattr(message, "reply_to_message", None) or message
    file_id = None
    photo = getattr(source, "photo", None)
    document = getattr(source, "document", None)
    if photo:
        file_id = photo[-1].file_id
    elif document and (document.mime_type or "").startswith("image/"):
        file_id = document.file_id
    if not file_id:
        await respond(update, "Reply to a photo or image file with <code>/upload NAME</code>, or send the photo with the command as its caption.")
        return
    args = list(context.args)
    if not args:
        await respond(update, "Usage: reply to an image with <code>/upload NAME</code> or <code>/upload TYPE NAME</code>.")
        return
    forced_type = None
    if len(args) > 1 and args[0].lower() in ART_TYPES:
        forced_type = args[0].lower()
        args = args[1:]
    query = " ".join(args).strip()
    target = _resolve_art_target(query, forced_type, db)
    if target is None:
        await respond(update, f"❌ No art target matches <b>{ui.esc(query)}</b>. Use /crownart for valid categories or <code>/upload boss NAME</code>.")
        return
    entity_type, entity_key, name = target
    db.art_set(entity_type, entity_key, name, file_id, update.effective_user.id)
    await respond(update, f"👑 Custom art saved for <b>{ui.esc(name)}</b> ({entity_type}).")


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    category = context.args[0].lower() if context.args else "players"
    await leaderboard_view(update, context, category)


async def cmd_inv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await inventory_view(update, context)


async def cmd_admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_admin(update, context)


async def cmd_admin_heal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = await guard_admin(update, context)
    if admin is None or not context.args or not context.args[0].isdigit():
        if admin:
            await respond(update, "Usage: /admin_heal &lt;user_id&gt;")
        return
    db = get_db(context)
    target_id = int(context.args[0])
    stats = game.effective_stats(db, target_id)
    db.set_vitals(target_id, hp=stats["hp"], mp=stats["max_mp"])
    await respond(update, f"✅ Fully healed player <code>{target_id}</code>.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ An unexpected error occurred. Please try again.")
        except TelegramError:
            pass


async def post_init(application: Application) -> None:
    db = Database(config.DB_PATH)
    application.bot_data["db"] = db
    logger.info("Database ready at %s", config.DB_PATH)
    logger.info("Loaded %d characters, %d gear, %d skills", len(data.CHARACTERS), len(data.GEAR), len(data.SKILLS))
    public_commands = [BotCommand(name, desc) for name, desc in COMMANDS]
    for attempt in range(3):
        try:
            await application.bot.set_my_commands(public_commands)
            logger.info("Registered %d public commands", len(public_commands))
            break
        except TelegramError as exc:
            logger.warning("Could not set public commands (attempt %d): %s", attempt + 1, exc)
            await asyncio.sleep(2)
    if config.ADMIN_IDS:
        admin_commands = public_commands + [BotCommand(name, desc) for name, desc in ADMIN_COMMANDS]
        admin_commands = admin_commands[:100]
        for admin_id in config.ADMIN_IDS:
            for attempt in range(3):
                try:
                    await application.bot.set_my_commands(
                        admin_commands,
                        scope=BotCommandScopeChat(chat_id=admin_id),
                    )
                    logger.info("Registered %d admin menu commands for %s", len(admin_commands), admin_id)
                    break
                except TelegramError as exc:
                    logger.warning("Could not set admin commands for %s (attempt %d): %s", admin_id, attempt + 1, exc)
                    await asyncio.sleep(2)
    username = application.bot.username or "unknown"
    logger.info("Connected to Telegram as @%s", username)


async def post_shutdown(application: Application) -> None:
    db = application.bot_data.get("db")
    if db is not None:
        db.ping()
    logger.info("Shutdown complete.")


COMMANDS: list[tuple[str, str]] = [
    ("start", "Start the multiverse adventure"),
    ("menu", "Open the main menu"),
    ("starter", "Claim your one-time starter pack"),
    ("redeem", "Redeem a code"),
    ("help", "Full command guide"),
    ("profile", "Profile, power and currencies"),
    ("register", "Choose your home series"),
    ("characters", "Browse your heroes"),
    ("character", "Inspect a hero"),
    ("team", "Set your 3-hero team"),
    ("equipchar", "Set your main hero"),
    ("levelup", "Level up a hero"),
    ("awaken", "Raise hero stars"),
    ("skills", "View skills"),
    ("learn", "Learn a skill"),
    ("skill_equip", "Equip a skill"),
    ("skillshop", "Shop series skills"),
    ("skillbuy", "Buy a skill"),
    ("inventory", "Items and gear"),
    ("use", "Use an item"),
    ("equip", "Equip gear"),
    ("unequip", "Unequip gear"),
    ("gacha", "Summon banners"),
    ("pull", "Summon heroes"),
    ("summonboss", "Fight a persistent summon boss"),
    ("wish", "Use 7 Dragon Balls"),
    ("shop", "Browse the shop"),
    ("buy", "Buy from the shop"),
    ("sell", "Sell an item"),
    ("daily_shop", "Daily rotating shop"),
    ("dailybuy", "Buy a daily shop slot"),
    ("forge", "Forge gear"),
    ("enhance", "Enhance equipped gear"),
    ("hunt", "Hunt NPCs"),
    ("npc", "View NPC zones"),
    ("boss", "Fight a persistent series boss"),
    ("summonattack", "Attack the active summon boss"),
    ("elite", "Fight an elite enemy"),
    ("raid", "World boss info"),
    ("attack", "Attack the world boss"),
    ("clanraid", "Clan raid info or actions"),
    ("explore", "Button-based exploration menu"),
    ("heal", "Heal with items and buttons"),
    ("stamina", "Restore stamina with items"),
    ("arena", "Random arena duel"),
    ("duel", "Challenge a player"),
    ("leaderboard", "Player, arena, clan and raid rankings"),
    ("clan", "Clan menu and actions"),
    ("clan_create", "Create a clan"),
    ("clan_join", "Join a clan"),
    ("clan_leave", "Leave your clan"),
    ("pity", "Gacha pity progress"),
    ("clan_donate", "Donate to your clan"),
    ("clan_kick", "Kick a clan member"),
    ("clan_promote", "Promote a member"),
    ("element", "Element strengths and weaknesses"),
    ("clan_announce", "Set clan announcement"),
    ("clan_disband", "Disband your clan"),
    ("clan_invite", "Invite a player to your clan"),
    ("unstuck", "Clear stuck battles and restore HP"),
    ("clan_accept", "Accept a clan invite"),
    ("clan_transfer", "Transfer clan leadership"),
    ("quests", "Quest log"),
    ("claim", "Claim quest rewards"),
    ("achievements", "Achievement log"),
    ("claimach", "Claim achievements"),
    ("titles", "View titles"),
    ("title", "Equip a title"),
    ("market", "Player market"),
    ("market_sell", "List an item"),
    ("market_buy", "Buy a listing"),
    ("give", "Send owned assets to a player"),
    ("trade", "Trade assets with a player"),
    ("daily", "Claim daily reward"),
    ("weekly", "Claim weekly reward"),
    ("monthly", "Claim monthly reward"),
    ("travel", "Change home series"),
    ("crown", "Profile avatar and clan hall"),
    ("chapters", "View story chapters"),
    ("chapter", "Fight a story chapter"),
    ("pets", "Companion collection"),
    ("pet_equip", "Equip a companion"),
    ("pet_feed", "Feed and level a companion"),
    ("userid", "Look up a player's Telegram ID"),
    ("petsummon", "Summon companions with gems"),
    ("dungeon", "Enter a series dungeon"),
    ("fish", "Fish for materials"),
    ("mine", "Mine for ore and crystals"),
    ("about", "About the bot"),
]

ADMIN_COMMANDS: list[tuple[str, str]] = [
    ("upload", "Upload custom art by replying to a photo"),
    ("createcode", "Create a redeem code"),
    ("admin_heal", "Admin: fully heal a player"),
    ("admin", "Admin panel"),
    ("grant", "Admin: grant any asset"),
    ("ban", "Admin: ban player"),
    ("unban", "Admin: unban player"),
    ("setlevel", "Admin: set player level"),
    ("resetplayer", "Admin: reset player"),
    ("broadcast", "Admin: broadcast"),
    ("backup", "Admin: backup database"),
]

HANDLERS = {
    "start": cmd_start,
    "starter": cmd_starter,
    "menu": cmd_menu,
    "help": cmd_help,
    "about": cmd_about,
    "myid": cmd_myid,
    "userid": cmd_userid,
    "id": cmd_userid,
    "register": cmd_register,
    "profile": cmd_profile,
    "stats": cmd_profile,
    "characters": cmd_characters,
    "chars": cmd_characters,
    "cnaracters": cmd_characters,
    "character": cmd_character,
    "team": cmd_team,
    "equipchar": cmd_equipchar,
    "levelup": cmd_levelup,
    "awaken": cmd_awaken,
    "fuse": cmd_awaken,
    "skills": cmd_skills,
    "learn": cmd_learn,
    "skill_equip": cmd_skill_equip,
    "skillshop": cmd_skillshop,
    "skillbuy": cmd_skillbuy,
    "inventory": cmd_inventory,
    "gear": cmd_gear,
    "use": cmd_use,
    "equip": cmd_equip,
    "unequip": cmd_unequip,
    "redeem": cmd_redeem,
    "createcode": cmd_createcode,
    "gacha": cmd_gacha,
    "pull": cmd_pull,
    "summon": cmd_summon,
    "summonboss": cmd_summonboss,
    "summonattack": cmd_summonattack,
    "wish": cmd_wish,
    "banner": cmd_banner,
    "shop": cmd_shop,
    "buy": cmd_buy,
    "sell": cmd_sell,
    "daily_shop": cmd_daily_shop,
    "dailybuy": cmd_dailybuy,
    "forge": cmd_forge,
    "craft": cmd_craft,
    "enhance": cmd_enhance,
    "hunt": cmd_hunt,
    "adventure": cmd_adventure,
    "npc": cmd_npc,
    "boss": cmd_boss,
    "elite": cmd_elite,
    "streak": cmd_streak,
    "raid": cmd_raid,
    "global": cmd_global,
    "worldboss": cmd_worldboss,
    "attack": cmd_attack,
    "clanraid": cmd_clanraid,
    "clanraid_start": cmd_clanraid_start,
    "clanraid_attack": cmd_clanraid_attack,
    "arena": cmd_arena,
    "duel": cmd_duel,
    "leaderboard": cmd_leaderboard,
    "wealth": cmd_wealth,
    "collection": cmd_collection,
    "codes": cmd_codes,
    "clan": cmd_clan,
    "clan_create": cmd_clan_create,
    "clan_join": cmd_clan_join,
    "clan_leave": cmd_clan_leave,
    "clan_info": cmd_clan_info,
    "clan_donate": cmd_clan_donate,
    "clan_kick": cmd_clan_kick,
    "clan_promote": cmd_clan_promote,
    "clan_demote": cmd_clan_demote,
    "clan_announce": cmd_clan_announce,
    "clan_disband": cmd_clan_disband,
    "clan_invite": cmd_clan_invite,
    "clan_add": cmd_clan_add,
    "clan_accept": cmd_clan_accept,
    "clan_transfer": cmd_clan_transfer,
    "quests": cmd_quests,
    "claim": cmd_claim,
    "achievements": cmd_achievements,
    "claimach": cmd_claimach,
    "titles": cmd_titles,
    "title": cmd_title,
    "market": cmd_market,
    "market_sell": cmd_market_sell,
    "market_buy": cmd_market_buy,
    "market_cancel": cmd_market_cancel,
    "give": cmd_give,
    "trade": cmd_trade,
    "grant": cmd_grant,
    "daily": cmd_daily,
    "weekly": cmd_weekly,
    "monthly": cmd_monthly,
    "travel": cmd_travel,
    "switch": cmd_switch,
    "chapters": cmd_chapters,
    "chapter": cmd_chapter,
    "series": cmd_series,
    "codex": cmd_codex,
    "events": cmd_events,
    "settings": cmd_settings,
    "pets": cmd_pets,
    "pet": cmd_pet,
    "pet_equip": cmd_pet_equip,
    "pet_feed": cmd_pet_feed,
    "pet_summon": cmd_pet_summon,
    "petsummon": cmd_petsummon,
    "dungeon": cmd_dungeon,
    "explore": cmd_explore,
    "heal": cmd_heal,
    "stamina": cmd_stamina,
    "pity": cmd_pity,
    "element": cmd_element,
    "unstuck": cmd_unstuck,
    "crown": cmd_crown,
    "crownart": cmd_crownart,
    "crown_art": cmd_crownart,
    "upload": cmd_upload,
    "top": cmd_top,
    "inv": cmd_inv,
    "admin_help": cmd_admin_help,
    "admin_heal": cmd_admin_heal,
    "fish": cmd_fish,
    "mine": cmd_mine,
    "admin": cmd_admin,
    "ban": cmd_ban,
    "unban": cmd_unban,
    "setlevel": cmd_setlevel,
    "resetplayer": cmd_resetplayer,
    "broadcast": cmd_broadcast,
    "backup": cmd_backup,
}


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    payload = query.data or ""
    parts = payload.split(":")
    key = parts[0]
    if key == "trade":
        await handle_trade_callback(update, context, parts)
        return
    if key == "menu":
        target = parts[1] if len(parts) > 1 else "main"
        if target == "main":
            player = await guard(update, context)
            if player:
                await respond(update, main_menu_text(player), ui.main_menu_keyboard())
        elif target == "profile":
            await cmd_profile(update, context)
        elif target == "gacha":
            await gacha_view(update, context)
        elif target == "hunt":
            await cmd_hunt(update, context)
        elif target == "boss":
            await cmd_boss(update, context)
        elif target == "raid":
            await raid_view(update, context)
        elif target == "clan":
            await clan_view(update, context)
        elif target == "clanraid":
            context.args = []
            await cmd_clanraid(update, context)
        elif target == "inventory":
            await inventory_view(update, context)
        elif target == "shop":
            await shop_view(update, context, "all")
        elif target == "dungeon":
            context.args = []
            await cmd_dungeon(update, context)
        elif target == "pets":
            await pets_view(update, context)
        elif target == "skills":
            await cmd_skills(update, context)
        elif target == "skillshop":
            context.args = []
            await cmd_skillshop(update, context)
        elif target == "fish":
            await cmd_fish(update, context)
        elif target == "mine":
            await cmd_mine(update, context)
        elif target == "chapters":
            context.args = []
            await cmd_chapters(update, context)
        elif target == "summonboss":
            context.args = []
            await cmd_summonboss(update, context)
        elif target == "explore":
            context.args = []
            await cmd_explore(update, context)
        elif target == "heal":
            await cmd_heal(update, context)
        elif target == "pity":
            await cmd_pity(update, context)
        elif target == "element":
            await cmd_element(update, context)
        elif target == "unstuck":
            await cmd_unstuck(update, context)
        elif target == "crown":
            await cmd_crown(update, context)
        elif target == "npc":
            context.args = []
            await cmd_npc(update, context)
        elif target == "travel":
            await travel_view(update, context)
        elif target == "quests":
            await quests_view(update, context, "daily")
        elif target == "leaderboard":
            await leaderboard_view(update, context, "wealth")
        elif target == "help":
            await cmd_help(update, context)
        return
    if key == "startseries":
        series = parts[1] if len(parts) > 1 else "dragonball"
        context.args = [series]
        await cmd_register(update, context)
        return
    if key == "banner":
        series = parts[1] if len(parts) > 1 else "dragonball"
        await banner_view(update, context, series)
        return
    if key == "pull":
        series = parts[1] if len(parts) > 1 else "dragonball"
        count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        await do_pull(update, context, series, count)
        return
    if key == "shop":
        action = parts[1] if len(parts) > 1 else "all"
        if action == "item" and len(parts) > 2:
            category = parts[3] if len(parts) > 3 and parts[3] in ("all", "potions", "summon", "materials", "gear") else "all"
            page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1
            await show_shop_item(update, context, parts[2], category, page)
            return
        if action == "page" and len(parts) > 3:
            category = parts[2] if parts[2] in ("all", "potions", "summon", "materials", "gear", "daily") else "all"
            page = int(parts[3]) if parts[3].isdigit() else 1
            await shop_view(update, context, category, page)
            return
        if action == "buy" and len(parts) > 3:
            player = await guard(update, context)
            if player is None:
                return
            qty = int(parts[3]) if parts[3].isdigit() else 1
            result = game.buy_shop(get_db(context), update.effective_user.id, parts[2], qty)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:shop"))
                return
            await respond(update, f"✅ Bought <b>{ui.esc(result['name'])}</b> x{result['qty']} for {ui.fmt(result['price'])} {result['currency']}.", InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Keep Shopping", callback_data="menu:shop"), InlineKeyboardButton("🎒 Inventory", callback_data="menu:inventory")],
            ]))
            return
        if action == "dailybuy" and len(parts) > 2 and parts[2].isdigit():
            player = await guard(update, context)
            if player is None:
                return
            result = game.buy_daily(get_db(context), update.effective_user.id, int(parts[2]))
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("shop:daily"))
                return
            offer = result["offer"]
            await respond(update, f"✅ Bought {offer['emoji']} <b>{ui.esc(offer['name'])}</b> for {ui.fmt(offer['price'])} {offer['currency']}.", InlineKeyboardMarkup([
                [InlineKeyboardButton("🌅 Daily Shop", callback_data="shop:daily"), InlineKeyboardButton("🎒 Inventory", callback_data="menu:inventory")],
            ]))
            return
        await shop_view(update, context, action)
        return
    if key == "inv":
        player = await guard(update, context)
        if player is None:
            return
        action = parts[1] if len(parts) > 1 else "view"
        db = get_db(context)
        if action == "use" and len(parts) > 2:
            result = game.use_item(db, update.effective_user.id, parts[2], 1)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:inventory"))
                return
            await inventory_view(update, context)
            return
        if action == "sell" and len(parts) > 2:
            result = game.sell_item(db, update.effective_user.id, parts[2], 1)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:inventory"))
                return
            await inventory_view(update, context)
            return
        if action == "equip" and len(parts) > 2 and parts[2].isdigit():
            result = db.equip_gear(update.effective_user.id, int(parts[2]))
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:inventory"))
                return
            await inventory_view(update, context)
            return
        if action == "unequip" and len(parts) > 2:
            db.unequip_gear(update.effective_user.id, parts[2])
            await inventory_view(update, context)
            return
        await inventory_view(update, context)
        return
    if key == "quests":
        action = parts[1] if len(parts) > 1 else "daily"
        if action == "claim":
            await cmd_claim(update, context)
        else:
            await quests_view(update, context, action)
        return
    if key == "chars":
        series = parts[1] if len(parts) > 1 and parts[1] != "all" else None
        rarity = parts[2] if len(parts) > 2 and parts[2] != "all" else None
        page = parts[3] if len(parts) > 3 else "1"
        args = []
        if series:
            args.append(series)
        if rarity:
            args.append(rarity)
        args.append(page)
        await characters_view(update, context, args)
        return
    if key == "pick" and len(parts) > 3:
        action = parts[1]
        series = parts[2] if parts[2] != "all" else None
        rarity = parts[3] if parts[3] != "all" else None
        page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1
        if action not in PICK_TITLES:
            await respond(update, "❌ Unknown hero action.", ui.back_keyboard())
            return
        await hero_picker(update, context, action, PICK_TITLES[action], series=series, rarity=rarity, page=page)
        return
    if key == "char":
        action = parts[1] if len(parts) > 1 else ""
        char_id = parts[2] if len(parts) > 2 else ""
        if action == "view":
            await character_detail(update, context, char_id)
        elif action in ("equip", "setmain"):
            context.args = [char_id]
            await cmd_equipchar(update, context)
        elif action == "level":
            context.args = [char_id]
            await cmd_levelup(update, context)
        elif action == "awaken":
            context.args = [char_id]
            await cmd_awaken(update, context)
        return
    if key == "team":
        player = await guard(update, context)
        if player is None:
            return
        action = parts[1] if len(parts) > 1 else "view"
        db = get_db(context)
        if action == "view":
            await team_view(update, context)
            return
        if action == "clear":
            db.set_team(update.effective_user.id, [])
            await team_view(update, context)
            return
        if action == "filter" and len(parts) > 3:
            series = parts[2] if parts[2] != "all" else None
            rarity = parts[3] if parts[3] != "all" else None
            page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1
            await team_view(update, context, series=series, rarity=rarity, page=page)
            return
        if action in ("up", "down") and len(parts) > 2:
            char_id = parts[2]
            team = [cid for cid in db.team(update.effective_user.id) if cid in {c["id"] for c in db.characters(update.effective_user.id)}]
            if char_id in team:
                index = team.index(char_id)
                target = max(0, index - 1) if action == "up" else min(len(team) - 1, index + 1)
                team[index], team[target] = team[target], team[index]
                db.set_team(update.effective_user.id, team)
            await team_view(update, context)
            return
        if action in ("add", "remove") and len(parts) > 2:
            char_id = parts[2]
            team = [cid for cid in db.team(update.effective_user.id)]
            if action == "add":
                if char_id not in team:
                    team.append(char_id)
                team = team[: config.MAX_TEAM]
            else:
                team = [cid for cid in team if cid != char_id]
            result = db.set_team(update.effective_user.id, team)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("team:view"))
                return
            await team_view(update, context)
            return
        await team_view(update, context)
        return
    if key == "clan":
        player = await guard(update, context)
        if player is None:
            return
        db = get_db(context)
        action = parts[1] if len(parts) > 1 else ""
        if action == "leave_request":
            await clan_leave_request(update, context)
            return
        if action == "leave_no":
            await clan_view(update, context)
            return
        if action == "leave_yes":
            result = db.leave_clan(update.effective_user.id)
            await respond(update, "✅ You left the clan." if result["ok"] else f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:clan"))
            return
        if action == "disband_yes":
            result = db.clan_disband(update.effective_user.id)
            await respond(update, "🏯 Clan disbanded." if result["ok"] else f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:clan"))
            return
        if action == "disband_no":
            await clan_view(update, context)
            return
        if action == "promote_menu":
            clan = db.clan(update.effective_user.id)
            member = db.clan_member(update.effective_user.id)
            if clan is None or member is None or member["role"] != "leader":
                await respond(update, "❌ Only the clan leader can promote a new leader.", ui.back_keyboard("menu:clan"))
                return
            info = db.clan_info(clan["id"])
            rows = []
            for target in info["members"]:
                if int(target["user_id"]) == int(update.effective_user.id):
                    continue
                name = target.get("first_name") or target.get("username") or str(target["user_id"])
                rows.append([InlineKeyboardButton(f"👑 Promote {name}", callback_data=f"clan:transfer:{target['user_id']}")])
            rows.append([InlineKeyboardButton("❌ Cancel", callback_data="menu:clan")])
            await respond(update, "👑 <b>Choose the new clan leader</b>\nThis transfers leadership immediately.", InlineKeyboardMarkup(rows))
            return
        if action == "transfer" and len(parts) > 2:
            result = db.clan_transfer(update.effective_user.id, parts[2])
            await respond(update, "👑 Leadership transferred." if result["ok"] else f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:clan"))
            return
        if action == "donate" and len(parts) > 2 and parts[2].isdigit():
            result = db.clan_donate(update.effective_user.id, "yens", int(parts[2]))
            await respond(update, f"✅ Donated {ui.fmt(result['amount'])} yens." if result["ok"] else f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:clan"))
            return
        if action == "settings":
            await respond(update, "⚙️ <b>Clan Settings</b>\n\n/clan desc &lt;text&gt;\n/clan open on|off\n/clan minlevel &lt;level&gt;\n/clan announce &lt;text&gt;\n/clan invite &lt;user&gt;\n/clan kick &lt;user&gt;\n/clan promote &lt;user&gt;\n/clan demote &lt;user&gt;", ui.back_keyboard("menu:clan"))
            return
    if key == "world" and len(parts) > 1 and parts[1] == "attack":
        await cmd_attack(update, context)
        return
    if key == "clanraid" and len(parts) > 1 and parts[1] == "attack":
        await cmd_clanraid_attack(update, context)
        return
    if key == "lb":
        await leaderboard_view(update, context, parts[1] if len(parts) > 1 else "wealth")
        return
    if key == "btl":
        player = await guard(update, context)
        if player is None:
            return
        raw_action = parts[1] if len(parts) > 1 else "a"
        action = {
            "a": "attack", "g": "guard", "d": "guard", "s": "skill",
            "u": "ultimate", "t": "transform", "x": "switch", "p": "potion", "f": "flee",
        }.get(raw_action, raw_action)
        battle_id = parts[-1]
        payload = parts[2] if raw_action in ("s", "p") and len(parts) > 3 else None
        result = battle.act(get_db(context), update.effective_user.id, battle_id, action, payload)
        if not result["ok"]:
            await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard())
            return
        await show_battle(update, context, result["battle"])
        return
    if key == "battle" and len(parts) > 2 and parts[1] == "start":
        mode = parts[2]
        series = parts[3] if len(parts) > 3 and parts[3] in data.SERIES else None
        await start_battle(update, context, mode, series=series)
        return
    if key == "travel" and len(parts) > 1:
        player = await guard(update, context)
        if player is None:
            return
        series = parse_series(parts[1])
        if series is None:
            await respond(update, "Unknown series.", ui.back_keyboard("menu:travel"))
            return
        game.travel(get_db(context), update.effective_user.id, series)
        await respond(update, f"🌍 Traveled to {series_name(series)} — <b>{data.SERIES[series]['home']}</b>.", ui.main_menu_keyboard())
        return
    if key == "stamina" and len(parts) > 2 and parts[1] == "use":
        player = await guard(update, context)
        if player is None:
            return
        result = game.use_item(get_db(context), update.effective_user.id, parts[2], 1)
        if not result["ok"]:
            await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard())
            return
        await cmd_stamina(update, context)
        return
    if key == "heal" and len(parts) > 2 and parts[1] == "use":
        player = await guard(update, context)
        if player is None:
            return
        result = game.use_item(get_db(context), update.effective_user.id, parts[2], 1)
        if not result["ok"]:
            await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:heal"))
            return
        await cmd_heal(update, context)
        return
    if key == "stat":
        player = await guard(update, context)
        if player is None:
            return
        stat = parts[1] if len(parts) > 1 else ""
        result = get_db(context).allocate_stat(update.effective_user.id, stat, 1)
        if not result["ok"]:
            await respond(update, f"❌ {ui.esc(result['reason'])}")
            return
        await cmd_profile(update, context)
        return
    if key == "crownart":
        await crown_art_view(update, context)
        return
    if key == "crown":
        player = await guard(update, context)
        if player is None:
            return
        action = parts[1] if len(parts) > 1 else "view"
        db = get_db(context)
        if action == "view":
            await cmd_crown(update, context)
            return
        if action == "art":
            await crown_art_view(update, context)
            return
        if action == "avatar" and len(parts) > 2:
            avatar_id = parts[2]
            avatar = data.PROFILE_AVATARS.get(avatar_id)
            if avatar is None:
                await respond(update, "❌ Unknown avatar.", ui.back_keyboard("crown:view"))
                return
            if int(player.get("level", 1)) < int(avatar["level"]):
                await respond(
                    update,
                    f"🔒 Reach level {avatar['level']} to unlock {avatar['icon']} <b>{ui.esc(avatar['name'])}</b>.",
                    ui.back_keyboard("crown:view"),
                )
                return
            db.set_field(update.effective_user.id, "avatar", avatar_id)
            await cmd_crown(update, context)
            return
        if action == "clan" and len(parts) > 2:
            result = db.join_clan(update.effective_user.id, parts[2])
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("crown:view"))
                return
            await cmd_crown(update, context)
            return
        await cmd_crown(update, context)
        return
    if key == "art" and len(parts) > 2 and parts[1] == "list":
        if not config.is_admin(update.effective_user.id if update.effective_user else None):
            await respond(update, "🔒 Custom art tools are available to admins only.")
            return
        player = await guard(update, context)
        if player is None:
            return
        db = get_db(context)
        entity_type = parts[2]
        if entity_type not in ART_TYPES:
            await respond(update, "❌ Unknown art category.", ui.back_keyboard("crownart:view"))
            return
        labels = {
            "character": "Heroes", "npc": "NPCs", "boss": "Bosses", "summon": "Summons",
            "world": "World Bosses", "clanraid": "Clan Raids", "pet": "Pets", "map": "Maps",
            "chapter": "Chapters", "clan": "Clans", "profile": "Profiles",
        }
        catalog = _art_catalog(db).get(entity_type, {})
        uploaded = db.art_keys(entity_type)
        entries = sorted(catalog.items(), key=lambda item: item[1].get("name", "").lower())
        page = max(1, int(parts[3])) if len(parts) > 3 and parts[3].isdigit() else 1
        per_page = 30
        total_pages = max(1, (len(entries) + per_page - 1) // per_page)
        page = min(page, total_pages)
        page_entries = entries[(page - 1) * per_page:page * per_page]
        have_count = sum(1 for key, _ in entries if key in uploaded)
        lines = [
            f"👑 <b>CROWN · {labels.get(entity_type, entity_type.title()).upper()}</b>",
            f"✅ Uploaded: <b>{have_count}</b> • ❌ Missing: <b>{len(entries) - have_count}</b> • 📦 Slots: <b>{len(entries)}</b> • Page {page}/{total_pages}",
            "",
        ]
        if page_entries:
            for key, entry in page_entries:
                marker = "✅" if key in uploaded else "❌"
                lines.append(f"{marker} {ui.esc(entry.get('name', key))} — <code>{ui.esc(key)}</code>")
            lines.append("")
            lines.append("Reply to a photo with <code>/upload TYPE NAME</code> to add art.")
        else:
            lines.append("No art slots exist for this category yet.")
            lines.append("Create the entity or clan first, then upload art.")
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"art:list:{entity_type}:{page - 1}"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"art:list:{entity_type}:{page + 1}"))
        rows = [nav] if nav else []
        rows.append([InlineKeyboardButton("🖼️ Crown Art", callback_data="crownart:view"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
        await respond(update, "\n".join(lines), InlineKeyboardMarkup(rows))
        return
    if key == "boss":
        player = await guard(update, context)
        if player is None:
            return
        action = parts[1] if len(parts) > 1 else ""
        if action == "flee":
            await respond(update, "🏃 You left the boss hunt. No stamina was used.", ui.main_menu_keyboard())
            return
        if action == "view" and len(parts) > 2:
            context.args = [parts[2]]
            await boss_view(update, context)
            return
        if action == "fight" and len(parts) > 3:
            await start_battle(update, context, "boss", series=parts[2], boss_id=parts[3])
            return
        context.args = []
        await boss_view(update, context)
        return
    if key == "hunt":
        player = await guard(update, context)
        if player is None:
            return
        action = parts[1] if len(parts) > 1 else ""
        if action == "flee":
            await respond(update, "🏃 You fled from the encounter. No stamina was used.", ui.main_menu_keyboard())
            return
        if action == "reroll" and len(parts) > 2:
            context.args = [parts[2]]
            await hunt_view(update, context)
            return
        if action == "fight" and len(parts) > 3:
            await start_battle(update, context, "hunt", series=parts[2], npc_id=parts[3])
            return
        context.args = []
        await hunt_view(update, context)
        return
    if key == "ach" and len(parts) > 1 and parts[1] == "claim":
        await cmd_claimach(update, context)
        return
    if key == "skill" and len(parts) > 2:
        player = await guard(update, context)
        if player is None:
            return
        action = parts[1]
        skill_id = parts[2]
        db = get_db(context)
        if action == "equip":
            result = db.equip_skill(update.effective_user.id, skill_id)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:skills"))
                return
            await cmd_skills(update, context)
            return
        if action == "learn":
            result = db.learn_skill(update.effective_user.id, skill_id)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:skills"))
                return
            await respond(update, f"✅ Learned <b>{ui.esc(result['skill']['name'])}</b>!", ui.back_keyboard("menu:skills"))
            return
        if action == "buy":
            result = game.buy_skill(db, update.effective_user.id, skill_id)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:skillshop"))
                return
            await respond(update, f"✅ Learned <b>{ui.esc(result['skill']['name'])}</b> for {ui.fmt(result['cost'])} {result['currency']}!", ui.back_keyboard("menu:skills"))
            return
    if key == "petsummon":
        count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        await pet_summon_result(update, context, count if count in config.PET_SUMMON_COSTS else 1)
        return
    if key == "pet":
        player = await guard(update, context)
        if player is None:
            return
        action = parts[1] if len(parts) > 1 else ""
        db = get_db(context)
        if action == "equip" and len(parts) > 2:
            result = db.equip_pet(update.effective_user.id, parts[2])
            if not result:
                await respond(update, "❌ You do not own that companion.", ui.back_keyboard("menu:pets"))
                return
            await pets_view(update, context)
            return
        if action == "feed" and len(parts) > 2:
            levels = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
            result = db.feed_pet(update.effective_user.id, parts[2], levels)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("menu:pets"))
                return
            await pets_view(update, context)
            return
        if action == "hatch" and len(parts) > 2:
            result = game.use_item(db, update.effective_user.id, parts[2], 1)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Shop", callback_data="shop:summon"), InlineKeyboardButton("⬅️ Pets", callback_data="menu:pets")],
                ]))
                return
            pet = result.get("pet", {})
            await respond(update, f"🥚 Hatched {pet.get('emoji', '🐾')} <b>{ui.esc(pet.get('name', 'Companion'))}</b>!", InlineKeyboardMarkup([
                [InlineKeyboardButton("🐾 Pets", callback_data="menu:pets"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
            ]))
            return
        await pets_view(update, context)
        return
    if key == "title" and len(parts) > 2 and parts[1] == "equip":
        player = await guard(update, context)
        if player is None:
            return
        if get_db(context).equip_title(update.effective_user.id, parts[2]):
            title = data.TITLES.get(parts[2], {})
            await respond(update, f"🏷️ Equipped title: <b>{ui.esc(title.get('name', parts[2]))}</b>.", ui.back_keyboard("menu:main"))
        else:
            await respond(update, "❌ Title is locked. Check /titles.", ui.back_keyboard("menu:main"))
        return
    if key == "market":
        if len(parts) > 1 and parts[1] in ("buy", "cancel"):
            player = await guard(update, context)
            if player is None:
                return
            listing_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            result = get_db(context).market_buy(update.effective_user.id, listing_id) if parts[1] == "buy" else get_db(context).market_cancel(update.effective_user.id, listing_id)
            if not result["ok"]:
                await respond(update, f"❌ {ui.esc(result['reason'])}", ui.back_keyboard("market:1"))
                return
            await market_view(update, context, 1)
            return
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        await market_view(update, context, page)
        return
    if key == "seriesinfo":
        series = parts[1] if len(parts) > 1 else "dragonball"
        info = data.SERIES.get(series)
        if info:
            owned = game.series_collection(get_db(context), update.effective_user.id).get(series, 0) if update.effective_user else 0
            await respond(update, f"{info['emoji']} <b>{ui.esc(info['name'])}</b>\n\nHome: {info['home']}\n{info['lore']}\n\nHeroes: {owned}/{len(data.CHARACTERS_BY_SERIES[series])} owned\nWorlds: {', '.join(info['worlds'])}", ui.back_keyboard("menu:main"))
        return


def build_application() -> Application:
    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    for name, handler in HANDLERS.items():
        application.add_handler(CommandHandler(name, handler))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    problems = config.validate()
    for problem in problems:
        logger.warning("Configuration: %s", problem)
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not configured. Set it in .env.")
    logger.info("Starting %s v%s", config.GAME_NAME, config.GAME_VERSION)
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
