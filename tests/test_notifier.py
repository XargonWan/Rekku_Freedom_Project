import os
import pytest
os.environ.setdefault("BOTFATHER_TOKEN", "test")
from core import notifier, config
from core.core_initializer import INTERFACE_REGISTRY

class DummyIF:
    def __init__(self):
        self.sent = []
    async def send_message(self, payload):
        self.sent.append(payload)


def test_notify_trainer_sends_discord_dm(monkeypatch):
    dummy = DummyIF()
    INTERFACE_REGISTRY['discord_bot'] = dummy
    monkeypatch.setattr(config, 'NOTIFY_ERRORS_TO_INTERFACES', {'discord_bot': 999})
    notifier.notify_trainer('err')
    assert dummy.sent == [{'text': 'err', 'target': 999}]
    INTERFACE_REGISTRY.pop('discord_bot', None)
