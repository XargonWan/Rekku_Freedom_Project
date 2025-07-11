# core/prompt_engine.py

from core.rekku_tagging import extract_tags, expand_tags
import os
from datetime import datetime
from core.db import get_db
import json
from logging_utils import log_debug, log_info, log_warning, log_error


async def build_json_prompt(message, context_memory) -> dict:
    """Build the JSON prompt expected by plugins.

    Parameters
    ----------
    message : telegram.Message
        Incoming message object from telegram bot.
    context_memory : dict[int, deque]
        Dictionary storing last messages per chat.
    """

    import core.weather
    import pytz

    chat_id = message.chat_id
    text = message.text or ""

    # === 1. Context messages ===
    messages = list(context_memory.get(chat_id, []))[-10:]

    # === 2. Tags and memory lookup ===
    tags = extract_tags(text)
    expanded_tags = expand_tags(tags)
    memories = []
    if expanded_tags:
        memories = search_memories(tags=expanded_tags, limit=5)

    # === 3. Temporal and weather info ===
    location = os.getenv("WEATHER_LOCATION", "Kyoto")
    try:
        tz = pytz.timezone("Asia/Tokyo")
    except Exception:
        tz = pytz.utc
    now_local = datetime.now(tz)
    date = now_local.strftime("%Y-%m-%d")
    time = now_local.strftime("%H:%M")
    weather = core.weather.current_weather

    context_section = {
        "messages": messages,
        "memories": memories,
        "location": location,
        "weather": weather if weather else "Unavailable",
        "date": date,
        "time": time,
    }

    # === 4. Input payload ===
    input_payload = {
        "text": text,
        "source": {
            "chat_id": chat_id,
            "message_id": message.message_id,
            "username": message.from_user.full_name,
            "usertag": f"@{message.from_user.username}" if message.from_user.username else "(no tag)",
        },
        "timestamp": message.date.isoformat(),
        "privacy": "default",
        "scope": "local",
    }

    if message.reply_to_message:
        reply = message.reply_to_message
        reply_text = reply.text or getattr(reply, "caption", None)
        if not reply_text:
            reply_text = "[Non-text content]"
        input_payload["reply_to"] = {
            "text": reply_text,
            "timestamp": reply.date.isoformat(),
            "from": {
                "username": reply.from_user.full_name,
                "usertag": f"@{reply.from_user.username}" if reply.from_user.username else "(no tag)",
            },
        }

    input_section = {"type": "message", "payload": input_payload}

    # Debug output for both sections
    log_debug("[json_prompt] context = " + json.dumps(context_section, ensure_ascii=False))
    log_debug("[json_prompt] input = " + json.dumps(input_section, ensure_ascii=False))

    return {"context": context_section, "input": input_section}

def load_identity_prompt() -> str:
    try:
        with open("persona/prompt.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        log_warning("prompt.txt not found. Identity prompt not loaded.")
        return ""

def search_memories(tags=None, scope=None, limit=5):
    if not tags:
        return []

    placeholders = ",".join(["?"] * len(tags))

    query = f"""
        SELECT DISTINCT content
        FROM memories
        WHERE json_valid(tags)
          AND EXISTS (
              SELECT 1
              FROM json_each(memories.tags)
              WHERE json_each.value IN ({placeholders})
          )
    """

    params = tags.copy()

    if scope:
        query += " AND scope = ?"
        params.append(scope)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    log_debug("Query:")
    log_debug(query)
    log_debug(f"Parameters: {params}")

    try:
        with get_db() as db:
            return [row[0] for row in db.execute(query, params)]
    except Exception as e:
        log_error(f"Query failed: {e}")
        return []

def build_prompt(
    user_text: str,
    identity_prompt: str = "",
    extract_tags_fn=extract_tags,
    search_memories_fn=None,
    limit: int = 5,
    log_path: str = "logs/prompt_cycle.log"
) -> list:
    tags = extract_tags_fn(user_text) if extract_tags_fn else []
    expanded_tags = expand_tags(tags) if tags else []
    memories = search_memories_fn(tags=expanded_tags, limit=limit) if search_memories_fn else []

    memory_block = "\n".join(f"- {mem}" for mem in memories) if memories else "No relevant memory found."

    messages = []

    if identity_prompt:
        messages.append({"role": "system", "content": identity_prompt})

    messages.append({
        "role": "system",
        "content": f"[MEMORIE RILEVANTI]\n{memory_block}"
    })

    messages.append({"role": "user", "content": user_text.strip()})

    # === LOGGING SU FILE ===
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        timestamp = datetime.utcnow().isoformat()
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n[{timestamp}] --- REASONING CYCLE ---\n")
            log_file.write(f"> User text: {user_text.strip()}\n")
            log_file.write(f"> Extracted tags: {tags}\n")
            log_file.write(f"> Expanded tags: {expanded_tags}\n")
            log_file.write(f"> Memories found: {len(memories)}\n")
            for msg in messages:
                role = msg.get("role", "").upper()
                content = msg.get("content", "").strip()
                log_file.write(f"[{role}]\n{content}\n\n")
            log_file.write("----------- END -----------\n")
    except Exception as e:
        log_warning(f"Error logging prompt: {e}")

    return messages

