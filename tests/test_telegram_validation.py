#!/usr/bin/env python3
"""
Test to verify the action validation fix.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.action_parser import validate_action

def test_telegram_action_validation():
    """Test validation of telegram action with both string and integer targets."""
    
    # Test with string target (should pass now)
    action_string_target = {
        "type": "message_telegram_bot",
        "payload": {
            "text": "Eccomi! Rispondo col nuovo schema, ben allineata 🔧📡 Fammi sapere se passa ✨",
            "target": "-1002654768042",  # String - should pass
            "message_thread_id": 2
        }
    }
    
    # Test with integer target (should pass)
    action_int_target = {
        "type": "message_telegram_bot", 
        "payload": {
            "text": "Eccomi! Rispondo col nuovo schema, ben allineata 🔧📡 Fammi sapere se passa ✨",
            "target": -1002654768042,  # Integer - should pass
            "message_thread_id": 2
        }
    }
    
    # Test with invalid target type (should fail)
    action_invalid_target = {
        "type": "message_telegram_bot",
        "payload": {
            "text": "Test message",
            "target": ["invalid", "target"],  # List - should fail
            "message_thread_id": 2
        }
    }
    
    print("Testing telegram action validation...")
    
    # Test string target
    valid, errors = validate_action(action_string_target)
    print(f"String target - Valid: {valid}, Errors: {errors}")
    
    # Test integer target
    valid, errors = validate_action(action_int_target)
    print(f"Integer target - Valid: {valid}, Errors: {errors}")
    
    # Test invalid target
    valid, errors = validate_action(action_invalid_target)
    print(f"Invalid target - Valid: {valid}, Errors: {errors}")

if __name__ == "__main__":
    test_telegram_action_validation()
