#!/usr/bin/env python3
"""Test script for image processing integration."""

import asyncio
import os
import sys
from types import SimpleNamespace
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, '/videodrome/videodrome-deployment/Rekku_Freedom_Project')

# Mock the problematic imports for testing
sys.modules['aiomysql'] = SimpleNamespace()
sys.modules['core.config'] = SimpleNamespace(
    get_trainer_id=lambda: 31321637
)
sys.modules['core.interfaces_registry'] = SimpleNamespace(
    get_interface_registry=lambda: SimpleNamespace(
        is_trainer=lambda interface, user_id: user_id == 31321637
    )
)

from core.image_processor import get_image_processor, process_image_message
from core.abstract_context import AbstractContext, AbstractUser, AbstractMessage


async def test_image_processing():
    """Test the image processing system."""
    print("Testing Image Processing System...")
    
    # Set test environment
    os.environ['RESTRICT_ACTIONS'] = 'off'  # Allow all users for testing
    
    # Create test image data (simulating a Telegram photo)
    test_image_data = {
        "type": "photo",
        "file_id": "test_file_id_123",
        "file_unique_id": "test_unique_id_456",
        "width": 1280,
        "height": 720,
        "file_size": 1024000,
        "caption": "Test image for processing",
        "mime_type": "image/jpeg"
    }
    
    # Create test context
    test_user = AbstractUser(id=31321637, interface_name="telegram_bot")
    test_message = AbstractMessage(
        id=12345,
        text="Test message with image",
        chat_id=67890,
        interface_name="telegram_bot"
    )
    test_context = AbstractContext(
        interface_name="telegram_bot",
        user=test_user,
        message=test_message
    )
    
    # Test the processor
    processor = get_image_processor()
    print(f"Processor restrict mode: {processor.restrict_mode}")
    
    # Test access control
    allowed, reason = await processor.should_process_image(test_context, has_trigger=True)
    print(f"Access check result: {allowed} - {reason}")
    
    # Test image processing
    result = await processor.process_image_message(
        test_image_data, 
        test_context, 
        has_trigger=True,
        forward_to_llm=False  # Don't actually forward to LLM for test
    )
    
    if result:
        print("✅ Image processing successful!")
        print(f"Processed data keys: {list(result.keys())}")
        print(f"Source info: {result.get('source', {})}")
        print(f"Image metadata: {result.get('metadata', {})}")
    else:
        print("❌ Image processing failed or denied")
    
    print("Test completed.")


if __name__ == "__main__":
    asyncio.run(test_image_processing())