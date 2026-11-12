"""Turn-based combat engine: PvE hunts, world-boss raids and PvP duels.

The engine is database-free; handlers translate player rows into
:class:`Fighter` objects, pass potion amounts in, and persist rewards.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from catalog import BOSSES, MONSTERS, SKILLS
from game_data import (
    CRIT_MULTIPLIER,
    FLEE_BASE_CHANCE,
    MAX_COMBAT_ROUNDS,
    derive_stats,
    element_multiplier,
    player_combat_skills,
    roll_loot,
)


@dataclass
class Fighter:
    name: str
    level: int
    element: str
    max_hp: int
    hp: int
    max_mana: int
    mana: int
    attack: int
    defense: int
    speed: int
    crit_chance: float
    uid: int | None = None
    skills: list[str] = field(default_factory=list)
    lifesteal: float = 0.0
    healing_bonus: float = 0.0
    resist: dict[str, float] = field(default_factory=dict)
    immune: tuple[str, ...] = ()
    buffs: dict[str, dict] = field(default_factory=dict)
    cooldowns: dict[str, int] = field(default_factory=dict)
    dot: dict | None = None
    stunned: bool = False

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def hp_pct(self) -> float:
        return max(0.0, min(1.0, self.hp / self.max_hp)) if self.max_hp else 0.0

    @property
    def mana_pct(self) -> float:
        return max(0.0, min(1.0, self.mana / self.max_mana)) if self.max_mana else 0.0

    def effective(self, stat: str) -> float:
        base = float(getattr(self, stat))
        modifier = sum(b.get(stat, 0.0) for b in self.buffs.values())
        return max(0.0, base * (1.0 + modifier))

    @property
    def effective_attack(self) -> float:
        return self.effective("attack")

    @property
    def effective_defense(self) -> float:
        return self.effective("defense")

    @property
    def effective_speed(self) -> float:
        return self.effective("speed")

    @property
    def effective_crit(self) -> float:
        bonus = sum(b.get("crit", 0.0) for b in self.buffs.values())
        return max(0.0, min(0.90, self.crit_chance + bonus))

    def take_damage(self, amount: int, element: str = "physical") -> int:
        amount = max(1, int(amount))
        if element in self.immune:
            return 0
        resist = self.resist.get(element, 0.0)
        if resist:
            amount = max(1, int(amount * (1 - resist)))
        self.hp = max(0, self.hp - amount)
        return amount

    def heal(self, amount: int) -> int:
        amount = max(0, int(amount * (1 + self.healing_bonus)))
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before

    def restore_mana(self, amount: int) -> int:
        before = self.mana
        self.mana = min(self.max_mana, self.mana + max(0, int(amount)))
        return self.mana - before

    def tick(self) -> None:
        for skill_id in list(self.cooldowns):
            self.cooldowns[skill_id] -= 1
            if self.cooldowns[skill_id] <= 0:
                del self.cooldowns[skill_id]
        for key in list(self.buffs):
            self.buffs[key]["turns"] -= 1
            if self.buffs[key]["turns"] <= 0:
                del self.buffs[key]

    def apply_dot(self) -> tuple[str, int] | None:
        if not self.dot:
            return None
        data = self.dot
        damage = self.take_damage(int(data["damage"]), data.get("element", "poison"))
        self.dot["turns"] -= 1
        if self.dot["turns"] <= 0:
            self.dot = None
        return ("dot", damage) if damage else None

    def skill_ready(self, skill_id: str) -> tuple[bool, str]:
        skill = SKILLS.get(skill_id)
        if not skill:
            return False, "Unknown skill."
        if skill_id not in self.skills:
            return False, "You have not learned that skill."
        if self.cooldowns.get(skill_id, 0) > 0:
            return False, f"{skill['name']} is on cooldown ({self.cooldowns[skill_id]})."
        if self.mana < int(skill.get("mana", 0)):
            return False, f"Not enough mana for {skill['name']}."
        return True, ""


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def fighter_from_player(player: dict, name: str | None = None) -> Fighter:
    derived = player.get("derived") or derive_stats(player, player.get("equipment"))
    return Fighter(
        uid=int(player["user_id"]),
        name=name or player.get("display_name") or "Hero",
        level=int(player.get("level") or 1),
        element=derived.get("element", "physical"),
        max_hp=derived["max_hp"],
        hp=min(derived["max_hp"], max(1, int(player.get("hp") or derived["max_hp"]))),
        max_mana=derived["max_mana"],
        mana=min(derived["max_mana"], max(0, int(player.get("mana") or derived["max_mana"]))),
        attack=derived["attack"],
        defense=derived["defense"],
        speed=derived["speed"],
        crit_chance=derived["crit_chance"],
        skills=player_combat_skills(player),
        lifesteal=derived.get("lifesteal", 0.0),
        healing_bonus=derived.get("healing_bonus", 0.0),
        resist=dict(derived.get("resist") or {}),
        immune=tuple(derived.get("immune") or ()),
    )


def fighter_from_monster(monster_id: str) -> Fighter:
    monster = MONSTERS[monster_id]
    return Fighter(
        name=f"{monster['emoji']} {monster['name']}",
        level=int(monster["level"]),
        element=monster.get("element", "physical"),
        max_hp=int(monster["hp"]),
        hp=int(monster["hp"]),
        max_mana=0,
        mana=0,
        attack=int(monster["attack"]),
        defense=int(monster["defense"]),
        speed=int(monster["speed"]),
        crit_chance=0.05 + int(monster["level"]) * 0.002,
    )


def fighter_from_boss(boss_id: str) -> Fighter:
    boss = BOSSES[boss_id]
    return Fighter(
        name=f"{boss['emoji']} {boss['name']}",
        level=int(boss["level"]),
        element=boss.get("element", "physical"),
        max_hp=int(boss["hp"]),
        hp=int(boss["hp"]),
        max_mana=0,
        mana=0,
        attack=int(boss["attack"]),
        defense=int(boss["defense"]),
        speed=int(boss["speed"]),
        crit_chance=0.08,
    )


# ---------------------------------------------------------------------------
# Damage
# ---------------------------------------------------------------------------

def calculate_damage(
    attacker: Fighter, defender: Fighter, power: float = 1.0,
    element: str | None = None, rng: random.Random | None = None,
    crit_bonus: float = 0.0,
) -> dict:
    rng = rng or random.Random()
    element = element or attacker.element or "physical"
    multiplier = element_multiplier(element, defender.element)

    raw = attacker.effective_attack * float(power) - defender.effective_defense * 0.5
    raw = max(1.0, raw)
    variance = rng.uniform(0.90, 1.10)
    is_crit = rng.random() < min(0.90, attacker.effective_crit + float(crit_bonus))
    damage = raw * multiplier * variance
    if is_crit:
        damage *= CRIT_MULTIPLIER
    damage = max(1, int(damage))

    dealt = defender.take_damage(damage, element)
    return {
        "damage": dealt,
        "crit": is_crit,
        "multiplier": multiplier,
        "element": element,
    }


def _element_note(multiplier: float) -> str:
    if multiplier > 1.0:
        return " (super effective!)"
    if multiplier < 1.0:
        return " (resisted)"
    return ""


# ---------------------------------------------------------------------------
# PvE battle
# ---------------------------------------------------------------------------

class PvEBattle:
    def __init__(
        self, monster_id: str, player_fighter: Fighter,
        rng: random.Random | None = None,
    ) -> None:
        self.monster_id = monster_id
        self.monster_data = MONSTERS[monster_id]
        self.player = player_fighter
        self.monster = fighter_from_monster(monster_id)
        self.rng = rng or random.Random()
        self.round = 1
        self.finished = False
        self.result: str | None = None  # win / lose / flee
        self.events: list[str] = []
        self.rewards: dict | None = None

    # -- helpers -----------------------------------------------------------
    def _log(self, text: str) -> None:
        self.events.append(text)

    def _finish(self, result: str) -> None:
        self.finished = True
        self.result = result
        if result == "win":
            drops = roll_loot(self.monster_data.get("loot"), self.rng)
            self.rewards = {
                "xp": int(self.monster_data["xp"]),
                "gold": int(self.monster_data["gold"]),
                "items": drops,
            }

    def _monster_turn(self) -> None:
        monster = self.monster
        if not monster.alive or self.finished:
            return
        monster.tick()
        dot = monster.apply_dot()
        if dot:
            self._log(f"{monster.name} suffers {dot[1]} poison damage.")
        if monster.stunned:
            monster.stunned = False
            self._log(f"{monster.name} is stunned and cannot act.")
            return
        if not monster.alive:
            self._finish("win")
            return
        hit = calculate_damage(monster, self.player, 1.0, monster.element, self.rng)
        note = _element_note(hit["multiplier"])
        crit = " Critical hit!" if hit["crit"] else ""
        self._log(f"{monster.name} hits you for {hit['damage']}{note}.{crit}")
        if not self.player.alive:
            self._finish("lose")

    def _player_turn_done(self) -> None:
        self.player.tick()
        if self.player.dot:
            tick = self.player.apply_dot()
            if tick:
                self._log(f"You suffer {tick[1]} poison damage.")
            if not self.player.alive:
                self._finish("lose")
                return
        if self.finished:
            return
        self._monster_turn()
        if self.finished:
            return
        self.round += 1
        if self.round > MAX_COMBAT_ROUNDS:
            self._finish("lose")
            self._log("The battle drags on too long. You retreat exhausted.")

    # -- actions -----------------------------------------------------------
    def player_attack(self) -> list[str]:
        if self.finished:
            return ["The battle is already over."]
        self.events = []
        hit = calculate_damage(self.player, self.monster, 1.0, self.player.element, self.rng)
        crit = " Critical hit!" if hit["crit"] else ""
        note = _element_note(hit["multiplier"])
        self._log(f"You hit {self.monster.name} for {hit['damage']}{note}.{crit}")
        self._lifesteal(hit["damage"])
        if not self.monster.alive:
            self._finish("win")
        else:
            self._player_turn_done()
        return self.events

    def player_skill(self, skill_id: str) -> list[str]:
        if self.finished:
            return ["The battle is already over."]
        ready, reason = self.player.skill_ready(skill_id)
        if not ready:
            return [reason]
        skill = SKILLS[skill_id]
        self.events = []
        self.player.mana -= int(skill.get("mana", 0))
        self.player.cooldowns[skill_id] = int(skill.get("cooldown", 1)) + 1
        self._log(f"✨ You use **{skill['name']}**!")

        skill_type = skill.get("type")
        if skill_type == "heal":
            healed = self.player.heal(int(self.player.max_hp * float(skill.get("heal_pct", 0.25))))
            self._log(f"You restore {healed} HP.")
        elif skill_type == "buff":
            self._apply_buff(self.player, skill.get("buff") or {})
            self._log("Your power surges.")
        elif skill_type == "debuff":
            self._apply_buff(self.monster, {k: -v if k != "turns" else v for k, v in (skill.get("debuff") or {}).items()})
            self._log(f"{self.monster.name} is weakened.")
        else:
            hits = max(1, int(skill.get("hits", 1)))
            total = 0
            for _ in range(hits):
                if not self.monster.alive:
                    break
                hit = calculate_damage(
                    self.player, self.monster, float(skill.get("power", 1.0)),
                    skill.get("element", self.player.element), self.rng,
                    float(skill.get("crit_bonus", 0.0)),
                )
                total += hit["damage"]
                crit = " Crit!" if hit["crit"] else ""
                note = _element_note(hit["multiplier"])
                self._log(f"Hit for {hit['damage']}{note}.{crit}")
                if skill.get("stun"):
                    self.monster.stunned = True
                if skill.get("dot") and self.monster.alive:
                    dot = skill["dot"]
                    self.monster.dot = {
                        "damage": int(dot["damage"]), "turns": int(dot["turns"]),
                        "element": skill.get("element", "poison"),
                    }
            self._log(f"Total damage: **{total}**.")
            if skill.get("lifesteal"):
                self._lifesteal(int(total * float(skill["lifesteal"])))
            if skill.get("self_damage_pct"):
                cost = max(1, int(self.player.max_hp * float(skill["self_damage_pct"])))
                self.player.take_damage(cost, "physical")
                self._log(f"Recoil costs you {cost} HP.")

        if not self.monster.alive:
            self._finish("win")
        elif not self.player.alive:
            self._finish("lose")
        else:
            self._player_turn_done()
        return self.events

    def player_heal(self, heal_amount: int) -> list[str]:
        if self.finished:
            return ["The battle is already over."]
        if heal_amount <= 0:
            return ["You have no healing potions!"]
        if self.player.hp >= self.player.max_hp:
            return ["You are already at full HP."]
        self.events = []
        healed = self.player.heal(heal_amount)
        self._log(f"🧪 You drink a potion and recover {healed} HP.")
        self._player_turn_done()
        return self.events

    def player_flee(self) -> list[str]:
        if self.finished:
            return ["The battle is already over."]
        self.events = []
        chance = FLEE_BASE_CHANCE + (self.player.effective_speed - self.monster.effective_speed) * 0.02
        chance = max(0.10, min(0.90, chance))
        if self.rng.random() < chance:
            self._finish("flee")
            self._log("You successfully flee from battle.")
        else:
            self._log("You fail to escape!")
            self._player_turn_done()
        return self.events

    def _lifesteal(self, damage: int) -> None:
        amount = self.player.lifesteal
        if amount and damage > 0:
            healed = self.player.heal(int(damage * amount))
            if healed:
                self._log(f"You drain {healed} HP.")

    @staticmethod
    def _apply_buff(target: Fighter, buff: dict) -> None:
        turns = int(buff.get("turns", 2))
        for key, value in buff.items():
            if key == "turns":
                continue
            target.buffs[key] = {"value": value, key: value, "turns": turns}


# ---------------------------------------------------------------------------
# World boss raid
# ---------------------------------------------------------------------------

class WorldBossRaid:
    def __init__(self, boss_id: str, rng: random.Random | None = None) -> None:
        self.boss_id = boss_id
        self.boss_data = BOSSES[boss_id]
        self.boss = fighter_from_boss(boss_id)
        self.rng = rng or random.Random()
        self.participants: dict[int, Fighter] = {}
        self.contributions: dict[int, int] = {}
        self.finished = False
        self.winner = False
        self.rewards: dict[int, dict] = {}
        self.round = 0
        self.log: list[str] = []

    def join(self, player: dict) -> tuple[bool, str]:
        if self.finished:
            return False, "This raid is already over."
        uid = int(player["user_id"])
        if int(player.get("level") or 1) < int(self.boss_data.get("min_level", 1)):
            return False, f"You need level {self.boss_data['min_level']} to join."
        if uid not in self.participants:
            self.participants[uid] = fighter_from_player(player)
            self.contributions[uid] = 0
            return True, f"You joined the raid against {self.boss.name}!"
        return True, "You are already in this raid."

    def attack(self, player: dict, skill_id: str | None = None,
               heal_amount: int = 0) -> list[str]:
        if self.finished:
            return ["The raid is already over."]
        uid = int(player["user_id"])
        if uid not in self.participants:
            ok, reason = self.join(player)
            if not ok:
                return [reason]
        fighter = self.participants[uid]
        if not fighter.alive:
            return ["You are downed and cannot act."]

        events: list[str] = []
        self.round += 1
        boss = self.boss

        if skill_id and skill_id != "heal":
            ready, reason = fighter.skill_ready(skill_id)
            if not ready:
                return [reason]
            skill = SKILLS[skill_id]
            fighter.mana -= int(skill.get("mana", 0))
            fighter.cooldowns[skill_id] = int(skill.get("cooldown", 1)) + 1
            events.append(f"✨ {fighter.name} uses {skill['name']}!")
            if skill.get("type") == "heal":
                events.append(f"{fighter.name} heals {fighter.heal(int(fighter.max_hp * skill.get('heal_pct', 0.25)))} HP.")
            elif skill.get("type") == "buff":
                PvEBattle._apply_buff(fighter, skill.get("buff") or {})
            else:
                hits = max(1, int(skill.get("hits", 1)))
                total = 0
                for _ in range(hits):
                    hit = calculate_damage(
                        fighter, boss, float(skill.get("power", 1.0)),
                        skill.get("element", fighter.element), self.rng,
                        float(skill.get("crit_bonus", 0.0)),
                    )
                    total += hit["damage"]
                self.contributions[uid] += total
                events.append(f"{fighter.name} deals {total} skill damage.")
        elif heal_amount > 0:
            healed = fighter.heal(heal_amount)
            events.append(f"{fighter.name} recovers {healed} HP.")
        else:
            hit = calculate_damage(fighter, boss, 1.0, fighter.element, self.rng)
            self.contributions[uid] += hit["damage"]
            events.append(f"{fighter.name} hits for {hit['damage']} damage.")

        if not boss.alive:
            self.finished = True
            self.winner = True
            self._distribute()
            events.append(f"🏆 {boss.name} has been defeated!")
            return events

        if boss.stunned:
            boss.stunned = False
            events.append(f"{boss.name} is stunned.")
        else:
            hit = calculate_damage(boss, fighter, 1.0, boss.element, self.rng)
            events.append(f"{boss.name} retaliates for {hit['damage']} damage to {fighter.name}.")
            if not fighter.alive:
                events.append(f"💀 {fighter.name} has fallen.")

        fighter.tick()
        if self.round >= MAX_COMBAT_ROUNDS * 6:
            self.finished = True
            self.winner = False
            events.append("The world boss retreats into the void. Raid failed.")
        return events

    def _distribute(self) -> None:
        total = sum(self.contributions.values()) or 1
        ranked = sorted(self.contributions.items(), key=lambda kv: kv[1], reverse=True)
        for rank, (uid, damage) in enumerate(ranked):
            share = damage / total
            gold = int(self.boss_data["gold"] * (0.25 + 0.75 * share))
            xp = int(self.boss_data["xp"] * (0.25 + 0.75 * share))
            gems = int(self.boss_data.get("gems", 0)) if rank == 0 else (1 if rank == 1 else 0)
            items: list[str] = []
            if rank == 0:
                items = roll_loot(self.boss_data.get("loot"), self.rng, drop_chance=0.9)
            elif rank < 3:
                items = roll_loot(self.boss_data.get("loot"), self.rng, drop_chance=0.4)
            self.rewards[uid] = {
                "gold": gold, "xp": xp, "gems": gems,
                "items": items, "damage": damage,
                "share": share, "rank": rank + 1,
            }

    def leaderboard(self, limit: int = 5) -> list[tuple[int, int]]:
        return sorted(self.contributions.items(), key=lambda kv: kv[1], reverse=True)[:limit]

    def total_contribution(self) -> int:
        return sum(self.contributions.values())


# ---------------------------------------------------------------------------
# PvP duel
# ---------------------------------------------------------------------------

class PvPBattle:
    def __init__(self, fighter_a: Fighter, fighter_b: Fighter,
                 rng: random.Random | None = None) -> None:
        if fighter_a.uid is None or fighter_b.uid is None:
            raise ValueError("PvP fighters need user ids.")
        self.fighters: dict[int, Fighter] = {
            int(fighter_a.uid): fighter_a,
            int(fighter_b.uid): fighter_b,
        }
        self.pending: dict[int, dict] = {}
        self.rng = rng or random.Random()
        self.round = 1
        self.finished = False
        self.winner: int | None = None
        self.result: str | None = None  # victory / draw / flee
        self.events: list[str] = []
        self.log: list[str] = []

    def opponent_of(self, uid: int) -> Fighter:
        for other_id, fighter in self.fighters.items():
            if other_id != uid:
                return fighter
        raise KeyError(uid)

    def fighter(self, uid: int) -> Fighter:
        return self.fighters[int(uid)]

    def submit(self, uid: int, action: str, skill_id: str | None = None,
               heal_amount: int = 0) -> dict:
        uid = int(uid)
        if self.finished:
            return {"ok": False, "waiting": False, "events": ["The duel is over."], "finished": True}
        fighter = self.fighters.get(uid)
        if fighter is None:
            return {"ok": False, "waiting": False, "events": ["You are not in this duel."], "finished": False}
        if not fighter.alive:
            return {"ok": False, "waiting": False, "events": ["You have fallen."], "finished": self.finished}
        if uid in self.pending:
            return {"ok": False, "waiting": True, "events": ["Waiting for your opponent..."], "finished": False}

        if action == "flee":
            self.finished = True
            self.result = "flee"
            self.winner = int(self.opponent_of(uid).uid)
            return {
                "ok": True, "waiting": False,
                "events": [f"🏃 {fighter.name} flees the duel!"],
                "finished": True, "winner": self.winner,
            }

        if action == "skill":
            ready, reason = fighter.skill_ready(skill_id or "")
            if not ready:
                return {"ok": False, "waiting": False, "events": [reason], "finished": False}

        self.pending[uid] = {"action": action, "skill_id": skill_id, "heal_amount": heal_amount}
        if len(self.pending) < len(self.fighters):
            return {"ok": True, "waiting": True, "events": ["Action locked. Waiting for your opponent..."], "finished": False}
        return self._resolve_round()

    def _resolve_round(self) -> dict:
        events: list[str] = []
        order = sorted(
            self.fighters.values(), key=lambda f: f.effective_speed, reverse=True
        )
        # Damage-over-time at the start of the round.
        for fighter in order:
            if fighter.alive and fighter.dot:
                tick = fighter.apply_dot()
                if tick:
                    events.append(f"☠️ {fighter.name} suffers {tick[1]} poison damage.")
        if not any(f.alive for f in order):
            self.finished = True
            self.result = "draw"
            self.winner = None
            self.pending.clear()
            events.append("Both fighters collapse. The duel is a draw.")
            self.events.extend(events)
            return {"ok": True, "waiting": False, "events": events,
                    "finished": True, "winner": None, "result": "draw"}
        for fighter in order:
            if not fighter.alive or self.finished:
                continue
            action = self.pending.get(int(fighter.uid))
            if not action:
                continue
            target = self.opponent_of(int(fighter.uid))
            kind = action["action"]
            if kind == "heal":
                if action.get("heal_amount", 0) <= 0:
                    events.append(f"{fighter.name} has no potions and hesitates.")
                else:
                    healed = fighter.heal(action["heal_amount"])
                    events.append(f"🧪 {fighter.name} heals {healed} HP.")
            elif kind == "skill":
                skill = SKILLS[action["skill_id"]]
                fighter.mana -= int(skill.get("mana", 0))
                fighter.cooldowns[action["skill_id"]] = int(skill.get("cooldown", 1)) + 1
                events.append(f"✨ {fighter.name} uses {skill['name']}!")
                if skill.get("type") == "heal":
                    events.append(f"{fighter.name} heals {fighter.heal(int(fighter.max_hp * skill.get('heal_pct', 0.25)))} HP.")
                elif skill.get("type") == "buff":
                    PvEBattle._apply_buff(fighter, skill.get("buff") or {})
                elif skill.get("type") == "debuff":
                    PvEBattle._apply_buff(target, {k: -v if k != "turns" else v for k, v in (skill.get("debuff") or {}).items()})
                else:
                    hits = max(1, int(skill.get("hits", 1)))
                    total = 0
                    for _ in range(hits):
                        if not target.alive:
                            break
                        hit = calculate_damage(
                            fighter, target, float(skill.get("power", 1.0)),
                            skill.get("element", fighter.element), self.rng,
                            float(skill.get("crit_bonus", 0.0)),
                        )
                        total += hit["damage"]
                        crit = " Crit!" if hit["crit"] else ""
                        events.append(f"  {hit['damage']} damage{crit}")
                    events.append(f"Total: {total} damage.")
            else:
                hit = calculate_damage(fighter, target, 1.0, fighter.element, self.rng)
                crit = " Critical hit!" if hit["crit"] else ""
                events.append(f"⚔️ {fighter.name} hits {target.name} for {hit['damage']}{crit}")
            if not target.alive:
                self.finished = True
                self.result = "victory"
                self.winner = int(fighter.uid)
                events.append(f"🏆 {fighter.name} wins the duel!")
                break

        for fighter in order:
            if fighter.alive:
                fighter.tick()
        self.pending.clear()
        self.round += 1
        if not self.finished and self.round > MAX_COMBAT_ROUNDS:
            self.finished = True
            self.result = "draw"
            self.winner = None
            events.append("The duel ends in a draw after too many rounds.")
        self.events.extend(events)
        return {
            "ok": True, "waiting": False, "events": events,
            "finished": self.finished, "winner": self.winner, "result": self.result,
        }
