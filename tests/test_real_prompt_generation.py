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

# Use local log directory
os.environ['LOG_DIR'] = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(os.environ['LOG_DIR'], exist_ok=True)

# Ensure repository root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:  # pragma: no cover - optional components
    from core.prompt_engine import build_json_prompt  # type: ignore
    from core.core_initializer import core_initializer  # type: ignore
except Exception:  # Missing deps
    build_json_prompt = None  # type: ignore
    core_initializer = None  # type: ignore


@unittest.skipIf(build_json_prompt is None or core_initializer is None, "core components unavailable")
class TestPromptGeneration(unittest.TestCase):
    """Test per vedere il prompt JSON reale."""

    def test_prompt_generation(self):
        """Test per vedere come viene generato il prompt JSON reale."""
        print("\n🧪 Generazione REALE del prompt JSON...")
        print("=" * 80)

        async def run_test():
            try:
                from datetime import datetime

                await core_initializer.initialize_all()
                
                # Mock di un messaggio Telegram reale
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
                
                # Simula un messaggio Telegram in arrivo
                message = MockMessage()

                # Context memory vuoto (come sarebbe all'inizio)
                context_memory = {}

                # Genera il prompt reale usando la vera funzione
                prompt = await build_json_prompt(message, context_memory)
                
                # Verifica che il prompt sia stato generato
                self.assertIsNotNone(prompt)
                
                # Mostra il risultato
                formatted_prompt = json.dumps(prompt, indent=2, ensure_ascii=False)
                print(formatted_prompt)
                
                print("=" * 80)
                print("✅ Prompt generato con successo!")
                print(f"📊 Azioni disponibili: {len(prompt.get('actions', {}))}")
                
                if 'actions' in prompt:
                    for action_name in prompt['actions']:
                        print(f"  - {action_name}")
                
                return prompt
                
            except Exception as e:
                print(f"❌ Errore: {e}")
                import traceback
                traceback.print_exc()
                self.fail(f"Test fallito: {e}")
        
        # Esegui il test asincrono
        prompt = asyncio.run(run_test())
        
        # Verifica la struttura
        self.assertIn("actions", prompt)
        self.assertIn("context", prompt)
        self.assertIn("input", prompt)
        self.assertIn("instructions", prompt)


if __name__ == "__main__":
    unittest.main()
