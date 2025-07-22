import asyncio
import os
import sys
from importlib import reload
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("BOTFATHER_TOKEN", "test")

import core.db as db_module
from core import plugin_instance
from core.event_dispatcher import dispatch_pending_events

class FakeBot:
    def __init__(self):
        self.sent = []

async def fake_handle(bot, message, prompt):
    fake_handle.called.append(prompt)

fake_handle.called = []


def test_dispatch_pending_events(tmp_path, monkeypatch):
    db_path = tmp_path / "events.db"
    os.environ["MEMORY_DB"] = str(db_path)
    reload(db_module)
    db_module.init_db()

    past = datetime.utcnow() - timedelta(minutes=1)
    db_module.insert_scheduled_event(past.strftime("%Y-%m-%d"), past.strftime("%H:%M"), None, "Test Event")

    monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)

    bot = FakeBot()
    asyncio.run(dispatch_pending_events(bot))

    assert len(fake_handle.called) == 1
    assert fake_handle.called[0]["input"]["payload"]["description"] == "Test Event"

    with db_module.get_db() as db:
        row = db.execute("SELECT delivered FROM scheduled_events").fetchone()
        assert row["delivered"] == 1
    os.environ.pop("MEMORY_DB")


def test_dispatch_repeating_event(tmp_path, monkeypatch):
    db_path = tmp_path / "events.db"
    os.environ["MEMORY_DB"] = str(db_path)
    reload(db_module)
    db_module.init_db()

    past = datetime.utcnow() - timedelta(minutes=1)
    db_module.insert_scheduled_event(
        past.strftime("%Y-%m-%d"), past.strftime("%H:%M"), "daily", "Repeat"
    )

    monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)

    bot = FakeBot()
    fake_handle.called.clear()
    asyncio.run(dispatch_pending_events(bot))

    assert len(fake_handle.called) == 1

    with db_module.get_db() as db:
        rows = db.execute(
            "SELECT date, delivered FROM scheduled_events ORDER BY id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["delivered"] == 1
        assert rows[1]["delivered"] == 0

    os.environ.pop("MEMORY_DB")


def test_unknown_repeat_value(tmp_path, monkeypatch, caplog):
    db_path = tmp_path / "events.db"
    os.environ["MEMORY_DB"] = str(db_path)
    reload(db_module)
    db_module.init_db()

    past = datetime.utcnow() - timedelta(minutes=1)
    db_module.insert_scheduled_event(
        past.strftime("%Y-%m-%d"), past.strftime("%H:%M"), "foobar", "Mystery"
    )

    monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)

    bot = FakeBot()
    fake_handle.called.clear()
    caplog.set_level("WARNING", logger="rekku")
    asyncio.run(dispatch_pending_events(bot))

    assert len(fake_handle.called) == 1
    with db_module.get_db() as db:
        rows = db.execute(
            "SELECT repeat, delivered FROM scheduled_events ORDER BY id"
        ).fetchall()
        # event marked delivered, no reschedule
        assert len(rows) == 1
        assert rows[0]["delivered"] == 1

    assert any(
        "Unknown repeat value" in record.getMessage() for record in caplog.records
    )

    os.environ.pop("MEMORY_DB")
