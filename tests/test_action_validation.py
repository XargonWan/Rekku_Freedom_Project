#!/usr/bin/env python3
"""Test per verificare che la validazione delle azioni respinga il formato vecchio."""


import sys
import os
import pytest
import types

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

# Stub core.core_initializer with a minimal registry
core_initializer_stub = types.ModuleType("core.core_initializer")
core_initializer_stub.INTERFACE_REGISTRY = {}


class CoreInitializer:
    def __init__(self):
        self.actions_block = {"available_actions": {}}

    def _build_actions_block(self):  # pragma: no cover - minimal stub
        return None


def register_interface(name, obj):
    core_initializer_stub.INTERFACE_REGISTRY[name] = obj


core_initializer_stub.register_interface = register_interface
core_initializer_stub.CoreInitializer = CoreInitializer
sys.modules['core.core_initializer'] = core_initializer_stub


class DummyTelegramInterface:
    @staticmethod
    def get_supported_actions():
        return {
            "message_telegram_bot": {
                "required_fields": ["text", "target"],
                "optional_fields": [],
            }
        }

    @staticmethod
    def validate_payload(action_type, payload):
        errors = []
        if not isinstance(payload.get("text"), str) or not payload.get("text"):
            errors.append("payload.text must be a non-empty string")
        if payload.get("target") is None:
            errors.append("payload.target is required for message_telegram_bot action")
        return errors

    async def send_message(self, payload, original_message=None):
        pass


# Register dummy interface so action_parser knows about message_telegram_bot
register_interface("telegram_bot", DummyTelegramInterface())

from core.action_parser import validate_action


valid_action = {
    "type": "message_telegram_bot",
    "payload": {
        "text": "Test message",
        "target": 12345
    }
}

old_format_action = {
    "type": "message",
    "interface": "telegram_bot",
    "payload": {
        "text": "Test message",
        "target": 12345
    }
}

invalid_action = {
    "type": "nonexistent_action",
    "payload": {
        "text": "Test message"
    }
}

@pytest.mark.parametrize("action,should_be_valid", [
    (valid_action, True),
    (old_format_action, False),
    (invalid_action, False)
])
def test_action_validation_cases(action, should_be_valid):
    valid, errors = validate_action(action, {}, None)
    if should_be_valid:
        assert valid, f"Expected valid, got invalid. Errors: {errors}"
    else:
        assert not valid, f"Expected invalid, got valid. Action: {action}"

if __name__ == "__main__":
    import pytest
    print("🧪 Esecuzione test con pytest...")
    pytest.main([__file__])
