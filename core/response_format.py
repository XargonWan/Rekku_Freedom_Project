"""Utilities for standardized assistant responses."""

from typing import Dict


def text_response(content: str) -> Dict[str, str]:
    """Return a text reply structure."""
    return {"type": "text", "content": content}


def sticker_response(emoji: str) -> Dict[str, str]:
    """Return a sticker reply structure using an emoji as identifier."""
    return {"type": "sticker", "emoji": emoji}
