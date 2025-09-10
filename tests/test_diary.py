#!/usr/bin/env python3
"""
Quick test script for AI Diary functionality
"""

import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_diary():
    """Test the AI diary functionality."""
    print("🧪 Testing AI Diary System...")
    
    try:
        from plugins.ai_diary import add_diary_entry_async, get_recent_entries, format_diary_for_injection, is_plugin_enabled
        
        # Test 0: Check if plugin is enabled
        print(f"\n0. Plugin status: {'✅ Enabled' if is_plugin_enabled() else '❌ Disabled'}")
        
        if not is_plugin_enabled():
            print("Plugin is disabled, attempting to enable...")
            from plugins.ai_diary import enable_plugin
            if enable_plugin():
                print("✅ Plugin enabled successfully")
            else:
                print("❌ Failed to enable plugin")
                return
        
        # Test 1: Add a diary entry
        print("\n1. Adding test diary entry...")
        await add_diary_entry_async(
            content="Test diary entry - System initialization completed successfully",
            tags=["test", "system", "startup"],
            involved=["TestUser"],
            emotions=[{"type": "satisfied", "intensity": 7}],
            interface="test",
            chat_id="test_chat",
            thread_id="0"
        )
        print("✅ Diary entry added")
        
        # Test 2: Get recent entries
        print("\n2. Retrieving recent entries...")
        entries = get_recent_entries(days=1)
        print(f"✅ Found {len(entries)} entries")
        
        # Test 3: Format for injection
        print("\n3. Formatting for injection...")
        formatted = format_diary_for_injection(entries)
        print("✅ Formatted entries:")
        print(formatted[:500] + "..." if len(formatted) > 500 else formatted)
        
        # Test 4: Test static injection
        print("\n4. Testing static injection...")
        from plugins.ai_diary import DiaryPlugin
        plugin = DiaryPlugin()
        injection = plugin.get_static_injection()
        print(f"✅ Static injection returned: {len(injection.get('diary', ''))} chars")
        
        print("\n🎉 All tests completed successfully!")
        
    except ImportError as e:
        print(f"❌ Plugin not available: {e}")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

async def test_diary_command():
    """Test the diary command."""
    print("\n🧪 Testing Diary Command...")
    
    try:
        from core.command_registry import diary_command
        
        result = await diary_command("1")
        print("✅ Diary command result:")
        print(result[:500] + "..." if len(result) > 500 else result)
        
    except Exception as e:
        print(f"❌ Command test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🤖 Rekku AI Diary Test Suite")
    print("=" * 40)
    
    try:
        asyncio.run(test_diary())
        asyncio.run(test_diary_command())
    except KeyboardInterrupt:
        print("\n👋 Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
