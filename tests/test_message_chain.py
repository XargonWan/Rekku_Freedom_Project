import pytest
from types import SimpleNamespace

from core import message_chain


@pytest.mark.asyncio
async def test_system_json_error_skips_corrector(monkeypatch):
    """System messages of type 'error' should be blocked without correction."""
    called = False

    async def fake_corrector(*args, **kwargs):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr("core.transport_layer.run_corrector_middleware", fake_corrector)

    msg = SimpleNamespace(chat_id=123, text="", from_llm=False)
    result = await message_chain.handle_incoming_message(
        bot=None,
        message=msg,
        text='{"system_message": {"type": "error", "message": "fail"}}',
        source="interface",
    )

    assert result == message_chain.BLOCKED
    assert called is False


@pytest.mark.asyncio
@pytest.mark.parametrize("sm_type", ["event", "output"])
async def test_system_json_forwarded_without_corrector(monkeypatch, sm_type):
    """Event/output system messages should be forwarded without invoking the corrector."""
    called = False

    async def fake_corrector(*args, **kwargs):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr("core.transport_layer.run_corrector_middleware", fake_corrector)

    msg = SimpleNamespace(chat_id=123, text="", from_llm=False)
    result = await message_chain.handle_incoming_message(
        bot=None,
        message=msg,
        text=f'{{"system_message": {{"type": "{sm_type}", "message": "ok"}}}}',
        source="interface",
    )

    assert result == message_chain.FORWARD_AS_TEXT
    assert called is False


@pytest.mark.asyncio
async def test_non_llm_invalid_json_skips_corrector(monkeypatch):
    """Invalid JSON from non-LLM sources should bypass the corrector."""
    called = False

    async def fake_corrector(*args, **kwargs):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr("core.transport_layer.run_corrector_middleware", fake_corrector)

    msg = SimpleNamespace(chat_id=123, text="", from_llm=False)
    result = await message_chain.handle_incoming_message(
        bot=None,
        message=msg,
        text="{invalid}",
        source="interface",
    )

    assert result == message_chain.FORWARD_AS_TEXT
    assert called is False
