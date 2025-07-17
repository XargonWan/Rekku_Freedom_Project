import asyncio
from types import SimpleNamespace
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.validate_action import validate_action
from core.action_parser import parse_actions

class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, reply_to_message_id=None):
        self.calls.append({
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": reply_to_message_id,
        })


def make_message():
    return SimpleNamespace(message_id=42, from_user=SimpleNamespace(id=1, username="tester"))


def test_validate_action_valid():
    data = {"actions": [{"message": {"content": "hi", "target": "Telegram/123"}}]}
    assert validate_action(data) == []


def test_validate_action_invalid():
    data = {"actions": [{"message": {"content": "", "target": "User/1"}}]}
    errors = validate_action(data)
    assert errors and any("Telegram/" in e or "non-empty" in e for e in errors)


def test_parse_actions_sends_message():
    bot = FakeBot()
    msg = make_message()
    data = {"actions": [{"message": {"content": "hello", "target": "Telegram/99"}}]}
    asyncio.run(parse_actions(data, bot, msg))
    assert bot.calls == [{"chat_id": "99", "text": "hello", "reply_to_message_id": 42}]
