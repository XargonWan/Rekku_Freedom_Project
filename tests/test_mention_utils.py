import os
import sys
from types import SimpleNamespace

import pytest
import asyncio

# Add parent directory to path so that 'core' can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('BOTFATHER_TOKEN', 'test')

from core import mention_utils


class DummyBot:
    def __init__(self):
        self._me = SimpleNamespace(id=999, username="RekkuBot")

    async def get_me(self):
        return self._me


def test_one_to_one_detection_with_explicit_count():
    bot = DummyBot()
    chat = SimpleNamespace(id=-100, type="group", title="Test")
    user = SimpleNamespace(id=1, is_bot=False, username="alice")
    message = SimpleNamespace(
        chat=chat,
        from_user=user,
        text="ciao",
        caption=None,
        entities=None,
        reply_to_message=None,
    )

    directed, reason = asyncio.run(
        mention_utils.is_message_for_bot(message, bot, human_count=1)
    )
    assert directed and reason is None

    directed, reason = asyncio.run(
        mention_utils.is_message_for_bot(message, bot, human_count=3)
    )
    assert not directed and reason == "multiple_humans"


def test_role_mention_detection(monkeypatch):
    bot = DummyBot()
    chat = SimpleNamespace(id=-100, type="group", title="Test")
    user = SimpleNamespace(id=1, is_bot=False, username="alice")
    message = SimpleNamespace(
        chat=chat,
        from_user=user,
        text="hello",
        caption=None,
        entities=None,
        reply_to_message=None,
        role_mentions=[1],
        bot_roles=[1],
    )

    directed, reason = asyncio.run(
        mention_utils.is_message_for_bot(message, bot, human_count=3)
    )
    assert directed and reason is None

    monkeypatch.setattr(mention_utils, "DISCORD_REACT_ROLES", False)
    directed, reason = asyncio.run(
        mention_utils.is_message_for_bot(message, bot, human_count=3)
    )
    assert not directed and reason == "multiple_humans"


def test_reply_to_bot_detection():
    bot = DummyBot()
    chat = SimpleNamespace(id=-100, type="group", title="Test")
    user = SimpleNamespace(id=1, is_bot=False, username="alice")
    reply_user = SimpleNamespace(id=999, username="RekkuBot")
    reply_message = SimpleNamespace(from_user=reply_user, message_id=10)
    message = SimpleNamespace(
        chat=chat,
        from_user=user,
        text="ciao",
        caption=None,
        entities=None,
        reply_to_message=reply_message,
    )

    directed, reason = asyncio.run(
        mention_utils.is_message_for_bot(message, bot, human_count=3)
    )
    assert directed and reason is None

