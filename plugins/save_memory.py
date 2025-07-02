"""Plugin to persist a memory entry in the database."""

from core.db import insert_memory
import json

async def run(bot, params: dict):
    content = params.get("content")
    author = params.get("author", "rekku")
    source = params.get("source", "system")
    tags = params.get("tags", [])

    if not content:
        raise ValueError("save_memory requires 'content'")

    if isinstance(tags, list):
        tags = json.dumps(tags)

    insert_memory(content=content, author=author, source=source, tags=tags)
