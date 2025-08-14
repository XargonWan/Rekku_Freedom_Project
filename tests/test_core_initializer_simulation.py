#!/usr/bin/env python3
"""Test per simulare il core_initializer e verificare che ManualAIPlugin non generi errori."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

def test_core_initializer_simulation():
    print("🧪 Testing core_initializer simulation with ManualAIPlugin...")
    print("=" * 60)
    
    try:
        # Simulate what core_initializer does when it finds ManualAIPlugin
        from llm_engines.manual import ManualAIPlugin
        
        print("📦 Found ManualAIPlugin class")
        
        # This is the call that was failing in core_initializer.py line 254
        print("🔍 Testing: obj.get_supported_actions() (static call)")
        
        try:
            supported = ManualAIPlugin.get_supported_actions()
            print(f"✅ SUCCESS: Static call returned: {supported}")
            print(f"   Type: {type(supported)}")
            
            if isinstance(supported, dict):
                print("✅ SUCCESS: Return type is dict as expected")
            else:
                print(f"🚨 WARNING: Expected dict, got {type(supported)}")
                
        except TypeError as e:
            if "missing 1 required positional argument: 'self'" in str(e):
                print(f"🚨 FAILED: The original error still exists: {e}")
            else:
                print(f"🚨 FAILED: Different TypeError: {e}")
        except Exception as e:
            print(f"💥 FAILED: Unexpected error: {e}")
            
        # Also test that hasattr works correctly
        print("\n🔍 Testing: hasattr(ManualAIPlugin, 'get_supported_actions')")
        has_method = hasattr(ManualAIPlugin, "get_supported_actions")
        print(f"   Result: {has_method}")
        
        if has_method:
            print("✅ SUCCESS: Method is detected by hasattr")
        else:
            print("🚨 FAILED: Method not detected by hasattr")
            
    except ImportError as e:
        print(f"💥 Import error: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Core initializer simulation completed!")
    print("   This simulates the exact scenario that was causing the 8:40 error")

if __name__ == "__main__":
    test_core_initializer_simulation()
