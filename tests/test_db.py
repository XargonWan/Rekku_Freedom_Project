import os
import sys
import sqlite3
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from importlib import reload
import core.db as db_module


def test_get_db_creates_db(tmp_path, capsys):
    db_path = tmp_path / "test.db"
    os.environ["MEMORY_DB"] = str(db_path)

    reload(db_module)

    with db_module.get_db():
        pass

    captured = capsys.readouterr()
    assert "not found, creating new database" in captured.out
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' and name='settings'"
        ).fetchone()
        assert row is not None

    os.environ.pop("MEMORY_DB")

