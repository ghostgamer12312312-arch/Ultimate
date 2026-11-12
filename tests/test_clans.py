from __future__ import annotations

import game
import clans as clan_service


async def _rich_player(db, uid: int, username: str, name: str):
    await game.create_character(db, uid, username, name, "elf", "ranger")
    await db.update_player(uid, level=10, gold=20_000, hp=1000, mana=500)
    return await game.load_player(db, uid)


async def test_clan_create_join_donate_upgrade(db, strong_player):
    p = strong_player
    ok, message, clan = await clan_service.create_clan(db, p, "Iron Wolves", "IW", "Strong and loyal")
    assert ok and clan is not None
    assert clan["name"] == "Iron Wolves"

    duplicate, reason, _ = await clan_service.create_clan(db, p, "Other", "OT")
    assert not duplicate and "already" in reason.lower()

    p2 = await _rich_player(db, 3001, "ranger_two", "Ranger Two")
    joined, message, _ = await clan_service.join_clan(db, p2, "Iron Wolves")
    assert joined
    assert (await db.get_player_clan(3001))["member_role"] == "member"

    ok, message = await clan_service.donate(db, p2, 3000)
    assert ok
    clan = await db.get_clan(clan["id"])
    assert clan["bank_gold"] == 3000
    assert clan["xp"] >= 300

    ok, message, cost = await clan_service.upgrade_clan(db, p2)
    assert not ok  # member cannot upgrade
    ok, message, cost = await clan_service.upgrade_clan(db, p)
    assert ok and cost == 2000
    clan = await db.get_clan(clan["id"])
    assert clan["level"] == 2


async def test_clan_invite_accept_and_management(db, strong_player):
    p = strong_player
    ok, _, clan = await clan_service.create_clan(db, p, "Bright Order", "BO")
    assert ok
    p2 = await _rich_player(db, 3002, "invitee", "Invitee")

    invited, message = await clan_service.invite_player(db, p, "@invitee")
    assert invited
    assert await db.get_clan_invites(3002)
    accepted, message, _ = await clan_service.accept_invite(db, p2)
    assert accepted
    assert await db.get_player_clan(3002)

    transferred, _ = await clan_service.transfer_leadership(db, p, 3002)
    assert transferred
    assert (await db.get_player_clan(3002))["member_role"] == "leader"
    assert (await db.get_player_clan(p["user_id"]))["member_role"] == "officer"

    kicked, message = await clan_service.kick_member(db, p2, p["user_id"])
    assert kicked
    assert await db.get_player_clan(p["user_id"]) is None


async def test_clan_war_and_rankings(db, strong_player):
    p1 = strong_player
    ok, _, clan1 = await clan_service.create_clan(db, p1, "North Guard", "NG")
    assert ok
    await clan_service.donate(db, p1, 5000)
    await clan_service.upgrade_clan(db, p1)
    await clan_service.donate(db, p1, 2000)

    p2 = await _rich_player(db, 3003, "south_hero", "South Hero")
    ok, _, clan2 = await clan_service.create_clan(db, p2, "South Legion", "SL")
    assert ok
    await clan_service.donate(db, p2, 5000)
    await clan_service.upgrade_clan(db, p2)
    await clan_service.donate(db, p2, 2000)

    ok, message, report = await clan_service.declare_war(db, p1, "South Legion")
    assert ok and report is not None
    assert report["attacker_score"] > 0 and report["defender_score"] > 0
    wars = await db.get_clan_wars(clan1["id"])
    assert wars

    rankings = await clan_service.clan_rankings(db)
    assert len(rankings) == 2
    ranks = {row["name"] for row in rankings}
    assert {"North Guard", "South Legion"} == ranks


async def test_clan_leave_disband_and_errors(db, strong_player):
    p = strong_player
    ok, _, clan = await clan_service.create_clan(db, p, "Lone Star", "LS")
    assert ok
    left, message = await clan_service.leave_clan(db, p)
    assert left and "disband" in message.lower()
    assert await db.get_clan(clan["id"]) is None

    p2 = await _rich_player(db, 3004, "clanless", "Clanless")
    not_joined, reason, _ = await clan_service.join_clan(db, p2, "Missing Clan")
    assert not not_joined and "no clan" in reason.lower()

    ok, _, _ = await clan_service.create_clan(db, p2, "Second Wind", "SW")
    assert ok
    disbanded, _ = await clan_service.disband_clan(db, p2)
    assert disbanded


async def test_clan_creation_level_and_gold_gates(db, player):
    poor = player
    ok, reason, _ = await clan_service.create_clan(db, poor, "Too Soon", "TS")
    assert not ok and "level" in reason.lower()

    await db.update_player(poor["user_id"], level=10, gold=10)
    poor = await game.load_player(db, poor["user_id"])
    ok, reason, _ = await clan_service.create_clan(db, poor, "Too Poor", "TP")
    assert not ok and "gold" in reason.lower()

    ok, reason, _ = await clan_service.create_clan(db, poor, "X", "BAD TAG")
    assert not ok
