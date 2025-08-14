#!/usr/bin/env python3
"""Test per verificare che la validazione delle azioni respinga il formato vecchio."""


import sys
import os
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

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
