#!/usr/bin/env python3
"""Test script to check if plugin discovery works."""

import sys
import os
import types

sys.path.insert(0, os.path.abspath('.'))

# Mock environment to avoid config errors
os.environ['BOTFATHER_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'

# Create a lightweight stub for core.core_initializer to avoid heavy imports
core_initializer_stub = types.ModuleType("core.core_initializer")
core_initializer_stub.INTERFACE_REGISTRY = {}


def register_interface(name, obj):
    core_initializer_stub.INTERFACE_REGISTRY[name] = obj


core_initializer_stub.register_interface = register_interface
sys.modules['core.core_initializer'] = core_initializer_stub

from core.action_parser import _plugins_for, _load_action_plugins


class DummyTelegramInterface:
    @staticmethod
    def get_supported_actions():
        return {
            "message_telegram_bot": {
                "required_fields": ["text", "target"],
                "optional_fields": [],
            }
        }

    async def send_message(self, payload, original_message=None):
        pass


# Register dummy interface so MessagePlugin can discover actions
register_interface("telegram_bot", DummyTelegramInterface())

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
