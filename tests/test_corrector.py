#!/usr/bin/env python3
"""
Test suite for the action parser corrector retry system.
"""

import unittest
import time
import pytest
from unittest.mock import Mock, patch
from types import SimpleNamespace

# Import the transport layer module
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.action_parser import (
    _get_retry_key,
    _should_retry,
    _increment_retry,
    _retry_tracker,
    corrector,
)
from core.transport_layer import extract_json_from_text


class TestCorrectorRetry(unittest.TestCase):
    """Test the retry system in action parser corrector."""
    
    def setUp(self):
        """Clear retry tracker before each test."""
        global _retry_tracker
        _retry_tracker.clear()
    
    def test_retry_key_generation(self):
        """Test that retry keys are generated correctly."""
        # Test with chat_id only
        message1 = SimpleNamespace()
        message1.chat_id = 12345
        message1.message_thread_id = None
        
        key1 = _get_retry_key(message1)
        self.assertEqual(key1, "12345_None")
        
        # Test with chat_id and thread_id
        message2 = SimpleNamespace()
        message2.chat_id = 12345
        message2.message_thread_id = 67890
        
        key2 = _get_retry_key(message2)
        self.assertEqual(key2, "12345_67890")
        
        # Test with missing attributes
        message3 = SimpleNamespace()
        key3 = _get_retry_key(message3)
        self.assertEqual(key3, "None_None")
    
    def test_should_retry_logic(self):
        """Test the retry logic."""
        message = SimpleNamespace()
        message.chat_id = 12345
        message.message_thread_id = None
        
        # First attempt should be allowed
        self.assertTrue(_should_retry(message, max_retries=2))
        
        # Increment retry count
        _increment_retry(message)
        self.assertTrue(_should_retry(message, max_retries=2))
        
        # Second increment
        _increment_retry(message)
        self.assertFalse(_should_retry(message, max_retries=2))
    
    def test_retry_cleanup(self):
        """Test that old retry entries are cleaned up."""
        message = SimpleNamespace()
        message.chat_id = 12345
        message.message_thread_id = None
        
        # Manually add an old entry
        retry_key = _get_retry_key(message)
        old_time = time.time() - 400  # 6+ minutes ago
        _retry_tracker[retry_key] = (1, old_time)
        
        # Should clean up and allow retry
        self.assertTrue(_should_retry(message, max_retries=2))
        self.assertNotIn(retry_key, _retry_tracker)
    
    def test_extract_json_system_messages(self):
        """Test that system messages are properly filtered out."""
        # System messages should return None
        self.assertIsNone(extract_json_from_text("[ERROR] Some error occurred"))
        self.assertIsNone(extract_json_from_text("[WARNING] Some warning"))
        self.assertIsNone(extract_json_from_text("[INFO] Some info"))
        self.assertIsNone(extract_json_from_text("[DEBUG] Some debug"))
        
        # Error reports should return None
        self.assertIsNone(extract_json_from_text('🚨 ACTION PARSING ERRORS DETECTED 🚨'))
        self.assertIsNone(extract_json_from_text('Please fix these actions'))
        
        # Valid JSON should parse
        valid_json = '{"type": "message", "payload": {"text": "Hello"}}'
        result = extract_json_from_text(valid_json)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "message")
    
    @patch('core.action_parser.log_warning')
    @patch('core.action_parser.log_info')
    @pytest.mark.asyncio
    async def test_corrector_max_retries(self, mock_log_info, mock_log_warning):
        """Test that max retries are respected."""
        message = SimpleNamespace()
        message.chat_id = 12345
        message.message_thread_id = None
        
        # Set retry count to max
        _increment_retry(message)
        _increment_retry(message)
        
        # Mock bot and errors
        mock_bot = Mock()
        errors = ["Missing 'type'", "Missing 'payload'"]
        failed_actions = [{"invalid": "action"}]
        
        # Should not retry when max reached
        await corrector(errors, failed_actions, mock_bot, message)
        
        # Verify warning was logged about max retries
        mock_log_warning.assert_called()
        warning_call = mock_log_warning.call_args[0][0]
        self.assertIn("Max retries", warning_call)
        self.assertIn("reached", warning_call)
    
    @patch('core.action_parser.log_warning')
    @pytest.mark.asyncio
    async def test_corrector_invalid_chat_id(self, mock_log_warning):
        """Test that invalid chat_id is handled properly."""
        message = SimpleNamespace()
        message.chat_id = None  # Invalid chat_id
        
        mock_bot = Mock()
        errors = ["Missing 'type'"]
        failed_actions = [{"invalid": "action"}]
        
        # Should not retry with invalid chat_id
        await corrector(errors, failed_actions, mock_bot, message)
        
        # Verify warning was logged about invalid chat_id
        mock_log_warning.assert_called()
        warning_call = mock_log_warning.call_args[0][0]
        self.assertIn("Cannot request correction", warning_call)
        self.assertIn("invalid chat_id", warning_call)
    
    def test_json_extraction_chatgpt_format(self):
        """Test extraction of JSON with ChatGPT prefixes."""
        # Test with "json\nCopy\nEdit\n" prefix
        chatgpt_text = 'json\nCopy\nEdit\n{"type": "message", "payload": {"text": "Hello"}}'
        result = extract_json_from_text(chatgpt_text)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "message")
        
        # Test with just "json\n" prefix
        simple_json_text = 'json\n{"type": "bash", "payload": {"command": "ls"}}'
        result = extract_json_from_text(simple_json_text)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "bash")


if __name__ == '__main__':
    unittest.main()
