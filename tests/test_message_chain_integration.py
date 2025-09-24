#!/usr/bin/env python3
"""Test message chain integration with fake messages."""

import unittest
import sys
import os
import json
from unittest.mock import patch, AsyncMock, MagicMock
from types import SimpleNamespace

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment variables - NO REAL API ACCESS
os.environ.setdefault('BOTFATHER_TOKEN', 'test_token')
os.environ.setdefault('OPENAI_API_KEY', 'test_key')
os.environ.setdefault('TRAINER_IDS', 'telegram_bot:12345')

class TestMessageChainIntegration(unittest.TestCase):
    """Test message chain processing with fake messages and mocked external services."""

    def setUp(self):
        """Set up test environment with all external services mocked."""
        # Mock all external dependencies to run completely offline
        self.db_patcher = patch('core.db.get_conn', new_callable=AsyncMock)
        self.db_patcher.start()

        self.llm_patcher = patch('core.config.get_active_llm', return_value={'engine': 'manual'})
        self.llm_patcher.start()

        self.interface_patcher = patch('core.transport_layer.llm_to_interface', new_callable=AsyncMock)
        self.interface_patcher.start()

    def tearDown(self):
        """Clean up patches."""
        self.llm_patcher.stop()
        self.interface_patcher.stop()
        self.db_patcher.stop()

    @patch('core.transport_layer.run_corrector_middleware')
    @patch('core.action_parser.run_actions')
    async def test_text_message_forwarded(self, mock_run_actions, mock_corrector):
        """Test that plain text messages are forwarded as TEXT."""
        from core import message_chain

        # Mock corrector to not be called for plain text
        mock_corrector.return_value = None

        # Create fake message
        msg = SimpleNamespace(
            chat_id=123,
            text="Hello world",
            from_llm=False
        )

        # Process message
        result = await message_chain.handle_incoming_message(
            bot=MagicMock(),  # Mock bot interface
            message=msg,
            text="Hello world",
            source="interface"
        )

        # Should forward as text
        self.assertEqual(result, message_chain.FORWARD_AS_TEXT)
        mock_corrector.assert_not_called()

    @patch('core.transport_layer.run_corrector_middleware')
    @patch('core.action_parser.run_actions')
    async def test_json_action_executed(self, mock_run_actions, mock_corrector):
        """Test that valid JSON actions are executed without real API calls."""
        from core import message_chain

        # Mock successful action execution
        mock_run_actions.return_value = True

        # Create fake message with JSON
        json_text = '{"type": "message_telegram_bot", "payload": {"text": "Test", "target": "123"}}'
        msg = SimpleNamespace(
            chat_id=123,
            text=json_text,
            from_llm=False
        )

        # Process message
        result = await message_chain.handle_incoming_message(
            bot=MagicMock(),  # Mock bot interface - no real Telegram/Discord calls
            message=msg,
            text=json_text,
            source="interface"
        )

        # Should execute actions
        self.assertEqual(result, message_chain.ACTIONS_EXECUTED)
        mock_run_actions.assert_called_once()

    @patch('core.transport_layer.run_corrector_middleware')
    @patch('core.action_parser.run_actions')
    async def test_invalid_json_corrected(self, mock_run_actions, mock_corrector):
        """Test that invalid JSON is corrected without calling real LLM."""
        from core import message_chain

        # Mock corrector to return valid JSON (simulates LLM correction without real API)
        mock_corrector.return_value = '{"type": "message_telegram_bot", "payload": {"text": "Corrected", "target": "123"}}'
        mock_run_actions.return_value = True

        # Create fake message with invalid JSON
        invalid_json = '{"type": "message_telegram_bot", "payload": {"text": "Test", "target": "123"'  # Missing closing brace
        msg = SimpleNamespace(
            chat_id=123,
            text=invalid_json,
            from_llm=False
        )

        # Process message
        result = await message_chain.handle_incoming_message(
            bot=MagicMock(),  # Mock bot - no real interface calls
            message=msg,
            text=invalid_json,
            source="interface"
        )

        # Should correct and execute
        self.assertEqual(result, message_chain.ACTIONS_EXECUTED)
        mock_corrector.assert_called_once()
        mock_run_actions.assert_called_once()

    @patch('core.transport_layer.run_corrector_middleware')
    @patch('core.action_parser.run_actions')
    async def test_system_message_blocked(self, mock_run_actions, mock_corrector):
        """Test that system messages are blocked."""
        from core import message_chain

        # Create system message
        system_json = '{"system_message": {"type": "output", "message": "test"}}'
        msg = SimpleNamespace(
            chat_id=123,
            text=system_json,
            from_llm=False
        )

        # Process message
        result = await message_chain.handle_incoming_message(
            bot=MagicMock(),  # Mock bot
            message=msg,
            text=system_json,
            source="interface"
        )

        # Should be blocked
        self.assertEqual(result, message_chain.BLOCKED)
        mock_corrector.assert_not_called()
        mock_run_actions.assert_not_called()

    def test_json_extraction(self):
        """Test JSON extraction from text."""
        from core.transport_layer import extract_json_from_text

        # Test valid JSON
        valid_json = '{"type": "test", "payload": {"key": "value"}}'
        result = extract_json_from_text(f"Some text {valid_json} more text")
        self.assertEqual(result, {"type": "test", "payload": {"key": "value"}})

        # Test no JSON
        result = extract_json_from_text("Just plain text")
        self.assertIsNone(result)

        # Test invalid JSON
        result = extract_json_from_text('{"invalid": json}')
        self.assertIsNone(result)


if __name__ == '__main__':
    # Run async tests
    import asyncio

    async def run_async_tests():
        suite = unittest.TestLoader().loadTestsFromTestCase(TestMessageChainIntegration)
        runner = unittest.TextTestRunner(verbosity=2)
        result = await runner.runAsync(suite)
        return result

    asyncio.run(run_async_tests())