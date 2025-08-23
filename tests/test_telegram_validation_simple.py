import unittest

try:  # pragma: no cover - optional dependency
    from interface.telegram_bot import TelegramInterface  # type: ignore
except Exception:  # Missing telegram or related deps
    TelegramInterface = None


@unittest.skipIf(TelegramInterface is None, "telegram interface unavailable")
class TestTelegramPayloadValidation(unittest.TestCase):
    def test_payload_validation(self):
        payload = {"text": "hi", "target": 1}
        errors = TelegramInterface.validate_payload("message_telegram_bot", payload)
        self.assertEqual(errors, [])
