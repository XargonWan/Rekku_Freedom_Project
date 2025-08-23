import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault('BOTFATHER_TOKEN', 'test')
os.environ.setdefault('OPENAI_API_KEY', 'test')

from core.action_parser import validate_action
from interface.telegram_bot import TelegramInterface


def _action(payload):
    return {"type": "message_telegram_bot", "payload": payload}


def _payload(target):
    payload = {"text": "Test message", "target": target, "message_thread_id": 2}
    return payload


def test_validate_action_accepts_string_and_int_targets():
    for target in ("-1002654768042", -1002654768042):
        valid, errors = validate_action(_action(_payload(target)))
        assert valid, f"Unexpected errors: {errors}"


def test_validate_action_rejects_invalid_target():
    valid, _ = validate_action(_action(_payload(["invalid", "target"])))
    assert not valid


def test_telegram_interface_payload_validation():
    payload_ok_str = _payload("-1002654768042")
    payload_ok_int = _payload(-1002654768042)
    payload_bad = _payload(["invalid", "target"])
    payload_missing = {"text": "Test message"}

    assert TelegramInterface.validate_payload("message_telegram_bot", payload_ok_str) == []
    assert TelegramInterface.validate_payload("message_telegram_bot", payload_ok_int) == []
    assert TelegramInterface.validate_payload("message_telegram_bot", payload_bad) != []
    assert TelegramInterface.validate_payload("message_telegram_bot", payload_missing) != []

