import ast
from pathlib import Path
import sys
import os
import pytest
import asyncio
import types

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("BOTFATHER_TOKEN", "test")

# Stub minimal telegram module for tests
telegram = types.ModuleType("telegram")
telegram.error = types.ModuleType("error")

class TimedOut(Exception):
    pass

telegram.error.TimedOut = TimedOut
sys.modules["telegram"] = telegram
sys.modules["telegram.error"] = telegram.error
aiomysql_module = types.ModuleType("aiomysql")
aiomysql_module.Connection = object
aiomysql_module.Cursor = object
sys.modules["aiomysql"] = aiomysql_module

from interface.telegram_utils import send_with_thread_fallback


def test_send_message_uses_markdown_parse_mode():
    tree = ast.parse(Path("interface/telegram_bot.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_message":
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and getattr(getattr(call, "func", None), "id", "") == "send_with_thread_fallback":
                    for kw in call.keywords:
                        if kw.arg == "parse_mode" and isinstance(kw.value, ast.Constant):
                            assert kw.value.value == "Markdown"
                            return
    assert False, "parse_mode='Markdown' not found in send_with_thread_fallback call"


class DummyBadRequest(Exception):
    pass


class DummyBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("parse_mode"):
            raise DummyBadRequest(
                "Can't parse entities: can't find end of the entity starting at byte offset 1"
            )


def test_parse_mode_fallback_on_bad_entities():
    bot = DummyBot()
    asyncio.run(send_with_thread_fallback(bot, 123, "hello_from_user_", parse_mode="Markdown"))
    # First call should include parse_mode, second should not
    assert len(bot.calls) == 2
    assert bot.calls[0]["parse_mode"] == "Markdown"
    assert "parse_mode" not in bot.calls[1]
