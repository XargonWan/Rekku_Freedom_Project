#!/usr/bin/env python3
"""
Test script for mention detection functionality.
Run this in the Docker container to test if reply detection works correctly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_mention_detection_detailed():
    """Test della logica di riconoscimento delle mention con debug dettagliato."""
    from core.mention_utils import is_rekku_mentioned, is_message_for_bot
    from core.logging_utils import setup_logging, log_debug, log_info
    
    # Setup logging per vedere i debug
    setup_logging()
    
    print("🔍 Test dettagliato riconoscimento mention")
    print("=" * 50)
    
    # Test basic alias recognition
    print("\n1. Test riconoscimento alias Rekku:")
    test_texts = [
        "Ciao rekku, come stai?",
        "Hey @rekku-chan puoi aiutarmi?", 
        "れっく può rispondere?",
        "Nessun alias qui",
        "Questa blu può fare qualcosa?",
        "Genietta aiutami!"
    ]
    
    for text in test_texts:
        result = is_rekku_mentioned(text)
        print(f"  '{text}' -> {result}")
    
    print("\n2. Test simulazione reply detection:")
    
    # Mock classes for testing
    class MockUser:
        def __init__(self, user_id, username=None):
            self.id = user_id
            self.username = username
    
    class MockChat:
        def __init__(self, chat_type):
            self.type = chat_type
    
    class MockMessage:
        def __init__(self, chat_type, text="", from_user=None, reply_to_message=None):
            self.chat = MockChat(chat_type)
            self.text = text
            self.caption = None
            self.entities = []
            self.from_user = from_user
            self.reply_to_message = reply_to_message
    
    class MockBot:
        def __init__(self, bot_id, username):
            self.id = bot_id
            self.username = username
            self.user = MockUser(bot_id, username)
        
        def get_me(self):
            return MockUser(self.id, self.username)
    
    # Test bot
    bot = MockBot(123456789, "rekku_freedom_project")
    
    # Test cases
    test_cases = [
        {
            "name": "Private message",
            "message": MockMessage("private", "Hello"),
            "expected": True
        },
        {
            "name": "Group message with Rekku alias",
            "message": MockMessage("group", "Hey Rekku, how are you?"),
            "expected": True
        },
        {
            "name": "Reply to bot message (by ID)",
            "message": MockMessage("group", "Thanks!", reply_to_message=MockMessage("group", "Bot response", from_user=MockUser(123456789, "rekku_freedom_project"))),
            "expected": True
        },
        {
            "name": "Reply to bot message (by username)",
            "message": MockMessage("group", "Thanks!", reply_to_message=MockMessage("group", "Bot response", from_user=MockUser(999999999, "rekku_freedom_project"))),
            "expected": True
        },
        {
            "name": "Reply to other user",
            "message": MockMessage("group", "Thanks!", reply_to_message=MockMessage("group", "User response", from_user=MockUser(888888888, "other_user"))),
            "expected": False
        },
        {
            "name": "Group message without mention",
            "message": MockMessage("group", "Just a normal message"),
            "expected": False
        }
    ]
    
    for test_case in test_cases:
        print(f"\n  Testing: {test_case['name']}")
        result = is_message_for_bot(test_case['message'], bot, "rekku_freedom_project")
        expected = test_case['expected']
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"    Result: {result}, Expected: {expected} - {status}")
        
        if result != expected:
            print(f"    ⚠️  UNEXPECTED RESULT for '{test_case['name']}'")

if __name__ == "__main__":
    test_mention_detection_detailed()
    print("\n" + "=" * 50)
    print("🎯 Test completato!")
    print("\nPer testare con messaggi reali:")
    print("1. Avvia il bot nel container")
    print("2. Invia un messaggio in un gruppo")
    print("3. Rispondi al messaggio del bot")
    print("4. Controlla i log per vedere se viene rilevato come mention")
