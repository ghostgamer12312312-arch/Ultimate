from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db as db_module  # noqa: E402


@pytest.fixture()
def database(tmp_path):
    database = db_module.Database(tmp_path / "test.db")
    return database


@pytest.fixture()
def player(database):
    return database.ensure_player(1001, "tester", "Tester")
