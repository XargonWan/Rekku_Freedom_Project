#!/usr/bin/env python3
"""
Test to verify the action validation fix.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:  # pragma: no cover - optional dependency
    from core.action_parser import validate_action  # type: ignore
    _test_valid, _ = validate_action(
        {"type": "message_telegram_bot", "payload": {"text": "x", "target": ["bad"]}}
    )
    _valid_action_parser = not _test_valid
except Exception:  # pragma: no cover - skip when deps missing
    validate_action = None
    _valid_action_parser = False


@unittest.skipUnless(_valid_action_parser, "Action parser dependencies not installed")
class TestTelegramActionValidation(unittest.TestCase):
    """Tests for telegram action validation."""

    def test_telegram_action_validation(self):
        action_string_target = {
            "type": "message_telegram_bot",
            "payload": {
                "text": "Eccomi! Rispondo col nuovo schema, ben allineata 🔧📡 Fammi sapere se passa ✨",
                "target": "-1002654768042",
                "message_thread_id": 2,
            },
        }
        action_int_target = {
            "type": "message_telegram_bot",
            "payload": {
                "text": "Eccomi! Rispondo col nuovo schema, ben allineata 🔧📡 Fammi sapere se passa ✨",
                "target": -1002654768042,
                "message_thread_id": 2,
            },
        }
        action_invalid_target = {
            "type": "message_telegram_bot",
            "payload": {
                "text": "Test message",
                "target": ["invalid", "target"],
                "message_thread_id": 2,
            },
        }

        valid, errors = validate_action(action_string_target)
        self.assertTrue(valid)
        self.assertFalse(errors)

        valid, errors = validate_action(action_int_target)
        self.assertTrue(valid)
        self.assertFalse(errors)

        valid, errors = validate_action(action_invalid_target)
        self.assertFalse(valid)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
