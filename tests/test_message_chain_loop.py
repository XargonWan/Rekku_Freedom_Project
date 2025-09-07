#!/usr/bin/env python3
"""
Test per verificare che il message queue/chain loop sia sistemato.
"""

import unittest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from types import SimpleNamespace

try:
    import pytest
except ImportError:
    pytest = None

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.message_chain import handle_incoming_message, ACTIONS_EXECUTED, BLOCKED, FORWARD_AS_TEXT


class TestMessageChainLoop(unittest.TestCase):
    """Test che il message chain loop funzioni correttamente."""

    def setUp(self):
        """Setup per ogni test."""
        pass

    @patch('core.message_chain.extract_json_from_text')
    @patch('core.message_chain.run_actions')
    def test_system_message_blocked(self, mock_run_actions, mock_extract_json):
        """I messaggi di sistema devono essere bloccati per evitare loop."""
        # Sistema un messaggio di sistema
        system_message_text = '{"system_message": {"type": "error", "message": "test error"}}'
        mock_extract_json.return_value = {"system_message": {"type": "error", "message": "test error"}}

        bot = Mock()
        message = SimpleNamespace()
        message.chat_id = 123
        message.from_llm = True

        # Il messaggio di sistema deve essere bloccato
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(handle_incoming_message(bot, message, system_message_text, source="llm"))
        finally:
            loop.close()
        
        self.assertEqual(result, BLOCKED)
        # run_actions non deve essere chiamato per messaggi di sistema
        mock_run_actions.assert_not_called()

    @patch('core.message_chain.extract_json_from_text')
    @patch('core.message_chain.run_actions')
    def test_valid_json_actions_executed(self, mock_run_actions, mock_extract_json):
        """I messaggi con JSON valido devono eseguire le azioni e interrompere il loop."""
        # Sistema un messaggio con azioni valide
        valid_action_text = '{"actions": [{"type": "message", "payload": {"text": "hello"}}]}'
        mock_extract_json.return_value = {"actions": [{"type": "message", "payload": {"text": "hello"}}]}
        mock_run_actions.return_value = AsyncMock()

        bot = Mock()
        message = SimpleNamespace()
        message.chat_id = 123
        message.from_llm = True

        # Le azioni devono essere eseguite
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(handle_incoming_message(bot, message, valid_action_text, source="llm"))
        finally:
            loop.close()
        
        self.assertEqual(result, ACTIONS_EXECUTED)
        # run_actions deve essere chiamato una volta
        mock_run_actions.assert_called_once()

    @patch('core.message_chain.extract_json_from_text')
    @patch('core.message_chain.run_corrector_middleware')
    def test_non_llm_message_forwarded(self, mock_corrector, mock_extract_json):
        """I messaggi non-LLM con JSON invalido devono essere inoltrati senza correzione."""
        # Sistema un messaggio JSON-like ma non da LLM
        invalid_json_text = '{"incomplete": "json"'
        mock_extract_json.return_value = None  # JSON invalido

        bot = Mock()
        message = SimpleNamespace()
        message.chat_id = 123
        message.from_llm = False  # Non da LLM

        # Il messaggio deve essere inoltrato come testo
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(handle_incoming_message(bot, message, invalid_json_text, source="interface"))
        finally:
            loop.close()
        
        self.assertEqual(result, FORWARD_AS_TEXT)
        # Il corrector non deve essere chiamato
        mock_corrector.assert_not_called()

    @patch('core.message_chain.extract_json_from_text')
    @patch('core.message_chain.run_corrector_middleware')
    def test_corrector_prevents_system_message_loop(self, mock_corrector, mock_extract_json):
        """Il corrector deve prevenire loop con messaggi di sistema."""
        # Sistema un messaggio che contiene un messaggio di sistema del corrector
        system_error_text = 'Some text with system_message and error keywords'
        mock_extract_json.return_value = None  # JSON invalido
        mock_corrector.return_value = None  # Corrector fallisce

        bot = Mock()
        message = SimpleNamespace()
        message.chat_id = 123
        message.from_llm = True

        # Il messaggio deve essere bloccato per prevenire loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(handle_incoming_message(bot, message, system_error_text, source="llm"))
        finally:
            loop.close()
        
        self.assertEqual(result, BLOCKED)

    def test_non_json_message_forwarded(self):
        """I messaggi non JSON-like devono essere inoltrati direttamente."""
        plain_text = "Hello, this is just plain text"

        bot = Mock()
        message = SimpleNamespace()
        message.chat_id = 123

        # Il messaggio deve essere inoltrato come testo
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(handle_incoming_message(bot, message, plain_text, source="interface"))
        finally:
            loop.close()
        
        self.assertEqual(result, FORWARD_AS_TEXT)


if __name__ == '__main__':
    unittest.main()
