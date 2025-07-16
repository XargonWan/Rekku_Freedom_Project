#!/usr/bin/env python3
"""
Script di test per verificare l'integrazione della logica delle mention.
Da eseguire nel container Docker per testare la funzionalità.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_mention_detection():
    """Test della logica di riconoscimento delle mention."""
    from core.mention_utils import is_rekku_mentioned, is_message_for_bot
    
    # Test riconoscimento alias Rekku
    test_texts = [
        "Ciao rekku, come stai?",
        "Hey @rekku-chan puoi aiutarmi?", 
        "れっく può rispondere?",
        "Nessun alias qui",
        "Questa blu può fare qualcosa?",
        "Genietta aiutami!"
    ]
    
    print("🔍 Test riconoscimento alias Rekku:")
    for text in test_texts:
        result = is_rekku_mentioned(text)
        print(f"  '{text}' -> {result}")
    
    print("\n✅ Test alias completato\n")

def test_mention_integration():
    """Test dell'integrazione con telegram_bot.py."""
    try:
        from interface.telegram_bot import handle_message
        print("✅ Import di handle_message riuscito")
    except ImportError as e:
        print(f"❌ Import fallito (normale fuori dal container): {e}")
    
    try:
        from core.mention_utils import is_message_for_bot
        print("✅ Import di is_message_for_bot riuscito")
    except ImportError as e:
        print(f"❌ Import di is_message_for_bot fallito: {e}")
        return False
    
    return True

def test_selenium_plugin():
    """Test che il plugin selenium non abbia logica di mention conflittuale."""
    try:
        from llm_engines.selenium_chatgpt import SeleniumChatGPTPlugin
        plugin = SeleniumChatGPTPlugin()
        print("✅ Plugin Selenium importato correttamente")
        
        # Verifica che non ci siano metodi di mention nel plugin
        mention_methods = [attr for attr in dir(plugin) if 'mention' in attr.lower()]
        if mention_methods:
            print(f"⚠️ Trovati metodi mention nel plugin: {mention_methods}")
        else:
            print("✅ Nessun metodo mention nel plugin Selenium (corretto)")
        
        return True
    except ImportError as e:
        print(f"❌ Import plugin Selenium fallito (normale fuori dal container): {e}")
        return False

if __name__ == "__main__":
    print("🧪 Test integrazione logica mention\n")
    
    test_mention_detection()
    
    if test_mention_integration():
        print("✅ Integrazione telegram_bot OK")
    
    if test_selenium_plugin():
        print("✅ Plugin Selenium OK")
    
    print("\n🎉 Test completati!")
    print("\n📝 Per testare completamente:")
    print("1. Avvia il bot nel container Docker")
    print("2. Invia un messaggio che menziona Rekku in un gruppo")
    print("3. Rispondi a un messaggio del bot")
    print("4. Verifica che entrambi vengano riconosciuti come mention")
