#!/usr/bin/env python3
"""
Test di validazione telegram isolato.
"""

def test_target_validation():
    """Test della logica di validazione per target."""
    
    def validate_target(target):
        """Simula la validazione del target."""
        errors = []
        
        if target is not None:
            if isinstance(target, dict):
                # Complex format with chat_id and message_id
                chat_id = target.get("chat_id")
                message_id = target.get("message_id")
                if not isinstance(chat_id, (int, str)):
                    errors.append("payload.target.chat_id must be an int or string")
                if message_id is not None and not isinstance(message_id, int):
                    errors.append("payload.target.message_id must be an int")
            elif not isinstance(target, (int, str)):
                # Simple format: chat_id as int or string
                errors.append("payload.target must be an int, string (chat_id) or dict with chat_id and message_id")
        else:
            errors.append("payload.target is required for message_telegram_bot action")
        
        return errors
    
    print("Testing target validation logic...")
    
    # Test con stringa
    print("1. String target '-1002654768042':")
    errors1 = validate_target("-1002654768042")
    print(f"   Errors: {errors1}")
    print(f"   Valid: {len(errors1) == 0}")
    
    # Test con intero
    print("2. Integer target -1002654768042:")
    errors2 = validate_target(-1002654768042)
    print(f"   Errors: {errors2}")
    print(f"   Valid: {len(errors2) == 0}")
    
    # Test con target invalido
    print("3. Invalid target ['invalid', 'target']:")
    errors3 = validate_target(["invalid", "target"])
    print(f"   Errors: {errors3}")
    print(f"   Valid: {len(errors3) == 0}")
    
    # Test con target mancante
    print("4. Missing target (None):")
    errors4 = validate_target(None)
    print(f"   Errors: {errors4}")
    print(f"   Valid: {len(errors4) == 0}")
    
    # Test con formato dict
    print("5. Dict target with string chat_id:")
    dict_target = {"chat_id": "-1002654768042", "message_id": 123}
    errors5 = validate_target(dict_target)
    print(f"   Errors: {errors5}")
    print(f"   Valid: {len(errors5) == 0}")

if __name__ == "__main__":
    test_target_validation()
