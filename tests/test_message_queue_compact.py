import os
import sys
import types
import asyncio
from types import SimpleNamespace
import pytest

# Ensure repository root on path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Stub out missing dependencies
class _Cursor:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, *args, **kwargs):
        return None

    async def fetchone(self):
        return None

class _Conn:
    async def cursor(self, *args, **kwargs):
        return _Cursor()

def _connect(**kwargs):
    return _Conn()

class Error(Exception):
    pass

dummy_aiomysql = types.ModuleType("aiomysql")
dummy_aiomysql.Connection = _Conn
dummy_aiomysql.Cursor = _Cursor
dummy_aiomysql.DictCursor = _Cursor
dummy_aiomysql.connect = _connect
dummy_aiomysql.Error = Error
sys.modules.setdefault("aiomysql", dummy_aiomysql)

# Stub telegram module
dummy_telegram = types.ModuleType("telegram")
class Update:
    pass
dummy_telegram.Update = Update
dummy_telegram_ext = types.ModuleType("telegram.ext")
class ContextTypes:
    DEFAULT_TYPE = object
dummy_telegram_ext.ContextTypes = ContextTypes
dummy_telegram.ext = dummy_telegram_ext
sys.modules.setdefault("telegram.ext", dummy_telegram_ext)
sys.modules.setdefault("telegram", dummy_telegram)

# Required environment variables for config import
os.environ.setdefault("BOTFATHER_TOKEN", "test")

from core import message_queue, plugin_instance, recent_chats


class DummyPlugin:
    def get_rate_limit(self):
        return 1000, 1, 0.0


class BotA:
    pass


class BotB:
    pass


class Msg:
    def __init__(self, chat_id, thread_id, text="", user_id=1):
        self.chat_id = chat_id
        self.message_thread_id = thread_id
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(title=None, username=None, first_name=None)

class StubQueue:
    def __init__(self):
        self._queue = []

    async def put(self, item):
        self._queue.append(item)

    async def get(self):
        while not self._queue:
            await asyncio.sleep(0)
        return self._queue.pop(0)

    def task_done(self):
        pass


def test_compact_respects_interface_and_thread(monkeypatch):
    async def scenario():
        monkeypatch.setattr(plugin_instance, "plugin", DummyPlugin())

        async def fake_track_chat(chat_id, meta):
            return None

        monkeypatch.setattr(recent_chats, "track_chat", fake_track_chat)

        message_queue._queue = StubQueue()

        bot_a = BotA()
        bot_b = BotB()

        msg1 = Msg(1, 10)
        msg2 = Msg(1, 10)
        msg3 = Msg(1, 20)
        msg4 = Msg(1, 10)

        await message_queue.enqueue(bot_a, msg1, None)
        await message_queue.enqueue(bot_a, msg2, None)
        await message_queue.enqueue(bot_a, msg3, None)
        await message_queue.enqueue(bot_b, msg4, None)

        _, first = await message_queue._queue.get()
        batch = await message_queue.compact_similar_messages(first)

        assert len(batch) == 2
        assert all(item["interface"] == "BotA" for item in batch)
        assert all(item["thread_id"] == 10 for item in batch)

        remaining = [item for _, item in message_queue._queue._queue]
        assert any(i["thread_id"] == 20 and i["interface"] == "BotA" for i in remaining)
        assert any(i["thread_id"] == 10 and i["interface"] == "BotB" for i in remaining)

    asyncio.run(scenario())


def test_batching_combines_text(monkeypatch):
    async def scenario():
        calls = []

        async def fake_handle(bot, message, context):
            calls.append(message.text)

        class Plugin:
            def get_rate_limit(self):
                return 1000, 1, 0.0

        plugin_instance.plugin = Plugin()
        monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)

        async def fake_track_chat(chat_id, meta):
            return None

        monkeypatch.setattr(recent_chats, "track_chat", fake_track_chat)

        message_queue._queue = StubQueue()

        bot = BotA()
        msg1 = Msg(1, 10, text="one")
        msg2 = Msg(1, 10, text="two")

        await message_queue.enqueue(bot, msg1, None)
        await message_queue.enqueue(bot, msg2, None)
        task = asyncio.create_task(message_queue._consumer_loop())
        await asyncio.sleep(0.1)
        task.cancel()
        await task

        assert calls == ["one\ntwo"]

    asyncio.run(scenario())


def test_messages_during_processing_are_grouped(monkeypatch):
    async def scenario():
        calls = []

        async def fake_handle(bot, message, context):
            calls.append(message.text)
            await asyncio.sleep(0.3)

        class Plugin:
            def get_rate_limit(self):
                return 1000, 1, 0.0

        plugin_instance.plugin = Plugin()
        monkeypatch.setattr(plugin_instance, "handle_incoming_message", fake_handle)

        async def fake_track_chat(chat_id, meta):
            return None

        monkeypatch.setattr(recent_chats, "track_chat", fake_track_chat)

        message_queue._queue = StubQueue()

        bot = BotA()
        msg1 = Msg(1, 10, text="first")
        await message_queue.enqueue(bot, msg1, None)

        task = asyncio.create_task(message_queue._consumer_loop())
        await asyncio.sleep(0.35)
        msg2 = Msg(1, 10, text="second")
        msg3 = Msg(1, 10, text="third")
        await message_queue.enqueue(bot, msg2, None)
        await message_queue.enqueue(bot, msg3, None)

        await asyncio.sleep(0.8)
        task.cancel()
        await task

        assert calls == ["first", "second\nthird"]

    asyncio.run(scenario())
