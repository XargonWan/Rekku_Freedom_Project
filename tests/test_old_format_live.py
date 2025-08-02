#!/usr/bin/env python3
"""Test per simulare un'azione con formato vecchio e verificare il sistema di retry."""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

from core.transport_layer import extract_json_from_text
from core.action_parser import validate_action

def test_old_format_parsing():
    print("🧪 Testing old format action parsing and validation...")
    print("=" * 60)
    
    # Test 1: Messaggio con formato vecchio
    old_format_text = '''
    {
        "type": "message",
        "interface": "telegram_bot",
        "payload": {
            "text": "Test messaggio con formato vecchio",
            "target": 12345
        }
    }
    '''
    
    # Test 2: Messaggio con formato nuovo 
    new_format_text = '''
    {
        "type": "message_telegram_bot",
        "payload": {
            "text": "Test messaggio con formato nuovo",
            "target": 12345
        }
    }
    '''
    
    test_cases = [
        ("❌ Old format", old_format_text, False),
        ("✅ New format", new_format_text, True)
    ]
    
    print("\n🔍 Testing JSON extraction and validation...")
    
    for name, text, should_be_valid in test_cases:
        print(f"\n📋 {name}")
        
        # Step 1: Extract JSON
        json_data = extract_json_from_text(text)
        print(f"   JSON extracted: {json_data is not None}")
        
        if json_data:
            print(f"   Extracted data: {json_data}")
            
            # Step 2: Validate action
            valid, errors = validate_action(json_data, {}, None)
            print(f"   Validation result: {'✅ Valid' if valid else '❌ Invalid'}")
            
            if errors:
                print(f"   Validation errors: {errors}")
            
            # Check result
            if valid == should_be_valid:
                print(f"   🎯 EXPECTED RESULT")
                if not valid:
                    print(f"   ✅ This would trigger retry system")
            else:
                print(f"   � UNEXPECTED! Expected {should_be_valid}, got {valid}")
        else:
            print(f"   💥 Failed to extract JSON from text")

if __name__ == "__main__":
    test_old_format_parsing()
