#!/usr/bin/env python3
"""
Test semplice per verificare la logica di filtraggio system_message.
"""
import json


def should_block_system_message(prompt):
    """
    Logica di filtraggio per system_message copiata dal plugin Selenium.
    Restituisce True se il messaggio deve essere bloccato.
    """
    try:
        if isinstance(prompt, str) and len(prompt.strip()) > 0:
            # Try to parse as JSON first
            try:
                prompt_json = json.loads(prompt.strip())
                if isinstance(prompt_json, dict) and "system_message" in prompt_json:
                    print(f"[FILTER] Blocking system_message from LLM processing: {prompt_json}")
                    return True
            except (json.JSONDecodeError, ValueError):
                # If not JSON, check for string patterns
                if "system_message" in prompt.lower():
                    print(f"[FILTER] Blocking system_message text from LLM processing: {prompt[:100]}...")
                    return True
        elif isinstance(prompt, dict) and "system_message" in prompt:
            print(f"[FILTER] Blocking system_message dict from LLM processing: {prompt}")
            return True
    except Exception as e:
        print(f"[FILTER] Error checking for system_message: {e}")
        # Continue processing if check fails
    return False


def test_system_message_filter():
    """Test che i system_message vengano bloccati correttamente."""
    
    # Test 1: system_message come dict
    print("\n=== Test 1: system_message come dict ===")
    system_msg_dict = {"system_message": "test system message"}
    blocked = should_block_system_message(system_msg_dict)
    assert blocked == True, "system_message dict dovrebbe essere bloccato"
    print("✓ system_message dict bloccato correttamente")
    
    # Test 2: system_message come JSON string
    print("\n=== Test 2: system_message come JSON string ===")
    system_msg_json = json.dumps({"system_message": "test system message"})
    blocked = should_block_system_message(system_msg_json)
    assert blocked == True, "system_message JSON dovrebbe essere bloccato"
    print("✓ system_message JSON bloccato correttamente")
    
    # Test 3: messaggio normale come dict
    print("\n=== Test 3: messaggio normale come dict ===")
    normal_msg = {"action": "send_message", "text": "Hello world"}
    blocked = should_block_system_message(normal_msg)
    assert blocked == False, "messaggio normale non dovrebbe essere bloccato"
    print("✓ messaggio normale passa correttamente")
    
    # Test 4: testo normale
    print("\n=== Test 4: testo normale ===")
    normal_text = "Hello, this is a normal message"
    blocked = should_block_system_message(normal_text)
    assert blocked == False, "testo normale non dovrebbe essere bloccato"
    print("✓ testo normale passa correttamente")
    
    # Test 5: testo con "system_message" nel contenuto (dovrebbe essere bloccato)
    print("\n=== Test 5: testo con 'system_message' nel contenuto ===")
    text_with_system = "This is a system_message in the text"
    blocked = should_block_system_message(text_with_system)
    assert blocked == True, "testo con 'system_message' dovrebbe essere bloccato"
    print("✓ testo con 'system_message' bloccato correttamente")
    
    # Test 6: JSON con system_message misto
    print("\n=== Test 6: JSON con system_message e altro ===")
    mixed_json = json.dumps({"action": "test", "system_message": "error", "text": "hello"})
    blocked = should_block_system_message(mixed_json)
    assert blocked == True, "JSON con system_message dovrebbe essere bloccato"
    print("✓ JSON con system_message bloccato correttamente")
    
    # Test 7: JSON valido senza system_message
    print("\n=== Test 7: JSON valido senza system_message ===")
    valid_json = json.dumps({"action": "send_message", "text": "Hello world", "chat_id": 123})
    blocked = should_block_system_message(valid_json)
    assert blocked == False, "JSON valido senza system_message non dovrebbe essere bloccato"
    print("✓ JSON valido passa correttamente")
    
    # Test 8: Stringa vuota
    print("\n=== Test 8: Stringa vuota ===")
    empty_string = ""
    blocked = should_block_system_message(empty_string)
    assert blocked == False, "stringa vuota non dovrebbe essere bloccata"
    print("✓ stringa vuota passa correttamente")
    
    # Test 9: None
    print("\n=== Test 9: None ===")
    none_value = None
    blocked = should_block_system_message(none_value)
    assert blocked == False, "None non dovrebbe essere bloccato"
    print("✓ None passa correttamente")
    
    print("\n🎉 Tutti i test sono passati! La logica di filtraggio system_message funziona correttamente.")
    print("\n📝 Riassunto:")
    print("- I messaggi con 'system_message' (dict, JSON, testo) vengono bloccati")
    print("- I messaggi normali passano senza problemi")
    print("- La logica gestisce correttamente casi edge come stringhe vuote e None")


if __name__ == "__main__":
    test_system_message_filter()
