import sys, os
from types import SimpleNamespace
import asyncio

# Ensure repository root in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auto_response import AutoResponseSystem


def test_request_llm_response_builds_chat(monkeypatch):
    # Provide fake interface registry without importing heavy modules
    fake_core_initializer = SimpleNamespace(
        INTERFACE_REGISTRY={'telegram_bot': SimpleNamespace(bot='INNER_BOT')}
    )
    sys.modules['core.core_initializer'] = fake_core_initializer

    captured = {}

    async def fake_enqueue(bot, message, context_memory, priority=True):
        captured['bot'] = bot
        captured['chat'] = getattr(message, 'chat', None)
        captured['chat_id'] = getattr(message.chat, 'id', None)
        captured['text'] = message.text
        captured['full_name'] = getattr(message.from_user, 'full_name', None)
        captured['date'] = getattr(message, 'date', None)

    sys.modules['core.message_queue'] = SimpleNamespace(enqueue=fake_enqueue)

    auto = AutoResponseSystem()
    asyncio.run(
        auto.request_llm_response(
            output='done',
            original_context={'chat_id': 42, 'message_id': 5, 'interface_name': 'telegram_bot'},
            action_type='terminal',
            command='ls'
        )
    )

    assert captured['bot'] == 'INNER_BOT'
    assert captured['chat'] is not None
    assert captured['chat_id'] == 42
    assert 'terminal' in captured['text']
    assert captured['full_name'] == 'AutoResponse'
    assert captured['date'] is not None
