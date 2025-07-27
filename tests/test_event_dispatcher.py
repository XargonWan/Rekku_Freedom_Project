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


async def test_dispatch_pending_events(tmp_path, monkeypatch):
    db_path = tmp_path / "events.db"
    os.environ["MEMORY_DB"] = str(db_path)
    reload(db_module)
    await db_module.init_db()

    past = datetime.utcnow() - timedelta(minutes=1)
    await db_module.insert_scheduled_event(past.strftime("%Y-%m-%d"), past.strftime("%H:%M"), None, "Test Event")

    monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)

    bot = FakeBot()
    await dispatch_pending_events(bot)

    assert len(fake_handle.called) == 1
    assert fake_handle.called[0]["input"]["payload"]["description"] == "Test Event"

    conn = await db_module.get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT delivered FROM scheduled_events")
            row = await cur.fetchone()
            assert row["delivered"] == 1
    finally:
        conn.close()
    os.environ.pop("MEMORY_DB")


async def test_dispatch_repeating_event(tmp_path, monkeypatch):
    db_path = tmp_path / "events.db"
    os.environ["MEMORY_DB"] = str(db_path)
    reload(db_module)
    await db_module.init_db()

    past = datetime.utcnow() - timedelta(minutes=1)
    await db_module.insert_scheduled_event(
        past.strftime("%Y-%m-%d"), past.strftime("%H:%M"), "daily", "Repeat"
    )

    monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)

    bot = FakeBot()
    fake_handle.called.clear()
    await dispatch_pending_events(bot)

    assert len(fake_handle.called) == 1

    conn = await db_module.get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT scheduled, delivered FROM scheduled_events ORDER BY id"
            )
            rows = await cur.fetchall()
            assert len(rows) == 2
            assert rows[0]["delivered"] == 1
            assert rows[1]["delivered"] == 0
    finally:
        conn.close()

    os.environ.pop("MEMORY_DB")


async def test_unknown_repeat_value(tmp_path, monkeypatch, caplog):
    db_path = tmp_path / "events.db"
    os.environ["MEMORY_DB"] = str(db_path)
    reload(db_module)
    await db_module.init_db()

    past = datetime.utcnow() - timedelta(minutes=1)
    await db_module.insert_scheduled_event(
        past.strftime("%Y-%m-%d"), past.strftime("%H:%M"), "foobar", "Mystery"
    )

    monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)

    bot = FakeBot()
    fake_handle.called.clear()
    caplog.set_level("WARNING", logger="rekku")
    await dispatch_pending_events(bot)

    assert len(fake_handle.called) == 1

    conn = await db_module.get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT repeat, delivered FROM scheduled_events ORDER BY id"
            )
            rows = await cur.fetchall()
            # event marked delivered, no reschedule
            assert len(rows) == 1
            assert rows[0]["delivered"] == 1
    finally:
        conn.close()

    assert any(
        "Unknown repeat value" in record.getMessage() for record in caplog.records
    )

    os.environ.pop("MEMORY_DB")
