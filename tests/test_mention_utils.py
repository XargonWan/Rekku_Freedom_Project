import pytest
from types import SimpleNamespace
import sys, os

# Add parent directory to path so that 'core' can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import mention_utils

class DummyBot:
    def __init__(self):
        self._me = SimpleNamespace(id=999, username="RekkuBot")
    async def get_me(self):
        return self._me

def test_one_to_one_group_chat_detection():
    mention_utils._GROUP_CHAT_HUMANS.clear()
    bot = DummyBot()
    chat = SimpleNamespace(id=-100, type="group", title="Test")

    async def run_test():
        user1 = SimpleNamespace(id=1, is_bot=False, username="alice")
        message1 = SimpleNamespace(chat=chat, from_user=user1, text="ciao", caption=None, entities=None, reply_to_message=None)
        assert await mention_utils.is_message_for_bot(message1, bot)

        user2 = SimpleNamespace(id=2, is_bot=False, username="bob")
        message2 = SimpleNamespace(chat=chat, from_user=user2, text="hello", caption=None, entities=None, reply_to_message=None)
        assert not await mention_utils.is_message_for_bot(message2, bot)

        message3 = SimpleNamespace(chat=chat, from_user=user1, text="again", caption=None, entities=None, reply_to_message=None)
        assert not await mention_utils.is_message_for_bot(message3, bot)

    import asyncio
    asyncio.run(run_test())
