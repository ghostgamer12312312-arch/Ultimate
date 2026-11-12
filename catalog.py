"""Static game content: races, classes, items, skills, monsters, bosses, quests.

All content is data-only so it can be validated by the test-suite and reloaded
without touching gameplay code.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Elements
# ---------------------------------------------------------------------------

ELEMENTS: dict[str, dict[str, str]] = {
    "physical": {"name": "Physical", "emoji": "⚔️", "color": "grey"},
    "fire": {"name": "Fire", "emoji": "🔥", "color": "red"},
    "ice": {"name": "Ice", "emoji": "❄️", "color": "blue"},
    "lightning": {"name": "Lightning", "emoji": "⚡", "color": "yellow"},
    "poison": {"name": "Poison", "emoji": "☠️", "color": "green"},
    "shadow": {"name": "Shadow", "emoji": "🌑", "color": "purple"},
    "holy": {"name": "Holy", "emoji": "✨", "color": "white"},
    "arcane": {"name": "Arcane", "emoji": "🔮", "color": "magenta"},
}

# attacker element -> elements it deals bonus damage against
ELEMENT_STRENGTHS: dict[str, tuple[str, ...]] = {
    "physical": ("arcane",),
    "fire": ("ice", "poison"),
    "ice": ("lightning", "physical"),
    "lightning": ("fire", "arcane"),
    "poison": ("fire", "physical"),
    "shadow": ("holy",),
    "holy": ("shadow", "poison"),
    "arcane": ("lightning", "ice"),
}

ELEMENT_MULTIPLIER_STRONG = 1.30
ELEMENT_MULTIPLIER_WEAK = 0.75

# ---------------------------------------------------------------------------
# Races
# ---------------------------------------------------------------------------

STAT_KEYS = ("strength", "agility", "intellect", "vitality", "luck")

RACES: dict[str, dict] = {
    "human": {
        "name": "Human",
        "emoji": "🧑",
        "element": "physical",
        "description": "Balanced and adaptable, humans excel at every discipline.",
        "passive": "+5% XP from all sources.",
        "bonuses": {"strength": 2, "agility": 2, "intellect": 2, "vitality": 2, "luck": 2},
        "xp_bonus": 0.05,
    },
    "elf": {
        "name": "Elf",
        "emoji": "🧝",
        "element": "arcane",
        "description": "Ancient keepers of arcane lore with keen senses.",
        "passive": "+10% mana and +1 critical chance per 20 luck.",
        "bonuses": {"strength": 0, "agility": 4, "intellect": 5, "vitality": 0, "luck": 4},
        "mana_bonus": 0.10,
    },
    "dwarf": {
        "name": "Dwarf",
        "emoji": "🧔",
        "element": "physical",
        "description": "Stalwart smiths forged in mountain fire and stone.",
        "passive": "+10% defense from equipment.",
        "bonuses": {"strength": 5, "agility": 0, "intellect": 1, "vitality": 5, "luck": 1},
        "defense_bonus": 0.10,
    },
    "orc": {
        "name": "Orc",
        "emoji": "👹",
        "element": "physical",
        "description": "Brutal warriors who value strength above all.",
        "passive": "+8% attack.",
        "bonuses": {"strength": 7, "agility": 1, "intellect": 0, "vitality": 4, "luck": 0},
        "attack_bonus": 0.08,
    },
    "undead": {
        "name": "Undead",
        "emoji": "💀",
        "element": "shadow",
        "description": "Deathless wanderers untouched by poison or fear.",
        "passive": "Immune to poison damage and +5% lifesteal.",
        "bonuses": {"strength": 3, "agility": 1, "intellect": 4, "vitality": 3, "luck": 0},
        "lifesteal": 0.05,
        "immune": ("poison",),
    },
    "demon": {
        "name": "Demon",
        "emoji": "😈",
        "element": "fire",
        "description": "Hellborn creatures wielding destructive flame.",
        "passive": "+12% fire damage and +5% attack.",
        "bonuses": {"strength": 5, "agility": 1, "intellect": 4, "vitality": 2, "luck": 1},
        "element_damage": {"fire": 0.12},
        "attack_bonus": 0.05,
    },
    "celestial": {
        "name": "Celestial",
        "emoji": "👼",
        "element": "holy",
        "description": "Beings of light blessed with healing grace.",
        "passive": "+15% healing and +10% holy damage.",
        "bonuses": {"strength": 1, "agility": 2, "intellect": 6, "vitality": 3, "luck": 3},
        "healing_bonus": 0.15,
        "element_damage": {"holy": 0.10},
    },
    "draconian": {
        "name": "Draconian",
        "emoji": "🐉",
        "element": "fire",
        "description": "Descendants of dragons with scales like iron.",
        "passive": "+8% max HP and +5% fire resistance.",
        "bonuses": {"strength": 5, "agility": 1, "intellect": 2, "vitality": 6, "luck": 0},
        "hp_bonus": 0.08,
        "resist": {"fire": 0.05},
    },
    "beastfolk": {
        "name": "Beastfolk",
        "emoji": "🐺",
        "element": "physical",
        "description": "Feral hunters guided by instinct and the moon.",
        "passive": "+15% speed and +5% critical chance.",
        "bonuses": {"strength": 3, "agility": 7, "intellect": 0, "vitality": 2, "luck": 3},
        "speed_bonus": 0.15,
        "crit_bonus": 0.05,
    },
    "elemental": {
        "name": "Elemental",
        "emoji": "🌪️",
        "element": "lightning",
        "description": "Living storms of raw elemental energy.",
        "passive": "+15% elemental damage and +10% mana.",
        "bonuses": {"strength": 1, "agility": 3, "intellect": 7, "vitality": 2, "luck": 2},
        "elemental_bonus": 0.15,
        "mana_bonus": 0.10,
    },
}

# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

CLASSES: dict[str, dict] = {
    "warrior": {
        "name": "Warrior",
        "emoji": "🛡️",
        "element": "physical",
        "description": "Master of blade and shield. High HP and defense.",
        "base": {"strength": 7, "agility": 3, "intellect": 1, "vitality": 7, "luck": 2},
        "skills": ["power_strike", "shield_bash", "battle_cry"],
        "starting_items": ["wooden_sword", "cloth_robe", "small_potion"],
    },
    "mage": {
        "name": "Mage",
        "emoji": "🧙",
        "element": "arcane",
        "description": "Wielder of devastating arcane spells.",
        "base": {"strength": 1, "agility": 3, "intellect": 10, "vitality": 3, "luck": 3},
        "skills": ["fireball", "ice_lance", "arcane_nova"],
        "starting_items": ["apprentice_staff", "cloth_robe", "mana_potion"],
    },
    "rogue": {
        "name": "Rogue",
        "emoji": "🗡️",
        "element": "poison",
        "description": "Swift assassin striking from the shadows.",
        "base": {"strength": 4, "agility": 9, "intellect": 2, "vitality": 3, "luck": 4},
        "skills": ["backstab", "poison_blade", "smoke_bomb"],
        "starting_items": ["rusty_dagger", "leather_armor", "small_potion"],
    },
    "ranger": {
        "name": "Ranger",
        "emoji": "🏹",
        "element": "physical",
        "description": "Deadly marksman of the wilds.",
        "base": {"strength": 4, "agility": 8, "intellect": 3, "vitality": 3, "luck": 4},
        "skills": ["snipe", "volley", "hunters_mark"],
        "starting_items": ["hunting_bow", "leather_armor", "small_potion"],
    },
    "paladin": {
        "name": "Paladin",
        "emoji": "⚜️",
        "element": "holy",
        "description": "Holy knight blending steel and divine magic.",
        "base": {"strength": 6, "agility": 2, "intellect": 5, "vitality": 6, "luck": 3},
        "skills": ["divine_smite", "lay_on_hands", "holy_shield"],
        "starting_items": ["iron_sword", "chainmail", "small_potion"],
    },
    "necromancer": {
        "name": "Necromancer",
        "emoji": "🪦",
        "element": "shadow",
        "description": "Commands the dead and drains the living.",
        "base": {"strength": 2, "agility": 3, "intellect": 9, "vitality": 4, "luck": 2},
        "skills": ["shadow_bolt", "life_drain", "curse_of_weakness"],
        "starting_items": ["bone_staff", "cloth_robe", "mana_potion"],
    },
    "berserker": {
        "name": "Berserker",
        "emoji": "🪓",
        "element": "fire",
        "description": "Frenzied fighter who trades defense for raw power.",
        "base": {"strength": 10, "agility": 4, "intellect": 0, "vitality": 4, "luck": 3},
        "skills": ["reckless_swing", "blood_rage", "whirlwind"],
        "starting_items": ["hand_axe", "leather_armor", "small_potion"],
    },
    "monk": {
        "name": "Monk",
        "emoji": "🥋",
        "element": "lightning",
        "description": "Disciplined martial artist channeling inner chi.",
        "base": {"strength": 5, "agility": 8, "intellect": 4, "vitality": 4, "luck": 2},
        "skills": ["flurry", "chi_strike", "inner_peace"],
        "starting_items": ["iron_knuckles", "cloth_robe", "small_potion"],
    },
}

# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

ITEMS: dict[str, dict] = {
    # --- weapons -----------------------------------------------------------
    "wooden_sword": {"name": "Wooden Sword", "type": "weapon", "slot": "weapon", "rarity": "common", "price": 25, "attack": 4, "element": "physical", "description": "A training sword. Better than fists."},
    "rusty_dagger": {"name": "Rusty Dagger", "type": "weapon", "slot": "weapon", "rarity": "common", "price": 30, "attack": 4, "stats": {"agility": 1}, "element": "physical", "description": "Quick, quiet, and slightly tetanus-prone."},
    "hunting_bow": {"name": "Hunting Bow", "type": "weapon", "slot": "weapon", "rarity": "common", "price": 40, "attack": 5, "stats": {"agility": 1}, "element": "physical", "description": "Reliable bow for hunting game."},
    "apprentice_staff": {"name": "Apprentice Staff", "type": "weapon", "slot": "weapon", "rarity": "common", "price": 40, "attack": 5, "stats": {"intellect": 2}, "element": "arcane", "description": "A novice's focus for channeling magic."},
    "bone_staff": {"name": "Bone Staff", "type": "weapon", "slot": "weapon", "rarity": "uncommon", "price": 90, "attack": 8, "stats": {"intellect": 3}, "element": "shadow", "description": "Carved from the spine of a fallen lich."},
    "hand_axe": {"name": "Hand Axe", "type": "weapon", "slot": "weapon", "rarity": "common", "price": 45, "attack": 6, "element": "physical", "description": "Chops wood and skulls alike."},
    "iron_knuckles": {"name": "Iron Knuckles", "type": "weapon", "slot": "weapon", "rarity": "common", "price": 45, "attack": 5, "stats": {"agility": 2}, "element": "physical", "description": "Punch harder. Much harder."},
    "iron_sword": {"name": "Iron Sword", "type": "weapon", "slot": "weapon", "rarity": "uncommon", "price": 150, "attack": 10, "stats": {"strength": 1}, "element": "physical", "description": "A dependable blade of good iron."},
    "steel_blade": {"name": "Steel Blade", "type": "weapon", "slot": "weapon", "rarity": "rare", "price": 420, "attack": 18, "stats": {"strength": 2}, "element": "physical", "description": "Forged from folded steel, sharp and true."},
    "flame_sword": {"name": "Flame Sword", "type": "weapon", "slot": "weapon", "rarity": "epic", "price": 1100, "attack": 26, "stats": {"strength": 3}, "element": "fire", "description": "The blade burns with an eternal flame."},
    "frost_axe": {"name": "Frost Axe", "type": "weapon", "slot": "weapon", "rarity": "epic", "price": 1150, "attack": 28, "stats": {"strength": 2}, "element": "ice", "description": "Leaves frozen wounds that never bleed."},
    "shadow_dagger": {"name": "Shadow Dagger", "type": "weapon", "slot": "weapon", "rarity": "epic", "price": 1050, "attack": 22, "stats": {"agility": 4, "luck": 2}, "element": "shadow", "description": "Strikes before the victim sees it."},
    "elven_bow": {"name": "Elven Longbow", "type": "weapon", "slot": "weapon", "rarity": "rare", "price": 600, "attack": 20, "stats": {"agility": 4}, "element": "physical", "description": "Singing string and weightless limbs."},
    "arcane_staff": {"name": "Arcane Staff", "type": "weapon", "slot": "weapon", "rarity": "epic", "price": 1200, "attack": 30, "stats": {"intellect": 6}, "element": "arcane", "description": "Crackles with untamed mana."},
    "holy_hammer": {"name": "Holy Hammer", "type": "weapon", "slot": "weapon", "rarity": "epic", "price": 1250, "attack": 27, "stats": {"strength": 3, "vitality": 3}, "element": "holy", "description": "Blessed by the sun itself."},
    "dragon_greatsword": {"name": "Dragon Greatsword", "type": "weapon", "slot": "weapon", "rarity": "legendary", "price": 3500, "attack": 45, "stats": {"strength": 8, "vitality": 3}, "element": "fire", "description": "Forged from a fallen dragon's fang."},
    "void_katana": {"name": "Void Katana", "type": "weapon", "slot": "weapon", "rarity": "legendary", "price": 4200, "attack": 50, "stats": {"agility": 6, "luck": 5}, "element": "shadow", "description": "It cuts the space between heartbeats."},

    # --- armor -------------------------------------------------------------
    "cloth_robe": {"name": "Cloth Robe", "type": "armor", "slot": "armor", "rarity": "common", "price": 20, "defense": 2, "stats": {"intellect": 1}, "description": "Comfortable but not very protective."},
    "leather_armor": {"name": "Leather Armor", "type": "armor", "slot": "armor", "rarity": "common", "price": 55, "defense": 5, "stats": {"agility": 1}, "description": "Light and flexible hunting gear."},
    "chainmail": {"name": "Chainmail", "type": "armor", "slot": "armor", "rarity": "uncommon", "price": 180, "defense": 11, "stats": {"vitality": 2}, "description": "Interlocking rings turn aside blades."},
    "plate_armor": {"name": "Plate Armor", "type": "armor", "slot": "armor", "rarity": "rare", "price": 480, "defense": 20, "stats": {"vitality": 4}, "description": "Heavy steel that makes you a fortress."},
    "shadow_cloak": {"name": "Shadow Cloak", "type": "armor", "slot": "armor", "rarity": "epic", "price": 900, "defense": 15, "stats": {"agility": 5, "luck": 3}, "description": "Woven from living darkness."},
    "dragon_scale": {"name": "Dragon Scale Armor", "type": "armor", "slot": "armor", "rarity": "legendary", "price": 3000, "defense": 35, "stats": {"vitality": 8}, "element": "fire", "description": "Scales that once turned aside dragonfire."},

    # --- helmets -----------------------------------------------------------
    "leather_cap": {"name": "Leather Cap", "type": "helmet", "slot": "helmet", "rarity": "common", "price": 30, "defense": 2, "description": "Keeps the sun and small rocks off your head."},
    "iron_helm": {"name": "Iron Helm", "type": "helmet", "slot": "helmet", "rarity": "uncommon", "price": 140, "defense": 6, "stats": {"vitality": 1}, "description": "A solid helm with a narrow visor."},
    "mage_hood": {"name": "Mage Hood", "type": "helmet", "slot": "helmet", "rarity": "rare", "price": 320, "defense": 4, "stats": {"intellect": 4}, "description": "Whispers secrets of the arcane to its wearer."},
    "dragon_helm": {"name": "Dragon Helm", "type": "helmet", "slot": "helmet", "rarity": "epic", "price": 950, "defense": 14, "stats": {"strength": 3, "vitality": 3}, "description": "A horned helm carved from dragon bone."},

    # --- boots -------------------------------------------------------------
    "leather_boots": {"name": "Leather Boots", "type": "boots", "slot": "boots", "rarity": "common", "price": 25, "defense": 1, "stats": {"agility": 1}, "description": "Good for long roads."},
    "swift_boots": {"name": "Boots of Swiftness", "type": "boots", "slot": "boots", "rarity": "rare", "price": 380, "defense": 3, "stats": {"agility": 5}, "description": "Your steps barely touch the ground."},
    "iron_greaves": {"name": "Iron Greaves", "type": "boots", "slot": "boots", "rarity": "uncommon", "price": 160, "defense": 7, "stats": {"vitality": 2}, "description": "Protects shins and pride."},

    # --- rings -------------------------------------------------------------
    "copper_ring": {"name": "Copper Ring", "type": "ring", "slot": "ring", "rarity": "common", "price": 50, "stats": {"luck": 2}, "description": "A simple band with a lucky feel."},
    "ruby_ring": {"name": "Ruby Ring", "type": "ring", "slot": "ring", "rarity": "rare", "price": 400, "stats": {"strength": 3}, "element": "fire", "description": "The ruby glows with inner heat."},
    "sapphire_ring": {"name": "Sapphire Ring", "type": "ring", "slot": "ring", "rarity": "rare", "price": 400, "stats": {"intellect": 3}, "element": "ice", "description": "Cold to the touch, clear as winter sky."},
    "lucky_ring": {"name": "Lucky Ring", "type": "ring", "slot": "ring", "rarity": "epic", "price": 900, "stats": {"luck": 8}, "description": "Fortune favours its wearer."},

    # --- amulets -----------------------------------------------------------
    "bone_amulet": {"name": "Bone Amulet", "type": "amulet", "slot": "amulet", "rarity": "uncommon", "price": 120, "stats": {"intellect": 2, "vitality": 1}, "element": "shadow", "description": "A grim charm that wards off spirits."},
    "holy_amulet": {"name": "Holy Amulet", "type": "amulet", "slot": "amulet", "rarity": "rare", "price": 450, "stats": {"vitality": 3, "intellect": 2}, "element": "holy", "description": "A blessing of the light, worn over the heart."},
    "demon_amulet": {"name": "Demon Amulet", "type": "amulet", "slot": "amulet", "rarity": "epic", "price": 1000, "stats": {"strength": 3, "luck": 3}, "element": "fire", "description": "A pact sealed in obsidian and blood."},

    # --- consumables -------------------------------------------------------
    "small_potion": {"name": "Small Health Potion", "type": "consumable", "rarity": "common", "price": 30, "effect": {"hp": 60}, "description": "Restores 60 HP."},
    "large_potion": {"name": "Large Health Potion", "type": "consumable", "rarity": "uncommon", "price": 90, "effect": {"hp": 180}, "description": "Restores 180 HP."},
    "mana_potion": {"name": "Mana Potion", "type": "consumable", "rarity": "common", "price": 40, "effect": {"mana": 50}, "description": "Restores 50 mana."},
    "elixir": {"name": "Elixir of Life", "type": "consumable", "rarity": "rare", "price": 250, "effect": {"hp": 500, "mana": 100}, "description": "Fully restores a large amount of HP and mana."},
    "antidote": {"name": "Antidote", "type": "consumable", "rarity": "common", "price": 35, "effect": {"cleanse": True}, "description": "Cures poison and debuffs."},
    "bomb": {"name": "Fire Bomb", "type": "consumable", "rarity": "uncommon", "price": 80, "effect": {"damage": 120, "element": "fire"}, "description": "Deals 120 fire damage to a monster."},
    "xp_scroll": {"name": "Scroll of Wisdom", "type": "consumable", "rarity": "rare", "price": 300, "effect": {"xp": 250}, "description": "Grants 250 bonus XP when used."},
    "respec_stone": {"name": "Respec Stone", "type": "consumable", "rarity": "epic", "price": 500, "effect": {"respec": True}, "description": "Refunds all allocated stat points."},

    # --- materials ---------------------------------------------------------
    "iron_ore": {"name": "Iron Ore", "type": "material", "rarity": "common", "price": 15, "description": "Raw ore used in smithing."},
    "wood": {"name": "Ancient Wood", "type": "material", "rarity": "common", "price": 10, "description": "Hard wood for shafts and hilts."},
    "leather": {"name": "Cured Leather", "type": "material", "rarity": "common", "price": 12, "description": "Tanned hide, ready for crafting."},
    "crystal": {"name": "Mana Crystal", "type": "material", "rarity": "uncommon", "price": 45, "description": "Hums faintly with stored magic."},
    "herb": {"name": "Healing Herb", "type": "material", "rarity": "common", "price": 8, "description": "A fragrant herb with restorative properties."},
    "shadow_essence": {"name": "Shadow Essence", "type": "material", "rarity": "rare", "price": 90, "description": "Bottled darkness that moves on its own."},
    "holy_relic": {"name": "Holy Relic", "type": "material", "rarity": "rare", "price": 100, "description": "A fragment of consecrated silver."},
    "dragon_scale_material": {"name": "Dragon Scale", "type": "material", "rarity": "epic", "price": 220, "description": "Nearly indestructible scale."},
    "void_shard": {"name": "Void Shard", "type": "material", "rarity": "legendary", "price": 600, "description": "A splinter of reality from beyond the veil."},
}

# ---------------------------------------------------------------------------
# Crafting recipes
# ---------------------------------------------------------------------------

CRAFTING_RECIPES: dict[str, dict] = {
    "small_potion": {"materials": {"herb": 2}, "gold": 10, "level": 1},
    "large_potion": {"materials": {"herb": 4, "crystal": 1}, "gold": 35, "level": 5},
    "mana_potion": {"materials": {"crystal": 1, "herb": 1}, "gold": 20, "level": 3},
    "bomb": {"materials": {"iron_ore": 2, "crystal": 1}, "gold": 40, "level": 5},
    "iron_sword": {"materials": {"iron_ore": 4, "wood": 2, "leather": 1}, "gold": 70, "level": 5},
    "steel_blade": {"materials": {"iron_ore": 10, "leather": 4, "crystal": 2}, "gold": 180, "level": 12},
    "chainmail": {"materials": {"iron_ore": 8, "leather": 4}, "gold": 90, "level": 8},
    "plate_armor": {"materials": {"iron_ore": 16, "leather": 6, "crystal": 3}, "gold": 250, "level": 15},
    "iron_helm": {"materials": {"iron_ore": 5, "leather": 2}, "gold": 60, "level": 7},
    "swift_boots": {"materials": {"leather": 6, "crystal": 2}, "gold": 120, "level": 10},
    "flame_sword": {"materials": {"iron_ore": 18, "crystal": 6, "shadow_essence": 2}, "gold": 600, "level": 20},
    "frost_axe": {"materials": {"iron_ore": 18, "crystal": 8, "void_shard": 1}, "gold": 650, "level": 22},
    "arcane_staff": {"materials": {"wood": 10, "crystal": 10, "void_shard": 1}, "gold": 700, "level": 22},
    "holy_hammer": {"materials": {"iron_ore": 15, "holy_relic": 3, "crystal": 5}, "gold": 700, "level": 22},
    "dragon_scale": {"materials": {"dragon_scale_material": 6, "leather": 10, "void_shard": 2}, "gold": 1500, "level": 30},
    "dragon_greatsword": {"materials": {"dragon_scale_material": 6, "iron_ore": 25, "void_shard": 3}, "gold": 1800, "level": 30},
}

# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

SKILLS: dict[str, dict] = {
    "power_strike": {"name": "Power Strike", "type": "damage", "element": "physical", "power": 1.55, "mana": 10, "cooldown": 2, "description": "A heavy blow dealing 155% weapon damage."},
    "shield_bash": {"name": "Shield Bash", "type": "damage", "element": "physical", "power": 1.20, "mana": 12, "cooldown": 3, "stun": 1, "description": "Deals 120% damage and stuns for a turn."},
    "battle_cry": {"name": "Battle Cry", "type": "buff", "element": "physical", "power": 0.0, "mana": 15, "cooldown": 4, "buff": {"attack": 0.25, "turns": 3}, "description": "Raises attack by 25% for 3 turns."},
    "fireball": {"name": "Fireball", "type": "damage", "element": "fire", "power": 1.75, "mana": 18, "cooldown": 2, "description": "Hurls a blazing sphere for 175% damage."},
    "ice_lance": {"name": "Ice Lance", "type": "damage", "element": "ice", "power": 1.60, "mana": 16, "cooldown": 2, "slow": 1, "description": "Deals 160% damage and slows the enemy."},
    "arcane_nova": {"name": "Arcane Nova", "type": "damage", "element": "arcane", "power": 2.20, "mana": 30, "cooldown": 4, "description": "Unleashes a nova for 220% damage."},
    "backstab": {"name": "Backstab", "type": "damage", "element": "physical", "power": 1.90, "mana": 14, "cooldown": 3, "crit_bonus": 0.25, "description": "190% damage with +25% crit chance."},
    "poison_blade": {"name": "Poison Blade", "type": "damage", "element": "poison", "power": 1.30, "mana": 12, "cooldown": 2, "dot": {"damage": 12, "turns": 2}, "description": "Poisons the target for 2 turns."},
    "smoke_bomb": {"name": "Smoke Bomb", "type": "buff", "element": "shadow", "power": 0.0, "mana": 10, "cooldown": 4, "buff": {"speed": 0.30, "turns": 2}, "description": "Raises speed by 30% for 2 turns."},
    "snipe": {"name": "Snipe", "type": "damage", "element": "physical", "power": 2.00, "mana": 18, "cooldown": 3, "description": "A precise shot for 200% damage."},
    "volley": {"name": "Arrow Volley", "type": "damage", "element": "physical", "power": 1.40, "mana": 20, "cooldown": 3, "hits": 2, "description": "Fires two arrows, each for 140% damage."},
    "hunters_mark": {"name": "Hunter's Mark", "type": "buff", "element": "physical", "power": 0.0, "mana": 12, "cooldown": 4, "buff": {"crit": 0.20, "turns": 3}, "description": "Adds 20% critical chance for 3 turns."},
    "divine_smite": {"name": "Divine Smite", "type": "damage", "element": "holy", "power": 1.80, "mana": 18, "cooldown": 2, "description": "Calls down holy wrath for 180% damage."},
    "lay_on_hands": {"name": "Lay on Hands", "type": "heal", "element": "holy", "power": 0.0, "mana": 25, "cooldown": 3, "heal_pct": 0.35, "description": "Heals 35% of maximum HP."},
    "holy_shield": {"name": "Holy Shield", "type": "buff", "element": "holy", "power": 0.0, "mana": 20, "cooldown": 4, "buff": {"defense": 0.35, "turns": 3}, "description": "Raises defense by 35% for 3 turns."},
    "shadow_bolt": {"name": "Shadow Bolt", "type": "damage", "element": "shadow", "power": 1.70, "mana": 15, "cooldown": 2, "description": "Fires a bolt of darkness for 170% damage."},
    "life_drain": {"name": "Life Drain", "type": "damage", "element": "shadow", "power": 1.30, "mana": 20, "cooldown": 3, "lifesteal": 0.5, "description": "Deals 130% damage and heals for half of it."},
    "curse_of_weakness": {"name": "Curse of Weakness", "type": "debuff", "element": "shadow", "power": 0.0, "mana": 16, "cooldown": 4, "debuff": {"attack": 0.25, "turns": 3}, "description": "Lowers enemy attack by 25% for 3 turns."},
    "reckless_swing": {"name": "Reckless Swing", "type": "damage", "element": "physical", "power": 2.10, "mana": 12, "cooldown": 2, "self_damage_pct": 0.08, "description": "Massive 210% damage, costs 8% HP."},
    "blood_rage": {"name": "Blood Rage", "type": "buff", "element": "fire", "power": 0.0, "mana": 15, "cooldown": 4, "buff": {"attack": 0.40, "defense": -0.15, "turns": 3}, "description": "Raises attack 40% but lowers defense 15%."},
    "whirlwind": {"name": "Whirlwind", "type": "damage", "element": "physical", "power": 1.50, "mana": 22, "cooldown": 3, "hits": 2, "description": "Spins for two hits of 150% damage."},
    "flurry": {"name": "Flurry of Blows", "type": "damage", "element": "physical", "power": 1.10, "mana": 15, "cooldown": 2, "hits": 3, "description": "Strikes three times for 110% damage each."},
    "chi_strike": {"name": "Chi Strike", "type": "damage", "element": "lightning", "power": 1.85, "mana": 18, "cooldown": 3, "description": "Channels inner energy for 185% damage."},
    "inner_peace": {"name": "Inner Peace", "type": "heal", "element": "lightning", "power": 0.0, "mana": 20, "cooldown": 3, "heal_pct": 0.25, "description": "Restores 25% of maximum HP."},
    "meteor": {"name": "Meteor", "type": "damage", "element": "fire", "power": 2.70, "mana": 40, "cooldown": 5, "description": "Calls a meteor for 270% damage."},
    "frost_nova": {"name": "Frost Nova", "type": "damage", "element": "ice", "power": 1.50, "mana": 24, "cooldown": 3, "slow": 1, "description": "Freezes enemies for 150% damage."},
}

# ---------------------------------------------------------------------------
# Monsters
# ---------------------------------------------------------------------------

MONSTERS: dict[str, dict] = {
    "forest_slime": {"name": "Forest Slime", "emoji": "🟢", "level": 1, "hp": 45, "attack": 8, "defense": 2, "speed": 4, "xp": 25, "gold": 18, "element": "poison", "loot": ["herb", "small_potion"], "description": "A wobbly green blob that smells of moss."},
    "wild_wolf": {"name": "Wild Wolf", "emoji": "🐺", "level": 2, "hp": 65, "attack": 12, "defense": 3, "speed": 12, "xp": 38, "gold": 24, "element": "physical", "loot": ["leather", "wood"], "description": "A hungry wolf with gleaming eyes."},
    "goblin_scout": {"name": "Goblin Scout", "emoji": "👺", "level": 3, "hp": 90, "attack": 16, "defense": 5, "speed": 10, "xp": 55, "gold": 40, "element": "physical", "loot": ["iron_ore", "copper_ring", "small_potion"], "description": "Sneaky, greedy and armed with a rusty blade."},
    "cave_bat": {"name": "Cave Bat", "emoji": "🦇", "level": 4, "hp": 80, "attack": 20, "defense": 4, "speed": 20, "xp": 65, "gold": 35, "element": "shadow", "loot": ["leather", "shadow_essence"], "description": "A shrieking blur of wings and fangs."},
    "skeleton_warrior": {"name": "Skeleton Warrior", "emoji": "💀", "level": 5, "hp": 150, "attack": 26, "defense": 12, "speed": 8, "xp": 95, "gold": 60, "element": "shadow", "loot": ["iron_ore", "bone_amulet", "iron_sword"], "description": "Rattling bones held together by spite."},
    "orc_brute": {"name": "Orc Brute", "emoji": "👹", "level": 7, "hp": 240, "attack": 38, "defense": 15, "speed": 7, "xp": 150, "gold": 95, "element": "physical", "loot": ["iron_ore", "chainmail", "large_potion"], "description": "A mountain of muscle and bad temper."},
    "fire_imp": {"name": "Fire Imp", "emoji": "👿", "level": 9, "hp": 220, "attack": 48, "defense": 12, "speed": 18, "xp": 190, "gold": 120, "element": "fire", "loot": ["crystal", "ruby_ring", "bomb"], "description": "A cackling demon wreathed in flame."},
    "frost_wraith": {"name": "Frost Wraith", "emoji": "👻", "level": 11, "hp": 300, "attack": 55, "defense": 18, "speed": 16, "xp": 240, "gold": 150, "element": "ice", "loot": ["crystal", "sapphire_ring", "frost_axe"], "description": "A spectre of frozen sorrow."},
    "venom_spider": {"name": "Venom Spider", "emoji": "🕷️", "level": 13, "hp": 360, "attack": 68, "defense": 20, "speed": 22, "xp": 300, "gold": 180, "element": "poison", "loot": ["shadow_essence", "antidote", "shadow_dagger"], "description": "Its bite melts armour and courage alike."},
    "dark_knight": {"name": "Dark Knight", "emoji": "🖤", "level": 16, "hp": 520, "attack": 90, "defense": 38, "speed": 14, "xp": 420, "gold": 260, "element": "shadow", "loot": ["void_shard", "plate_armor", "shadow_cloak"], "description": "A fallen champion in blackened plate."},
    "ancient_golem": {"name": "Ancient Golem", "emoji": "🗿", "level": 20, "hp": 900, "attack": 110, "defense": 60, "speed": 6, "xp": 650, "gold": 400, "element": "physical", "loot": ["crystal", "iron_ore", "dragon_scale_material"], "description": "Stone given purpose by forgotten magic."},
    "shadow_stalker": {"name": "Shadow Stalker", "emoji": "🌑", "level": 24, "hp": 800, "attack": 140, "defense": 40, "speed": 30, "xp": 800, "gold": 500, "element": "shadow", "loot": ["void_shard", "shadow_essence", "void_katana"], "description": "It is behind you. It has always been behind you."},
}

# ---------------------------------------------------------------------------
# World bosses
# ---------------------------------------------------------------------------

BOSSES: dict[str, dict] = {
    "goblin_king": {"name": "Goblin King", "emoji": "👑", "level": 8, "hp": 2500, "attack": 50, "defense": 20, "speed": 10, "xp": 500, "gold": 400, "gems": 2, "element": "physical", "loot": ["iron_sword", "chainmail", "large_potion"], "description": "Ruler of a thousand squabbling goblins.", "min_level": 3},
    "frost_dragon": {"name": "Frost Dragon", "emoji": "🐲", "level": 18, "hp": 9000, "attack": 130, "defense": 52, "speed": 18, "xp": 1800, "gold": 1200, "gems": 5, "element": "ice", "loot": ["frost_axe", "dragon_scale_material", "sapphire_ring"], "description": "An ancient wyrm of the frozen north.", "min_level": 10},
    "demon_lord": {"name": "Demon Lord", "emoji": "😈", "level": 25, "hp": 16000, "attack": 190, "defense": 70, "speed": 22, "xp": 3200, "gold": 2200, "gems": 8, "element": "fire", "loot": ["flame_sword", "demon_amulet", "dragon_scale_material"], "description": "A tyrant of the burning abyss.", "min_level": 18},
    "lich_king": {"name": "Lich King", "emoji": "☠️", "level": 32, "hp": 26000, "attack": 260, "defense": 90, "speed": 25, "xp": 5000, "gold": 3600, "gems": 12, "element": "shadow", "loot": ["bone_staff", "shadow_cloak", "void_shard"], "description": "Death itself wears a crown.", "min_level": 25},
    "void_titan": {"name": "Void Titan", "emoji": "🌌", "level": 45, "hp": 48000, "attack": 400, "defense": 140, "speed": 30, "xp": 9000, "gold": 6000, "gems": 20, "element": "arcane", "loot": ["void_katana", "dragon_greatsword", "void_shard"], "description": "A colossus from beyond the edge of reality.", "min_level": 35},
}

# ---------------------------------------------------------------------------
# Quests
# ---------------------------------------------------------------------------

QUESTS: dict[str, dict] = {
    "slime_cleanup": {
        "name": "Slime Cleanup",
        "emoji": "🧹",
        "min_level": 1,
        "description": "The village well is clogged with slimes.",
        "stages": [
            {"objective": "kill", "target": "forest_slime", "count": 3, "text": "Defeat 3 Forest Slimes", "reward": {"gold": 60, "xp": 60}},
            {"objective": "kill", "target": "wild_wolf", "count": 2, "text": "Defeat 2 Wild Wolves", "reward": {"gold": 100, "xp": 100, "items": {"small_potion": 2}}},
        ],
    },
    "goblin_trouble": {
        "name": "Goblin Trouble",
        "emoji": "⚔️",
        "min_level": 3,
        "description": "Goblin scouts raid the trade roads.",
        "stages": [
            {"objective": "kill", "target": "goblin_scout", "count": 4, "text": "Defeat 4 Goblin Scouts", "reward": {"gold": 150, "xp": 150}},
            {"objective": "kill", "target": "cave_bat", "count": 3, "text": "Clear 3 Cave Bats", "reward": {"gold": 180, "xp": 180, "items": {"iron_ore": 3}}},
        ],
    },
    "bone_to_pick": {
        "name": "Bone to Pick",
        "emoji": "🦴",
        "min_level": 5,
        "description": "The old graveyard stirs with restless dead.",
        "stages": [
            {"objective": "kill", "target": "skeleton_warrior", "count": 5, "text": "Put 5 Skeleton Warriors to rest", "reward": {"gold": 250, "xp": 250}},
            {"objective": "boss", "target": "goblin_king", "count": 1, "text": "Defeat the Goblin King", "reward": {"gold": 400, "xp": 400, "gems": 1}},
        ],
    },
    "pvp_glory": {
        "name": "Glory of the Arena",
        "emoji": "🏟️",
        "min_level": 5,
        "description": "Prove your worth against other heroes.",
        "stages": [
            {"objective": "duel", "target": "any", "count": 3, "text": "Win 3 PvP duels", "reward": {"gold": 300, "xp": 300, "gems": 1}},
        ],
    },
    "frost_bite": {
        "name": "The Frost Bite",
        "emoji": "❄️",
        "min_level": 10,
        "description": "A chill wind blows from the northern peaks.",
        "stages": [
            {"objective": "kill", "target": "fire_imp", "count": 4, "text": "Defeat 4 Fire Imps", "reward": {"gold": 400, "xp": 400}},
            {"objective": "kill", "target": "frost_wraith", "count": 3, "text": "Defeat 3 Frost Wraiths", "reward": {"gold": 500, "xp": 500, "items": {"sapphire_ring": 1}}},
        ],
    },
    "dragon_slayer": {
        "name": "Dragon Slayer",
        "emoji": "🐉",
        "min_level": 15,
        "description": "The Frost Dragon terrorizes the north.",
        "stages": [
            {"objective": "kill", "target": "dark_knight", "count": 3, "text": "Defeat 3 Dark Knights", "reward": {"gold": 800, "xp": 800}},
            {"objective": "boss", "target": "frost_dragon", "count": 1, "text": "Slay the Frost Dragon", "reward": {"gold": 1500, "xp": 1500, "gems": 3, "items": {"dragon_scale_material": 2}}},
        ],
    },
    "void_hunter": {
        "name": "Void Hunter",
        "emoji": "🌌",
        "min_level": 25,
        "description": "Reality frays at the edges of the world.",
        "stages": [
            {"objective": "kill", "target": "shadow_stalker", "count": 5, "text": "Defeat 5 Shadow Stalkers", "reward": {"gold": 1500, "xp": 1500}},
            {"objective": "boss", "target": "void_titan", "count": 1, "text": "Defeat the Void Titan", "reward": {"gold": 4000, "xp": 4000, "gems": 10, "items": {"void_shard": 2}}},
        ],
    },
}

# Convenience indexes -------------------------------------------------------

RARITY_EMOJI = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟠",
}

RARITY_ORDER = {"common": 0, "uncommon": 1, "rare": 2, "epic": 3, "legendary": 4}

SLOTS = ("weapon", "armor", "helmet", "boots", "ring", "amulet")

EQUIPMENT_SLOT_NAMES = {
    "weapon": "Weapon",
    "armor": "Armor",
    "helmet": "Helmet",
    "boots": "Boots",
    "ring": "Ring",
    "amulet": "Amulet",
}

CRAFTABLE_ITEMS = tuple(CRAFTING_RECIPES.keys())
SHOP_ITEMS = tuple(k for k, v in ITEMS.items() if v.get("price", 0) > 0 and v.get("type") != "material")
