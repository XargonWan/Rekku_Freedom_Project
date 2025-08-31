import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('BOTFATHER_TOKEN', 'test')
os.environ.setdefault('OPENAI_API_KEY', 'test')

from core.telegram_utils import _send_with_retry, safe_edit
from core.transport_layer import telegram_safe_send


@pytest.mark.asyncio
async def test_event_id_filtered_from_helpers():
    kwargs = {
        "reply_to_message_id": 123,
        "event_id": 456,
        "parse_mode": "HTML",
        "thread_id": 789,
    }

    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(return_value="sent")

    await _send_with_retry(bot=mock_bot, chat_id=1, text="hi", retries=1, **kwargs)
    assert "event_id" not in mock_bot.send_message.call_args.kwargs
    assert mock_bot.send_message.call_args.kwargs["parse_mode"] == "HTML"

    mock_bot.edit_message_text = AsyncMock(return_value="edited")
    await safe_edit(bot=mock_bot, chat_id=1, message_id=2, text="hi", retries=1, **kwargs)
    assert "event_id" not in mock_bot.edit_message_text.call_args.kwargs

    mock_bot.send_message.reset_mock()
    await telegram_safe_send(bot=mock_bot, chat_id=1, text="hi", retries=1, **kwargs)
    assert "event_id" not in mock_bot.send_message.call_args.kwargs

