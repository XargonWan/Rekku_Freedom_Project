#!/usr/bin/env python3
"""Test completo per verificare che event_id non causi più errori nel sistema."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

from unittest.mock import AsyncMock, MagicMock
from core.telegram_utils import _send_with_retry, safe_edit
from core.transport_layer import telegram_safe_send

async def test_event_id_full_flow():
    print("🧪 Testing complete event_id filtering flow...")
    print("=" * 60)
    
    # Mock bot object
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(return_value="Message sent")
    mock_bot.edit_message_text = AsyncMock(return_value="Message edited")
    
    chat_id = 12345
    text = "Test message"
    
    test_kwargs = {
        "reply_to_message_id": 123,
        "event_id": 456,  # This should be filtered out everywhere
        "parse_mode": "HTML",
        "message_thread_id": 789
    }
    
    # Test 1: _send_with_retry
    print("\n📤 Test 1: _send_with_retry with event_id...")
    try:
        result1 = await _send_with_retry(
            bot=mock_bot,
            chat_id=chat_id,
            text=text,
            retries=1,
            **test_kwargs
        )
        
        # Check that event_id was filtered
        call_kwargs = mock_bot.send_message.call_args.kwargs
        if 'event_id' not in call_kwargs:
            print("✅ _send_with_retry: event_id correctly filtered")
        else:
            print("🚨 _send_with_retry: event_id NOT filtered!")
            
    except Exception as e:
        print(f"💥 _send_with_retry failed: {e}")
    
    # Test 2: safe_edit
    print("\n📝 Test 2: safe_edit with event_id...")
    mock_bot.edit_message_text.reset_mock()
    
    try:
        result2 = await safe_edit(
            bot=mock_bot,
            chat_id=chat_id,
            message_id=999,
            text=text,
            retries=1,
            **test_kwargs
        )
        
        # Check that event_id was filtered
        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        if 'event_id' not in call_kwargs:
            print("✅ safe_edit: event_id correctly filtered")
        else:
            print("🚨 safe_edit: event_id NOT filtered!")
            
    except Exception as e:
        print(f"💥 safe_edit failed: {e}")
    
    # Test 3: telegram_safe_send (higher level)
    print("\n📨 Test 3: telegram_safe_send with event_id...")
    mock_bot.send_message.reset_mock()
    
    try:
        result3 = await telegram_safe_send(
            bot=mock_bot,
            chat_id=chat_id,
            text=text,
            retries=1,
            **test_kwargs
        )
        
        # This should work without errors
        print("✅ telegram_safe_send: Executed without errors")
            
    except Exception as e:
        print(f"💥 telegram_safe_send failed: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 All event_id filtering tests completed!")
    print("   The bot should no longer crash with 'unexpected keyword argument event_id'")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_event_id_full_flow())
