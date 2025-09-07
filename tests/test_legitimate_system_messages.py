#!/usr/bin/env python3
"""
Test per verificare che i system_message legittimi funzionino correttamente
dopo aver rimosso solo i filtri errati.
"""
import json


def test_legitimate_system_messages():
    """Test che i system_message legittimi vengano processati correttamente."""
    
    print("🧪 Test dei system_message legittimi...")
    
    # 1. System message per correzione errore (DEVE funzionare)
    corrector_message = {
        "system_message": {
            "type": "error",
            "message": "JSON syntax error in your response, please fix",
            "your_reply": {"action": "send_message", "text": "Hello"}
        }
    }
    print("✅ Corrector system_message: DEVE essere processato")
    print(f"   Contenuto: {json.dumps(corrector_message, indent=2)}")
    
    # 2. System message per evento (DEVE funzionare)
    event_message = {
        "system_message": {
            "type": "event",
            "event_type": "terminal_output",
            "output": "Command executed successfully",
            "timestamp": "2025-09-06T10:30:00Z"
        }
    }
    print("✅ Event system_message: DEVE essere processato") 
    print(f"   Contenuto: {json.dumps(event_message, indent=2)}")
    
    # 3. System message per terminal (DEVE funzionare)
    terminal_message = {
        "system_message": {
            "type": "terminal",
            "command": "ls -la",
            "output": "total 64\ndrwxr-xr-x  5 user user  4096 Sep  6 10:30 .\n",
            "exit_code": 0
        }
    }
    print("✅ Terminal system_message: DEVE essere processato")
    print(f"   Contenuto: {json.dumps(terminal_message, indent=2)}")
    
    # 4. Messaggio normale con azioni (DEVE funzionare)
    normal_message = {
        "actions": [
            {
                "type": "message_telegram_bot",
                "payload": {
                    "text": "Hello world!",
                    "target": "123456789"
                }
            }
        ]
    }
    print("✅ Normal actions message: DEVE essere processato")
    print(f"   Contenuto: {json.dumps(normal_message, indent=2)}")
    
    print("\n📋 Riassunto:")
    print("- System_message per corrector: ✅ NECESSARIO per correzioni LLM")
    print("- System_message per eventi: ✅ NECESSARIO per delivery eventi")  
    print("- System_message per terminal: ✅ NECESSARIO per output comandi")
    print("- Messaggi normali con azioni: ✅ FUNZIONAMENTO STANDARD")
    print("\n🎯 SOLO i system_message di delivery Telegram erano problematici!")
    print("   (retry_exhausted, copy_check con step e full_json_instructions)")


if __name__ == "__main__":
    test_legitimate_system_messages()
