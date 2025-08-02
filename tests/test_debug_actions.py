#!/usr/bin/env python3
"""Debug script to see what actions are available to the AI."""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from core.core_initializer import CoreInitializer
import json

def main():
    print("🔍 Debugging available actions...")
    print("=" * 60)
    
    # Initialize without database connection
    try:
        initializer = CoreInitializer()
        initializer._build_actions_block()
        
        actions = initializer.actions_block.get("available_actions", {})
        
        print(f"Found {len(actions)} action types:")
        print()
        
        for action_type, details in actions.items():
            print(f"📋 {action_type}")
            print(f"   Description: {details.get('description', 'N/A')}")
            print(f"   Required: {details.get('required_fields', [])}")
            print(f"   Optional: {details.get('optional_fields', [])}")
            instructions = details.get('instructions', {})
            if instructions:
                print(f"   Instructions: {json.dumps(instructions, indent=4)}")
            print()
        
        print("=" * 60)
        print("🎯 Full actions block:")
        print(json.dumps(actions, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
