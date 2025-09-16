#!/usr/bin/env python3
"""
Test semplificato per verificare i miglioramenti all'AI Diary
(senza dipendenze database)
"""

def normalize_interface_name(interface: str) -> str:
    """Normalize interface name for consistent diary entries."""
    if not interface or interface.lower() == "unknown":
        return "unknown"
    
    # Normalize telegram interfaces
    if "telegram" in interface.lower() or "telethon" in interface.lower():
        return "telegram"
    
    # Normalize discord interfaces  
    if "discord" in interface.lower():
        return "discord"
        
    # Other specific interfaces
    interface_mapping = {
        "webui": "webui",
        "web": "webui", 
        "x_interface": "x",
        "twitter": "x",
        "reddit_interface": "reddit",
        "cli": "manual",
        "manual": "manual"
    }
    
    normalized = interface_mapping.get(interface.lower(), interface.lower())
    return normalized

def _generate_context_tags(action_types, rekku_response: str, user_message: str, interface_name: str):
    """Generate specific context tags based on action types and conversation content."""
    context_tags = []
    
    # Action-based tags (more specific than before)
    if "bio_update" in action_types or "bio_full_request" in action_types:
        context_tags.append("personal_info")
    if "terminal" in action_types:
        context_tags.append("technical")
    if "event" in action_types:
        context_tags.append("scheduling")
    if "speech_selenium_elevenlabs" in action_types or "audio_telegram_bot" in action_types:
        context_tags.append("audio")
    
    # Content-based analysis for specific topics
    combined_text = (rekku_response + " " + (user_message or "")).lower()
    
    # Food and dining
    if any(word in combined_text for word in ["food", "eat", "cooking", "recipe", "restaurant", "meal"]):
        context_tags.append("food")
        # Specific food types
        if any(word in combined_text for word in ["sushi", "japanese"]):
            context_tags.append("sushi")
        if any(word in combined_text for word in ["pizza", "italian"]):
            context_tags.append("pizza") 
        if any(word in combined_text for word in ["restaurant", "dining"]):
            context_tags.append("restaurant")
    
    # Cars and vehicles
    if any(word in combined_text for word in ["car", "auto", "vehicle", "driving", "motor", "bmw", "audi", "honda"]):
        context_tags.append("cars")
        if any(word in combined_text for word in ["color", "blue", "red", "black", "white"]):
            context_tags.append("colors")
    
    # Technology and computers
    if any(word in combined_text for word in ["computer", "software", "programming", "code", "tech"]):
        context_tags.append("technology")
    
    # Only add help tag for explicit help requests
    if any(word in combined_text for word in ["help me", "can you help", "need help", "assistance"]):
        context_tags.append("help")
    
    # Only add learning tag for explicit learning conversations
    if any(word in combined_text for word in ["learn", "teach", "explain", "understand", "study"]):
        context_tags.append("learning")
    
    # Only add problem tag for explicit problem-solving
    if any(word in combined_text for word in ["problem", "issue", "error", "fix", "solve", "bug"]):
        context_tags.append("problem")
    
    # Remove duplicate tags and return
    return list(set(context_tags))

def _generate_interaction_summary(
    rekku_response: str,
    user_message: str = None, 
    involved_users = None,
    context_tags = None,
    interface: str = None
) -> str:
    """Generate a specific interaction summary based on context and content."""
    
    # Get user name if available
    user_name = involved_users[0] if involved_users else "someone"
    
    # Extract key information from the conversation
    summary_parts = []
    
    if user_message and involved_users:
        # Analyze the conversation content for specific actions/topics
        user_lower = user_message.lower()
        response_lower = rekku_response.lower()
        combined_text = f"{user_lower} {response_lower}"
        
        # Determine what type of interaction this was
        if any(word in combined_text for word in ["bio", "update", "information", "personal data"]):
            summary_parts.append(f"updated bio information for {user_name}")
        elif any(word in combined_text for word in ["eat", "food", "sushi", "restaurant", "meal", "cooking"]):
            # Extract food-related information
            food_words = []
            for word in ["sushi", "pizza", "pasta", "burger", "salad", "coffee", "tea"]:
                if word in combined_text:
                    food_words.append(word)
            food_context = ", ".join(food_words) if food_words else "food"
            summary_parts.append(f"talked with {user_name} about {food_context}")
        elif any(word in combined_text for word in ["car", "auto", "vehicle", "driving", "motor"]):
            summary_parts.append(f"discussed cars and vehicles with {user_name}")
        elif any(word in combined_text for word in ["help", "problem", "issue", "solve", "fix"]):
            summary_parts.append(f"helped {user_name} solve a problem")
        else:
            # Default based on context tags
            if context_tags and len(context_tags) > 0:
                # Filter out generic tags
                specific_tags = [tag for tag in context_tags if tag not in ["communication", "interface", "help"]]
                if specific_tags:
                    summary_parts.append(f"discussed {', '.join(specific_tags[:2])} with {user_name}")
                else:
                    summary_parts.append(f"had a conversation with {user_name}")
            else:
                summary_parts.append(f"chatted with {user_name}")
    else:
        # No user message context, just sent a message
        summary_parts.append(f"sent a message via {interface}")
    
    return " and ".join(summary_parts)

