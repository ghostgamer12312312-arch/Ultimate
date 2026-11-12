"""Procedural card images for characters, enemies, bosses, gear and profiles."""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    from . import config, data
except ImportError:
    import config
    import data

SIZE = (1024, 576)
FONT_DIRS = [
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts"),
]
RARITY_COLORS = {
    "common": "#b8c0cc", "rare": "#4fa3ff", "epic": "#c77dff",
    "legendary": "#ffb703", "mythic": "#ff4d6d", "divine": "#ffe066",
}
ELEMENT_COLORS = {
    "fire": "#ff6b35", "water": "#3aa8ff", "earth": "#b08968", "wind": "#7ae582",
    "lightning": "#ffe066", "ice": "#a0e7ff", "light": "#fff3b0", "dark": "#9d4edd",
    "spirit": "#4fd1c5", "void": "#b388ff",
}


def _find_font(bold: bool = False) -> str:
    names = ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"] if bold else ["DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
    for directory in FONT_DIRS:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return str(candidate)
    return ""


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    path = _find_font(bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _mix(first: tuple[int, int, int], second: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(int(a + (b - a) * ratio) for a, b in zip(first, second))


def _theme(series: str | None) -> dict:
    return data.SERIES_THEME.get(series or "universal", data.SERIES_THEME["universal"])


def _gradient(draw: ImageDraw.ImageDraw, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    for y in range(SIZE[1]):
        ratio = y / SIZE[1]
        draw.line([(0, y), (SIZE[0], y)], fill=_mix(top, bottom, ratio))


def _wrapped(draw: ImageDraw.ImageDraw, text: str, font, max_chars: int, max_lines: int = 3) -> list[str]:
    clean = " ".join(str(text).split())
    lines = textwrap.wrap(clean, width=max_chars) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(0, max_chars - 3)] + "..."
    return lines


def _safe_name(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum() or ch in "_-")[:60] or "card"


def _cache_path(kind: str, entity_id: str, extra: str = "") -> Path:
    directory = Path(config.IMAGE_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{kind}:{entity_id}:{extra}".encode("utf-8")).hexdigest()[:16]
    return directory / f"{kind}_{_safe_name(entity_id)}_{digest}.png"


def _base_card(theme_key: str) -> tuple[Image.Image, ImageDraw.ImageDraw, dict]:
    theme = _theme(theme_key)
    bg = _rgb(theme["bg"])
    accent = _rgb(theme["accent"])
    image = Image.new("RGB", SIZE, bg)
    draw = ImageDraw.Draw(image)
    _gradient(draw, _mix(bg, (0, 0, 0), 0.28), _mix(bg, accent, 0.20))
    glow_layer = Image.new("RGB", SIZE, bg)
    glow = ImageDraw.Draw(glow_layer)
    glow.ellipse((650, -180, 1250, 430), fill=_mix(accent, bg, 0.55))
    glow.ellipse((-220, 280, 380, 820), fill=_mix(_rgb(theme["glow"]), bg, 0.72))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(95))
    image = Image.blend(image, glow_layer, 0.55)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((22, 22, SIZE[0] - 22, SIZE[1] - 22), radius=34, outline=_mix(accent, (255, 255, 255), 0.32), width=4)
    draw.rounded_rectangle((38, 38, SIZE[0] - 38, SIZE[1] - 38), radius=28, outline=_mix(accent, (0, 0, 0), 0.35), width=2)
    return image, draw, theme


def _silhouette(image: Image.Image, accent: tuple[int, int, int], seed: str) -> None:
    layer = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    variant = sum(ord(ch) for ch in seed) % 4
    cx = 800 + (variant - 1) * 20
    color = (*_mix(accent, (255, 255, 255), 0.18), 130)
    draw.ellipse((cx - 84, 126, cx + 84, 294), fill=color)
    draw.polygon([(cx - 150, 560), (cx - 108, 300), (cx - 30, 274), (cx + 30, 274), (cx + 108, 300), (cx + 150, 560)], fill=color)
    if variant in (1, 3):
        draw.polygon([(cx - 150, 380), (cx - 290, 460), (cx - 240, 510), (cx - 118, 430)], fill=color)
    if variant in (2, 3):
        draw.polygon([(cx + 150, 380), (cx + 290, 460), (cx + 240, 510), (cx + 118, 430)], fill=color)
    glow = layer.filter(ImageFilter.GaussianBlur(12))
    image.alpha_composite(glow) if image.mode == "RGBA" else image.paste(glow, (0, 0), glow)
    image.paste(layer, (0, 0), layer)


def _finish(image: Image.Image, draw: ImageDraw.ImageDraw, path: Path, footer: str = "MULTIVERSE LEGENDS") -> str:
    draw.text((52, SIZE[1] - 54), footer, font=_font(18, True), fill=(220, 220, 230))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)
    return str(path)


def _draw_header(draw: ImageDraw.ImageDraw, theme: dict, badge: str, title: str, subtitle: str = "") -> int:
    accent = _rgb(theme["accent"])
    glow = _rgb(theme["glow"])
    draw.text((56, 48), theme.get("label", "MULTIVERSE").upper(), font=_font(20, True), fill=glow)
    if badge:
        badge_width = max(90, int(draw.textlength(badge, font=_font(18, True))) + 34)
        draw.rounded_rectangle((56, 82, 56 + badge_width, 118), radius=18, fill=_mix(accent, (0, 0, 0), 0.42), outline=accent, width=2)
        draw.text((73, 88), badge.upper(), font=_font(16, True), fill=(255, 255, 255))
    title_lines = _wrapped(draw, title, _font(44, True), 26, 2)
    y = 136
    for line in title_lines:
        draw.text((56, y), line, font=_font(44, True), fill=(255, 255, 255))
        y += 52
    if subtitle:
        for line in _wrapped(draw, subtitle, _font(21), 52, 2):
            draw.text((58, y + 6), line, font=_font(21), fill=_mix(_rgb(theme["glow"]), (255, 255, 255), 0.55))
            y += 28
    return y + 18


def generic_card(kind: str, entity_id: str, title: str, subtitle: str, lines: list[str], series: str = "universal", badge: str = "", accent: str | None = None, extra: str = "") -> str:
    path = _cache_path(kind, entity_id, f"{title}|{subtitle}|{series}|{extra}|{'|'.join(lines)}")
    if path.exists():
        return str(path)
    image, draw, theme = _base_card(series)
    if accent:
        theme = dict(theme)
        theme["accent"] = accent
    y = _draw_header(draw, theme, badge, title, subtitle)
    _silhouette(image, _rgb(theme["accent"]), entity_id)
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines[:9]):
        if not line:
            continue
        color = (238, 238, 245) if index % 2 == 0 else (198, 204, 218)
        for wrapped in _wrapped(draw, line, _font(21), 54, 1):
            draw.text((58, y), wrapped, font=_font(21), fill=color)
        y += 32
    return _finish(image, draw, path)


