#!/usr/bin/env python3
"""Test per verificare che ManualAIPlugin non generi più errori."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

def test_manual_ai_plugin():
    print("🧪 Testing ManualAIPlugin get_supported_actions...")
    print("=" * 60)
    
    try:
        from llm_engines.manual import ManualAIPlugin
        
        # Test 1: Static call (as done by core_initializer)
        print("\n📤 Test 1: Static call (ManualAIPlugin.get_supported_actions())")
        try:
            result = ManualAIPlugin.get_supported_actions()
            print(f"✅ SUCCESS: Static call returned: {result}")
        except Exception as e:
            print(f"🚨 FAILED: Static call error: {e}")
        
        # Test 2: Instance call (as done by action_parser)
        print("\n📦 Test 2: Instance call")
        try:
            instance = ManualAIPlugin()
            result = instance.get_supported_actions()
            print(f"✅ SUCCESS: Instance call returned: {result}")
        except Exception as e:
            print(f"🚨 FAILED: Instance call error: {e}")
            
        # Test 3: Check other methods are still working
        print("\n🔍 Test 3: Other methods functionality")
        try:
            instance = ManualAIPlugin()
            rate_limit = instance.get_rate_limit()
            print(f"✅ SUCCESS: get_rate_limit() returned: {rate_limit}")
        except Exception as e:
            print(f"🚨 FAILED: get_rate_limit() error: {e}")
            
    except ImportError as e:
        print(f"💥 Import error: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Manual AI Plugin tests completed!")

if __name__ == "__main__":
    test_manual_ai_plugin()
