import asyncio
from types import SimpleNamespace
from core.action_parser import parse_action

class DummyBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append((chat_id, text, reply_to_message_id))


def test_parse_action_executes_message():
    bot = DummyBot()
    msg = SimpleNamespace(message_id=5)
    asyncio.run(parse_action({'type': 'message', 'interface': 'telegram', 'payload': {'text': 'hi', 'target': '123'}}, bot, msg))
    assert bot.sent == [('123', 'hi', 5)]

def test_parse_action_unknown_type():
    bot = DummyBot()
    msg = SimpleNamespace(message_id=5)
    asyncio.run(parse_action({'type': 'unknown', 'interface': 'telegram', 'payload': {'text': 'hi', 'target': '123'}}, bot, msg))
    assert bot.sent == []
