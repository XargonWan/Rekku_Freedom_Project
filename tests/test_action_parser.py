import os
import sys
import types
from types import SimpleNamespace
from datetime import datetime
import asyncio
import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

_dummy_plugin_instance = types.SimpleNamespace()
_dummy_plugin_instance.handle_incoming_message = None
sys.modules['core.plugin_instance'] = _dummy_plugin_instance

import core.action_parser as action_parser
import plugins.test_action_plugin as test_plugin

plugin_instance = sys.modules['core.plugin_instance']


def _make_message():
    return SimpleNamespace(
        message_id=1,
        chat_id=123,
        chat=SimpleNamespace(id=123, type="private"),
        from_user=SimpleNamespace(id=42, full_name="Tester", username="tester"),
        text="orig",
        date=datetime.utcnow(),
        reply_to_message=None,
    )


async def fake_handle(bot, message, context_memory):
    fake_handle.called.append(message.text)

fake_handle.called = []


def test_message_action(monkeypatch):
    monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)
    action = {"type": "message", "payload": {"text": "hello", "scope": "local", "privacy": "default"}}
    ctx = {"context": {"messages": []}}
    asyncio.run(action_parser.run_action(action, ctx, None, _make_message()))
    assert fake_handle.called == ["hello"]


def test_action_list(monkeypatch):
    monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)
    actions = [
        {"type": "message", "payload": {"text": "one", "scope": "local", "privacy": "default"}},
        {"type": "message", "payload": {"text": "two", "scope": "local", "privacy": "default"}},
    ]
    ctx = {"context": {"messages": []}}
    fake_handle.called.clear()
    asyncio.run(action_parser.run_actions(actions, ctx, None, _make_message()))
    assert fake_handle.called == ["one", "two"]


def test_run_actions_invalid(monkeypatch):
    monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)
    actions = [
        {"type": "message", "payload": {}},
        {"type": "message", "payload": {"text": "ok", "scope": "local", "privacy": "default"}},
    ]
    ctx = {"context": {"messages": []}}
    fake_handle.called.clear()
    asyncio.run(action_parser.run_actions(actions, ctx, None, _make_message()))
    assert fake_handle.called == ["ok"]


def test_plugin_action():
    test_plugin.executed_actions.clear()
    action = {"type": "command", "payload": {"name": "doit"}}
    ctx = {"context": {"messages": []}}
    asyncio.run(action_parser.run_action(action, ctx, None, _make_message()))
    assert test_plugin.executed_actions == [action]


class DummyBot:
    async def send_message(self, *args, **kwargs):
        pass


async def _dummy_custom(action_type, payload):
    _dummy_custom.called.append((action_type, payload))


def test_parse_custom_action(monkeypatch):
    _dummy_custom.called = []
    plugin = types.SimpleNamespace(
        handle_custom_action=_dummy_custom,
        get_supported_action_types=lambda: ["event"],
    )
    monkeypatch.setattr(plugin_instance, "plugin", plugin, raising=False)

    action = {"type": "event", "interface": "telegram", "payload": {"foo": "bar"}}
    asyncio.run(action_parser.parse_action(action, DummyBot(), _make_message()))

    assert _dummy_custom.called == [("event", {"foo": "bar"})]


