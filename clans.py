"""Clan system: creation, membership, bank, upgrades, wars and rankings."""

from __future__ import annotations

import random

from database import Database
from game_data import (
    CLAN_CREATE_COST,
    CLAN_MIN_LEVEL,
    CLAN_WAR_COST,
    clan_member_limit,
    clan_power,
    clan_upgrade_cost,
    validate_clan_name,
    validate_clan_tag,
)

MANAGE_ROLES = ("leader", "officer")


async def create_clan(
    db: Database, player: dict, name: str, tag: str, description: str = "",
) -> tuple[bool, str, dict | None]:
    if int(player.get("level") or 1) < CLAN_MIN_LEVEL:
        return False, f"You need level {CLAN_MIN_LEVEL} to found a clan.", None
    if await db.get_player_clan(int(player["user_id"])):
        return False, "You are already in a clan.", None
    if int(player.get("gold") or 0) < CLAN_CREATE_COST:
        return False, f"Founding a clan costs {CLAN_CREATE_COST} gold.", None

    ok, reason = validate_clan_name(name)
    if not ok:
        return False, reason, None
    ok, reason = validate_clan_tag(tag)
    if not ok:
        return False, reason, None
    if await db.get_clan_by_name(name):
        return False, "That clan name is already taken.", None
    if await db.get_clan_by_tag(tag):
        return False, "That clan tag is already taken.", None

    await db.add_gold(int(player["user_id"]), -CLAN_CREATE_COST)
    player["gold"] = int(player.get("gold") or 0) - CLAN_CREATE_COST
    clan_id = await db.create_clan(name.strip(), tag.upper(), int(player["user_id"]), description)
    clan = await db.get_clan(clan_id)
    return True, f"Clan **[{tag.upper()}] {name.strip()}** founded!", clan


async def join_clan(db: Database, player: dict, name: str) -> tuple[bool, str, dict | None]:
    if await db.get_player_clan(int(player["user_id"])):
        return False, "You are already in a clan.", None
    clan = await db.get_clan_by_name(name)
    if clan is None:
        return False, "No clan with that name exists.", None
    count = await db.get_clan_member_count(int(clan["id"]))
    if count >= clan_member_limit(int(clan["level"])):
        return False, "That clan is full.", None
    await db.add_clan_member(int(clan["id"]), int(player["user_id"]), "member")
    await db.delete_clan_invite(int(clan["id"]), int(player["user_id"]))
    return True, f"You joined **[{clan['tag']}] {clan['name']}**!", clan


async def accept_invite(db: Database, player: dict) -> tuple[bool, str, dict | None]:
    invites = await db.get_clan_invites(int(player["user_id"]))
    if not invites:
        return False, "You have no clan invitations.", None
    invite = invites[0]
    return await join_clan(db, player, invite["clan_name"])


async def leave_clan(db: Database, player: dict) -> tuple[bool, str]:
    clan = await db.get_player_clan(int(player["user_id"]))
    if clan is None:
        return False, "You are not in a clan."
    members = await db.get_clan_members(int(clan["id"]))
    if clan["member_role"] == "leader":
        others = [m for m in members if int(m["player_id"]) != int(player["user_id"])]
        if others:
            return False, "Transfer leadership before leaving, or disband the clan with /clan disband."
        await db.delete_clan(int(clan["id"]))
        return True, "You disbanded your clan."
    await db.remove_clan_member(int(clan["id"]), int(player["user_id"]))
    return True, f"You left **[{clan['tag']}] {clan['name']}**."


async def disband_clan(db: Database, player: dict) -> tuple[bool, str]:
    clan = await db.get_player_clan(int(player["user_id"]))
    if clan is None:
        return False, "You are not in a clan."
    if clan["member_role"] != "leader":
        return False, "Only the clan leader can disband the clan."
    await db.delete_clan(int(clan["id"]))
    return True, f"Clan **[{clan['tag']}] {clan['name']}** has been disbanded."


async def transfer_leadership(db: Database, player: dict, target_id: int) -> tuple[bool, str]:
    clan = await db.get_player_clan(int(player["user_id"]))
    if clan is None or clan["member_role"] != "leader":
        return False, "Only the clan leader can transfer leadership."
    target = await db.get_clan_member(target_id)
    if target is None or int(target["clan_id"]) != int(clan["id"]):
        return False, "That player is not in your clan."
    await db.execute(
        "UPDATE clan_members SET role = 'officer' WHERE clan_id = ? AND player_id = ?",
        (int(clan["id"]), int(player["user_id"])),
    )
    await db.execute(
        "UPDATE clan_members SET role = 'leader' WHERE clan_id = ? AND player_id = ?",
        (int(clan["id"]), target_id),
    )
    await db.update_clan(int(clan["id"]), owner_id=target_id)
    return True, "Leadership transferred."


async def invite_player(
    db: Database, inviter: dict, target_username: str,
) -> tuple[bool, str]:
    clan = await db.get_player_clan(int(inviter["user_id"]))
    if clan is None:
        return False, "You are not in a clan."
    if clan["member_role"] not in MANAGE_ROLES:
        return False, "Only leaders and officers can invite players."
    target = await db.get_player_by_username(target_username)
    if target is None:
        return False, "No registered player with that username."
    if int(target["user_id"]) == int(inviter["user_id"]):
        return False, "You cannot invite yourself."
    if await db.get_player_clan(int(target["user_id"])):
        return False, "That player is already in a clan."
    count = await db.get_clan_member_count(int(clan["id"]))
    if count >= clan_member_limit(int(clan["level"])):
        return False, "Your clan is full."
    await db.add_clan_invite(int(clan["id"]), int(inviter["user_id"]), int(target["user_id"]))
    return True, f"Invited **{target['display_name']}** to the clan."


