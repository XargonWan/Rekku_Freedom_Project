import asyncio
from types import SimpleNamespace
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.validate_action import validate_action
from core.action_parser import parse_actions
from core.interface_loader import register_interface, REGISTERED_INTERFACES

class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, reply_to_message_id=None):
        self.calls.append({
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": reply_to_message_id,
        })


class FakeHandler:
    def __init__(self, bot):
        self.bot = bot

    async def send(self, action_type, payload, source_message):
        if action_type == "message":
            await self.bot.send_message(
                chat_id=payload["target"],
                text=payload["content"],
                reply_to_message_id=payload.get("reply_to"),
            )

    def get_target_string(self, chat_id):
        return f"telegram/{chat_id}"


def make_message():
    return SimpleNamespace(message_id=42, from_user=SimpleNamespace(id=1, username="tester"))


def test_validate_action_valid():
    REGISTERED_INTERFACES.clear()
    register_interface("telegram", FakeHandler(FakeBot()))
    data = {"actions": [{"message": {"content": "hi", "target": "telegram/123"}}]}
    assert validate_action(data) == []


def test_validate_action_invalid():
    REGISTERED_INTERFACES.clear()
    register_interface("telegram", FakeHandler(FakeBot()))
    data = {"actions": [{"message": {"content": "", "target": "unknown/1"}}]}
    errors = validate_action(data)
    assert errors and any("unknown interface" in e or "non-empty" in e for e in errors)


def test_parse_actions_sends_message():
    bot = FakeBot()
    REGISTERED_INTERFACES.clear()
    register_interface("telegram", FakeHandler(bot))
    msg = make_message()
    data = {"actions": [{"message": {"content": "hello", "target": "telegram/99"}}]}
    asyncio.run(parse_actions(data, bot, msg))
    assert bot.calls == [{"chat_id": "99", "text": "hello", "reply_to_message_id": 42}]
