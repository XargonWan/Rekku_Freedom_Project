import os
import sys

# Ensure the project root is on sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.mention_utils import is_rekku_mentioned, is_message_for_bot


def test_is_rekku_mentioned():
    assert is_rekku_mentioned("Hi Rekku!") is True
    assert is_rekku_mentioned("Привет, рекку!") is True
    assert is_rekku_mentioned("れっくたん、元気？") is True
    assert is_rekku_mentioned("Ammiro la tanukina oggi") is True
    assert is_rekku_mentioned("@The_Official_Rekku sei viva?") is True
    assert is_rekku_mentioned("Salve a tutti") is False


class MockUser:
    def __init__(self, user_id, username=None):
        self.id = user_id
        self.username = username


class MockChat:
    def __init__(self, chat_type):
        self.type = chat_type


class MockEntity:
    def __init__(self, entity_type, offset, length):
        self.type = entity_type
        self.offset = offset
        self.length = length


class MockMessage:
    def __init__(self, chat_type, text="", entities=None, from_user=None, reply_to_message=None):
        self.chat = MockChat(chat_type)
        self.text = text
        self.caption = None
        self.entities = entities or []
        self.from_user = from_user
        self.reply_to_message = reply_to_message


class MockBot:
    def __init__(self, bot_id, username):
        self.bot_id = bot_id
        self.username = username
    
    def get_me(self):
        return MockUser(self.bot_id, self.username)


def test_is_message_for_bot():
    # Test private message - always for bot
    bot = MockBot(123, "test_bot")
    message = MockMessage("private", "Hello")
    assert is_message_for_bot(message, bot) is True
    
    # Test group message with explicit mention
    entity = MockEntity("mention", 0, 9)
    message = MockMessage("group", "@test_bot hello", entities=[entity])
    assert is_message_for_bot(message, bot, "test_bot") is True
    
    # Test group message with reply to bot
    bot_message = MockMessage("group", "Bot response", from_user=MockUser(123, "test_bot"))
    reply_message = MockMessage("group", "Reply to bot", reply_to_message=bot_message)
    assert is_message_for_bot(reply_message, bot) is True
    
    # Test group message with Rekku alias
    message = MockMessage("group", "Hey Rekku, how are you?")
    assert is_message_for_bot(message, bot) is True
    
    # Test group message without mention
    message = MockMessage("group", "Just a normal message")
    assert is_message_for_bot(message, bot) is False
