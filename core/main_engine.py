"""JSON protocol processing engine."""

import json
from typing import List, Dict, Any
from plugins import load_action


class ParseError(Exception):
    pass


async def process(json_message: str, bot=None) -> None:
    """Parse a Rekku JSON message and execute the contained actions."""
    try:
        data = json.loads(json_message)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ParseError("Root element must be an object")

    actions = data.get("actions")
    if not isinstance(actions, list):
        raise ParseError("'actions' must be a list")

    for act in actions:
        if not isinstance(act, dict):
            raise ParseError("Each action must be an object")
        name = act.get("action")
        params = act.get("params", {})
        if not name:
            raise ParseError("Action missing 'action' field")
        handler = load_action(name)
        await handler(bot, params)
