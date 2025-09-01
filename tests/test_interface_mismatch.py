import asyncio
import types
import sys


def setup_module(module):
    core_init = types.ModuleType('core.core_initializer')

    class DummyDiscord:
        def __init__(self):
            self.sent = False
        def get_supported_action_types(self):
            return ['message_discord_bot']
        async def execute_action(self, action, context, bot, original_message=None):
            self.sent = True
    class DummyTelegram(DummyDiscord):
        def get_supported_action_types(self):
            return ['message_telegram_bot']

    module.discord_iface = DummyDiscord()
    module.telegram_iface = DummyTelegram()

    core_init.INTERFACE_REGISTRY = {
        'discord_bot': module.discord_iface,
        'telegram_bot': module.telegram_iface,
    }
    core_init.PLUGIN_REGISTRY = {}
    sys.modules['core.core_initializer'] = core_init


def test_run_actions_interface_fallback():
    from core.action_parser import run_actions
    # Create a dummy bot whose class appears to come from the discord library
    class DiscordClient:
        __module__ = 'discord.client'

    bot = DiscordClient()
    msg = types.SimpleNamespace(chat_id=1, message_id=1)
    action = [{'type': 'message_telegram_bot', 'payload': {'text': 'hi', 'target': 1}}]
    asyncio.run(run_actions(action, {}, bot, msg))
    assert discord_iface.sent
    assert not telegram_iface.sent
