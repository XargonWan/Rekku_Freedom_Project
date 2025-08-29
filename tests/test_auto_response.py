import os
import sys
from types import SimpleNamespace

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'


@pytest.mark.asyncio
async def test_request_llm_delivery_includes_from_user(monkeypatch):
    from core import auto_response

    captured = {}

    async def fake_handle(bot, message, prompt):
        captured['from_user'] = getattr(message, 'from_user', None)

    monkeypatch.setattr(
        "core.plugin_instance.handle_incoming_message", fake_handle
    )

    interface = SimpleNamespace()
    await auto_response.request_llm_delivery(
        message=None,
        interface=interface,
        context={"test": True},
        reason="unit_test_event",
    )

    assert captured['from_user'] is not None
