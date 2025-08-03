#!/usr/bin/env python3
"""Test per verificare che event_id venga filtrato correttamente dai kwargs."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

from unittest.mock import AsyncMock, MagicMock
from core.telegram_utils import _send_with_retry

async def test_event_id_filtering():
    print("🧪 Testing event_id filtering in _send_with_retry...")
    print("=" * 60)
    
    # Mock bot object
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(return_value="Message sent")
    
    chat_id = 12345
    text = "Test message"
    
    # Test with event_id in kwargs (should be filtered out)
    kwargs_with_event_id = {
        "reply_to_message_id": 123,
        "event_id": 456,  # This should be filtered out
        "parse_mode": "HTML"
    }
    
    print("📤 Calling _send_with_retry with event_id in kwargs...")
    print(f"   Original kwargs: {kwargs_with_event_id}")
    
    try:
        result = await _send_with_retry(
            bot=mock_bot,
            chat_id=chat_id,
            text=text,
            retries=1,
            **kwargs_with_event_id
        )
        
        print(f"✅ Function call successful: {result}")
        
        # Check what arguments were passed to bot.send_message
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        
        print(f"📋 Arguments passed to bot.send_message:")
        print(f"   args: {call_args.args}")
        print(f"   kwargs: {call_args.kwargs}")
        
        # Verify event_id was filtered out
        if 'event_id' not in call_args.kwargs:
            print("✅ SUCCESS: event_id was correctly filtered out!")
        else:
            print("🚨 FAILURE: event_id was NOT filtered out!")
            
        # Verify other params were preserved
        expected_kwargs = {"reply_to_message_id": 123, "parse_mode": "HTML"}
        actual_kwargs = {k: v for k, v in call_args.kwargs.items() if k not in ['chat_id', 'text']}
        
        if actual_kwargs == expected_kwargs:
            print("✅ SUCCESS: Other parameters were preserved correctly!")
        else:
            print(f"🚨 FAILURE: Expected {expected_kwargs}, got {actual_kwargs}")
            
    except Exception as e:
        print(f"💥 Exception during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_event_id_filtering())