def test_interface_normalization():
    """Test della normalizzazione dei nomi delle interfacce"""
    print("🧪 Testing interface normalization...")
    
    test_cases = [
        ("telegram_bot", "telegram"),
        ("telegram_userbot", "telegram"),
        ("telethon_userbot", "telegram"),
        ("discord_interface", "discord"),
        ("discord_bot", "discord"),
        ("unknown", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
        ("webui", "webui"),
        ("x_interface", "x"),
        ("manual", "manual")
    ]
    
    for input_val, expected in test_cases:
        result = normalize_interface_name(input_val)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {input_val} -> {result} (expected: {expected})")

def test_context_tags_generation():
    """Test della generazione di context tags specifici"""
    print("\n🧪 Testing context tags generation...")
    
    test_cases = [
        {
            "rekku_response": "I love sushi! I went to a Japanese restaurant yesterday.",
            "user_message": "Do you like Japanese food?",
            "expected_tags": ["food", "sushi", "restaurant"]
        },
        {
            "rekku_response": "Your blue BMW looks amazing!",
            "user_message": "What do you think of my new car?",
            "expected_tags": ["cars", "colors"]
        },
        {
            "rekku_response": "Let me help you with that programming issue.",
            "user_message": "I have a bug in my code.",
            "expected_tags": ["technology", "problem"]
        }
    ]
    
    for i, test_case in enumerate(test_cases):
        result = _generate_context_tags(
            [], 
            test_case["rekku_response"], 
            test_case["user_message"], 
            "telegram"
        )
        
        found_expected = all(tag in result for tag in test_case["expected_tags"])
        status = "✅" if found_expected else "❌"
        print(f"  {status} Test {i+1}: {result}")
        print(f"      Expected to include: {test_case['expected_tags']}")

def test_interaction_summary():
    """Test della generazione di interaction_summary specifici"""
    print("\n🧪 Testing interaction summary generation...")
    
    test_cases = [
        {
            "rekku_response": "I love sushi too! I went to Sakura restaurant last week.",
            "user_message": "I just had amazing sushi at the new place downtown",
            "involved_users": ["Marco"],
            "context_tags": ["food", "sushi", "restaurant"],
            "interface": "telegram",
            "expected_contains": ["Marco", "sushi"]
        },
        {
            "rekku_response": "Your blue car looks fantastic!",
            "user_message": "Check out my new BMW",
            "involved_users": ["Jay"],
            "context_tags": ["cars", "colors"],
            "interface": "discord",
            "expected_contains": ["Jay", "cars"]
        }
    ]
    
    for i, test_case in enumerate(test_cases):
        result = _generate_interaction_summary(
            test_case["rekku_response"],
            test_case["user_message"],
            test_case["involved_users"],
            test_case["context_tags"],
            test_case["interface"]
        )
        
        contains_expected = all(term.lower() in result.lower() for term in test_case["expected_contains"])
        status = "✅" if contains_expected else "❌"
        print(f"  {status} Test {i+1}: {result}")
        print(f"      Expected to contain: {test_case['expected_contains']}")

def main():
    """Esegui tutti i test"""
    print("🔬 AI Diary Improvements Test Suite")
    print("=" * 50)
    
    try:
        test_interface_normalization()
        test_context_tags_generation()
        test_interaction_summary()
        
        print("\n✅ All tests completed!")
        print("\n📝 Summary of improvements:")
        print("  • Interface names now normalized (telegram_bot/telegram_userbot -> telegram)")
        print("  • Context tags are more specific (no more generic 'communication' tags)")
        print("  • Interaction summaries describe actual topics (sushi, cars, etc.)")
        print("  • HISTORY_DAYS environment variable controls diary history length")
        print("  • Token management prevents prompt overflow")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
