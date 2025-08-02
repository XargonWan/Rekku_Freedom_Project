#!/usr/bin/env python3
"""
Test script to verify JSON generation for action instructions
without starting the full bot system.
"""

import sys
import os
import json
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_json_generation():
    """Test the JSON generation for action instructions."""
    print("🧪 Testing JSON generation for action instructions...")
    
    try:
        # Import the core initializer
        from core.core_initializer import CoreInitializer
        
        # Create a test instance
        initializer = CoreInitializer()
        
        print("📦 Building actions block...")
        initializer._build_actions_block()
        
        # Get the generated actions block
        actions_block = initializer.actions_block
        
        print("✅ Actions block generated successfully!")
        print("📋 Generated JSON structure:")
        print("=" * 60)
        
        # Pretty print the JSON
        formatted_json = json.dumps(actions_block, indent=2, ensure_ascii=False)
        print(formatted_json)
        
        print("=" * 60)
        print(f"📊 Statistics:")
        print(f"  - Available actions: {len(actions_block.get('available_actions', {}))}")
        print(f"  - Action instructions: {len(actions_block.get('action_instructions', {}))}")
        
        # Check for specific action types
        available_actions = actions_block.get('available_actions', {})
        for action_type in available_actions:
            interfaces = available_actions[action_type].get('interfaces', {})
            print(f"  - {action_type}: {len(interfaces)} interfaces ({', '.join(interfaces.keys())})")
            
        return True
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_prompt_engine():
    """Test the prompt engine JSON generation."""
    print("\n🔬 Testing prompt engine JSON generation...")
    
    try:
        from core.prompt_engine import build_json_prompt
        
        # Create test context and input
        test_context = {
            "messages": [
                {
                    "message_id": 123,
                    "username": "Test User",
                    "usertag": "@testuser",
                    "text": "Hello, this is a test message",
                    "timestamp": "2025-08-02T12:00:00+00:00"
                }
            ],
            "memories": [],
            "location": "Test Location",
            "weather": "Test weather data",
            "date": "2025-08-02",
            "time": "12:00 UTC"
        }
        
        test_input = {
            "type": "message",
            "payload": {
                "text": "Hello, this is a test message",
                "source": {
                    "chat_id": -123456789,
                    "message_id": 123,
                    "username": "Test User",
                    "usertag": "@testuser",
                    "message_thread_id": 1
                },
                "timestamp": "2025-08-02T12:00:00+00:00",
                "privacy": "default",
                "scope": "local"
            }
        }
        
        print("🔧 Building JSON prompt...")
        prompt_data = build_json_prompt(test_context, test_input)
        
        print("✅ JSON prompt generated successfully!")
        print("📋 Generated prompt structure:")
        print("=" * 60)
        
        # Pretty print the JSON prompt
        formatted_prompt = json.dumps(prompt_data, indent=2, ensure_ascii=False)
        print(formatted_prompt)
        
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ Error during prompt engine test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting JSON generation tests...")
    print("=" * 60)
    
    # Test 1: Core initializer actions block
    success1 = test_json_generation()
    
    # Test 2: Prompt engine JSON
    success2 = test_prompt_engine()
    
    print("=" * 60)
    if success1 and success2:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("💥 Some tests failed!")
        sys.exit(1)
