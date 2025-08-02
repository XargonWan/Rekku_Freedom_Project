#!/usr/bin/env python3
"""Test script to check if plugin discovery works."""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

from core.action_parser import _plugins_for, _load_action_plugins

def main():
    print("🔍 Testing plugin discovery...")
    print("=" * 50)
    
    try:
        # Load all plugins first
        plugins = _load_action_plugins()
        print(f"📦 Loaded {len(plugins)} plugins:")
        for plugin in plugins:
            print(f"   - {plugin.__class__.__name__}")
        print()
        
        # Test specific action
        action_type = "message_telegram_bot"
        supporting_plugins = _plugins_for(action_type)
        
        print(f"🎯 Plugins supporting '{action_type}':")
        if supporting_plugins:
            for plugin in supporting_plugins:
                print(f"   ✅ {plugin.__class__.__name__}")
        else:
            print("   ❌ No plugins found!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