def character_card(character: dict, *, level: int | None = None, stars: int | None = None) -> str:
    level = int(level if level is not None else character.get("level", 1))
    stars = int(stars if stars is not None else character.get("stars", 1))
    skills = ", ".join(data.SKILLS[sid]["name"] for sid in character.get("skills", []) if sid in data.SKILLS) or "None"
    lines = [
        f"Rarity: {character.get('rarity', 'common').title()}    Element: {character.get('element', 'spirit').title()}",
        f"Level {level}    Stars {stars}    Series: {data.SERIES.get(character.get('series'), {}).get('name', 'Multiverse')}",
        f"HP {character.get('hp', 0):,}    ATK {character.get('atk', 0):,}",
        f"DEF {character.get('def', 0):,}    SPD {character.get('spd', 0):,}",
        f"Power {character.get('power', 0):,}",
        f"Skills: {skills}",
        character.get("description", ""),
    ]
    return generic_card("character", str(character.get("id", "unknown")), character.get("name", "Unknown Warrior"), character.get("title", "Multiverse Legend"), lines, character.get("series", "universal"), character.get("rarity", "common").upper())


def enemy_card(entity: dict, *, kind: str = "enemy") -> str:
    lines = [
        f"Element: {entity.get('element', 'spirit').title()}    Level: {entity.get('level', 0)}",
        f"HP {entity.get('hp', 0):,}    ATK {entity.get('atk', 0):,}",
        f"DEF {entity.get('def', 0):,}    SPD {entity.get('spd', 0):,}",
        f"Series: {data.SERIES.get(entity.get('series'), {}).get('name', 'Multiverse')}",
        entity.get("description", ""),
    ]
    return generic_card(kind, str(entity.get("id", entity.get("name", "unknown"))), entity.get("name", "Unknown Enemy"), "HOSTILE ENCOUNTER", lines, entity.get("series", "universal"), kind.upper())


def boss_card(boss: dict, *, kind: str = "boss") -> str:
    lines = [
        f"Element: {boss.get('element', 'spirit').title()}    Level: {boss.get('level', 0)}",
        f"HP {boss.get('hp', 0):,}    ATK {boss.get('atk', 0):,}",
        f"DEF {boss.get('def', 0):,}    SPD {boss.get('spd', 0):,}",
        f"Series: {data.SERIES.get(boss.get('series'), {}).get('name', 'Multiverse')}",
        "Defeat this boss to claim rare rewards.",
    ]
    return generic_card(kind, str(boss.get("id", boss.get("name", "unknown"))), boss.get("name", "Unknown Boss"), "BOSS BATTLE", lines, boss.get("series", "universal"), kind.upper(), accent="#ff4d4d")


