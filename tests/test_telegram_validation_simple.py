#!/usr/bin/env python3
"""
Test di validazione telegram semplificato.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Test diretto della validazione telegram
from interface.telegram_bot import TelegramInterface

def test_telegram_payload_validation():
    """Test della validazione del payload telegram."""
    
    print("Testing Telegram payload validation directly...")
    
    # Test con target stringa (dovrebbe passare)
    payload_string = {
        "text": "Test message",
        "target": "-1002654768042",
        "message_thread_id": 2
    }
    
    # Test con target intero (dovrebbe passare)
    payload_int = {
        "text": "Test message", 
        "target": -1002654768042,
        "message_thread_id": 2
    }
    
    # Test con target invalido (dovrebbe fallire)
    payload_invalid = {
        "text": "Test message",
        "target": ["invalid", "target"],
        "message_thread_id": 2
    }
    
    # Test con campo mancante (dovrebbe fallire)
    payload_missing = {
        "text": "Test message"
        # target mancante
    }
    
    print("1. String target:")
    errors1 = TelegramInterface.validate_payload("message_telegram_bot", payload_string)
    print(f"   Errors: {errors1}")
    print(f"   Valid: {len(errors1) == 0}")
    
    print("2. Integer target:")
    errors2 = TelegramInterface.validate_payload("message_telegram_bot", payload_int)
    print(f"   Errors: {errors2}")
    print(f"   Valid: {len(errors2) == 0}")
    
    print("3. Invalid target:")
    errors3 = TelegramInterface.validate_payload("message_telegram_bot", payload_invalid)
    print(f"   Errors: {errors3}")
    print(f"   Valid: {len(errors3) == 0}")
    
    print("4. Missing target:")
    errors4 = TelegramInterface.validate_payload("message_telegram_bot", payload_missing)
    print(f"   Errors: {errors4}")
    print(f"   Valid: {len(errors4) == 0}")

if __name__ == "__main__":
    test_telegram_payload_validation()
