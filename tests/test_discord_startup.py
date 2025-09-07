from types import SimpleNamespace

# Ensure environment token
import os
os.environ.setdefault('DISCORD_BOT_TOKEN', 'token')

import interface.discord_interface as di

def test_client_starts(monkeypatch):
    tasks = []
    fake_loop = SimpleNamespace(create_task=lambda coro: tasks.append(coro))
    monkeypatch.setattr(di.asyncio, 'get_event_loop', lambda: fake_loop)

    class DummyClient:
        def __init__(self, *args, **kwargs):
            self.handlers = {}

        def event(self, func):
            self.handlers[func.__name__] = func
            return func

        async def start(self, token):
            pass

    dummy_discord = SimpleNamespace(
        Intents=SimpleNamespace(default=lambda: SimpleNamespace(message_content=True)),
        Client=lambda intents: DummyClient(),
    )
    monkeypatch.setattr(di, 'discord', dummy_discord)

    di.DiscordInterface('token')
    assert any(getattr(coro, 'cr_code', None) and coro.cr_code.co_name == 'start' for coro in tasks)
