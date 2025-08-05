#!/usr/bin/env python3
"""
Test di validazione telegram semplificato.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:  # pragma: no cover - optional dependency
    from interface.telegram_bot import TelegramInterface  # type: ignore
except Exception:  # pragma: no cover - skip when deps missing
    TelegramInterface = None


@unittest.skipIf(TelegramInterface is None, "Telegram dependencies not installed")
class TestTelegramPayloadValidation(unittest.TestCase):
    """Simple tests for Telegram payload validation."""

    def test_telegram_payload_validation(self):
        print("Testing Telegram payload validation directly...")

        payload_string = {
            "text": "Test message",
            "target": "-1002654768042",
            "message_thread_id": 2,
        }
        payload_int = {
            "text": "Test message",
            "target": -1002654768042,
            "message_thread_id": 2,
        }
        payload_invalid = {
            "text": "Test message",
            "target": ["invalid", "target"],
            "message_thread_id": 2,
        }
        payload_missing = {"text": "Test message"}

        errors1 = TelegramInterface.validate_payload("message_telegram_bot", payload_string)
        self.assertEqual(errors1, [])

        errors2 = TelegramInterface.validate_payload("message_telegram_bot", payload_int)
        self.assertEqual(errors2, [])

        errors3 = TelegramInterface.validate_payload("message_telegram_bot", payload_invalid)
        self.assertTrue(errors3)

        errors4 = TelegramInterface.validate_payload("message_telegram_bot", payload_missing)
        self.assertTrue(errors4)


if __name__ == "__main__":
    unittest.main()
