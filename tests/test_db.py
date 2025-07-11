import os
import sys
import sqlite3
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from importlib import reload
import logging
import core.db as db_module
from logging_utils import setup_logging


def test_get_db_creates_db(tmp_path, caplog):
    db_path = tmp_path / "test.db"
    os.environ["MEMORY_DB"] = str(db_path)

    reload(db_module)
    logger = setup_logging()
    logger.setLevel(logging.WARNING)
    logger.propagate = True
    caplog.set_level(logging.WARNING, logger="rekku")
    with db_module.get_db():
        pass

    assert any(
        "not found, creating new database" in record.getMessage() for record in caplog.records
    )
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' and name='settings'"
        ).fetchone()
        assert row is not None

    os.environ.pop("MEMORY_DB")

