import asyncio
import os
import sys
from importlib import reload, import_module

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import core.db as db_module


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append({"chat_id": chat_id, "text": text})


class FakeMessage:
    def __init__(self, chat_id=1, message_id=1):
        self.chat_id = chat_id
        self.message_id = message_id


def _load_plugin(tmp_path):
    db_path = tmp_path / "events.db"
    os.environ["MEMORY_DB"] = str(db_path)
    reload(db_module)
    db_module.init_db()
    plugin_mod = import_module("plugins.event_plugin")
    reload(plugin_mod)
    return plugin_mod.EventPlugin()


def test_event_saved(tmp_path):
    prompt = {
        "actions": [
            {
                "type": "event",
                "payload": {
                    "scheduled": "2025-08-10T14:00:00+00:00",
                    "repeat": "daily",
                    "description": "Call Mom",
                },
            }
        ]
    }
    plugin = _load_plugin(tmp_path)
    bot = FakeBot()
    msg = FakeMessage()
    asyncio.run(plugin.handle_incoming_message(bot, msg, prompt))
    assert bot.sent[0]["text"].startswith("📅 Event(s) saved")
    with db_module.get_db() as db:
        row = db.execute("SELECT description, repeat FROM scheduled_events").fetchone()
        assert row["description"] == "Call Mom"
        assert row["repeat"] == "daily"
    os.environ.pop("MEMORY_DB")


def test_invalid_repeat(tmp_path):
    prompt = {
        "actions": [
            {
                "type": "event",
                "payload": {
                    "scheduled": "2025-08-10T14:00:00+00:00",
                    "repeat": "foobar",
                    "description": "Bad Repeat",
                },
            }
        ]
    }
    plugin = _load_plugin(tmp_path)
    bot = FakeBot()
    msg = FakeMessage()
    asyncio.run(plugin.handle_incoming_message(bot, msg, prompt))
    assert bot.sent[0]["text"].startswith("\u274c Invalid repeat value")
    with db_module.get_db() as db:
        row = db.execute("SELECT COUNT(*) AS c FROM scheduled_events").fetchone()
        assert row["c"] == 0
    os.environ.pop("MEMORY_DB")


def test_duplicate_event(tmp_path):
    prompt = {
        "actions": [
            {
                "type": "event",
                "payload": {
                    "scheduled": "2025-08-10T08:00:00+00:00",
                    "description": "Water the plants",
                },
            }
        ]
    }
    plugin = _load_plugin(tmp_path)
    bot = FakeBot()
    msg = FakeMessage()
    asyncio.run(plugin.handle_incoming_message(bot, msg, prompt))
    asyncio.run(plugin.handle_incoming_message(bot, msg, prompt))
    # second call should produce duplicate warning
    assert any(text.startswith("\u26a0\ufe0f Event already exists") for text in [m["text"] for m in bot.sent])
    os.environ.pop("MEMORY_DB")


def test_no_valid_event(tmp_path):
    prompt = {"actions": [{"type": "command", "payload": {"name": "noop"}}]}
    plugin = _load_plugin(tmp_path)
    bot = FakeBot()
    msg = FakeMessage()
    asyncio.run(plugin.handle_incoming_message(bot, msg, prompt))
    assert bot.sent[0]["text"] == "⚠️ No valid event actions in this prompt."
    os.environ.pop("MEMORY_DB")
