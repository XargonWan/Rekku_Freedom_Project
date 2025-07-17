import asyncio
import json
import types
from types import SimpleNamespace
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("BOTFATHER_TOKEN", "dummy")

import importlib, importlib.util, types

module_in_sys = sys.modules.get("core.plugin_instance")
if isinstance(module_in_sys, types.ModuleType):
    plugin_instance = importlib.reload(module_in_sys)
else:
    spec = importlib.util.spec_from_file_location(
        "core.plugin_instance",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "plugin_instance.py"),
    )
    plugin_instance = importlib.util.module_from_spec(spec)
    sys.modules["core.plugin_instance"] = plugin_instance
    spec.loader.exec_module(plugin_instance)

class DummyBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append((chat_id, text, reply_to_message_id))


def make_message():
    return SimpleNamespace(
        chat_id=1,
        chat=SimpleNamespace(id=1),
        message_id=5,
        from_user=SimpleNamespace(id=2, username="foo"),
        text="hi",
    )


async def dummy_json_response(prompt):
    return json.dumps({
        "type": "message",
        "interface": "telegram",
        "payload": {"text": "hello", "target": "1"}
    })

async def dummy_text_response(prompt):
    return "plain"


def test_handle_incoming_message_parses_action(monkeypatch):
    bot = DummyBot()
    msg = make_message()
    plugin_instance.plugin = types.SimpleNamespace(generate_response=dummy_json_response)
    async def fake_build_json_prompt(m, c):
        return {}
    monkeypatch.setattr(plugin_instance, "build_json_prompt", fake_build_json_prompt)
    captured = {}

    async def fake_parse_action(data, b, m):
        captured["data"] = data
        captured["bot"] = b
        captured["msg"] = m

    monkeypatch.setattr(plugin_instance, "parse_action", fake_parse_action)

    asyncio.run(plugin_instance.handle_incoming_message(bot, msg, {}))

    assert captured["data"]["type"] == "message"
    assert not bot.sent


def test_handle_incoming_message_fallback(monkeypatch):
    bot = DummyBot()
    msg = make_message()
    plugin_instance.plugin = types.SimpleNamespace(generate_response=dummy_text_response)
    async def fake_build_json_prompt(m, c):
        return {}
    monkeypatch.setattr(plugin_instance, "build_json_prompt", fake_build_json_prompt)
    monkeypatch.setattr(plugin_instance, "parse_action", lambda *a, **k: None)

    asyncio.run(plugin_instance.handle_incoming_message(bot, msg, {}))

    assert bot.sent == [(1, "plain", 5)]


def test_handle_incoming_message_plugin_method(monkeypatch):
    bot = DummyBot()
    msg = make_message()
    called = {}

    async def dummy_handle(bot_arg, msg_arg, prompt):
        called["done"] = True

    plugin_instance.plugin = types.SimpleNamespace(handle_incoming_message=dummy_handle)

    async def fake_build_json_prompt(m, c):
        return {}

    monkeypatch.setattr(plugin_instance, "build_json_prompt", fake_build_json_prompt)

    asyncio.run(plugin_instance.handle_incoming_message(bot, msg, {}))

    assert called.get("done") is True
    assert bot.sent == []
