import sys
import os
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

    captured = {}
    async def fake_request_llm_delivery(output, original_context, action_type, command):
        captured['interface'] = original_context.get('interface_name')
        captured['output'] = output
        captured['command'] = command
    monkeypatch.setattr("core.auto_response.request_llm_delivery", fake_request_llm_delivery)

    action = {"type": "terminal", "payload": {"command": "echo hi"}}
    context = {"interface": "telegram"}
    message = SimpleNamespace(chat_id=1, message_id=2)

    output = await plugin.execute_action(action, context, bot=None, original_message=message)

    assert captured['interface'] == 'telegram_bot'
    assert 'echo hi' in notified['msg']
    assert 'result' in notified['msg']
    assert output == 'result'
