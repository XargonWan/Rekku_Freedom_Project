#!/usr/bin/env python3
"""Test per verificare che la validazione delle azioni respinga il formato vecchio."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

try:
    from core.action_parser import validate_action
except ImportError as e:
    print(f"Error importing: {e}")
    print(f"Current path: {sys.path}")
    print(f"Looking for: core.action_parser")
    sys.exit(1)

def test_action_validation():
    print("🧪 Testing action validation...")
    print("=" * 60)
    
    # Test 1: Valid new format action
    valid_action = {
        "type": "message_telegram_bot",
        "payload": {
            "text": "Test message",
            "target": 12345
        }
    }
    
    # Test 2: Invalid old format action (should be rejected)
    old_format_action = {
        "type": "message",
        "interface": "telegram_bot", 
        "payload": {
            "text": "Test message",
            "target": 12345
        }
    }
    
    # Test 3: Completely invalid action type
    invalid_action = {
        "type": "nonexistent_action",
        "payload": {
            "text": "Test message"
        }
    }
    
    test_cases = [
        ("✅ Valid new format (message_telegram_bot)", valid_action, True),
        ("❌ Invalid old format (message + interface)", old_format_action, False), 
        ("❌ Completely invalid action type", invalid_action, False)
    ]
    
    print("\nTesting action validation...")
    all_passed = True
    
    for name, action, should_be_valid in test_cases:
        print(f"\n📋 {name}")
        print(f"   Action: {action}")
        
        try:
            valid, errors = validate_action(action, {}, None)
            print(f"   Result: {'✅ Valid' if valid else '❌ Invalid'}")
            
            if errors:
                print(f"   Errors: {errors}")
            
            # Check if result matches expectation
            if valid == should_be_valid:
                print(f"   🎯 EXPECTED RESULT")
            else:
                print(f"   🚨 UNEXPECTED RESULT! Expected {should_be_valid}, got {valid}")
                all_passed = False
                
        except Exception as e:
            print(f"   💥 Exception: {e}")
            if should_be_valid:
                print(f"   🚨 UNEXPECTED EXCEPTION!")
                all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Action validation works correctly.")
        print("   - New format actions are accepted")
        print("   - Old format actions are rejected (will trigger retry)")
        print("   - Invalid actions are rejected")
    else:
        print("🚨 SOME TESTS FAILED! There are issues with action validation.")
    
    return all_passed

if __name__ == "__main__":
    test_action_validation()