async def kick_member(db: Database, actor: dict, target_id: int) -> tuple[bool, str]:
    clan = await db.get_player_clan(int(actor["user_id"]))
    if clan is None or clan["member_role"] not in MANAGE_ROLES:
        return False, "Only leaders and officers can kick members."
    target = await db.get_clan_member(target_id)
    if target is None or int(target["clan_id"]) != int(clan["id"]):
        return False, "That player is not in your clan."
    if int(target["player_id"]) == int(actor["user_id"]):
        return False, "You cannot kick yourself."
    if target["role"] == "leader":
        return False, "You cannot kick the clan leader."
    if target["role"] == "officer" and clan["member_role"] != "leader":
        return False, "Only the leader can kick officers."
    await db.remove_clan_member(int(clan["id"]), target_id)
    return True, "Member removed from the clan."


async def donate(db: Database, player: dict, amount: int) -> tuple[bool, str]:
    amount = int(amount)
    if amount <= 0:
        return False, "Donation must be positive."
    clan = await db.get_player_clan(int(player["user_id"]))
    if clan is None:
        return False, "You are not in a clan."
    if int(player.get("gold") or 0) < amount:
        return False, "You do not have that much gold."
    await db.add_gold(int(player["user_id"]), -amount)
    player["gold"] = int(player.get("gold") or 0) - amount
    await db.add_clan_contribution(int(clan["id"]), int(player["user_id"]), amount)
    await db.update_clan(int(clan["id"]), xp=int(clan["xp"]) + max(1, amount // 10))
    return True, f"Donated **{amount} gold** to the clan bank."


async def upgrade_clan(db: Database, player: dict) -> tuple[bool, str, int]:
    clan = await db.get_player_clan(int(player["user_id"]))
    if clan is None:
        return False, "You are not in a clan.", 0
    if clan["member_role"] != "leader":
        return False, "Only the clan leader can upgrade the clan.", 0
    level = int(clan["level"])
    if level >= 20:
        return False, "Your clan is already at maximum level.", 0
    cost = clan_upgrade_cost(level)
    if int(clan["bank_gold"]) < cost:
        return False, f"The clan bank needs {cost} gold (currently {clan['bank_gold']}).", 0
    await db.update_clan(int(clan["id"]), bank_gold=int(clan["bank_gold"]) - cost, level=level + 1)
    return True, f"Clan upgraded to level **{level + 1}**! New member cap: {clan_member_limit(level + 1)}.", cost


async def declare_war(
    db: Database, player: dict, target_name: str, rng: random.Random | None = None,
) -> tuple[bool, str, dict | None]:
    rng = rng or random.Random()
    clan = await db.get_player_clan(int(player["user_id"]))
    if clan is None:
        return False, "You are not in a clan.", None
    if clan["member_role"] != "leader":
        return False, "Only the clan leader can declare war.", None
    target = await db.get_clan_by_name(target_name)
    if target is None:
        return False, "Target clan not found.", None
    if int(target["id"]) == int(clan["id"]):
        return False, "You cannot declare war on your own clan.", None
    if int(clan["level"]) < 2 or int(target["level"]) < 2:
        return False, "Both clans must be at least level 2.", None
    if int(clan["bank_gold"]) < CLAN_WAR_COST:
        return False, f"Declaring war costs {CLAN_WAR_COST} gold from the clan bank.", None

    attacker_members = await db.get_clan_members(int(clan["id"]))
    defender_members = await db.get_clan_members(int(target["id"]))
    attacker_power = clan_power(attacker_members)
    defender_power = clan_power(defender_members)
    attacker_score = int(attacker_power * rng.uniform(0.90, 1.10))
    defender_score = int(defender_power * rng.uniform(0.90, 1.10))
    winner_id = int(clan["id"]) if attacker_score >= defender_score else int(target["id"])

    attacker_bank = int(clan["bank_gold"]) - CLAN_WAR_COST
    defender_bank = int(target["bank_gold"])
    attacker_won = winner_id == int(clan["id"])
    loser_bank = defender_bank if attacker_won else attacker_bank
    spoils = max(0, int(loser_bank * 0.10))
    new_attacker_bank = attacker_bank + spoils if attacker_won else attacker_bank - spoils
    new_defender_bank = defender_bank - spoils if attacker_won else defender_bank + spoils

    await db.update_clan(int(clan["id"]),
                         bank_gold=max(0, new_attacker_bank),
                         wins=int(clan.get("wins", 0)) + (1 if attacker_won else 0),
                         losses=int(clan.get("losses", 0)) + (0 if attacker_won else 1))
    await db.update_clan(int(target["id"]),
                         bank_gold=max(0, new_defender_bank),
                         wins=int(target.get("wins", 0)) + (1 if not attacker_won else 0),
                         losses=int(target.get("losses", 0)) + (0 if not attacker_won else 1))
    await db.create_clan_war(int(clan["id"]), int(target["id"]), attacker_score, defender_score, winner_id)

    won = attacker_won
    winner_name = clan["name"] if won else target["name"]
    report = {
        "won": won,
        "attacker_score": attacker_score,
        "defender_score": defender_score,
        "winner_name": winner_name,
        "spoils": spoils,
    }
    verb = "victory" if won else "defeat"
    return True, f"Clan war resolved: **{verb}**! {winner_name} won and claimed {spoils} gold.", report


async def clan_rankings(db: Database, limit: int = 10) -> list[dict]:
    return await db.get_clan_leaderboard(limit)
