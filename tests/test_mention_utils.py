import os
import sys
from types import SimpleNamespace

import pytest

# Add parent directory to path so that 'core' can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('BOTFATHER_TOKEN', 'test')

from core import mention_utils


class DummyBot:
    def __init__(self):
        self._me = SimpleNamespace(id=999, username="RekkuBot")

    async def get_me(self):
        return self._me


@pytest.mark.asyncio
async def test_one_to_one_detection_with_explicit_count():
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

    directed, reason = await mention_utils.is_message_for_bot(
        message, bot, human_count=1
    )
    assert directed and reason is None

    directed, reason = await mention_utils.is_message_for_bot(
        message, bot, human_count=3
    )
    assert not directed and reason == "multiple_humans"


@pytest.mark.asyncio
async def test_no_auto_detection_when_count_unknown(monkeypatch):
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
    )

    directed, reason = await mention_utils.is_message_for_bot(message, bot)
    assert directed and reason is None

    monkeypatch.setattr(mention_utils, "REACT_TO_GROUPS", False)
    directed, reason = await mention_utils.is_message_for_bot(message, bot)
    assert not directed and reason == "missing_human_count"

