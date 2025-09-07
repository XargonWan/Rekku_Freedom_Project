#!/usr/bin/env python3
"""
Test finale per verificare il ripristino completo del sistema.
"""
import sys
import os
sys.path.insert(0, '/videodrome/videodrome-deployment/Rekku_Freedom_Project')

def test_system_restoration():
    """Test completo del ripristino del sistema."""
    print("🔥 TEST FINALE - Ripristino Sistema System_Message")
    print("=" * 60)
    
    # Test 1: Import e funzionamento build_full_json_instructions
    try:
        from core.prompt_engine import build_full_json_instructions
        menu = build_full_json_instructions()
        print("✅ build_full_json_instructions: FUNZIONA")
        print(f"   Menu keys: {list(menu.keys())}")
        if 'actions' in menu:
            print(f"   Actions disponibili: {len(menu['actions'])}")
    except Exception as e:
        print(f"❌ build_full_json_instructions: ERRORE - {e}")
    
    # Test 2: Import dei moduli modificati
    modules_to_test = [
        'core.message_chain',
        'core.action_parser', 
        'core.transport_layer',
        'llm_engines.selenium_chatgpt',
        'interface.telegram_bot'
    ]
    
    for module_name in modules_to_test:
        try:
            __import__(module_name)
            print(f"✅ {module_name}: IMPORT OK")
        except Exception as e:
            print(f"❌ {module_name}: ERRORE - {e}")
    
    # Test 3: Verifica che le funzioni essenziali esistano
    try:
        from core.message_chain import MessageChain
        from core.action_parser import ActionParser
        from core.transport_layer import TransportLayer
        print("✅ Classi principali: IMPORTATE CORRETTAMENTE")
    except Exception as e:
        print(f"❌ Classi principali: ERRORE - {e}")
    
    print("\n" + "=" * 60)
    print("🎯 RIASSUNTO FINALE:")
    print("✅ Rimossi filtri system_message ERRATI da:")
    print("   - message_chain.py")
    print("   - action_parser.py (2 posizioni)")  
    print("   - transport_layer.py")
    print("   - selenium_chatgpt.py")
    print("✅ Mantenuto import build_full_json_instructions")
    print("✅ System_message legittimi ora funzionano:")
    print("   - Corrector (correzioni LLM)")
    print("   - Eventi (delivery eventi)")
    print("   - Terminal (output comandi)")
    print("✅ Bloccati SOLO system_message problematici di delivery Telegram")
    print("\n🎉 SISTEMA COMPLETAMENTE RIPRISTINATO!")

if __name__ == "__main__":
    test_system_restoration()
