"""Formatting and inline keyboard helpers."""

from __future__ import annotations

import html

try:
    from . import data
except ImportError:
    import data


def esc(value) -> str:
    return html.escape(str(value), quote=False)


def fmt(value: int | float) -> str:
    return f"{int(value):,}"


def bar(current: int | float, maximum: int | float, length: int = 10) -> str:
    maximum = max(1, int(maximum))
    current = max(0, min(int(current), maximum))
    filled = int(round(length * current / maximum))
    return "█" * filled + "░" * (length - filled)


def percent_bar(current: int | float, maximum: int | float, length: int = 10) -> str:
    maximum = max(1, int(maximum))
    pct = max(0, min(100, int(current / maximum * 100)))
    return f"{bar(current, maximum, length)} {pct}%"


def reward_text(rewards: dict | None, drops: dict | None = None) -> str:
    if not rewards and not drops:
        return ""
    parts = []
    for key, value in (rewards or {}).items():
        if not value:
            continue
        if key in ("exp", "clan_exp"):
            parts.append(f"{int(value):,} {key.replace('_', ' ').title()}")
        elif key in ("yens", "gems", "crystals", "tickets"):
            parts.append(f"{fmt(value)} {key.title()}")
        elif key in data.ITEMS:
            parts.append(f"{data.ITEMS[key]['emoji']} {data.ITEMS[key]['name']} x{int(value)}")
        else:
            parts.append(f"{esc(key)}: {value}")
    for key, value in (drops or {}).items():
        item = data.ITEMS.get(key)
        if item:
            parts.append(f"{item['emoji']} {esc(item['name'])} x{int(value)}")
        else:
            parts.append(f"{esc(key)} x{int(value)}")
    return " • ".join(parts)


def main_menu_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Profile", callback_data="menu:profile"), InlineKeyboardButton("🎴 Summon", callback_data="menu:gacha")],
        [InlineKeyboardButton("⚔️ Hunt", callback_data="menu:hunt"), InlineKeyboardButton("👹 Boss", callback_data="menu:boss")],
        [InlineKeyboardButton("🌍 World Raid", callback_data="menu:raid"), InlineKeyboardButton("🏯 Clan", callback_data="menu:clan")],
        [InlineKeyboardButton("🎒 Inventory", callback_data="menu:inventory"), InlineKeyboardButton("🛒 Shop", callback_data="menu:shop")],
        [InlineKeyboardButton("🏰 Dungeon", callback_data="menu:dungeon"), InlineKeyboardButton("🐾 Pets", callback_data="menu:pets")],
        [InlineKeyboardButton("🎣 Fish", callback_data="menu:fish"), InlineKeyboardButton("⛏️ Mine", callback_data="menu:mine")],
        [InlineKeyboardButton("📖 Story", callback_data="menu:chapters"), InlineKeyboardButton("🌌 Summon Boss", callback_data="menu:summonboss")],
        [InlineKeyboardButton("📜 Quests", callback_data="menu:quests"), InlineKeyboardButton("🏆 Rankings", callback_data="menu:leaderboard")],
        [InlineKeyboardButton("📖 Help", callback_data="menu:help")],
    ])


def back_keyboard(callback: str = "menu:main"):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=callback)]])


def series_keyboard(prefix: str, include_all: bool = False):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = []
    for series in data.SERIES_ORDER:
        info = data.SERIES[series]
        buttons.append(InlineKeyboardButton(f"{info['emoji']} {info['short']}", callback_data=f"{prefix}:{series}"))
    rows = [buttons[:3], buttons[3:]]
    if include_all:
        rows.append([InlineKeyboardButton("🌌 All Series", callback_data=f"{prefix}:all")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def gacha_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    for series in data.SERIES_ORDER:
        info = data.SERIES[series]
        rows.append([InlineKeyboardButton(f"{info['emoji']} {info['name']}", callback_data=f"banner:{series}")])
    rows.append([InlineKeyboardButton("🌌 Multiverse Ultimate", callback_data="banner:multiverse")])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def banner_keyboard(series: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟️ Summon x1", callback_data=f"pull:{series}:1"), InlineKeyboardButton("🎟️ Summon x10", callback_data=f"pull:{series}:10")],
        [InlineKeyboardButton("🎴 All Banners", callback_data="menu:gacha"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ])


def shop_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧪 Potions", callback_data="shop:potions"), InlineKeyboardButton("🎟️ Summon", callback_data="shop:summon")],
        [InlineKeyboardButton("🧰 Materials", callback_data="shop:materials"), InlineKeyboardButton("⚙️ Gear", callback_data="shop:gear")],
        [InlineKeyboardButton("🌅 Daily Shop", callback_data="shop:daily"), InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ])


def quest_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Daily", callback_data="quests:daily"), InlineKeyboardButton("🗓️ Weekly", callback_data="quests:weekly")],
        [InlineKeyboardButton("🌕 Monthly", callback_data="quests:monthly"), InlineKeyboardButton("✅ Claim All", callback_data="quests:claim")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:main")],
    ])


def battle_text(title: str, result: dict, rewards: dict | None = None, drops: dict | None = None) -> str:
    won = result["winner"] == "player"
    header = "🏆 <b>VICTORY</b>" if won else "💀 <b>DEFEAT</b>" if result["winner"] == "enemy" else "🤝 <b>DRAW</b>"
    lines = [
        f"<b>{esc(title)}</b>",
        header,
        "",
        f"❤️ You: {percent_bar(result['player_hp'], result['player_max_hp'])}",
        f"💀 Enemy: {percent_bar(result['enemy_hp'], result['enemy_max_hp'])}",
        "",
        "📜 <b>Battle Log</b>",
    ]
    lines.extend(esc(line) for line in result["log"][-10:])
    reward = reward_text(rewards, drops)
    if reward:
        lines.extend(["", f"🎁 <b>Rewards:</b> {reward}"])
    return "\n".join(lines)


def char_summary(character: dict, owned: bool = True) -> str:
    rarity = data.RARITIES[character["rarity"]]
    element = data.ELEMENTS[character["element"]]
    series = data.SERIES[character["series"]]
    if not owned:
        return f"{rarity['emoji']} {element['emoji']} <b>{esc(character['name'])}</b> — {esc(series['name'])}"
    return (
        f"{rarity['emoji']} {element['emoji']} <b>{esc(character['name'])}</b> "
        f"Lv.{character.get('level', 1)} ⭐{character.get('stars', 1)} — {esc(series['name'])}"
    )