def gear_card(gear: dict, *, level: int = 1, instance_id: int | None = None) -> str:
    lines = [
        f"Slot: {gear.get('slot', 'gear').title()}    Rarity: {gear.get('rarity', 'common').title()}",
        f"Level: {level}    Element: {gear.get('element', 'spirit').title()}",
        f"HP +{gear.get('hp', 0):,}    ATK +{gear.get('atk', 0):,}",
        f"DEF +{gear.get('def', 0):,}    SPD +{gear.get('spd', 0):,}",
        gear.get("description", ""),
    ]
    return generic_card("gear", str(instance_id or gear.get("id", "gear")), gear.get("name", "Unknown Gear"), "EQUIPMENT", lines, gear.get("series", "universal"), gear.get("rarity", "common").upper(), extra=str(level))


def item_card(item: dict, *, qty: int = 1) -> str:
    lines = [
        f"Type: {item.get('kind', 'item').replace('_', ' ').title()}    Quantity: {qty}",
        f"Value: {item.get('value', 0):,}    Price: {item.get('price', 0):,}",
        f"Currency: {item.get('currency', 'none').title()}",
        item.get("desc", ""),
    ]
    return generic_card("item", str(item.get("id", "item")), item.get("name", "Unknown Item"), "INVENTORY ITEM", lines, "universal", "ITEM", accent="#4fd1c5")


def profile_card(player: dict, stats: dict, characters: int, pets: int, clan: dict | None = None) -> str:
    lines = [
        f"Level {player.get('level', 1)}    Rank: {player.get('rank', 'Rookie')}    Series: {data.SERIES.get(player.get('series'), {}).get('name', 'Multiverse')}",
        f"HP {stats.get('hp', 0):,}    ATK {stats.get('atk', 0):,}    DEF {stats.get('def', 0):,}    SPD {stats.get('spd', 0):,}",
        f"Yens {player.get('yens', 0):,}    Gems {player.get('gems', 0):,}    Crystals {player.get('crystals', 0):,}",
        f"Characters {characters}    Companions {pets}    PvP wins {player.get('pvp_wins', 0)}",
        f"Clan: {clan.get('name') if clan else 'None'}",
        f"Total battles {player.get('total_battles', 0)}    Boss kills {player.get('boss_kills', 0)}",
    ]
    return generic_card("profile", str(player.get("user_id", "player")), player.get("first_name") or player.get("username") or "Summoner", "PLAYER PROFILE", lines, player.get("series", "universal"), "PROFILE", extra=str(stats.get("atk", 0)))


def clan_card(clan: dict, members: int, leader_name: str = "") -> str:
    lines = [
        f"Tag: {clan.get('tag', '???')}    Level: {clan.get('level', 1)}    Members: {members}/30",
        f"Leader: {leader_name or clan.get('leader_id', 'Unknown')}",
        f"Yens {clan.get('treasury_yens', 0):,}    Gems {clan.get('treasury_gems', 0):,}    Crystals {clan.get('treasury_crystals', 0):,}",
        f"EXP {clan.get('exp', 0):,}    Invite only: {'No' if clan.get('open_join', 1) else 'Yes'}    Min level: {clan.get('min_level', 1)}",
        clan.get("description") or clan.get("announcement") or "A new clan ready to conquer the multiverse.",
    ]
    return generic_card("clan", str(clan.get("id", "clan")), clan.get("name", "Unknown Clan"), "CLAN BANNER", lines, "universal", "CLAN", accent="#f5c542")


def chapter_card(chapter: dict) -> str:
    lines = [
        f"Chapter {chapter.get('number', 0)}    Recommended level {chapter.get('level', 1)}",
        f"Enemy: {chapter.get('enemy', {}).get('name', 'Unknown')}",
        f"Enemy HP {chapter.get('enemy', {}).get('hp', 0):,}    ATK {chapter.get('enemy', {}).get('atk', 0):,}",
        f"Rewards: {chapter.get('rewards', {}).get('yens', 0):,} yens, {chapter.get('rewards', {}).get('exp', 0):,} EXP",
        "Clear the previous chapter to unlock this battle.",
    ]
    return generic_card("chapter", str(chapter.get("id", "chapter")), chapter.get("name", "Unknown Chapter"), chapter.get("story", ""), lines, chapter.get("series", "universal"), "STORY")
