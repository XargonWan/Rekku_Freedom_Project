import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault('DISCORD_BOT_TOKEN', 'test')
os.environ.setdefault('BOTFATHER_TOKEN', 'test')

import asyncio

from interface.discord_interface import discord_interface


def test_ping_response(monkeypatch):
    sent = []

    async def fake_send(channel_id, text):
        sent.append((channel_id, text))

    monkeypatch.setattr(discord_interface, '_discord_send', fake_send)

    message = SimpleNamespace(
        content='ping',
        author=SimpleNamespace(id=1, bot=False),
        channel=SimpleNamespace(id=123),
    )

    asyncio.run(discord_interface._process_message(message))
    assert sent == [(123, 'pong')]


def test_slash_command(monkeypatch):
    sent = []

    async def fake_send(channel_id, text):
        sent.append((channel_id, text))

    monkeypatch.setattr(discord_interface, '_discord_send', fake_send)

    with patch('interface.discord_interface.execute_command', new=AsyncMock(return_value='ok')) as mock_exec:
        message = SimpleNamespace(
            content='/help',
            author=SimpleNamespace(id=1, bot=False),
            channel=SimpleNamespace(id=999),
        )

        asyncio.run(discord_interface._process_message(message))
        mock_exec.assert_called_once_with('help')
        assert sent == [(999, 'ok')]


def test_message_forwarding(monkeypatch):
    calls = []

    async def fake_enqueue(bot, msg, ctx):
        calls.append(msg.text)

    monkeypatch.setattr('interface.discord_interface.message_queue.enqueue', fake_enqueue)

    message = SimpleNamespace(
        content='hi rekku',
        author=SimpleNamespace(id=2, bot=False, name='user', display_name='user'),
        channel=SimpleNamespace(id=55, name='chan'),
        id=444,
        created_at=None,
        guild=SimpleNamespace(id=1),
    )

    asyncio.run(discord_interface._process_message(message))
    assert calls == ['hi rekku']


def test_execute_action(monkeypatch):
    sent = []

    async def fake_send(channel_id, text):
        sent.append((channel_id, text))

    monkeypatch.setattr(discord_interface, '_discord_send', fake_send)

    action = {'type': 'message_discord_bot', 'payload': {'text': 'hi', 'target': '42'}}
    asyncio.run(discord_interface.execute_action(action, {}, None))
    assert sent == [('42', 'hi')]
