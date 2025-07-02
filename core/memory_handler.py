"""Wrapper around database memory operations."""

from core.db import insert_memory
import json
from typing import List


def save(content: str, tags: List[str] | None = None, author: str = "rekku"):
    t = json.dumps(tags or [])
    insert_memory(content=content, author=author, source="system", tags=t)
