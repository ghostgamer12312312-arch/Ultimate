from __future__ import annotations


def test_nickname_validation_and_update(database, player):
    assert database.set_nickname(1001, "A")["ok"] is False
    assert database.set_nickname(1001, "bad<name")["ok"] is False
    result = database.set_nickname(1001, "  Shadow   King  ")
    assert result["ok"] is True
    assert database.player(1001)["nickname"] == "Shadow King"


def test_spin_is_once_per_day(database, player):
    first = database.claim_spin(1001)
    assert first["ok"] is True
    assert first["label"]
    assert first["rewards"]
    second = database.claim_spin(1001)
    assert second["ok"] is False
    assert database.spin_ready(1001) is False


def test_work_has_cooldown(database, player):
    first = database.work_shift(1001)
    assert first["ok"] is True
    assert first["rewards"]["yens"] > 0
    second = database.work_shift(1001)
    assert second["ok"] is False
    assert second["remaining"] > 0


def test_referral_rewards_only_once(database):
    database.ensure_player(2001, "veteran", "Veteran")
    database.ensure_player(2002, "recruit", "Recruit")
    applied = database.apply_referral(2002, 2001)
    assert applied is not None
    assert database.referral_count(2001) == 1
    assert database.apply_referral(2002, 2001) is None
    assert database.referral_count(2001) == 1
    assert database.apply_referral(2001, 2001) is None


def test_tournament_fills_and_resolves(database):
    for index in range(10):
        database.ensure_player(3000 + index, f"fighter{index}", f"Fighter {index}")
    for index in range(9):
        result = database.tournament_join(3000 + index)
        assert result["ok"] is True
        assert result["resolved"] is False
    duplicate = database.tournament_join(3000)
    assert duplicate["ok"] is False
    final = database.tournament_join(3009)
    assert final["ok"] is True
    assert final["resolved"] is True
    state = database.tournament_state()
    assert state["status"] == "done"
    assert state["champion"]["user_id"] in {3000 + index for index in range(10)}
    assert state["rounds"]
    assert len(state["placements"]) == 10
    champion_id = int(state["champion"]["user_id"])
    assert state["placements"][str(champion_id)] == "champion"
    assert database.player(champion_id)["gems"] >= 60
    assert database.tournament_join(3000)["ok"] is False


def test_aura_grant_and_duplicates(database, player):
    assert database.grant_aura(1001, "dragonball_saiyan_aura") is True
    assert database.aura_qty(1001, "dragonball_saiyan_aura") == 1
    assert database.grant_aura(1001, "dragonball_saiyan_aura") is False
    assert database.aura_qty(1001, "dragonball_saiyan_aura") == 2
    assert len(database.player_auras(1001)) == 1


def test_aura_equip_validation_and_global_replace(database, player):
    database.add_character(1001, "db_goku")
    database.add_character(1001, "db_vegeta")
    database.grant_aura(1001, "dragonball_saiyan_aura")
    database.grant_aura(1001, "dragonball_kaioken_aura")
    assert database.equip_aura(1001, "dragonball_saiyan_aura", "missing")["ok"] is False
    assert database.equip_aura(1001, "naruto_chidori_aura")["ok"] is False
    assert database.equip_aura(1001, "dragonball_saiyan_aura", "db_goku")["ok"] is True
    assert database.equipped_aura(1001)["aura_id"] == "dragonball_saiyan_aura"
    assert database.equip_aura(1001, "dragonball_kaioken_aura", "db_vegeta")["ok"] is True
    equipped = database.equipped_aura(1001)
    assert equipped["aura_id"] == "dragonball_kaioken_aura"
    assert equipped["char_id"] == "db_vegeta"
    assert database.unequip_aura(1001) is True
    assert database.equipped_aura(1001) is None


def test_aura_spin_once_per_day(database, player):
    first = database.claim_aura_spin(1001)
    assert first["ok"] is True
    assert first["aura"]["id"] == database.player_auras(1001)[0]["aura_id"]
    second = database.claim_aura_spin(1001)
    assert second["ok"] is False
    assert database.aura_spin_ready(1001) is False


def test_aura_stats_apply_only_to_carrier(database, player):
    import game

    database.add_character(1001, "db_goku")
    database.add_character(1001, "db_vegeta")
    database.equip_character(1001, "db_goku")
    base = game.effective_stats(database, 1001)
    database.grant_aura(1001, "dragonball_saiyan_aura")
    assert database.equip_aura(1001, "dragonball_saiyan_aura", "db_goku")["ok"] is True
    boosted = game.effective_stats(database, 1001)
    assert boosted["hp"] == base["hp"] + 90
    assert database.equip_aura(1001, "dragonball_saiyan_aura", "db_vegeta")["ok"] is True
    benched = game.effective_stats(database, 1001)
    assert benched["hp"] == base["hp"]
