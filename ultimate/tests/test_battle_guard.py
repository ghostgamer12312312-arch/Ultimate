from __future__ import annotations


def _battle(database):
    import battle

    database.add_character(1001, "db_goku")
    database.equip_character(1001, "db_goku")
    started = battle.start_hunt(database, 1001, series="dragonball")
    assert started["ok"] is True
    return battle, started["battle"]


def test_battle_rejects_stale_turn(database, player):
    battle, current = _battle(database)
    turn = int(current["state"]["turn"])
    stale = battle.act(database, 1001, current["battle_id"], "attack", expected_turn=turn + 5)
    assert stale["ok"] is False
    assert stale.get("stale") is True
    fresh = battle.act(database, 1001, current["battle_id"], "attack", expected_turn=turn)
    assert fresh["ok"] is True
    assert int(fresh["battle"]["state"]["turn"]) == turn + 1


def test_battle_expires_after_timeout(database, player):
    battle, current = _battle(database)
    with database.conn() as c:
        c.execute(
            "UPDATE active_battles SET created_at=? WHERE battle_id=?",
            ("2000-01-01 00:00:00", current["battle_id"]),
        )
    expired = battle.act(database, 1001, current["battle_id"], "attack")
    assert expired["ok"] is False
    assert expired.get("stale") is True
    assert database.active_battle(1001) is None
