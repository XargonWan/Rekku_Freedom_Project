import asyncio
from types import SimpleNamespace
import types

from core.action_parser import parse_action, ACTION_PLUGINS
from core.interface_loader import register_interface, REGISTERED_INTERFACES

class DummyBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append((chat_id, text, reply_to_message_id))

async def dummy_handle_action(payload, bot, source_message):
    await bot.send_message(payload['target'], payload['text'], getattr(source_message, 'message_id', None))

def get_supported_actions():
    return [{'name': 'message'}]

dummy_plugin = types.SimpleNamespace(handle_action=dummy_handle_action, get_supported_actions=get_supported_actions)


def test_parse_action_executes_plugin():
    bot = DummyBot()
    msg = SimpleNamespace(message_id=5)
    ACTION_PLUGINS.clear()
    ACTION_PLUGINS['message'] = dummy_plugin
    REGISTERED_INTERFACES.clear()
    register_interface('telegram', object())
    asyncio.run(parse_action({'type': 'message', 'interface': 'telegram', 'payload': {'text': 'hi', 'target': '123'}}, bot, msg))
    assert bot.sent == [('123', 'hi', 5)]

def test_parse_action_unknown_type():
    bot = DummyBot()
    msg = SimpleNamespace(message_id=5)
    ACTION_PLUGINS.clear()
    REGISTERED_INTERFACES.clear()
    register_interface('telegram', object())
    asyncio.run(parse_action({'type': 'unknown', 'interface': 'telegram', 'payload': {'text': 'hi', 'target': '123'}}, bot, msg))
    assert bot.sent == []
