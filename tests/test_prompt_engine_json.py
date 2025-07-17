import asyncio
from collections import deque
from types import SimpleNamespace
from datetime import datetime, timezone
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.prompt_engine import build_json_prompt


def make_message():
    user = SimpleNamespace(full_name="Jay Cheshire", username="Xargon", id=1)
    return SimpleNamespace(
        chat_id=123,
        message_id=50,
        text="Hello",
        date=datetime(2025, 7, 17, 6, 0, tzinfo=timezone.utc),
        from_user=user,
        reply_to_message=None,
    )


def test_build_json_prompt_structure():
    message = make_message()
    context_memory = {
        123: deque(
            [
                {
                    "message_id": 49,
                    "username": "Jay Cheshire",
                    "usertag": "@Xargon",
                    "text": "Previous",
                    "timestamp": "2025-07-17T05:55:00+00:00",
                },
                {
                    "message_id": 50,
                    "username": "Jay Cheshire",
                    "usertag": "@Xargon",
                    "text": "Hello",
                    "timestamp": "2025-07-17T06:00:00+00:00",
                },
            ],
            maxlen=10,
        )
    }

    prompt = asyncio.run(build_json_prompt(message, context_memory))

    assert set(prompt.keys()) == {
        "context",
        "input",
        "available_actions",
        "interface_instructions",
        "bio",
    }
    msgs = prompt["context"]["messages"]
    assert len(msgs) == 1
    assert msgs[0]["message_id"] == 49
    assert msgs[0]["timestamp"].endswith("+09:00")
    assert prompt["input"]["payload"]["timestamp"].endswith("+09:00")
    assert prompt["bio"] == {}
