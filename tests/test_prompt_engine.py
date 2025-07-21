import asyncio
import os
import sys
from datetime import datetime
import types
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

sys.modules['core.plugin_instance'] = types.SimpleNamespace(handle_incoming_message=None)
from core import prompt_engine
plugin_instance = sys.modules['core.plugin_instance']


class FakeFrom:
    def __init__(self):
        self.full_name = "Tester"
        self.username = "tester"
        self.id = 42


class FakeMessage:
    def __init__(self):
        self.chat_id = 1
        self.message_id = 1
        self.text = "hi"
        self.from_user = FakeFrom()
        self.date = datetime.utcnow()
        self.reply_to_message = None
        self.message_thread_id = None


class DummyPlugin:
    def get_supported_actions(self):
        return [{"name": "dummy", "description": "d", "usage": {"type": "dummy"}}]


def _build_prompt(monkeypatch, plugin):
    sys.modules['pytz'] = types.SimpleNamespace(timezone=lambda name: ZoneInfo("UTC"))
    monkeypatch.setattr(plugin_instance, "get_plugin", lambda: plugin, raising=False)
    msg = FakeMessage()
    return asyncio.run(prompt_engine.build_json_prompt(msg, {}))


def test_available_actions_present(monkeypatch):
    plugin = DummyPlugin()
    prompt = _build_prompt(monkeypatch, plugin)
    assert prompt["available_actions"] == plugin.get_supported_actions()


def test_no_available_actions(monkeypatch):
    prompt = _build_prompt(monkeypatch, None)
    assert "available_actions" not in prompt
