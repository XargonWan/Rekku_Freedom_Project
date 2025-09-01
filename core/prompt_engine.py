# core/prompt_engine.py

from core.rekku_tagging import extract_tags, expand_tags
from core.db import get_conn
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.json_utils import dumps as json_dumps
import aiomysql


async def build_json_prompt(message, context_memory) -> dict:
    """Build the JSON prompt expected by plugins.

    Parameters
    ----------
    message : telegram.Message
        Incoming message object from telegram bot.
    context_memory : dict[int, deque]
        Dictionary storing last messages per chat.
    """

    chat_id = message.chat_id
    text = message.text or ""

    # === 1. Context messages ===
    messages = list(context_memory.get(chat_id, []))[-10:]

    # === 2. Tags and memory lookup ===
    tags = extract_tags(text)
    expanded_tags = expand_tags(tags)
    memories = []
    if expanded_tags:
        memories = await search_memories(tags=expanded_tags, limit=5)

    # === 3. Context base ===
    context_section = {
        "messages": messages,
        "memories": memories,
    }

    # === 3a. Static injections from plugins ===
    try:
        from core.action_parser import gather_static_injections

        injections = await gather_static_injections(message, context_memory)
        if isinstance(injections, dict):
            context_section.update(injections)
    except Exception as e:
        log_warning(f"[json_prompt] Failed to gather static injections: {e}")

    # === 4. Input payload ===
    message_thread_id = getattr(message, "message_thread_id", None)
    input_payload = {
        "text": text,
        "source": {
            "chat_id": chat_id,
            "message_id": message.message_id,
            "username": message.from_user.full_name,
            "usertag": f"@{message.from_user.username}" if message.from_user.username else "(no tag)",
            "message_thread_id": message_thread_id,
        },
        "timestamp": message.date.isoformat(),
        "privacy": "default",
        "scope": "local",
    }

    if message.reply_to_message:
        reply = message.reply_to_message
        reply_text = getattr(reply, "text", None) or getattr(reply, "caption", None)
        if not reply_text:
            reply_text = "[Non-text content]"
        reply_date = getattr(reply, "date", None)
        reply_timestamp = reply_date.isoformat() if reply_date else ""
        reply_from = getattr(reply, "from_user", None)
        reply_full_name = getattr(reply_from, "full_name", "Unknown") if reply_from else "Unknown"
        reply_username = getattr(reply_from, "username", None) if reply_from else None
        input_payload["reply_message_id"] = {
            "text": reply_text,
            "timestamp": reply_timestamp,
            "from": {
                "username": reply_full_name,
                "usertag": f"@{reply_username}" if reply_username else "(no tag)",
            },
        }

    input_section = {"type": "message", "payload": input_payload}

    # Debug output for both sections
    log_debug("[json_prompt] context = " + json_dumps(context_section))
    log_debug("[json_prompt] input = " + json_dumps(input_section))

    # Add JSON instructions to the prompt
    json_instructions = load_json_instructions()
    
    # Interface-specific instructions are provided via the available actions block
    # No hardcoded interface references - plugins define their own instructions

    prompt_with_instructions = {
        "context": context_section,
        "input": input_section,
        "instructions": json_instructions,
    }

    # Include unified actions metadata from the initializer
    try:
        from core.core_initializer import core_initializer
        prompt_with_instructions["actions"] = core_initializer.actions_block.get(
            "available_actions", {}
        )
    except Exception as e:
        log_warning(f"[prompt_engine] Failed to inject actions block: {e}")
        prompt_with_instructions["actions"] = {}

    return prompt_with_instructions

def load_identity_prompt() -> str:
    try:
        with open("persona/prompt.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        log_warning("prompt.txt not found. Identity prompt not loaded.")
        return ""

async def search_memories(tags=None, scope=None, limit=5):
    if not tags:
        return []

    # Build OR conditions using JSON_CONTAINS to check if any tag exists in the JSON array
    conditions = " OR ".join(["JSON_CONTAINS(tags, %s)"] * len(tags))

    query = f"""
        SELECT DISTINCT content
        FROM memories
        WHERE json_valid(tags)
          AND ({conditions})
    """

    # Parameters: each tag encoded as a JSON string for JSON_CONTAINS
    params = [json_dumps(tag) for tag in tags]

    if scope:
        query += " AND scope = %s"
        params.append(scope)

    query += " ORDER BY timestamp DESC LIMIT %s"
    params.append(limit)

    log_debug("Query:")
    log_debug(query)
    log_debug(f"Parameters: {params}")

    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            rows = await cur.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        log_error(f"Query failed: {repr(e)}")
        return []
    finally:
        conn.close()

async def build_prompt(
    user_text: str,
    identity_prompt: str = "",
    extract_tags_fn=extract_tags,
    search_memories_fn=None,
    limit: int = 5,
    log_path: str = "logs/prompt_cycle.log"
) -> list:
    tags = extract_tags_fn(user_text) if extract_tags_fn else []
    expanded_tags = expand_tags(tags) if tags else []
    memories = await search_memories_fn(tags=expanded_tags, limit=limit) if search_memories_fn else []

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

def load_json_instructions() -> str:
    return """
- Check the available_actions section below for supported interfaces and their capabilities
- Search memories when unsure about a detail
- When responding, pay attention to which interface the message came from and normally reply via that same interface unless explicitly instructed otherwise

All rules:
- Use 'input.payload.source.chat_id' as message target when applicable
- Include 'thread_id' if present in the context
- Use 'reply_message_id' to reply to specific messages and maintain conversation context.
- Always return syntactically valid JSON
- Use the 'actions' array, even for single actions

The JSON is just a wrapper — speak naturally as you always do.
"""


def build_full_json_instructions() -> dict:
    """Return combined JSON instructions and available actions block.

    Always returns the full set of available actions so the model is aware of
    every capability, preserving flexibility and avoiding accidental action
    masking.
    """
    instructions = load_json_instructions()
    actions = {}
    try:
        from core.core_initializer import core_initializer
        actions = core_initializer.actions_block.get("available_actions", {})
    except Exception as e:  # pragma: no cover - defensive
        log_warning(f"[prompt_engine] Failed to load actions block: {e}")
    return {"instructions": instructions, "actions": actions}



