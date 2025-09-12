#!/usr/bin/env python3
"""
Script per impostare il LLM attivo nel database.
Questo script risolve il problema "Plugins: none" impostando selenium_chatgpt invece di manual.

Usage: python3 fix_llm.py
"""

import asyncio
import os
import sys

# Aggiungi il percorso root del progetto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def set_llm_engine():
    """Imposta selenium_chatgpt come LLM attivo."""
    try:
        print("Inizializzazione sistema...")
        
        # Setup environment
        os.environ['LOGGING_LEVEL'] = 'INFO'
        
        from core.db import ensure_core_tables
        from core.config import set_active_llm, get_active_llm
        from core.logging_utils import setup_logging
        
        # Setup logging
        setup_logging()
        
        print("Connessione al database...")
        # Ensure database tables exist
        await ensure_core_tables()
        
        print("Controllo LLM attuale...")
        # Check current LLM
        current = await get_active_llm()
        print(f"LLM attuale: {current}")
        
        # Set to selenium_chatgpt
        if current != "selenium_chatgpt":
            print("Aggiornamento LLM a selenium_chatgpt...")
            await set_active_llm("selenium_chatgpt")
            new_current = await get_active_llm()
            print(f"✅ LLM aggiornato da '{current}' a '{new_current}'")
        else:
            print("✅ LLM già impostato correttamente su selenium_chatgpt")
            
        print("\nRiavvia il bot per applicare le modifiche.")
            
    except Exception as e:
        print(f"❌ Errore durante l'impostazione del LLM: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(set_llm_engine())
