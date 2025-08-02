#!/usr/bin/env python3
"""
Minimal test script to verify JSON generation for action instructions
without logging or database dependencies.
"""

import sys
import os
import json
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def mock_log(*args, **kwargs):
    """Mock logging function to avoid file system issues."""
    pass

def test_interface_only():
    """Test only interface action generation without full system."""
    print("🧪 Testing interface-only JSON generation...")
    
    try:
        # Mock the logging functions to avoid file system issues
        import core.logging_utils
        core.logging_utils.log_debug = mock_log
        core.logging_utils.log_info = mock_log
        core.logging_utils.log_warning = mock_log
        core.logging_utils.log_error = mock_log
        
        # Import the telegram interface class directly
        sys.path.insert(0, str(project_root / "interface"))
        
        # Create a minimal mock telegram bot
        class MockBot:
            pass
        
        # Import TelegramInterface
        from interface.telegram_bot import TelegramInterface
        
        # Test the interface methods
        interface = TelegramInterface(MockBot())
        
        print("📦 Testing TelegramInterface methods...")
        
        # Test get_supported_actions
        supported_actions = interface.get_supported_actions()
        print(f"✅ Supported actions: {json.dumps(supported_actions, indent=2)}")
        
        # Test get_prompt_instructions for message_telegram_bot
        instructions = interface.get_prompt_instructions("message_telegram_bot")
        print(f"✅ Prompt instructions: {json.dumps(instructions, indent=2)}")
        
        # Test get_prompt_instructions for unsupported action
        no_instructions = interface.get_prompt_instructions("unsupported_action")
        print(f"✅ No instructions for unsupported action: {no_instructions}")
        
        print("=" * 60)
        print("🎯 Interface test completed successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during interface test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_actions_structure():
    """Test building a complete actions structure manually."""
    print("\n🔧 Testing manual actions structure building...")
    
    try:
        # Create a sample actions structure like what the system would generate
        actions_structure = {
            "available_actions": {
                "message_telegram_bot": {
                    "description": "Send a text message via Telegram",
                    "interfaces": {
                        "telegram_bot": {
                            "required_fields": ["text", "target"],
                            "optional_fields": ["message_thread_id"]
                        }
                    }
                },
                "message_reddit": {
                    "description": "Post a submission or comment to Reddit",
                    "interfaces": {
                        "reddit": {
                            "required_fields": ["text", "target", "title"],
                            "optional_fields": ["thread_id"]
                        }
                    }
                }
            },
            "action_instructions": {
                "message_telegram_bot": {
                    "telegram_bot": {
                        "description": "Send a message via Telegram",
                        "payload": {
                            "text": {"type": "string", "example": "Hello!", "description": "The message text to send"},
                            "target": {"type": "integer", "example": 123456789, "description": "The chat_id of the recipient"},
                            "message_thread_id": {"type": "integer", "example": 456, "description": "Optional thread ID for group chats", "optional": True}
                        }
                    }
                },
                "message_reddit": {
                    "reddit": {
                        "description": "Send a post or comment on Reddit",
                        "payload": {
                            "text": {"type": "string", "example": "Post content here", "description": "The content of the post or comment"},
                            "target": {"type": "string", "example": "r/example_subreddit", "description": "The subreddit to post to"},
                            "title": {"type": "string", "example": "Optional post title", "description": "Title for new posts", "optional": True},
                            "thread_id": {"type": "string", "example": "abc123", "description": "Optional comment thread ID for replies", "optional": True}
                        }
                    }
                }
            }
        }
        
        print("📋 Sample actions structure:")
        print("=" * 60)
        formatted_json = json.dumps(actions_structure, indent=2, ensure_ascii=False)
        print(formatted_json)
        print("=" * 60)
        
        # Statistics
        available_actions = actions_structure.get('available_actions', {})
        action_instructions = actions_structure.get('action_instructions', {})
        
        print(f"📊 Statistics:")
        print(f"  - Available actions: {len(available_actions)}")
        print(f"  - Action instructions: {len(action_instructions)}")
        
        for action_type in available_actions:
            interfaces = available_actions[action_type].get('interfaces', {})
            print(f"  - {action_type}: {len(interfaces)} interfaces ({', '.join(interfaces.keys())})")
        
        print("🎯 Manual structure test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error during manual structure test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting minimal JSON generation tests...")
    print("=" * 60)
    
    # Test 1: Interface-only test
    success1 = test_interface_only()
    
    # Test 2: Manual structure test
    success2 = test_actions_structure()
    
    print("=" * 60)
    if success1 and success2:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("💥 Some tests failed!")
        sys.exit(1)
