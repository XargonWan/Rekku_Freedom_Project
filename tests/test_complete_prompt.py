#!/usr/bin/env python3
"""
Test script to show how the complete JSON prompt should look
for the LLM with the new action structure.
"""

import json
from core.prompt_engine import load_json_instructions

def create_sample_prompt():
    """Create a sample prompt structure as it would be sent to the LLM."""
    
    # Sample context
    context = {
        "messages": [
            {
                "message_id": 1280,
                "username": "Jay Cheshire",
                "usertag": "@Xargon",
                "text": "Rekku, send a message to the main channel",
                "timestamp": "2025-08-02T05:39:04+00:00"
            }
        ],
        "memories": [],
        "location": "Kizugawa,Japan",
        "weather": "Kizugawa,Japan: ☁️ Partly cloudy +34°C (Feels like 38°C, Humidity 56%, Wind 14km/h NNW, Visibility 10km, Pressure 1001hPa, Cloud cover 75%)",
        "date": "2025-08-02",
        "time": "14:39 JST (05:39 UTC)"
    }
    
    # Sample input
    input_data = {
        "type": "message",
        "payload": {
            "text": "Rekku, send a message to the main channel",
            "source": {
                "chat_id": -1002654768042,
                "message_id": 1280,
                "username": "Jay Cheshire",
                "usertag": "@Xargon",
                "message_thread_id": 2
            },
            "timestamp": "2025-08-02T05:39:04+00:00",
            "privacy": "default",
            "scope": "local"
        }
    }
    
    # Instructions
    instructions = load_json_instructions()
    
    # Available actions (simplified structure)
    available_actions = {
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
        },
        "event": {
            "description": "Create or schedule a future event",
            "interfaces": {
                "event": {
                    "required_fields": ["date", "description"],
                    "optional_fields": ["time", "repeat", "created_by"]
                }
            }
        }
    }
    
    # Action instructions (simplified structure)
    action_instructions = {
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
        },
        "event": {
            "event": {
                "description": "Schedule a future reminder or event",
                "payload": {
                    "date": {"type": "string", "example": "2025-07-30", "description": "Event date"},
                    "time": {"type": "string", "example": "13:00", "description": "Event time", "optional": True},
                    "repeat": {"type": "string", "example": "weekly", "description": "Repeat pattern", "optional": True},
                    "description": {"type": "string", "example": "Remind me to water the plants", "description": "Event description"},
                    "created_by": {"type": "string", "example": "rekku", "description": "Creator", "optional": True}
                }
            }
        }
    }
    
    # Complete prompt structure
    complete_prompt = {
        "context": context,
        "input": input_data,
        "instructions": instructions,
        "available_actions": available_actions,
        "action_instructions": action_instructions
    }
    
    return complete_prompt

def main():
    print("🧪 Creating sample LLM prompt with new action structure...")
    print("=" * 80)
    
    prompt = create_sample_prompt()
    
    # Pretty print the complete prompt
    formatted_prompt = json.dumps(prompt, indent=2, ensure_ascii=False)
    print(formatted_prompt)
    
    print("=" * 80)
    print("📊 Prompt Analysis:")
    print(f"  - Available action types: {len(prompt['available_actions'])}")
    
    for action_type, action_data in prompt['available_actions'].items():
        interfaces = action_data.get('interfaces', {})
        print(f"  - {action_type}: {list(interfaces.keys())}")
    
    print("\n🎯 This structure is much cleaner than the malformed JSON!")
    print("✅ Each action type is specific to its interface")
    print("✅ No complex nested interface mappings")
    print("✅ Clear field definitions with types and examples")
    print("✅ Consistent structure throughout")
    
    print("\n📝 Expected LLM response format:")
    sample_response = {
        "actions": [
            {
                "type": "message_telegram_bot",
                "interface": "telegram_bot",
                "payload": {
                    "text": "✨ Message sent to the main channel!",
                    "target": -1002654768042,
                    "message_thread_id": 2
                }
            }
        ]
    }
    
    print(json.dumps(sample_response, indent=2, ensure_ascii=False))
    
if __name__ == "__main__":
    main()
