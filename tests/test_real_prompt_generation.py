#!/usr/bin/env python3
"""
Test per generare e visualizzare il prompt JSON reale con tutte le azioni disponibili.
Questo test inizializza il sistema completo di Rekku e mostra:
1. Il JSON completo che viene inviato all'LLM
2. Tutte le azioni disponibili (terminal, bash, message_telegram_bot, event, etc.)
3. La struttura unificata delle azioni con validazione dinamica
"""

import json
import sys
import os
import asyncio
import unittest

try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - fallback when dotenv missing
    def load_dotenv(*args, **kwargs):
        return False

# Load the real .env file if available
load_dotenv()

# Set up log directory to local logs folder for testing
os.environ['LOG_DIR'] = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(os.environ['LOG_DIR'], exist_ok=True)

# Aggiunge la directory principale al PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestPromptGeneration(unittest.TestCase):
    """Test per vedere il prompt JSON reale."""
    
    def test_prompt_generation(self):
        """Test per vedere come viene generato il prompt JSON reale."""
        print("\n🧪 Generazione REALE del prompt JSON...")
        print("=" * 80)
        
        async def run_test():
            try:
                from core.prompt_engine import build_json_prompt
                from datetime import datetime
                from core.core_initializer import core_initializer
            except Exception as e:
                raise unittest.SkipTest(f"Dependencies missing: {e}")

            await core_initializer.initialize_all()

            class MockUser:
                def __init__(self):
                    self.id = 123456789
                    self.full_name = "Jay Cheshire"
                    self.username = "Xargon"

            class MockMessage:
                def __init__(self):
                    self.chat_id = -1002654768042
                    self.message_id = 1280
                    self.text = "Rekku, send a message to the main channel"
                    self.from_user = MockUser()
                    self.date = datetime.fromisoformat("2025-08-02T05:39:04+00:00")
                    self.reply_to_message = None
                    self.message_thread_id = None

            message = MockMessage()
            context_memory = {}
            prompt = await build_json_prompt(message, context_memory)

            formatted_prompt = json.dumps(prompt, indent=2, ensure_ascii=False)
            print(formatted_prompt)
            return prompt

        try:
            prompt = asyncio.run(run_test())
        except unittest.SkipTest as e:
            self.skipTest(str(e))
            return

        self.assertIn("actions", prompt)
        self.assertIn("context", prompt)
        self.assertIn("input", prompt)
        self.assertIn("instructions", prompt)


if __name__ == "__main__":
    unittest.main()
