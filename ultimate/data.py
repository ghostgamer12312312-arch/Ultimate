"""Static game content for Dragon Ball: Multiverse Legends."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy

SERIES_ORDER = ["dragonball", "naruto", "bleach", "jujutsu", "tempest"]

SERIES = {
    "dragonball": {
        "name": "Dragon Ball",
        "short": "DB",
        "emoji": "🐉",
        "home": "Earth",
        "worlds": ["Earth", "Namek", "Planet Vegeta", "Universe 6", "Beerus' Planet"],
        "lore": "Saiyans, gods, and dragons collide across the multiverse.",
    },
    "naruto": {
        "name": "Naruto",
        "short": "NAR",
        "emoji": "🍥",
        "home": "Hidden Leaf Village",
        "worlds": ["Hidden Leaf", "Hidden Sand", "Hidden Mist", "Akatsuki Base", "Valley of the End"],
        "lore": "Shinobi channel chakra, willpower, and forbidden techniques.",
    },
    "bleach": {
        "name": "Bleach",
        "short": "BLH",
        "emoji": "⚔️",
        "home": "Soul Society",
        "worlds": ["Karakura Town", "Soul Society", "Hueco Mundo", "Royal Palace", "Wandenreich"],
        "lore": "Soul Reapers, Hollows, and Quincy wage war beyond death.",
    },
    "jujutsu": {
        "name": "Jujutsu Kaisen",
        "short": "JJK",
        "emoji": "🔮",
        "home": "Tokyo Jujutsu High",
        "worlds": ["Tokyo Jujutsu High", "Shibuya", "Culling Game", "Sendai Colony", "Shinjuku"],
        "lore": "Cursed energy turns fear, grief, and ambition into power.",
    },
    "tempest": {
        "name": "That Time I Got Reincarnated as a Slime",
        "short": "TEN",
        "emoji": "💧",
        "home": "Tempest",
        "worlds": ["Great Jura Forest", "Tempest City", "Dwargon", "Demon Lord Domain", "Walpurgis"],
        "lore": "A slime unites monsters, dragons, and demon lords under one banner.",
    },
}

ELEMENT_ORDER = ["fire", "water", "earth", "wind", "lightning", "ice", "light", "dark", "spirit", "void"]

ELEMENTS = {
    "fire": {"name": "Fire", "emoji": "🔥", "strong": ["wind", "ice"], "weak": ["water", "earth"]},
    "water": {"name": "Water", "emoji": "🌊", "strong": ["fire", "earth"], "weak": ["lightning", "wind"]},
    "earth": {"name": "Earth", "emoji": "🌪️", "strong": ["fire", "lightning"], "weak": ["water", "wind"]},
    "wind": {"name": "Wind", "emoji": "🍃", "strong": ["earth", "water"], "weak": ["fire", "ice"]},
    "lightning": {"name": "Lightning", "emoji": "⚡", "strong": ["water", "wind"], "weak": ["earth", "void"]},
    "ice": {"name": "Ice", "emoji": "❄️", "strong": ["wind", "water"], "weak": ["fire", "light"]},
    "light": {"name": "Light", "emoji": "✨", "strong": ["dark", "void"], "weak": ["spirit", "dark"]},
    "dark": {"name": "Dark", "emoji": "🌑", "strong": ["light", "spirit"], "weak": ["light", "void"]},
    "spirit": {"name": "Spirit", "emoji": "🌀", "strong": ["void", "dark"], "weak": ["light", "ice"]},
    "void": {"name": "Void", "emoji": "🕳️", "strong": ["light", "spirit"], "weak": ["dark", "lightning"]},
}

RARITY_ORDER = ["common", "rare", "epic", "legendary", "mythic", "divine"]
RARITY_INDEX = {rarity: index for index, rarity in enumerate(RARITY_ORDER)}
RARITIES = {
    "common": {"name": "Common", "emoji": "⚪", "weight": 565, "mult": 1.00, "sell": 80, "gem_dup": 5},
    "rare": {"name": "Rare", "emoji": "🔵", "weight": 270, "mult": 1.12, "sell": 240, "gem_dup": 10},
    "epic": {"name": "Epic", "emoji": "🟣", "weight": 118, "mult": 1.28, "sell": 650, "gem_dup": 20},
    "legendary": {"name": "Legendary", "emoji": "🟡", "weight": 37, "mult": 1.48, "sell": 1800, "gem_dup": 40},
    "mythic": {"name": "Mythic", "emoji": "🔴", "weight": 8, "mult": 1.72, "sell": 5000, "gem_dup": 80},
    "divine": {"name": "Divine", "emoji": "🟠", "weight": 2, "mult": 2.05, "sell": 14000, "gem_dup": 160},
}

RANKS = [
    {"min_level": 1, "name": "Rookie", "bonus": 1.00, "crystals": 0},
    {"min_level": 5, "name": "Fighter", "bonus": 1.04, "crystals": 10},
    {"min_level": 12, "name": "Warrior", "bonus": 1.09, "crystals": 18},
    {"min_level": 20, "name": "Elite", "bonus": 1.15, "crystals": 28},
    {"min_level": 30, "name": "Super Elite", "bonus": 1.22, "crystals": 40},
    {"min_level": 45, "name": "Master", "bonus": 1.30, "crystals": 55},
    {"min_level": 60, "name": "Grandmaster", "bonus": 1.40, "crystals": 75},
    {"min_level": 75, "name": "Legend", "bonus": 1.52, "crystals": 100},
    {"min_level": 90, "name": "Mythic", "bonus": 1.66, "crystals": 140},
    {"min_level": 100, "name": "God of Destruction", "bonus": 1.85, "crystals": 200},
]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def rank_for_level(level: int) -> dict:
    result = RANKS[0]
    for rank in RANKS:
        if level >= rank["min_level"]:
            result = rank
    return result


def rarity_for_power(power: int) -> str:
    if power >= 95:
        return "divine"
    if power >= 88:
        return "mythic"
    if power >= 80:
        return "legendary"
    if power >= 70:
        return "epic"
    if power >= 60:
        return "rare"
    return "common"


def upgrade_rarity(rarity: str, steps: int = 1) -> str:
    index = min(len(RARITY_ORDER) - 1, RARITY_INDEX.get(rarity, 0) + steps)
    return RARITY_ORDER[index]


def _stats(power: int, rarity: str, scale: float = 1.0) -> dict:
    mult = RARITIES[rarity]["mult"] * scale
    return {
        "hp": int((520 + power * 24 + RARITY_INDEX[rarity] * 140) * mult),
        "atk": int((32 + power * 5 + RARITY_INDEX[rarity] * 10) * mult),
        "def": int((20 + power * 3.5 + RARITY_INDEX[rarity] * 8) * mult),
        "spd": int((14 + power * 1.3 + RARITY_INDEX[rarity] * 2.2) * mult),
    }


SKILLS: dict[str, dict] = {}


def _skill(
    skill_id: str,
    name: str,
    element: str,
    power: float,
    description: str,
    kind: str = "active",
    bonus: dict | None = None,
    series: str | None = None,
    cooldown: int = 2,
) -> None:
    SKILLS[skill_id] = {
        "id": skill_id,
        "name": name,
        "element": element,
        "type": kind,
        "power": power,
        "description": description,
        "bonus": bonus or {},
        "series": series,
        "cooldown": cooldown,
    }


ELEMENT_SKILL_IDS: dict[str, list[str]] = {}
for element, names in {
    "fire": [("flame_burst", "Flame Burst", 1.35), ("inferno_wave", "Inferno Wave", 1.75), ("phoenix_fang", "Phoenix Fang", 2.15)],
    "water": [("aqua_edge", "Aqua Edge", 1.30), ("tidal_crush", "Tidal Crush", 1.70), ("abyss_requiem", "Abyss Requiem", 2.10)],
    "earth": [("gaia_hammer", "Gaia Hammer", 1.32), ("quake_slam", "Quake Slam", 1.68), ("world_breaker", "World Breaker", 2.18)],
    "wind": [("gale_slash", "Gale Slash", 1.30), ("tempest_kick", "Tempest Kick", 1.66), ("cyclone_storm", "Cyclone Storm", 2.12)],
    "lightning": [("thunder_strike", "Thunder Strike", 1.36), ("volt_lance", "Volt Lance", 1.74), ("raijin_rush", "Raijin Rush", 2.20)],
    "ice": [("ice_shard", "Ice Shard", 1.28), ("absolute_zero", "Absolute Zero", 1.72), ("glacier_fang", "Glacier Fang", 2.08)],
    "light": [("holy_ray", "Holy Ray", 1.34), ("radiance_slash", "Radiance Slash", 1.70), ("celestial_judgement", "Celestial Judgement", 2.24)],
    "dark": [("shadow_bite", "Shadow Bite", 1.38), ("abyss_wave", "Abyss Wave", 1.76), ("nightfall", "Nightfall", 2.22)],
    "spirit": [("soul_pulse", "Soul Pulse", 1.33), ("spirit_bomb", "Spirit Bomb", 1.82), ("astral_break", "Astral Break", 2.26)],
    "void": [("void_rend", "Void Rend", 1.40), ("singularity", "Singularity", 1.80), ("dimension_slash", "Dimension Slash", 2.30)],
}.items():
    ids: list[str] = []
    for index, (sid, name, power) in enumerate(names):
        _skill(sid, name, element, power, f"A {ELEMENTS[element]['name']} technique.", cooldown=2 + index)
        ids.append(sid)
    ELEMENT_SKILL_IDS[element] = ids

SERIES_SKILL_IDS: dict[str, list[str]] = {}
for series, entries in {
    "dragonball": [
        ("kamehameha", "Kamehameha", "light", 1.95, "A concentrated wave of ki."),
        ("final_flash", "Final Flash", "light", 2.05, "A devastating golden ki beam."),
        ("galick_gun", "Galick Gun", "fire", 1.70, "A violet Saiyan ki blast."),
        ("special_beam_cannon", "Special Beam Cannon", "spirit", 1.90, "A piercing spiral ki drill."),
        ("instant_transmission", "Instant Transmission", "void", 1.55, "Strike from a folded space."),
        ("hakai", "Hakai", "void", 2.45, "Erase matter with destructive energy."),
        ("ultra_instinct", "Ultra Instinct", "spirit", 2.35, "Move without conscious thought."),
        ("dragon_fist", "Dragon Fist", "light", 2.25, "A dragon-shaped ki charge."),
    ],
    "naruto": [
        ("rasengan", "Rasengan", "wind", 1.85, "A spiraling sphere of chakra."),
        ("chidori", "Chidori", "lightning", 1.90, "A blade of concentrated lightning."),
        ("rasenshuriken", "Rasenshuriken", "wind", 2.25, "A wind release shuriken."),
        ("amaterasu", "Amaterasu", "fire", 2.15, "Black flames that never die."),
        ("susanoo", "Susanoo", "spirit", 2.30, "A colossal avatar of chakra."),
        ("kamui", "Kamui", "void", 2.05, "Warp the target into another dimension."),
        ("sage_art", "Sage Art: Massive Rasengan", "earth", 2.20, "Nature energy compressed into a sphere."),
        ("eight_gates", "Eight Inner Gates", "fire", 2.55, "Open the limits of the body."),
    ],
    "bleach": [
        ("getsuga_tensho", "Getsuga Tensho", "dark", 1.95, "A crescent moon of spiritual pressure."),
        ("bankai", "Bankai", "spirit", 2.15, "Release the true form of a Zanpakuto."),
        ("cero", "Cero", "void", 1.90, "A Hollow's destructive energy blast."),
        ("quincy_arrow", "Quincy Arrow", "light", 1.75, "A bow of reishi."),
        ("respira", "Respira", "dark", 2.20, "Accelerated decay and aging."),
        ("kyoka_suigetsu", "Kyoka Suigetsu", "spirit", 2.30, "Complete hypnosis of the senses."),
        ("zanka_no_tachi", "Zanka no Tachi", "fire", 2.45, "A blade of absolute heat."),
        ("mugetsu", "Mugetsu", "void", 2.60, "A moonlight slash that cuts existence."),
    ],
    "jujutsu": [
        ("divergent_fist", "Divergent Fist", "spirit", 1.65, "A delayed second impact of cursed energy."),
        ("black_flash", "Black Flash", "dark", 2.10, "A distortion of space at impact."),
        ("domain_expansion", "Domain Expansion", "void", 2.35, "An inescapable barrier of cursed technique."),
        ("malevolent_shrine", "Malevolent Shrine", "dark", 2.55, "Sukuna's open-barrier domain."),
        ("hollow_purple", "Hollow Purple", "void", 2.45, "Imaginary mass that erases everything."),
        ("ten_shadows", "Ten Shadows Technique", "dark", 2.15, "Summon shikigami from shadow."),
        ("cursed_speech", "Cursed Speech", "spirit", 1.80, "Commands enforced by cursed energy."),
        ("idle_transfiguration", "Idle Transfiguration", "spirit", 2.20, "Reshape the soul of a target."),
    ],
    "tempest": [
        ("predator", "Predator", "void", 2.05, "Devour and analyze an opponent."),
        ("great_sage", "Great Sage", "spirit", 1.85, "Perfect calculation and support."),
        ("megiddo", "Megiddo", "light", 2.40, "Rays of concentrated holy energy."),
        ("gluttony", "Gluttony", "dark", 2.10, "Consume the power of the fallen."),
        ("beelzebuth", "Beelzebuth", "void", 2.50, "Lord of Gluttony's ultimate predation."),
        ("dragon_burst", "Dragon Burst", "fire", 2.20, "A storm of draconic aura."),
        ("holy_barrier", "Holy Barrier", "light", 1.35, "A multi-layered defensive field."),
        ("ultimate_skill", "Ultimate Skill", "spirit", 2.35, "A perfected skill born of evolution."),
    ],
}.items():
    ids = []
    for index, (sid, name, element, power, desc) in enumerate(entries):
        _skill(sid, name, element, power, desc, series=series, cooldown=2 + (index % 4))
        ids.append(sid)
    SERIES_SKILL_IDS[series] = ids

PASSIVE_IDS: dict[str, list[str]] = {}
for series, entries in {
    "dragonball": [
        ("passive_saiyan_blood", "Saiyan Blood", {"atk_pct": 0.10, "hp_pct": 0.06}),
        ("passive_ki_mastery", "Ki Mastery", {"atk_pct": 0.08, "crit": 0.05}),
    ],
    "naruto": [
        ("passive_jinchuriki", "Jinchuriki", {"hp_pct": 0.12, "atk_pct": 0.06}),
        ("passive_sharingan", "Sharingan", {"crit": 0.09, "dodge": 0.04}),
    ],
    "bleach": [
        ("passive_hollow_mask", "Hollow Mask", {"atk_pct": 0.12, "spd_pct": 0.05}),
        ("passive_reiatsu", "Reiatsu Pressure", {"def_pct": 0.10, "hp_pct": 0.08}),
    ],
    "jujutsu": [
        ("passive_six_eyes", "Six Eyes", {"crit": 0.10, "atk_pct": 0.08}),
        ("passive_cursed_energy", "Cursed Energy Core", {"hp_pct": 0.10, "def_pct": 0.07}),
    ],
    "tempest": [
        ("passive_great_sage", "Great Sage", {"atk_pct": 0.08, "def_pct": 0.08}),
        ("passive_slime_body", "Slime Body", {"hp_pct": 0.14, "dodge": 0.04}),
    ],
}.items():
    ids = []
    for sid, name, bonus in entries:
        _skill(sid, name, "spirit", 0.0, "A permanent passive ability.", kind="passive", bonus=bonus, series=series)
        ids.append(sid)
    PASSIVE_IDS[series] = ids


ROSTER: dict[str, list[tuple[str, str, int]]] = {
    "dragonball": [
        ("Goku", "light", 99), ("Vegeta", "fire", 95), ("Gohan", "light", 92), ("Piccolo", "earth", 82),
        ("Frieza", "ice", 92), ("Cell", "earth", 88), ("Majin Buu", "dark", 85), ("Kid Buu", "dark", 90),
        ("Trunks", "lightning", 84), ("Goten", "lightning", 72), ("Gotenks", "lightning", 86), ("Krillin", "earth", 65),
        ("Android 18", "wind", 74), ("Android 17", "wind", 75), ("Beerus", "void", 98), ("Whis", "spirit", 99),
        ("Broly", "fire", 96), ("Gogeta", "light", 99), ("Vegito", "light", 98), ("Bardock", "fire", 70),
        ("Goku Black", "dark", 89), ("Zamasu", "light", 87), ("Hit", "void", 86), ("Jiren", "spirit", 95),
        ("Toppo", "light", 84), ("Dyspo", "lightning", 78), ("Caulifla", "fire", 76), ("Kale", "dark", 80),
        ("Kefla", "lightning", 88), ("Cabba", "wind", 70), ("Raditz", "fire", 62), ("Nappa", "earth", 64),
        ("Captain Ginyu", "spirit", 68), ("Cooler", "ice", 82), ("Janemba", "dark", 85), ("Tapion", "wind", 72),
        ("Master Roshi", "water", 60), ("Tien", "earth", 63), ("Yamcha", "earth", 52), ("Chiaotzu", "spirit", 45),
        ("Videl", "wind", 48), ("Pan", "light", 58), ("Uub", "spirit", 72), ("Super Buu", "dark", 84),
        ("Golden Frieza", "ice", 94), ("Ultra Instinct Goku", "void", 100), ("Ultra Ego Vegeta", "dark", 97),
        ("Moro", "earth", 93), ("Granolah", "spirit", 90), ("Black Frieza", "ice", 98),
    ],
    "naruto": [
        ("Naruto Uzumaki", "wind", 95), ("Sasuke Uchiha", "lightning", 94), ("Sakura Haruno", "earth", 78),
        ("Kakashi Hatake", "lightning", 84), ("Itachi Uchiha", "fire", 88), ("Madara Uchiha", "fire", 96),
        ("Hashirama Senju", "earth", 94), ("Tobirama Senju", "water", 86), ("Minato Namikaze", "wind", 90),
        ("Jiraiya", "earth", 80), ("Tsunade Senju", "earth", 82), ("Orochimaru", "dark", 83),
        ("Pain", "spirit", 89), ("Konan", "wind", 76), ("Obito Uchiha", "void", 88), ("Nagato", "spirit", 87),
        ("Gaara", "earth", 82), ("Rock Lee", "wind", 74), ("Neji Hyuga", "wind", 72), ("Hinata Hyuga", "light", 68),
        ("Shikamaru Nara", "dark", 70), ("Choji Akimichi", "earth", 66), ("Ino Yamanaka", "light", 62),
        ("Kiba Inuzuka", "wind", 58), ("Shino Aburame", "earth", 60), ("Temari", "wind", 68),
        ("Kankuro", "earth", 64), ("Killer Bee", "lightning", 86), ("Ay", "lightning", 84), ("Mei Terumi", "water", 78),
        ("Onoki", "earth", 76), ("Danzo Shimura", "wind", 74), ("Kabuto Yakushi", "water", 76),
        ("Deidara", "earth", 78), ("Sasori", "dark", 77), ("Hidan", "dark", 72), ("Kakuzu", "earth", 78),
        ("Kisame Hoshigaki", "water", 82), ("Zabuza Momochi", "water", 72), ("Haku", "ice", 66),
        ("Boruto Uzumaki", "lightning", 84), ("Sarada Uchiha", "fire", 76), ("Mitsuki", "wind", 75),
        ("Kawaki", "dark", 82), ("Isshiki Otsutsuki", "void", 97), ("Momoshiki Otsutsuki", "void", 92),
        ("Kaguya Otsutsuki", "light", 96), ("Hagoromo Otsutsuki", "light", 95), ("Indra Otsutsuki", "lightning", 88),
        ("Asura Otsutsuki", "wind", 87),
    ],
    "bleach": [
        ("Ichigo Kurosaki", "dark", 96), ("Rukia Kuchiki", "ice", 78), ("Renji Abarai", "fire", 80),
        ("Uryu Ishida", "light", 78), ("Orihime Inoue", "light", 70), ("Yasutora Sado", "earth", 66),
        ("Byakuya Kuchiki", "wind", 88), ("Kenpachi Zaraki", "dark", 94), ("Yachiru Kusajishi", "wind", 62),
        ("Toshiro Hitsugaya", "ice", 88), ("Rangiku Matsumoto", "wind", 68), ("Soi Fon", "wind", 80),
        ("Yoruichi Shihoin", "lightning", 86), ("Kisuke Urahara", "spirit", 90), ("Yhwach", "void", 99),
        ("Sosuke Aizen", "dark", 97), ("Gin Ichimaru", "ice", 86), ("Kaname Tosen", "dark", 78),
        ("Coyote Starrk", "fire", 86), ("Baraggan Louisenbairn", "dark", 88), ("Tier Harribel", "water", 82),
        ("Ulquiorra Cifer", "dark", 90), ("Grimmjow Jaegerjaquez", "lightning", 84), ("Nnoitra Gilga", "earth", 80),
        ("Nel Tu", "water", 76), ("Szayelaporro Granz", "dark", 74), ("Aaroniero Arruruerie", "water", 68),
        ("Zommari Rureaux", "dark", 66), ("Wonderweiss Margela", "fire", 70), ("Genryusai Yamamoto", "fire", 96),
        ("Shunsui Kyoraku", "wind", 90), ("Jushiro Ukitake", "water", 86), ("Retsu Unohana", "earth", 92),
        ("Mayuri Kurotsuchi", "dark", 82), ("Sajin Komamura", "earth", 76), ("Shinji Hirako", "wind", 82),
        ("Hiyori Sarugaki", "wind", 64), ("Lisa Yadomaru", "dark", 68), ("Kensei Muguruma", "wind", 78),
        ("Mashiro Kuna", "lightning", 66), ("Rose Otoribashi", "light", 74), ("Love Aikawa", "fire", 70),
        ("Isshin Kurosaki", "fire", 84), ("Ryuken Ishida", "light", 80), ("Masaki Kurosaki", "light", 72),
        ("Kazui Kurosaki", "light", 60), ("Ichibei Hyosube", "void", 98), ("Oetsu Nimaiya", "lightning", 90),
        ("Senjumaru Shutara", "spirit", 92), ("Tenjiro Kirinji", "water", 88),
    ],
    "jujutsu": [
        ("Yuji Itadori", "fire", 84), ("Megumi Fushiguro", "dark", 80), ("Nobara Kugisaki", "spirit", 72),
        ("Satoru Gojo", "void", 99), ("Ryomen Sukuna", "dark", 98), ("Yuta Okkotsu", "spirit", 94),
        ("Maki Zenin", "earth", 82), ("Toge Inumaki", "wind", 70), ("Panda", "earth", 70),
        ("Kento Nanami", "light", 80), ("Mahito", "dark", 86), ("Jogo", "fire", 82),
        ("Hanami", "earth", 78), ("Dagon", "water", 76), ("Choso", "dark", 80),
        ("Suguru Geto", "dark", 90), ("Toji Fushiguro", "void", 88), ("Aoi Todo", "earth", 78),
        ("Mai Zenin", "fire", 62), ("Kasumi Miwa", "wind", 58), ("Momo Nishimiya", "wind", 60),
        ("Noritoshi Kamo", "water", 64), ("Kokichi Muta", "earth", 74), ("Yuki Tsukumo", "spirit", 90),
        ("Hajime Kashimo", "lightning", 88), ("Hiromi Higuruma", "light", 82), ("Uraume", "ice", 80),
        ("Kenjaku", "dark", 94), ("Rika Orimoto", "dark", 92), ("Miguel", "spirit", 70),
        ("Larue", "earth", 60), ("Manami Suda", "light", 56), ("Nanako Hasaba", "fire", 54),
        ("Mimiko Hasaba", "dark", 54), ("Takako Uro", "void", 72), ("Ishigori Ryu", "fire", 78),
        ("Haba", "wind", 66), ("Daido Hagane", "earth", 64), ("Hagane Daido", "earth", 62),
        ("Charles Bernard", "light", 58), ("Remi", "spirit", 50), ("Fumi", "light", 46),
        ("Tsumiki Fushiguro", "light", 48), ("Yorozu", "earth", 80), ("Angel", "light", 86),
        ("Hana Kurusu", "light", 74), ("Takaba", "spirit", 88), ("Masamichi Yaga", "earth", 68),
        ("Utahime Iori", "light", 66), ("Shoko Ieiri", "light", 70),
    ],
    "tempest": [
        ("Rimuru Tempest", "void", 99), ("Veldora Tempest", "wind", 98), ("Velzard", "ice", 96),
        ("Velgrynd", "fire", 96), ("Guy Crimson", "dark", 97), ("Milim Nava", "fire", 97),
        ("Luminous Valentine", "light", 94), ("Dino", "wind", 88), ("Ramiris", "earth", 80),
        ("Leon Cromwell", "light", 90), ("Chloe Aubert", "light", 84), ("Hinata Sakaguchi", "light", 82),
        ("Benimaru", "fire", 88), ("Shion", "dark", 80), ("Shuna", "spirit", 76),
        ("Souei", "dark", 78), ("Hakurou", "wind", 84), ("Rigurd", "earth", 66),
        ("Rigur", "earth", 60), ("Gobta", "wind", 58), ("Ranga", "lightning", 74),
        ("Geld", "earth", 78), ("Gabiru", "water", 62), ("Gabil", "water", 64),
        ("Diablo", "dark", 95), ("Testarossa", "dark", 90), ("Ultima", "dark", 88),
        ("Carrera", "dark", 88), ("Beretta", "earth", 82), ("Venti", "wind", 78),
        ("Adalmann", "light", 74), ("Albert", "light", 70), ("Mjurran", "spirit", 68),
        ("Youm", "earth", 64), ("Grucius", "earth", 66), ("Laplace", "dark", 80),
        ("Tear", "dark", 70), ("Footman", "dark", 72), ("Clayman", "spirit", 82),
        ("Frey", "wind", 84), ("Carrion", "earth", 84), ("Middray", "fire", 80),
        ("Dagruel", "earth", 92), ("Feldway", "void", 94), ("Michael", "light", 96),
        ("Cornu", "earth", 86), ("Obera", "water", 82), ("Zalario", "void", 88),
        ("Vega", "dark", 80), ("Zegion", "void", 94),
    ],
}

CHARACTERS: dict[str, dict] = {}
CHARACTERS_BY_SERIES: dict[str, list[str]] = {series: [] for series in SERIES_ORDER}
CHARACTERS_BY_RARITY: dict[str, list[str]] = {rarity: [] for rarity in RARITY_ORDER}


def _make_character(
    name: str,
    series: str,
    element: str,
    power: int,
    rarity: str,
    form: str = "",
    base_id: str | None = None,
    stat_scale: float = 1.0,
) -> dict:
    display = name if not form else f"{name} ({form})"
    char_id = f"{SERIES[series]['short'].lower()}_{_slug(display)}"
    stats = _stats(power, rarity, stat_scale)
    signature_pool = SERIES_SKILL_IDS[series]
    element_pool = ELEMENT_SKILL_IDS[element]
    seed = int(hashlib.sha1(char_id.encode()).hexdigest()[:8], 16)
    skills = [
        signature_pool[seed % len(signature_pool)],
        element_pool[(seed // 7) % len(element_pool)],
        PASSIVE_IDS[series][(seed // 13) % len(PASSIVE_IDS[series])],
    ]
    if form == "Transcendent":
        skills[1] = element_pool[-1]
    character = {
        "id": char_id,
        "name": display,
        "base_name": name,
        "series": series,
        "element": element,
        "power": power,
        "rarity": rarity,
        "form": form or "Base",
        "base_id": base_id or char_id,
        "hp": stats["hp"],
        "atk": stats["atk"],
        "def": stats["def"],
        "spd": stats["spd"],
        "skills": skills,
        "lore": f"{display} from {SERIES[series]['name']}.",
        "sell": RARITIES[rarity]["sell"],
    }
    CHARACTERS[char_id] = character
    CHARACTERS_BY_SERIES[series].append(char_id)
    CHARACTERS_BY_RARITY[rarity].append(char_id)
    return character


for _series in SERIES_ORDER:
    for _name, _element, _power in ROSTER[_series]:
        _rarity = rarity_for_power(_power)
        _base = _make_character(_name, _series, _element, _power, _rarity)
        if _power >= 80:
            _awakened_rarity = upgrade_rarity(_rarity, 1)
            _make_character(
                _name,
                _series,
                _element,
                min(112, _power + 6),
                _awakened_rarity,
                form="Awakened",
                base_id=_base["id"],
                stat_scale=1.10,
            )
        if _power >= 94:
            _make_character(
                _name,
                _series,
                _element,
                min(115, _power + 12),
                "divine",
                form="Transcendent",
                base_id=_base["id"],
                stat_scale=1.22,
            )

CHARACTERS_BY_SERIES = {key: sorted(value) for key, value in CHARACTERS_BY_SERIES.items()}
CHARACTERS_BY_RARITY = {key: sorted(value) for key, value in CHARACTERS_BY_RARITY.items()}

STARTER_CHARACTERS = {
    series: sorted(
        [cid for cid in CHARACTERS_BY_SERIES[series] if CHARACTERS[cid]["rarity"] in ("common", "rare") and CHARACTERS[cid]["form"] == "Base"],
        key=lambda cid: CHARACTERS[cid]["power"],
    )[-1]
    for series in SERIES_ORDER
}

ITEMS: dict[str, dict] = {
    "senzu_small": {"name": "Small Senzu Bean", "emoji": "🫘", "kind": "heal", "value": 400, "price": 120, "currency": "yens", "desc": "Restore 400 HP."},
    "senzu_large": {"name": "Senzu Bean", "emoji": "🫘", "kind": "heal", "value": 1800, "price": 650, "currency": "yens", "desc": "Restore 1800 HP."},
    "senzu_divine": {"name": "Divine Senzu", "emoji": "🌟", "kind": "heal", "value": 9000, "price": 40, "currency": "crystals", "desc": "Restore 9000 HP."},
    "stamina_drink": {"name": "Stamina Drink", "emoji": "🥤", "kind": "stamina", "value": 35, "price": 180, "currency": "yens", "desc": "Restore 35 stamina."},
    "stamina_feast": {"name": "Feast of Tempest", "emoji": "🍖", "kind": "stamina", "value": 100, "price": 25, "currency": "crystals", "desc": "Restore full stamina."},
    "exp_scroll": {"name": "EXP Scroll", "emoji": "📜", "kind": "exp", "value": 500, "price": 220, "currency": "yens", "desc": "Gain 500 account EXP."},
    "exp_tome": {"name": "Grand Tome of Wisdom", "emoji": "📚", "kind": "exp", "value": 2500, "price": 900, "currency": "yens", "desc": "Gain 2500 account EXP."},
    "gacha_ticket": {"name": "Summon Ticket", "emoji": "🎟️", "kind": "ticket", "value": 1, "price": 300, "currency": "gems", "desc": "One free gacha pull."},
    "elite_key": {"name": "Elite Key", "emoji": "🗝️", "kind": "key_elite", "value": 1, "price": 15, "currency": "crystals", "desc": "Open an elite boss battle."},
    "boss_key": {"name": "Boss Key", "emoji": "🔑", "kind": "key_boss", "value": 1, "price": 30, "currency": "crystals", "desc": "Open a series boss battle."},
    "raid_token": {"name": "Raid Token", "emoji": "🎫", "kind": "raid", "value": 1, "price": 20, "currency": "crystals", "desc": "Attack a global or clan raid."},
    "awakening_stone": {"name": "Awakening Stone", "emoji": "💎", "kind": "awaken", "value": 1, "price": 50, "currency": "crystals", "desc": "Unlock a character star."},
    "forge_core": {"name": "Forge Core", "emoji": "⚙️", "kind": "craft", "value": 1, "price": 250, "currency": "yens", "desc": "Used to forge high rarity gear."},
    "crystal_shard": {"name": "Crystal Shard", "emoji": "🔹", "kind": "material", "value": 1, "price": 80, "currency": "yens", "desc": "Crafting material."},
    "dragon_ball": {"name": "Dragon Ball", "emoji": "🟠", "kind": "dragonball", "value": 1, "price": 0, "currency": "none", "desc": "Collect all 7 to wish for a divine hero."},
    "wish_ticket": {"name": "Wish Ticket", "emoji": "🌠", "kind": "wish", "value": 1, "price": 0, "currency": "none", "desc": "A completed wish waiting to be granted."},
    "shard_common": {"name": "Common Shard", "emoji": "⚪", "kind": "shard", "value": 1, "price": 30, "currency": "yens", "desc": "Character awakening material."},
    "shard_rare": {"name": "Rare Shard", "emoji": "🔵", "kind": "shard", "value": 1, "price": 90, "currency": "yens", "desc": "Character awakening material."},
    "shard_epic": {"name": "Epic Shard", "emoji": "🟣", "kind": "shard", "value": 1, "price": 220, "currency": "yens", "desc": "Character awakening material."},
    "shard_legendary": {"name": "Legendary Shard", "emoji": "🟡", "kind": "shard", "value": 1, "price": 550, "currency": "yens", "desc": "Character awakening material."},
    "shard_mythic": {"name": "Mythic Shard", "emoji": "🔴", "kind": "shard", "value": 1, "price": 1200, "currency": "yens", "desc": "Character awakening material."},
    "shard_divine": {"name": "Divine Shard", "emoji": "🟠", "kind": "shard", "value": 1, "price": 3000, "currency": "yens", "desc": "Character awakening material."},
    "energy_fire": {"name": "Flame Essence", "emoji": "🔥", "kind": "material", "value": 1, "price": 60, "currency": "yens", "desc": "Elemental crafting material."},
    "energy_water": {"name": "Aqua Essence", "emoji": "🌊", "kind": "material", "value": 1, "price": 60, "currency": "yens", "desc": "Elemental crafting material."},
    "energy_dark": {"name": "Void Essence", "emoji": "🌑", "kind": "material", "value": 1, "price": 80, "currency": "yens", "desc": "Elemental crafting material."},
    "energy_light": {"name": "Radiant Essence", "emoji": "✨", "kind": "material", "value": 1, "price": 80, "currency": "yens", "desc": "Elemental crafting material."},
    "energy_spirit": {"name": "Spirit Essence", "emoji": "🌀", "kind": "material", "value": 1, "price": 70, "currency": "yens", "desc": "Elemental crafting material."},
}

for index in range(1, 8):
    ITEMS[f"dragon_ball_{index}"] = {
        "name": f"{index}-Star Dragon Ball",
        "emoji": "🟠",
        "kind": "dragonball",
        "value": index,
        "price": 0,
        "currency": "none",
        "desc": "One of the seven Dragon Balls.",
    }

GEAR: dict[str, dict] = {}
GEAR_BY_SERIES: dict[str, list[str]] = {series: [] for series in SERIES_ORDER}

GEAR_TEMPLATES: dict[str, list[tuple[str, str, str, int, int]]] = {
    "dragonball": [
        ("Power Pole", "weapon", "earth", 62, 520), ("Z Sword", "weapon", "light", 82, 1600),
        ("Whis' Staff", "weapon", "spirit", 96, 6200), ("Saiyan Battle Armor", "armor", "fire", 70, 900),
        ("Ultra Divine Armor", "armor", "light", 95, 5800), ("Dragon Radar", "accessory", "spirit", 58, 420),
        ("Potara Earrings", "accessory", "void", 90, 4200), ("Capsule Corp Jacket", "armor", "wind", 55, 350),
    ],
    "naruto": [
        ("Kunai of the Leaf", "weapon", "wind", 52, 280), ("Kusanagi Blade", "weapon", "lightning", 84, 1800),
        ("Samehada", "weapon", "water", 90, 4400), ("Akatsuki Cloak", "armor", "dark", 78, 1500),
        ("Sage Robe", "armor", "earth", 88, 3600), ("Sharingan Charm", "accessory", "spirit", 80, 2200),
        ("Jinchuriki Seal", "accessory", "void", 92, 5000), ("Anbu Mask", "armor", "wind", 60, 520),
    ],
    "bleach": [
        ("Zangetsu", "weapon", "dark", 92, 4800), ("Senbonzakura", "weapon", "wind", 86, 2600),
        ("Hyorinmaru", "weapon", "ice", 84, 2200), ("Captain Haori", "armor", "spirit", 80, 1900),
        ("Hogyoku Fragment", "accessory", "void", 98, 7200), ("Quincy Cross", "accessory", "light", 72, 1100),
        ("Hollow Mask", "armor", "dark", 88, 3200), ("Reiatsu Bracers", "armor", "spirit", 64, 700),
    ],
    "jujutsu": [
        ("Cursed Blade", "weapon", "dark", 74, 1200), ("Playful Cloud", "weapon", "earth", 86, 2800),
        ("Inverted Spear of Heaven", "weapon", "void", 94, 5400), ("Jujutsu Uniform", "armor", "spirit", 66, 800),
        ("Six Eyes Blindfold", "accessory", "light", 96, 6400), ("Cursed Corpse Armor", "armor", "dark", 82, 2100),
        ("Prison Realm Key", "accessory", "void", 88, 3300), ("Black Flash Gloves", "armor", "fire", 76, 1400),
    ],
    "tempest": [
        ("Great Sage Staff", "weapon", "spirit", 84, 2400), ("Dragon Knuckle", "weapon", "fire", 92, 4600),
        ("Tempest Armor", "armor", "earth", 88, 3100), ("Slime Core", "accessory", "void", 98, 7600),
        ("Holy Barrier Charm", "accessory", "light", 80, 1800), ("Ogre Blade", "weapon", "dark", 70, 950),
        ("Demon Lord Mantle", "armor", "dark", 90, 3900), ("Jura Forest Cloak", "armor", "wind", 58, 430),
    ],
}

for _series, _templates in GEAR_TEMPLATES.items():
    for _name, _slot, _element, _power, _price in _templates:
        _rarity = rarity_for_power(_power)
        _gear_id = f"gear_{SERIES[_series]['short'].lower()}_{_slug(_name)}"
        _base = _stats(_power, _rarity, 0.34)
        GEAR[_gear_id] = {
            "id": _gear_id,
            "name": _name,
            "series": _series,
            "slot": _slot,
            "element": _element,
            "rarity": _rarity,
            "power": _power,
            "price": _price,
            "currency": "yens" if _price < 3000 else "crystals",
            "hp": _base["hp"],
            "atk": _base["atk"],
            "def": _base["def"],
            "spd": _base["spd"],
            "desc": f"{_rarity.title()} {_slot} from {SERIES[_series]['name']}.",
        }
        GEAR_BY_SERIES[_series].append(_gear_id)

UNIVERSAL_GEAR = [
    ("Adventurer's Blade", "weapon", "wind", 40, 100), ("Iron Guard", "armor", "earth", 38, 90),
    ("Lucky Charm", "accessory", "light", 42, 120), ("Battle Boots", "armor", "wind", 46, 180),
    ("Champion's Blade", "weapon", "fire", 68, 760), ("Guardian Plate", "armor", "earth", 66, 700),
    ("Sage Pendant", "accessory", "spirit", 74, 1250), ("Dragon Scale", "armor", "ice", 84, 2500),
    ("Multiverse Relic", "accessory", "void", 100, 9000), ("Time Ring", "accessory", "void", 94, 5600),
]
for _name, _slot, _element, _power, _price in UNIVERSAL_GEAR:
    _rarity = rarity_for_power(_power)
    _gear_id = f"gear_univ_{_slug(_name)}"
    _base = _stats(_power, _rarity, 0.34)
    GEAR[_gear_id] = {
        "id": _gear_id,
        "name": _name,
        "series": "universal",
        "slot": _slot,
        "element": _element,
        "rarity": _rarity,
        "power": _power,
        "price": _price,
        "currency": "yens" if _price < 3000 else "crystals",
        "hp": _base["hp"],
        "atk": _base["atk"],
        "def": _base["def"],
        "spd": _base["spd"],
        "desc": f"Universal {_rarity} {_slot}.",
    }

GEAR_BY_SERIES["universal"] = [gid for gid in GEAR if GEAR[gid]["series"] == "universal"]

NPC_TEMPLATES: dict[str, list[str]] = {
    "dragonball": ["Saibaman", "Frieza Soldier", "Red Ribbon Android", "Namekian Warrior", "Saiyan Invader", "Galactic Patrolman", "Moro Minion", "Tournament Fighter", "Shadow Dragon", "Time Breaker"],
    "naruto": ["Rogue Ninja", "Anbu Operative", "Akatsuki Scout", "Sand Shinobi", "Mist Swordsman", "Stone Golem", "White Zetsu", "Otsutsuki Drone", "Curse Seal Adept", "Missing-nin"],
    "bleach": ["Base Hollow", "Gillian", "Adjuchas", "Soul Reaper Trainee", "Quincy Soldier", "Arrancar Scout", "Wandenreich Ritter", "Hell Chain", "Reishi Beast", "Vasto Lorde"],
    "jujutsu": ["Grade 4 Curse", "Grade 3 Curse", "Grade 2 Curse", "Grade 1 Curse", "Special Grade Curse", "Cursed Corpse", "Curse User", "Shikigami", "Culling Game Player", "Domain Fragment"],
    "tempest": ["Jura Wolf", "Goblin Raider", "Lizardman Scout", "Ogre Brute", "Direwolf Alpha", "Orc Lord Soldier", "Demon Lord Spy", "Undead Knight", "Insectar Drone", "Sky Dragon"],
}

NPCS: dict[str, list[dict]] = {series: [] for series in SERIES_ORDER}
for _series in SERIES_ORDER:
    for _index, _name in enumerate(NPC_TEMPLATES[_series]):
        _power = 30 + _index * 6
        _rarity = rarity_for_power(_power)
        _base = _stats(_power, _rarity, 0.75)
        NPCS[_series].append({
            "id": f"npc_{SERIES[_series]['short'].lower()}_{_index + 1}",
            "name": _name,
            "series": _series,
            "level": 1 + _index * 8,
            "power": _power,
            "element": ELEMENT_ORDER[_index % len(ELEMENT_ORDER)],
            "hp": _base["hp"],
            "atk": _base["atk"],
            "def": _base["def"],
            "spd": _base["spd"],
            "exp": 60 + _index * 45,
            "yens": 45 + _index * 30,
            "gems": 1 if _index % 3 == 0 else 0,
            "drop": ["senzu_small", "energy_fire", "crystal_shard"][_index % 3],
        })

BOSS_NAMES: dict[str, list[tuple[str, int, str]]] = {
    "dragonball": [("Raditz, Saiyan Scout", 64, "fire"), ("Frieza, Emperor of Evil", 82, "ice"), ("Cell, Perfect Android", 88, "earth"), ("Majin Buu, Ancient Terror", 90, "dark"), ("Jiren, Pride of Universe 11", 96, "spirit")],
    "naruto": [("Zabuza, Demon of the Mist", 66, "water"), ("Orochimaru, Serpent Sage", 78, "dark"), ("Pain, Leader of Akatsuki", 86, "spirit"), ("Madara, Ghost of the Valley", 95, "fire"), ("Kaguya, Rabbit Goddess", 97, "light")],
    "bleach": [("Grimmjow, Sexta Espada", 74, "lightning"), ("Ulquiorra, Cuatro Espada", 86, "dark"), ("Aizen, Master of Illusions", 94, "dark"), ("Yhwach, Quincy King", 98, "void"), ("Ichibei, Monk of Names", 96, "void")],
    "jujutsu": [("Jogo, Volcano Curse", 74, "fire"), ("Mahito, Soul Shaper", 82, "dark"), ("Geto, Curse Manipulator", 88, "dark"), ("Sukuna, King of Curses", 99, "dark"), ("Gojo, Strongest Sorcerer", 100, "void")],
    "tempest": [("Geld, Orc Lord", 70, "earth"), ("Clayman, Marionette Master", 80, "spirit"), ("Diablo, Demon Lord Butler", 92, "dark"), ("Milim, Dragon Princess", 96, "fire"), ("Rimuru, Demon Lord Slime", 100, "void")],
}

BOSSES: dict[str, list[dict]] = {series: [] for series in SERIES_ORDER}
for _series in SERIES_ORDER:
    for _index, (_name, _power, _element) in enumerate(BOSS_NAMES[_series]):
        _rarity = rarity_for_power(_power)
        _base = _stats(_power, _rarity, 1.9)
        BOSSES[_series].append({
            "id": f"boss_{SERIES[_series]['short'].lower()}_{_index + 1}",
            "name": _name,
            "series": _series,
            "level": 10 + _index * 15,
            "power": _power,
            "element": _element,
            "hp": _base["hp"] * 2,
            "atk": _base["atk"],
            "def": _base["def"],
            "spd": _base["spd"],
            "exp": 800 + _index * 700,
            "yens": 600 + _index * 550,
            "gems": 8 + _index * 5,
            "crystals": 2 + _index * 2,
            "drop": ["shard_epic", "awakening_stone", "shard_legendary", "shard_mythic", "shard_divine"][_index],
        })

WORLD_BOSSES = [
    {"id": "wb_dragonball", "name": "Omega Shenron", "series": "dragonball", "element": "dark", "level": 120, "hp": 2500000, "atk": 5200, "def": 3600, "spd": 900, "reward": {"gems": 250, "crystals": 80, "tickets": 3}},
    {"id": "wb_naruto", "name": "Ten-Tails", "series": "naruto", "element": "void", "level": 120, "hp": 2400000, "atk": 5000, "def": 3400, "spd": 860, "reward": {"gems": 250, "crystals": 80, "tickets": 3}},
    {"id": "wb_bleach", "name": "Soul King Yhwach", "series": "bleach", "element": "void", "level": 120, "hp": 2450000, "atk": 5100, "def": 3500, "spd": 880, "reward": {"gems": 250, "crystals": 80, "tickets": 3}},
    {"id": "wb_jujutsu", "name": "Cursed King Sukuna", "series": "jujutsu", "element": "dark", "level": 120, "hp": 2350000, "atk": 5300, "def": 3300, "spd": 920, "reward": {"gems": 250, "crystals": 80, "tickets": 3}},
    {"id": "wb_tempest", "name": "Ultimate Skill Michael", "series": "tempest", "element": "light", "level": 120, "hp": 2500000, "atk": 5050, "def": 3550, "spd": 870, "reward": {"gems": 250, "crystals": 80, "tickets": 3}},
]
WORLD_BOSS_BY_ID = {boss["id"]: boss for boss in WORLD_BOSSES}

CLAN_RAIDS = [
    {"id": "cr_dragonball", "name": "Saiyan Invasion", "series": "dragonball", "element": "fire", "hp": 400000, "atk": 3600, "def": 2200, "spd": 600, "reward": {"gems": 120, "crystals": 40}},
    {"id": "cr_naruto", "name": "Akatsuki Assault", "series": "naruto", "element": "dark", "hp": 380000, "atk": 3500, "def": 2100, "spd": 620, "reward": {"gems": 120, "crystals": 40}},
    {"id": "cr_bleach", "name": "Hollow Tide", "series": "bleach", "element": "void", "hp": 390000, "atk": 3550, "def": 2150, "spd": 610, "reward": {"gems": 120, "crystals": 40}},
    {"id": "cr_jujutsu", "name": "Culling Game Riot", "series": "jujutsu", "element": "spirit", "hp": 375000, "atk": 3650, "def": 2050, "spd": 640, "reward": {"gems": 120, "crystals": 40}},
    {"id": "cr_tempest", "name": "Demon Lord March", "series": "tempest", "element": "earth", "hp": 410000, "atk": 3450, "def": 2300, "spd": 590, "reward": {"gems": 120, "crystals": 40}},
]
CLAN_RAID_BY_ID = {raid["id"]: raid for raid in CLAN_RAIDS}

GACHA_BANNERS: dict[str, dict] = {}
for _index, _series in enumerate(SERIES_ORDER):
    _featured_pool = [
        cid for cid in CHARACTERS_BY_SERIES[_series]
        if CHARACTERS[cid]["rarity"] in ("mythic", "divine") and CHARACTERS[cid]["form"] == "Base"
    ]
    _featured_pool.sort(key=lambda cid: CHARACTERS[cid]["power"], reverse=True)
    GACHA_BANNERS[_series] = {
        "id": _series,
        "name": f"{SERIES[_series]['name']} Legendary Summon",
        "series": _series,
        "emoji": SERIES[_series]["emoji"],
        "description": f"Summon heroes from {SERIES[_series]['name']}.",
        "featured": _featured_pool[:5],
        "boost": 0.35,
    }
GACHA_BANNERS["multiverse"] = {
    "id": "multiverse",
    "name": "Multiverse Ultimate Summon",
    "series": "all",
    "emoji": "🌌",
    "description": "All five series in one banner with boosted divine rates.",
    "featured": [cid for cid in CHARACTERS if CHARACTERS[cid]["rarity"] == "divine"][:8],
    "boost": 0.50,
}

QUESTS: list[dict] = []
for _quest in [
    ("daily_hunt", "Hunt 5 times", "daily", "hunt", 5, {"yens": 500, "gems": 10, "exp": 200}),
    ("daily_win", "Win 3 battles", "daily", "wins", 3, {"yens": 650, "gems": 12, "exp": 250}),
    ("daily_boss", "Defeat 1 boss", "daily", "boss_kills", 1, {"gems": 15, "crystals": 5, "exp": 300}),
    ("daily_gacha", "Summon 5 heroes", "daily", "gacha_pulls", 5, {"yens": 700, "tickets": 1, "exp": 200}),
    ("daily_arena", "Win 2 arena duels", "daily", "pvp_wins", 2, {"gems": 18, "crystals": 6, "exp": 350}),
    ("daily_clan", "Donate to your clan", "daily", "clan_donation", 1, {"yens": 800, "clan_exp": 100}),
    ("weekly_hunt", "Hunt 30 times", "weekly", "hunt", 30, {"gems": 60, "tickets": 2, "exp": 1500}),
    ("weekly_win", "Win 15 battles", "weekly", "wins", 15, {"gems": 70, "crystals": 20, "exp": 1800}),
    ("weekly_boss", "Defeat 5 bosses", "weekly", "boss_kills", 5, {"gems": 80, "crystals": 25, "exp": 2200}),
    ("weekly_raid", "Deal 5000 raid damage", "weekly", "raid_damage", 5000, {"gems": 100, "tickets": 3, "exp": 2500}),
    ("weekly_gacha", "Summon 30 heroes", "weekly", "gacha_pulls", 30, {"gems": 120, "tickets": 4, "exp": 2000}),
    ("monthly_win", "Win 60 battles", "monthly", "wins", 60, {"gems": 300, "crystals": 80, "tickets": 8, "exp": 8000}),
    ("monthly_boss", "Defeat 20 bosses", "monthly", "boss_kills", 20, {"gems": 350, "crystals": 100, "tickets": 10, "exp": 9000}),
    ("monthly_raid", "Deal 100000 raid damage", "monthly", "raid_damage", 100000, {"gems": 400, "crystals": 120, "tickets": 12, "exp": 10000}),
    ("monthly_level", "Reach level 50", "monthly", "level", 50, {"gems": 500, "crystals": 150, "tickets": 15, "exp": 12000}),
]:
    QUESTS.append({
        "id": _quest[0], "name": _quest[1], "type": _quest[2], "metric": _quest[3],
        "target": _quest[4], "rewards": _quest[5],
    })

QUEST_BY_ID = {quest["id"]: quest for quest in QUESTS}
QUEST_PERIOD = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}

ACHIEVEMENTS: list[dict] = []
for _index, (_metric, _target, _name, _reward) in enumerate([
    ("total_battles", 10, "First Steps", {"gems": 20, "yens": 500}),
    ("total_battles", 50, "Battle Hardened", {"gems": 40, "yens": 1500}),
    ("total_battles", 200, "Veteran of the Multiverse", {"gems": 80, "crystals": 20}),
    ("total_battles", 1000, "Eternal Warrior", {"gems": 250, "crystals": 80}),
    ("wins", 10, "Rising Star", {"gems": 20, "yens": 600}),
    ("wins", 100, "Champion", {"gems": 70, "crystals": 20}),
    ("wins", 500, "Conqueror", {"gems": 200, "crystals": 70}),
    ("boss_kills", 1, "Boss Slayer", {"gems": 15, "yens": 500}),
    ("boss_kills", 25, "Boss Hunter", {"gems": 60, "crystals": 15}),
    ("boss_kills", 100, "Boss Executioner", {"gems": 180, "crystals": 60}),
    ("gacha_pulls", 10, "Summoner", {"gems": 20, "tickets": 1}),
    ("gacha_pulls", 50, "Collector", {"gems": 50, "tickets": 2}),
    ("gacha_pulls", 200, "Gacha Master", {"gems": 150, "tickets": 5}),
    ("npc_streak", 5, "Streak Starter", {"gems": 15, "yens": 800}),
    ("npc_streak", 15, "Streak King", {"gems": 50, "crystals": 15}),
    ("npc_streak", 30, "Unstoppable", {"gems": 120, "crystals": 40}),
    ("raid_damage", 10000, "Raid Striker", {"gems": 40, "crystals": 10}),
    ("raid_damage", 100000, "Raid Breaker", {"gems": 120, "crystals": 35}),
    ("raid_damage", 1000000, "Raid Legend", {"gems": 300, "crystals": 100}),
    ("arena_rating", 1200, "Arena Challenger", {"gems": 30, "crystals": 10}),
    ("arena_rating", 1600, "Arena Elite", {"gems": 100, "crystals": 30}),
    ("arena_rating", 2000, "Arena Apex", {"gems": 250, "crystals": 80}),
    ("characters", 5, "Roster Builder", {"gems": 20, "tickets": 1}),
    ("characters", 15, "Roster Tactician", {"gems": 50, "tickets": 2}),
    ("characters", 40, "Roster Legend", {"gems": 150, "tickets": 5}),
    ("characters", 80, "Multiverse Archivist", {"gems": 300, "crystals": 100}),
    ("clan_donation", 10000, "Clan Patron", {"gems": 40, "crystals": 12}),
    ("clan_donation", 100000, "Clan Benefactor", {"gems": 120, "crystals": 35}),
    ("market_sales", 10, "Merchant", {"gems": 20, "yens": 1000}),
    ("market_sales", 100, "Trade Baron", {"gems": 80, "crystals": 20}),
    ("level", 25, "Awakened", {"gems": 30, "crystals": 10}),
    ("level", 50, "Super Warrior", {"gems": 80, "crystals": 25}),
    ("level", 75, "Transcendent", {"gems": 150, "crystals": 50}),
    ("level", 100, "Multiverse God", {"gems": 300, "crystals": 120}),
    ("pvp_wins", 10, "Duelist", {"gems": 25, "crystals": 8}),
    ("pvp_wins", 50, "Gladiator", {"gems": 90, "crystals": 28}),
    ("pvp_wins", 200, "Arena Immortal", {"gems": 220, "crystals": 75}),
    ("series_dragonball", 10, "Dragon Ball Devotee", {"gems": 30, "tickets": 1}),
    ("series_naruto", 10, "Will of Fire", {"gems": 30, "tickets": 1}),
    ("series_bleach", 10, "Soul Reaper", {"gems": 30, "tickets": 1}),
    ("series_jujutsu", 10, "Cursed Prodigy", {"gems": 30, "tickets": 1}),
    ("series_tempest", 10, "Tempest Founder", {"gems": 30, "tickets": 1}),
]):
    ACHIEVEMENTS.append({
        "id": f"ach_{_index + 1:02d}",
        "name": _name,
        "metric": _metric,
        "target": _target,
        "rewards": _reward,
        "desc": f"Reach {_target} {_metric.replace('_', ' ')}.",
    })
ACHIEVEMENT_BY_ID = {achievement["id"]: achievement for achievement in ACHIEVEMENTS}

TITLES = {
    "title_rookie": {"name": "Rookie", "desc": "A new legend begins.", "bonus": {"hp_pct": 0.01}, "requirement": None},
    "title_fighter": {"name": "Multiverse Fighter", "desc": "Prove yourself in battle.", "bonus": {"atk_pct": 0.02}, "requirement": ("wins", 10)},
    "title_boss_slayer": {"name": "Boss Slayer", "desc": "Hunt the strongest enemies.", "bonus": {"atk_pct": 0.03}, "requirement": ("boss_kills", 10)},
    "title_summoner": {"name": "Grand Summoner", "desc": "Call heroes across worlds.", "bonus": {"hp_pct": 0.03}, "requirement": ("gacha_pulls", 50)},
    "title_arena": {"name": "Arena Champion", "desc": "Rule the arena.", "bonus": {"atk_pct": 0.04, "spd_pct": 0.03}, "requirement": ("arena_rating", 1600)},
    "title_clan": {"name": "Clan Pillar", "desc": "Support your clan.", "bonus": {"def_pct": 0.04, "hp_pct": 0.03}, "requirement": ("clan_donation", 50000)},
    "title_collector": {"name": "Multiverse Collector", "desc": "Gather heroes from every series.", "bonus": {"hp_pct": 0.05, "atk_pct": 0.03}, "requirement": ("characters", 50)},
    "title_god": {"name": "God of the Multiverse", "desc": "Reach the pinnacle.", "bonus": {"hp_pct": 0.08, "atk_pct": 0.06, "def_pct": 0.05}, "requirement": ("level", 100)},
}

CRAFTING_RECIPES = [
    {"id": "craft_rare_weapon", "result": "gear_univ_champion_s_blade", "cost": {"yens": 800, "crystal_shard": 2, "forge_core": 1}},
    {"id": "craft_epic_armor", "result": "gear_univ_guardian_plate", "cost": {"yens": 1200, "crystal_shard": 3, "forge_core": 1}},
    {"id": "craft_sage_pendant", "result": "gear_univ_sage_pendant", "cost": {"yens": 2000, "energy_spirit": 2, "forge_core": 2}},
    {"id": "craft_dragon_scale", "result": "gear_univ_dragon_scale", "cost": {"yens": 4000, "energy_light": 3, "forge_core": 3}},
    {"id": "craft_multiverse_relic", "result": "gear_univ_multiverse_relic", "cost": {"yens": 15000, "energy_dark": 5, "crystal_shard": 10, "forge_core": 5}},
]

PROFILE_AVATARS = {
    "rookie": {"name": "Rookie", "icon": "🌱", "level": 1},
    "fighter": {"name": "Fighter", "icon": "⚔️", "level": 5},
    "hunter": {"name": "Hunter", "icon": "🏹", "level": 10},
    "ninja": {"name": "Shinobi", "icon": "🥷", "level": 15},
    "soul": {"name": "Soul Reaper", "icon": "⛩️", "level": 20},
    "flame": {"name": "Flame Lord", "icon": "🔥", "level": 25},
    "dragon": {"name": "Dragon Master", "icon": "🐉", "level": 30},
    "storm": {"name": "Storm King", "icon": "⚡", "level": 40},
    "oracle": {"name": "Oracle", "icon": "🔮", "level": 50},
    "crown": {"name": "Crowned Legend", "icon": "👑", "level": 60},
}

CLAN_BONUS_PER_LEVEL = 0.02

DAILY_SHOP_POOL = [
    "senzu_large", "stamina_drink", "exp_tome", "gacha_ticket", "elite_key", "boss_key",
    "raid_token", "awakening_stone", "forge_core", "crystal_shard", "shard_rare",
    "energy_fire", "energy_water", "energy_dark", "energy_light", "energy_spirit",
]

EVENTS = [
    {"id": "event_saiyan", "name": "Saiyan Festival", "series": "dragonball", "bonus": "Dragon Ball drop rate +25%", "emoji": "🐉"},
    {"id": "event_chunin", "name": "Chunin Exams", "series": "naruto", "bonus": "Naruto EXP +25%", "emoji": "🍥"},
    {"id": "event_hollow", "name": "Hollow Night", "series": "bleach", "bonus": "Bleach crystal drops +25%", "emoji": "⚔️"},
    {"id": "event_culling", "name": "Culling Game", "series": "jujutsu", "bonus": "JJK raid damage +25%", "emoji": "🔮"},
    {"id": "event_walpurgis", "name": "Walpurgis Banquet", "series": "tempest", "bonus": "Tempest gem drops +25%", "emoji": "💧"},
]

ELEMENTAL_SYNERGY = {
    ("fire", "wind"): "Blazing Gale",
    ("water", "lightning"): "Storm Surge",
    ("earth", "ice"): "Permafrost",
    ("light", "dark"): "Eclipse",
    ("spirit", "void"): "Astral Rift",
}

NEW_COMMANDS = ["/codex", "/series", "/events", "/titles", "/achievements", "/arena", "/market", "/clanraid", "/global", "/worldboss", "/forge", "/enhance", "/fuse", "/team", "/travel", "/daily_shop", "/banner", "/settings", "/about", "/admin"]

FUSION_COST = {"yens": 1000, "crystal_shard": 2}


def search_characters(query: str, series: str | None = None, rarity: str | None = None) -> list[str]:
    query = query.strip().lower()
    results = []
    for char_id, character in CHARACTERS.items():
        if series and series != "all" and character["series"] != series:
            continue
        if rarity and character["rarity"] != rarity:
            continue
        if query and query not in character["name"].lower() and query not in character["id"].lower():
            continue
        results.append(char_id)
    results.sort(key=lambda cid: (CHARACTERS[cid]["series"], CHARACTERS[cid]["power"], CHARACTERS[cid]["name"]))
    return results


def character_line(char_id: str) -> str:
    character = CHARACTERS[char_id]
    series = SERIES[character["series"]]
    rarity = RARITIES[character["rarity"]]
    element = ELEMENTS[character["element"]]
    return f"{rarity['emoji']} {element['emoji']} {character['name']} — {series['name']}"


def gear_line(gear_id: str) -> str:
    gear = GEAR[gear_id]
    rarity = RARITIES[gear["rarity"]]
    element = ELEMENTS[gear["element"]]
    return f"{rarity['emoji']} {element['emoji']} {gear['name']} [{gear['slot']}]"


def clone(value):
    return deepcopy(value)

ITEMS.update({
    "fish_common": {"name": "Jura River Fish", "emoji": "🐟", "kind": "material", "value": 1, "price": 70, "currency": "yens", "desc": "A fresh fish from the multiverse rivers."},
    "fish_rare": {"name": "Golden Koi", "emoji": "🐠", "kind": "material", "value": 1, "price": 260, "currency": "yens", "desc": "A rare golden fish said to bring luck."},
    "ore_iron": {"name": "Iron Ore", "emoji": "🪨", "kind": "material", "value": 1, "price": 90, "currency": "yens", "desc": "Sturdy ore used by smiths."},
    "ore_gold": {"name": "Gold Ore", "emoji": "🪙", "kind": "material", "value": 1, "price": 320, "currency": "yens", "desc": "A gleaming vein of gold."},
    "treasure_map": {"name": "Treasure Map", "emoji": "🗺️", "kind": "material", "value": 1, "price": 500, "currency": "yens", "desc": "A map leading to hidden loot."},
    "pet_egg": {"name": "Companion Egg", "emoji": "🥚", "kind": "pet", "value": 1, "price": 150, "currency": "gems", "desc": "Hatches a random companion."},
    "pet_egg_premium": {"name": "Radiant Companion Egg", "emoji": "🌟", "kind": "pet", "value": 2, "price": 450, "currency": "gems", "desc": "Hatches a rare or better companion."},
})

PETS = {
    "pet_shenron": {"id": "pet_shenron", "name": "Mini Shenron", "emoji": "🐉", "series": "dragonball", "rarity": "divine", "element": "spirit", "bonus": {"hp_pct": 0.03, "atk_pct": 0.02}, "desc": "A tiny wish-granting dragon."},
    "pet_puar": {"id": "pet_puar", "name": "Puar", "emoji": "🐈", "series": "dragonball", "rarity": "rare", "element": "wind", "bonus": {"spd_pct": 0.03}, "desc": "A loyal shape-shifting companion."},
    "pet_kurama": {"id": "pet_kurama", "name": "Kurama", "emoji": "🦊", "series": "naruto", "rarity": "mythic", "element": "fire", "bonus": {"atk_pct": 0.03, "hp_pct": 0.01}, "desc": "The Nine-Tails sealed in miniature."},
    "pet_akamaru": {"id": "pet_akamaru", "name": "Akamaru", "emoji": "🐕", "series": "naruto", "rarity": "rare", "element": "earth", "bonus": {"def_pct": 0.03}, "desc": "A faithful ninja hound."},
    "pet_kon": {"id": "pet_kon", "name": "Kon", "emoji": "🦁", "series": "bleach", "rarity": "common", "element": "light", "bonus": {"hp_pct": 0.02}, "desc": "A modified soul in a plush lion."},
    "pet_hooleer": {"id": "pet_hooleer", "name": "Hooleer", "emoji": "👁️", "series": "bleach", "rarity": "epic", "element": "dark", "bonus": {"atk_pct": 0.025}, "desc": "A strange Hollow companion."},
    "pet_divine_dog": {"id": "pet_divine_dog", "name": "Divine Dog", "emoji": "🐺", "series": "jujutsu", "rarity": "legendary", "element": "light", "bonus": {"atk_pct": 0.02, "def_pct": 0.02}, "desc": "A Ten Shadows shikigami."},
    "pet_nue": {"id": "pet_nue", "name": "Nue", "emoji": "🦅", "series": "jujutsu", "rarity": "rare", "element": "lightning", "bonus": {"spd_pct": 0.03}, "desc": "A winged shikigami."},
    "pet_ranga": {"id": "pet_ranga", "name": "Ranga", "emoji": "🐺", "series": "tempest", "rarity": "legendary", "element": "lightning", "bonus": {"atk_pct": 0.02, "spd_pct": 0.02}, "desc": "A tempest wolf pup."},
    "pet_beretta": {"id": "pet_beretta", "name": "Beretta", "emoji": "🪆", "series": "tempest", "rarity": "mythic", "element": "earth", "bonus": {"def_pct": 0.03, "hp_pct": 0.02}, "desc": "A loyal demon construct."},
}
STARTER_PET = "pet_shenron"

DUNGEONS = {series: [] for series in SERIES_ORDER}
for _series in SERIES_ORDER:
    for _floor, _boss in enumerate(BOSSES[_series], 1):
        DUNGEONS[_series].append({
            "id": f"dungeon_{SERIES[_series]['short'].lower()}_{_floor}",
            "name": f"{SERIES[_series]['name']} Dungeon Floor {_floor}",
            "series": _series,
            "floor": _floor,
            "level": _boss["level"],
            "element": _boss["element"],
            "hp": int(_boss["hp"] * 1.15),
            "atk": int(_boss["atk"] * 1.10),
            "def": int(_boss["def"] * 1.10),
            "spd": int(_boss["spd"] * 1.05),
            "exp": int(_boss["exp"] * 1.3),
            "yens": int(_boss["yens"] * 1.3),
            "gems": int(_boss["gems"] * 1.5),
            "crystals": int(_boss["crystals"] * 1.5),
            "drop": _boss["drop"],
        })

SERIES_THEME = {
    "dragonball": {"bg": "#2b1206", "accent": "#ff7a18", "glow": "#ffd166", "label": "DRAGON BALL"},
    "naruto": {"bg": "#1a1206", "accent": "#ff9f1c", "glow": "#ffe066", "label": "NARUTO"},
    "bleach": {"bg": "#10151f", "accent": "#49b6ff", "glow": "#c7f0ff", "label": "BLEACH"},
    "jujutsu": {"bg": "#160f1f", "accent": "#9d4edd", "glow": "#e0aaff", "label": "JUJUTSU KAISEN"},
    "tempest": {"bg": "#061a1c", "accent": "#20c997", "glow": "#b7f7e8", "label": "TEMPEST"},
    "universal": {"bg": "#0a0f1f", "accent": "#f5c542", "glow": "#fff3b0", "label": "MULTIVERSE"},
}

EXTRA_SKILLS = {
    "dragonball": [
        ("masenko", "Masenko", "light", 1.72, "A two-handed ki wave."),
        ("destructo_disc", "Destructo Disc", "void", 2.00, "A razor-sharp disc that cuts through anything."),
        ("spirit_sword", "Spirit Sword", "spirit", 2.18, "A blade formed from condensed ki."),
        ("burning_attack", "Burning Attack", "fire", 1.88, "A rapid-fire heat wave."),
        ("final_kamehameha", "Final Kamehameha", "light", 2.52, "A combined final-wave attack."),
        ("big_bang_attack", "Big Bang Attack", "fire", 2.05, "A sphere of explosive ki."),
        ("death_beam", "Death Beam", "dark", 1.82, "A precise piercing beam."),
        ("death_ball", "Death Ball", "dark", 2.36, "A planet-crushing orb."),
        ("time_skip", "Time Skip", "void", 2.20, "Strike in a frozen instant."),
        ("god_kamehameha", "God Kamehameha", "spirit", 2.48, "A divine ki wave."),
        ("soul_punisher", "Soul Punisher", "spirit", 2.40, "Erase evil energy itself."),
        ("stardust_breaker", "Stardust Breaker", "light", 2.58, "A brilliant spirit blast."),
        ("meteor_explosion", "Meteor Explosion", "fire", 2.34, "An explosive barrage."),
        ("dragon_thunder", "Dragon Thunder", "lightning", 2.28, "A roaring dragon of lightning."),
        ("divine_rage", "Divine Rage", "void", 2.62, "A godly explosion of destructive power."),
    ],
    "naruto": [
        ("shadow_clone", "Shadow Clone Jutsu", "spirit", 1.55, "Create a squad of clones."),
        ("substitution", "Substitution Jutsu", "wind", 1.30, "Swap places with a decoy."),
        ("fireball_jutsu", "Fireball Jutsu", "fire", 1.78, "A roaring sphere of flame."),
        ("phoenix_flower", "Phoenix Flower Jutsu", "fire", 1.90, "Scatter multiple fireballs."),
        ("water_dragon", "Water Dragon Jutsu", "water", 2.00, "A serpent of surging water."),
        ("earth_wall", "Earth Wall", "earth", 1.62, "Raise a fortress of stone."),
        ("wind_vacuum", "Wind Vacuum Blast", "wind", 1.95, "A blade of compressed air."),
        ("lightning_blade", "Lightning Blade", "lightning", 2.12, "A piercing spear of lightning."),
        ("susanoo_arrow", "Susanoo Arrow", "spirit", 2.30, "A massive chakra arrow."),
        ("truth_seeking_orb", "Truth-Seeking Orb", "void", 2.55, "A sphere of all nature releases."),
        ("six_paths", "Six Paths Power", "light", 2.45, "Awaken the power of the Sage."),
        ("infinite_tsukuyomi", "Infinite Tsukuyomi", "dark", 2.60, "Trap the world in an endless dream."),
        ("amenotejikara", "Amenotejikara", "void", 2.20, "Instantly swap space."),
        ("karma_seal", "Karma Seal", "dark", 2.38, "Borrow the power of an Otsutsuki."),
        ("sage_lightning", "Sage Art: Lightning Release", "lightning", 2.26, "Nature energy fused with lightning."),
    ],
    "bleach": [
        ("cero_oscuro", "Cero Oscuras", "dark", 2.23, "A black Cero of immense pressure."),
        ("gran_rey_cero", "Gran Rey Cero", "void", 2.30, "A Cero fit for a king."),
        ("hado_90", "Hado #90: Kurohitsugi", "dark", 2.48, "A coffin of black spiritual energy."),
        ("bakudo_99", "Bakudo #99: Kin", "spirit", 2.10, "Bind a target in spirit chains."),
        ("senbonzakura_kageyoshi", "Senbonzakura Kageyoshi", "wind", 2.32, "A storm of a thousand blades."),
        ("daiguren_hyorinmaru", "Daiguren Hyorinmaru", "ice", 2.36, "An ice dragon's frozen wings."),
        ("kamishini_no_yari", "Kamishini no Yari", "void", 2.44, "A blade that extends and destroys cells."),
        ("katen_kyokotsu", "Katen Kyokotsu", "wind", 2.18, "Turn children's games into reality."),
        ("ryujin_jakka", "Ryujin Jakka", "fire", 2.50, "The strongest fire-type Zanpakuto."),
        ("zanka_north", "Zanka no Tachi: North", "fire", 2.62, "A slash of absolute heat."),
        ("sankt_altar", "Sankt Altar", "light", 2.28, "Steal power through a Quincy ritual."),
        ("auswahlen", "Auswahlen", "light", 2.58, "A divine selection of souls."),
        ("the_almighty", "The Almighty", "void", 2.70, "See and rewrite every future."),
        ("irazusando", "Irazusando", "spirit", 2.40, "A forbidden technique of the Soul King."),
        ("getsuga_jujisho", "Getsuga Jujisho", "dark", 2.46, "A cross-shaped crescent of reiatsu."),
    ],
    "jujutsu": [
        ("ratio_technique", "Ratio Technique", "spirit", 1.82, "Create a weak point at 7:3."),
        ("boogie_woogie", "Boogie Woogie", "void", 1.95, "Swap positions with cursed claps."),
        ("maximum_meteor", "Maximum Meteor", "fire", 2.35, "Call down a blazing meteor."),
        ("maximum_volcano", "Maximum Volcano", "fire", 2.18, "Erupt a field of lava."),
        ("wooden_ball", "Wooden Ball Curse", "earth", 1.90, "Crush with animated roots."),
        ("water_edge", "Water Edge", "water", 1.88, "A slicing wave of cursed water."),
        ("idle_death_gamble", "Idle Death Gamble", "spirit", 2.28, "A domain of impossible odds."),
        ("judgeman", "Judgeman", "light", 2.34, "Pass judgment through a cursed trial."),
        ("executioner_blade", "Executioner's Blade", "dark", 2.42, "A blade that cuts the guilty."),
        ("rika_manifest", "Rika Manifestation", "dark", 2.40, "Unleash the Queen of Curses."),
        ("pure_love_beam", "Pure Love Beam", "light", 2.52, "A beam powered by pure love."),
        ("world_cutting_slash", "World Cutting Slash", "void", 2.68, "Cut the world itself."),
        ("furnace", "Furnace", "fire", 2.56, "A domain of overwhelming flame."),
        ("divine_flames", "Divine Flames", "fire", 2.44, "Flames that burn cursed energy."),
        ("limitless_void", "Limitless Void", "void", 2.60, "An infinite void of information."),
    ],
    "tempest": [
        ("water_blade", "Water Blade", "water", 1.80, "A high-pressure cutting jet."),
        ("black_flame", "Black Flame", "dark", 2.05, "Flames that cling to the soul."),
        ("spatial_motion", "Spatial Motion", "void", 2.12, "Teleport through folded space."),
        ("thought_communication", "Thought Communication", "spirit", 1.62, "Link minds across a battlefield."),
        ("nuclear_flame", "Nuclear Flame", "fire", 2.35, "A controlled nuclear detonation."),
        ("death_storm", "Death Storm", "wind", 2.22, "A lethal storm of aura."),
        ("gravity_collapse", "Gravity Collapse", "void", 2.48, "Crush space into a single point."),
        ("ice_age", "Ice Age", "ice", 2.30, "Freeze an entire battlefield."),
        ("time_stop", "Time Stop", "void", 2.65, "Stop time for a decisive strike."),
        ("castle_guard", "Castle Guard", "earth", 1.70, "A multilayered absolute defense."),
        ("universal_thread", "Universal Thread", "spirit", 2.38, "Connect and control all things."),
        ("predator_king", "Predator King", "dark", 2.50, "Devour an enemy's existence."),
        ("void_god", "Void God", "void", 2.72, "Rule the emptiness between worlds."),
        ("true_dragon", "True Dragon Form", "wind", 2.58, "Awaken the power of a true dragon."),
        ("melt_slash", "Melt Slash", "fire", 2.26, "A blade of superheated fluid."),
    ],
}

for _series, _entries in EXTRA_SKILLS.items():
    for _index, (_sid, _name, _element, _power, _desc) in enumerate(_entries):
        _skill(_sid, _name, _element, _power, _desc, series=_series, cooldown=2 + (_index % 4))
        SKILLS[_sid]["cost"] = 1 if _power < 2.2 else 2 if _power < 2.5 else 3
        SERIES_SKILL_IDS[_series].append(_sid)

SKILLS_BY_SERIES = {series: list(ids) for series, ids in SERIES_SKILL_IDS.items()}


# Give every active technique a concrete gameplay effect instead of only raw damage.
for _index, _skill_data in enumerate(SKILLS.values()):
    if _skill_data.get("type") != "active" or _skill_data.get("bonus"):
        continue
    _text = f"{_skill_data.get('id', '')} {_skill_data.get('name', '')} {_skill_data.get('description', '')}".lower()
    _bonus: dict[str, float | int] = {"atk_pct": 0.04, "crit": 0.01}
    if any(word in _text for word in ("phoenix", "heal", "regen", "restore", "recover", "life")):
        _bonus["heal_hp"] = 26
        _bonus["heal_hp_min"] = 20
        _bonus["heal_hp_max"] = 32
        _bonus["hp_pct"] = 0.02
    if any(word in _text for word in ("barrier", "shield", "guard", "wall", "aegis", "fortress", "defense", "armor")):
        _bonus["def_pct"] = 0.06
        _bonus["hp_flat"] = 40
    if any(word in _text for word in ("luck", "fate", "fortune", "almighty", "dice", "gamble")):
        _bonus["crit"] = 0.035
        _bonus["drop_rate"] = 0.03
        _bonus["gacha_luck"] = 0.02
    if any(word in _text for word in ("greed", "gold", "treasure", "plunder", "loot", "gluttony", "predator")):
        _bonus["drop_rate"] = round(float(_bonus.get("drop_rate", 0.0)) + 0.06, 3)
    if any(word in _text for word in ("summon", "pull", "banner", "wish", "almighty")):
        _bonus["gacha_luck"] = round(float(_bonus.get("gacha_luck", 0.0)) + 0.04, 3)
    if any(word in _text for word in ("speed", "swift", "flash", "transmission", "motion", "rush")):
        _bonus["spd_pct"] = 0.05
    if _index % 3 == 0:
        _bonus["hp_flat"] = int(_bonus.get("hp_flat", 0)) + 40
    _skill_data["bonus"] = _bonus

EXTRA_GEAR = {
    "dragonball": [
        ("Capsule Corps Blade", "weapon", "wind", 58, 420), ("Saiyan Royal Armor", "armor", "fire", 76, 1300),
        ("Namekian Battle Vest", "armor", "earth", 64, 700), ("Grand Priest Staff", "weapon", "spirit", 99, 8200),
        ("Angel Halo", "accessory", "light", 92, 4800), ("Time Chamber Gi", "armor", "spirit", 84, 2600),
        ("Fusion Dance Belt", "accessory", "void", 78, 1800), ("Destroyer Gauntlets", "weapon", "void", 96, 6800),
        ("Capsule Corp Holster", "accessory", "wind", 62, 620), ("Super Dragon Radar", "accessory", "light", 86, 2900),
    ],
    "naruto": [
        ("Kunai of the Anbu", "weapon", "wind", 56, 380), ("Chakra Blade", "weapon", "spirit", 80, 1700),
        ("Akatsuki Ring", "accessory", "dark", 90, 4100), ("Hokage Cloak", "armor", "fire", 92, 4500),
        ("Sage Mode Cloak", "armor", "earth", 84, 2400), ("Byakugan Veil", "accessory", "light", 88, 3300),
        ("Kage Gauntlets", "weapon", "earth", 86, 2800), ("Shinobi Flak Jacket", "armor", "wind", 60, 540),
        ("Otsutsuki Relic", "accessory", "void", 98, 7600), ("Tailed Beast Seal", "accessory", "spirit", 94, 5200),
    ],
    "bleach": [
        ("Asauchi", "weapon", "spirit", 52, 300), ("Shihakusho", "armor", "dark", 58, 420),
        ("Captain's Coat", "armor", "spirit", 90, 3900), ("Vasto Lorde Mask", "armor", "dark", 94, 5000),
        ("Soul Candy", "accessory", "light", 68, 900), ("Quincy Seele Schneider", "weapon", "light", 88, 3400),
        ("Arrancar Blade", "weapon", "void", 84, 2700), ("Hogyoku Ring", "accessory", "void", 100, 9000),
        ("Reiatsu Gauntlet", "weapon", "spirit", 80, 1900), ("Wandenreich Medal", "accessory", "light", 92, 4600),
    ],
    "jujutsu": [
        ("Cursed Tool: Split Soul", "weapon", "dark", 82, 2200), ("Jujutsu High Uniform", "armor", "spirit", 60, 560),
        ("Zenin Cursed Armor", "armor", "earth", 88, 3500), ("Gojo's Blindfold", "accessory", "void", 98, 8000),
        ("Sukuna's Finger", "accessory", "dark", 100, 8800), ("Cursed Spear", "weapon", "spirit", 90, 4200),
        ("Shikigami Charm", "accessory", "dark", 76, 1600), ("Culling Game Badge", "accessory", "void", 84, 2500),
        ("Nanami's Cleaver", "weapon", "light", 74, 1400), ("Black Flash Wraps", "armor", "fire", 80, 2000),
    ],
    "tempest": [
        ("Jura Fang", "weapon", "wind", 72, 1100), ("Ogre Lord Armor", "armor", "earth", 86, 3000),
        ("Demon Lord Cape", "armor", "dark", 94, 5000), ("Rimuru's Mask", "accessory", "void", 100, 9000),
        ("Veldora Scale", "armor", "wind", 96, 6200), ("Great Sage Crystal", "accessory", "spirit", 88, 3300),
        ("Slime Blade", "weapon", "water", 78, 1600), ("Walpurgis Invitation", "accessory", "dark", 82, 2300),
        ("Dragon Knuckle II", "weapon", "fire", 92, 4600), ("Tempest Banner", "accessory", "light", 70, 1000),
    ],
}

for _series, _templates in EXTRA_GEAR.items():
    for _name, _slot, _element, _power, _price in _templates:
        _rarity = rarity_for_power(_power)
        _gear_id = f"gear_{SERIES[_series]['short'].lower()}_{_slug(_name)}"
        if _gear_id in GEAR:
            continue
        _base = _stats(_power, _rarity, 0.34)
        GEAR[_gear_id] = {
            "id": _gear_id, "name": _name, "series": _series, "slot": _slot,
            "element": _element, "rarity": _rarity, "rank": _rarity.title(),
            "power": _power, "price": _price,
            "currency": "yens" if _price < 3000 else "crystals",
            "hp": _base["hp"], "atk": _base["atk"], "def": _base["def"], "spd": _base["spd"],
            "desc": f"{_rarity.title()} {_slot} from {SERIES[_series]['name']}.",
        }
        GEAR_BY_SERIES[_series].append(_gear_id)

for _gear in GEAR.values():
    _gear.setdefault("rank", _gear["rarity"].title())

EXTRA_ITEMS = {
    "rank_common_core": {"name": "Common Rank Core", "emoji": "⚪", "kind": "material", "value": 1, "price": 80, "currency": "yens", "rank": "Common", "desc": "Rank-up material for basic gear."},
    "rank_rare_core": {"name": "Rare Rank Core", "emoji": "🔵", "kind": "material", "value": 1, "price": 220, "currency": "yens", "rank": "Rare", "desc": "Rank-up material for rare gear."},
    "rank_epic_core": {"name": "Epic Rank Core", "emoji": "🟣", "kind": "material", "value": 1, "price": 650, "currency": "yens", "rank": "Epic", "desc": "Rank-up material for epic gear."},
    "rank_legendary_core": {"name": "Legendary Rank Core", "emoji": "🟡", "kind": "material", "value": 1, "price": 1500, "currency": "crystals", "rank": "Legendary", "desc": "Rank-up material for legendary gear."},
    "rank_mythic_core": {"name": "Mythic Rank Core", "emoji": "🔴", "kind": "material", "value": 1, "price": 45, "currency": "crystals", "rank": "Mythic", "desc": "Rank-up material for mythic gear."},
    "rank_divine_core": {"name": "Divine Rank Core", "emoji": "🟠", "kind": "material", "value": 1, "price": 120, "currency": "crystals", "rank": "Divine", "desc": "Rank-up material for divine gear."},
    "weapon_scroll": {"name": "Weapon Rune Scroll", "emoji": "📜", "kind": "material", "value": 1, "price": 350, "currency": "yens", "rank": "Rare", "desc": "A rune scroll for weapons."},
    "armor_scroll": {"name": "Armor Rune Scroll", "emoji": "📜", "kind": "material", "value": 1, "price": 350, "currency": "yens", "rank": "Rare", "desc": "A rune scroll for armor."},
    "accessory_scroll": {"name": "Accessory Rune Scroll", "emoji": "📜", "kind": "material", "value": 1, "price": 350, "currency": "yens", "rank": "Rare", "desc": "A rune scroll for accessories."},
    "skill_scroll": {"name": "Skill Codex Page", "emoji": "🧠", "kind": "material", "value": 1, "price": 500, "currency": "yens", "rank": "Epic", "desc": "Rare knowledge used for skill upgrades."},
    "reroll_stone": {"name": "Reroll Stone", "emoji": "🎲", "kind": "material", "value": 1, "price": 25, "currency": "crystals", "rank": "Epic", "desc": "Reroll a gear bonus."},
    "luck_charm": {"name": "Luck Charm", "emoji": "🍀", "kind": "material", "value": 1, "price": 20, "currency": "crystals", "rank": "Rare", "desc": "A small luck boost."},
    "exp_crystal": {"name": "EXP Crystal", "emoji": "🔷", "kind": "exp", "value": 1500, "price": 700, "currency": "yens", "rank": "Epic", "desc": "Gain 1,500 account EXP."},
    "stamina_crystal": {"name": "Stamina Crystal", "emoji": "🔶", "kind": "stamina", "value": 60, "price": 15, "currency": "crystals", "rank": "Rare", "desc": "Restore 60 stamina."},
    "boss_summon_scroll": {"name": "Boss Summon Scroll", "emoji": "🌀", "kind": "summon", "value": 1, "price": 30, "currency": "crystals", "rank": "Legendary", "desc": "Summons a persistent series boss."},
    "raid_summon_scroll": {"name": "Raid Summon Scroll", "emoji": "🌋", "kind": "summon", "value": 1, "price": 70, "currency": "crystals", "rank": "Mythic", "desc": "Summons a powerful raid boss."},
    "transcend_token": {"name": "Transcendence Token", "emoji": "🌟", "kind": "material", "value": 1, "price": 180, "currency": "crystals", "rank": "Divine", "desc": "A token of ultimate ascension."},
    "pet_treat": {"name": "Companion Treat", "emoji": "🍖", "kind": "material", "value": 1, "price": 160, "currency": "yens", "rank": "Common", "desc": "A treat loved by companions."},
    "clan_banner": {"name": "Clan Banner", "emoji": "🚩", "kind": "material", "value": 1, "price": 40, "currency": "gems", "rank": "Epic", "desc": "A banner to rally your clan."},
}
ITEMS.update(EXTRA_ITEMS)

for _item in ITEMS.values():
    _item.setdefault("rank", "Common" if _item.get("price", 0) < 150 else "Rare" if _item.get("price", 0) < 700 else "Epic" if _item.get("price", 0) < 2500 else "Legendary")

STARTER_CHARACTER_POOL = {
    series: [cid for cid in CHARACTERS_BY_SERIES[series] if CHARACTERS[cid]["form"] == "Base" and CHARACTERS[cid]["rarity"] in ("common", "rare", "epic")]
    for series in SERIES_ORDER
}
STARTER_GEAR_POOL = {
    slot: [gid for gid, gear in GEAR.items() if gear["slot"] == slot and gear["rarity"] in ("common", "rare")]
    for slot in ("weapon", "armor", "accessory")
}

CHAPTER_TITLES = {
    "dragonball": ["A Saiyan Arrives", "Desert Showdown", "Namek's Shadow", "Android Awakening", "Cell Games", "Majin Resurgence", "Gods of Destruction", "Tournament of Power", "Moro's Return", "The Final Wish", "Omni-King's Trial", "Multiverse Apex"],
    "naruto": ["Academy Days", "Land of Waves", "Chunin Exams", "Konoha Crush", "Search for Tsunade", "Sasuke Retrieval", "Akatsuki Strikes", "Pain's Assault", "Fourth Great War", "Kaguya's Awakening", "Boruto's Era", "Will of Fire"],
    "bleach": ["Substitute Soul Reaper", "Hollow Hunt", "Soul Society Rescue", "Arrancar Invasion", "Hueco Mundo", "Winter War", "Fullbringer Arc", "Quincy Blood War", "Royal Palace", "Soul King's Fall", "The Almighty", "Beyond Death"],
    "jujutsu": ["Cursed Child", "Detention Center", "Vs. Mahito", "Kyoto Goodwill Event", "Shibuya Incident", "Culling Game", "Sendai Colony", "Shinjuku Showdown", "Sukuna's Domain", "The Strongest", "Final Curse", "New Era"],
    "tempest": ["Slime Awakening", "Jura Forest Alliance", "Dwarven Kingdom", "Orc Lord", "Demon Lord Seed", "Walpurgis", "Tenma War", "Eastern Empire", "True Dragons", "Ultimate Skill", "World's End", "Slime God"],
}
CHAPTER_STORIES = {
    "dragonball": "Ki flares across the sky as a new challenger enters the battlefield.",
    "naruto": "A shinobi's resolve is tested against impossible odds.",
    "bleach": "Spiritual pressure shakes the boundary between life and death.",
    "jujutsu": "Cursed energy twists fear into a terrifying new enemy.",
    "tempest": "A monster nation rises, and the world takes notice.",
}

CHAPTERS: dict[str, list[dict]] = {series: [] for series in SERIES_ORDER}
for _series in SERIES_ORDER:
    for _index, _title in enumerate(CHAPTER_TITLES[_series]):
        _source = BOSSES[_series][_index % len(BOSSES[_series])]
        _scale = 0.55 + _index * 0.07
        CHAPTERS[_series].append({
            "id": f"chapter_{SERIES[_series]['short'].lower()}_{_index + 1}",
            "number": _index + 1,
            "name": _title,
            "series": _series,
            "story": f"{CHAPTER_STORIES[_series]} {_title} begins a new arc in {SERIES[_series]['name']}.",
            "level": 5 + _index * 8,
            "enemy": {
                "id": _source["id"], "name": _source["name"], "series": _series,
                "element": _source["element"], "level": 5 + _index * 8,
                "hp": int(_source["hp"] * _scale * 0.35),
                "atk": int(_source["atk"] * _scale * 0.55),
                "def": int(_source["def"] * _scale * 0.55),
                "spd": int(_source["spd"] * _scale * 0.55),
            },
            "rewards": {
                "yens": 300 + _index * 260, "exp": 220 + _index * 180,
                "gems": 8 + _index * 4, "crystals": 2 + _index * 2,
            },
            "drop": ["shard_common", "shard_rare", "shard_epic", "shard_legendary", "shard_mythic", "shard_divine"][min(5, _index // 2)],
        })

SUMMON_BOSSES: list[dict] = []
for _series in SERIES_ORDER:
    for _index, _boss in enumerate(BOSSES[_series]):
        SUMMON_BOSSES.append({
            "id": f"summon_{SERIES[_series]['short'].lower()}_{_index + 1}",
            "name": f"Summoned {_boss['name']}",
            "series": _series,
            "element": _boss["element"],
            "level": _boss["level"] + 10,
            "hp": int(_boss["hp"] * 2.4),
            "atk": int(_boss["atk"] * 1.25),
            "def": int(_boss["def"] * 1.2),
            "spd": int(_boss["spd"] * 1.1),
            "reward": {
                "yens": int(_boss["yens"] * 2),
                "exp": int(_boss["exp"] * 2),
                "gems": int(_boss["gems"] * 2),
                "crystals": int(_boss["crystals"] * 2),
                "tickets": 1,
            },
            "drop": _boss["drop"],
        })
SUMMON_BOSS_BY_ID = {boss["id"]: boss for boss in SUMMON_BOSSES}
SUMMON_BOSSES_BY_SERIES = {series: [boss for boss in SUMMON_BOSSES if boss["series"] == series] for series in SERIES_ORDER}

CHAPTER_BY_ID = {chapter["id"]: chapter for chapters in CHAPTERS.values() for chapter in chapters}
