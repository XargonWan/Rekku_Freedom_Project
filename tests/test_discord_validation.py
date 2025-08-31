import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault('DISCORD_BOT_TOKEN', 'test')
os.environ.setdefault('BOTFATHER_TOKEN', 'test')

from interface.discord_interface import DiscordInterface


def _payload(target):
    return {"text": "Test message", "target": target}


def test_validate_payload_accepts_string_and_int_targets():
    for target in ("1234567890", 1234567890):
        errors = DiscordInterface.validate_payload("message_discord_bot", _payload(target))
        assert errors == []


def test_validate_payload_rejects_invalid_target():
    errors = DiscordInterface.validate_payload("message_discord_bot", _payload(["invalid"]))
    assert errors != []


def test_validate_payload_requires_fields():
    assert DiscordInterface.validate_payload("message_discord_bot", {"target": "123"}) != []
    assert DiscordInterface.validate_payload("message_discord_bot", {"text": "hi"}) != []
