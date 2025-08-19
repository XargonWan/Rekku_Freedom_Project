import sys
import os
import sys
from types import SimpleNamespace
import pytest

# Ensure repository root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.terminal import TerminalPlugin

@pytest.mark.asyncio
async def test_execute_action_notifies_and_normalizes(monkeypatch):
    plugin = TerminalPlugin()

    async def fake_send_command(cmd):
        return "result"

    monkeypatch.setattr(plugin, "_send_command", fake_send_command)

    notified = {}
    def fake_notify(msg):
        notified['msg'] = msg
    monkeypatch.setattr("plugins.terminal.notify_trainer", fake_notify)

    action = {"type": "terminal", "payload": {"command": "echo hi"}}
    context = {"interface": "telegram"}
    message = SimpleNamespace(chat_id=1, message_id=2)

    output = await plugin.execute_action(action, context, bot=None, original_message=message)

    assert 'echo hi' in notified['msg']
    assert 'result' in notified['msg']
    assert output == 'result'


@pytest.mark.asyncio
async def test_run_actions_stops_after_terminal(monkeypatch):
    plugin = TerminalPlugin()

    async def fake_send_command(cmd):
        return "done"

    monkeypatch.setattr(plugin, "_send_command", fake_send_command)

    # Capture auto-response call
    captured = {}

    async def fake_request_llm_delivery(**kwargs):
        captured['outputs'] = kwargs.get('action_outputs')
        captured['interface'] = kwargs.get('original_context', {}).get('interface_name')

    monkeypatch.setattr("core.auto_response.request_llm_delivery", fake_request_llm_delivery)

    # Fake telegram interface to detect if second action runs
    called = {}

    class FakeTelegram:
        def send_message(self, payload, original_message):
            called["payload"] = payload

    from core.core_initializer import INTERFACE_REGISTRY

    INTERFACE_REGISTRY["telegram_bot"] = FakeTelegram()

    actions = [
        {"type": "terminal", "payload": {"command": "echo hi"}},
        {
            "type": "message_telegram_bot",
            "payload": {"text": "should not run", "target": 1},
        },
    ]

    message = SimpleNamespace(chat_id=1, message_id=2)

    from core.action_parser import run_actions

    result = await run_actions(actions, {"interface": "telegram"}, None, message)

    assert "payload" not in called
    assert captured['interface'] == 'telegram_bot'
    assert captured['outputs'][0]['command'] == 'echo hi'
    assert result['action_outputs'][0]['output'] == 'done'


@pytest.mark.asyncio
async def test_run_actions_multiple_terminals(monkeypatch):
    plugin = TerminalPlugin()

    async def fake_send_command(cmd):
        return f"out-{cmd}"

    monkeypatch.setattr(plugin, "_send_command", fake_send_command)

    captured = {}

    async def fake_request_llm_delivery(**kwargs):
        captured['outputs'] = kwargs.get('action_outputs')

    monkeypatch.setattr("core.auto_response.request_llm_delivery", fake_request_llm_delivery)

    actions = [
        {"type": "terminal", "payload": {"command": "a"}},
        {"type": "terminal", "payload": {"command": "b"}},
    ]

    message = SimpleNamespace(chat_id=1, message_id=2)

    from core.action_parser import run_actions

    res = await run_actions(actions, {"interface": "telegram"}, None, message)

    assert len(captured['outputs']) == 2
    assert res['action_outputs'][1]['output'] == 'out-b'
