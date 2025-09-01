import os
import sys
import types
import json
import pytest

# Ensure required environment variables
os.environ.setdefault("TELEGRAM_TRAINER_ID", "123456")

# Stub minimal telegram modules before importing the interface
telegram = types.ModuleType("telegram")
telegram.Update = object
telegram.Bot = object
telegram.error = types.ModuleType("error")
telegram.error.TelegramError = Exception
telegram.error.RetryAfter = Exception
telegram.ext = types.ModuleType("ext")
telegram.ext.ApplicationBuilder = object
telegram.ext.MessageHandler = object
telegram.ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=None)
telegram.ext.CommandHandler = object
telegram.ext.filters = types.SimpleNamespace()
sys.modules["telegram"] = telegram
sys.modules["telegram.error"] = telegram.error
sys.modules["telegram.ext"] = telegram.ext

import core.plugin_instance as plugin_instance
from interface.telegram_bot import TelegramInterface

class DummyBot:
    async def send_message(self, *args, **kwargs):
        pass

class DummyPlugin:
    def __init__(self):
        self.calls = []

    async def handle_incoming_message(self, bot, message, payload_json):
        self.calls.append((bot, message, payload_json))

@pytest.mark.asyncio
async def test_emit_system_error_avoids_retry():
    orig_plugin = plugin_instance.plugin
    plugin = DummyPlugin()
    plugin_instance.plugin = plugin
    interface = TelegramInterface(DummyBot())
    payload = {"text": "hi", "target": "999"}
    await interface._emit_system_error("retry_exhausted", "failed", payload)
    assert len(plugin.calls) == 1
    payload_json = plugin.calls[0][2]
    data = json.loads(payload_json)
    assert "your_reply" not in data["system_message"]
    assert hasattr(plugin.calls[0][1], "from_user")
    plugin_instance.plugin = orig_plugin
