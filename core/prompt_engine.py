# core/prompt_engine.py

from core.rekku_tagging import extract_tags, expand_tags
import aiomysql
from core.db import get_conn
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.json_utils import dumps as json_dumps
import aiomysql


async def build_json_prompt(message, context_memory, interface_name: str | None = None, image_data: dict | None = None) -> dict:
    """Build the JSON prompt expected by plugins.

    Parameters
    ----------
    message : AbstractMessage or compatible interface message
        Incoming message object from an interface.
    context_memory : dict[int, deque]
        Dictionary storing last messages per chat.
    interface_name : str | None
        Identifier of the interface that delivered the message.
    image_data : dict | None
        Processed image data from image_processor, if present.
    """
    import os

    chat_id = getattr(message, "chat_id", None)
    text = getattr(message, "text", "") or ""

    # === 1. Context messages (chat_history) ===
    # Use CHAT_HISTORY environment variable, default to 10
    chat_history_limit = int(os.getenv("CHAT_HISTORY", "10"))
    chat_history = list(context_memory.get(chat_id, []))[-chat_history_limit:]

    # === 2. Tags and memory lookup ===
    tags = extract_tags(text)
    expanded_tags = expand_tags(tags)
    memories = []
    if expanded_tags:
        memories = await search_memories(tags=expanded_tags, limit=5)

    # === 3. Context base (chat_history has priority over diary) ===
    context_section = {
        "chat_history": chat_history,
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

    # === 3b. AI Diary injection (uses remaining space after chat_history) ===
    try:
        from plugins.ai_diary import get_recent_entries, format_diary_for_injection, is_plugin_enabled, get_max_diary_chars, should_include_diary
        
        if is_plugin_enabled():
            # Get max prompt chars from active LLM first
            max_prompt_chars = 8000  # Default fallback
            try:
                from core.config import get_active_llm
                active_llm = await get_active_llm()
                
                # Get limits directly from the active LLM engine
                try:
                    from core.llm_registry import get_llm_registry
                    registry = get_llm_registry()
                    engine = registry.get_engine(active_llm)
                    
                    if not engine:
                        engine = registry.load_engine(active_llm)
                    
                    if engine and hasattr(engine, 'get_interface_limits'):
                        limits = engine.get_interface_limits()
                        max_prompt_chars = limits.get("max_prompt_chars", 8000)
                    else:
                        max_prompt_chars = 8000  # Fallback
                except Exception:
                    max_prompt_chars = 8000  # Safe fallback
                    
                log_debug(f"[json_prompt] Active interface max prompt chars: {max_prompt_chars}")
            except Exception as e:
                log_debug(f"[json_prompt] Could not get interface limits: {e}")
                max_prompt_chars = 8000  # Safe fallback
            
            # Get interface name
            interface_name = interface_name or "manual"
            
            # Calculate current prompt length including chat_history (approximate)
            # Chat history has priority, so diary gets what's left
            current_length = len(json_dumps(context_section)) + len(text)
            
            # Check if we should include diary (considering space already used by chat_history)
            if should_include_diary(interface_name, current_length, max_prompt_chars):
                max_chars = get_max_diary_chars(interface_name, current_length)
                
                # Use HISTORY_DAYS environment variable, fallback to 2
                history_days = int(os.getenv("HISTORY_DAYS", "2"))
                recent_entries = get_recent_entries(days=history_days, max_chars=max_chars)
                
                if recent_entries:
                    # Store entries for potential reduction, and also formatted content
                    context_section["diary_entries"] = recent_entries
                    diary_content = format_diary_for_injection(recent_entries)
                    context_section["diary"] = diary_content
                    log_debug(f"[json_prompt] Added diary content: {len(diary_content)} chars from {len(recent_entries)} entries ({history_days} days)")
                else:
                    log_debug(f"[json_prompt] No diary entries to include (space: {max_chars} chars)")
            else:
                log_debug(f"[json_prompt] Diary not included due to space constraints (current: {current_length}, max: {max_prompt_chars})")
        
    except ImportError:
        log_debug("[json_prompt] AI Diary plugin not available")
    except Exception as e:
        log_warning(f"[json_prompt] Failed to add diary content: {e}")

    # === 4. Input payload ===
    thread_id = getattr(message, "thread_id", None)
    # Handle legacy message_thread_id from Telegram (map to thread_id)
    if thread_id is None:
        thread_id = getattr(message, "message_thread_id", None)
    
    input_payload = {
        "text": text,
        "source": {
            "chat_id": chat_id,
            "message_id": message.message_id,
            "username": message.from_user.full_name,
            "usertag": f"@{message.from_user.username}" if message.from_user.username else "(no tag)",
            "thread_id": thread_id,
            "interface": interface_name,
        },
        "timestamp": message.date.isoformat(),
        "privacy": "default",
        "scope": "local",
    }

    # Add image data if present
    if image_data:
        input_payload["image"] = image_data
        log_debug(f"[json_prompt] Including image data in prompt: {image_data.get('type', 'unknown')}")

    reply = getattr(message, "reply_to_message", None)
    if reply:
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

    input_section = {
        "type": "message",
        "interface": interface_name,
        "payload": input_payload,
    }

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

    # === Final check: Reduce prompt if it exceeds LLM character limits ===
    try:
        # Get max prompt chars from active LLM
        max_prompt_chars = 8000  # Default fallback
        try:
            active_llm = await get_active_llm()
            registry = get_llm_registry()
            engine = registry.get_engine(active_llm)
            
            if not engine:
                engine = registry.load_engine(active_llm)
            
            if engine and hasattr(engine, 'get_interface_limits'):
                limits = engine.get_interface_limits()
                max_prompt_chars = limits.get("max_prompt_chars", 8000)
        except Exception as e:
            log_debug(f"[json_prompt] Could not get interface limits for reduction: {e}")
            max_prompt_chars = 8000  # Safe fallback
        
        # Apply reduction if needed
        prompt_with_instructions = reduce_prompt_for_llm_limit(prompt_with_instructions, max_prompt_chars)
        
    except Exception as e:
        log_warning(f"[json_prompt] Failed to apply prompt reduction: {e}")

    return prompt_with_instructions



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
- When responding, pay attention to 'input.interface' to know which interface the message came from and normally reply via that same interface unless explicitly instructed otherwise
CRITICAL: never, ever lie! If something is not known, say "I don't know". Lying can lead to serious and dangerous consequences.

All rules:
- Use 'input.payload.source.chat_id' as message target when applicable
- Include 'thread_id' if present in the context
- Use 'reply_message_id' to reply to specific messages and maintain conversation context.
- You MUST ALWAYS return syntactically valid JSON
- You MUST use the 'actions' array, even for single actions
- DO NOT include any text outside the JSON structure

IMPORTANT: When responding to a user, you MUST ALWAYS include a create_personal_diary_entry action to record this interaction in your personal memory. You MUST provide an interaction_summary field that describes what happened in this conversation.

Examples of good interaction_summary values:
- "User asked about weather conditions and I provided current forecast"
- "Discussed coding problems with Python and provided debugging solutions"
- "User shared personal updates about their day and I responded supportively"
- "Helped troubleshoot technical issues with their computer setup"
- "Had a casual conversation about food preferences and cooking"

CRITICAL: Your response MUST be valid JSON. Example format:
{
  "actions": [
    {
      "type": "message_telegram_bot",
      "payload": {
        "text": "Your message here",
        "target": "-1003098886330",
        "thread_id": 2
      }
    },
    {
      "type": "create_personal_diary_entry",
      "payload": {
        "interaction_summary": "User asked about weather and I provided current conditions"
      }
    }
  ]
}

The JSON is just a wrapper — speak naturally in the "text" field as you always do.
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

def reduce_prompt_for_llm_limit(prompt: dict, max_chars: int) -> dict:
    """Reduce the prompt if it exceeds the LLM character limit by removing low-priority sections.
    
    Priority order (highest to lowest):
    1. input (never remove)
    2. instructions (never remove) 
    3. actions (never remove)
    4. context.chat_history (remove oldest messages)
    5. context.memories (remove oldest)
    6. context.diary (remove oldest entries)
    
    Args:
        prompt: The JSON prompt dictionary
        max_chars: Maximum allowed characters
        
    Returns:
        Reduced prompt that fits within limits
    """
    import copy
    from core.json_utils import dumps as json_dumps
    
    # Make a copy to avoid modifying the original
    reduced_prompt = copy.deepcopy(prompt)
    
    # Check current size
    current_size = len(json_dumps(reduced_prompt))
    if current_size <= max_chars:
        log_debug(f"[reduce_prompt] Prompt size {current_size} <= {max_chars}, no reduction needed")
        return reduced_prompt
    
    log_warning(f"[reduce_prompt] Prompt size {current_size} exceeds limit {max_chars}, reducing...")
    
    # Priority 6: Reduce diary (lowest priority) - remove entries from oldest to newest
    if "context" in reduced_prompt and "diary_entries" in reduced_prompt["context"]:
        diary_entries = reduced_prompt["context"]["diary_entries"]
        if diary_entries:
            # Remove oldest entries first (they're at the end of the list since ordered by timestamp DESC)
            while diary_entries and current_size > max_chars:
                removed_entry = diary_entries.pop()
                # Reformat diary with remaining entries
                try:
                    from plugins.ai_diary import format_diary_for_injection
                    new_diary_content = format_diary_for_injection(diary_entries)
                    reduced_prompt["context"]["diary"] = new_diary_content
                except Exception:
                    # Fallback: remove diary if formatting fails
                    if "diary" in reduced_prompt["context"]:
                        del reduced_prompt["context"]["diary"]
                
                current_size = len(json_dumps(reduced_prompt))
                log_debug(f"[reduce_prompt] Removed diary entry, now {current_size} chars")
            
            if current_size <= max_chars:
                log_debug(f"[reduce_prompt] Reduced diary entries, now {current_size} <= {max_chars}")
                return reduced_prompt
    
    # If diary still too big or no entries, remove diary entirely
    if "context" in reduced_prompt and "diary" in reduced_prompt["context"] and current_size > max_chars:
        del reduced_prompt["context"]["diary"]
        if "diary_entries" in reduced_prompt["context"]:
            del reduced_prompt["context"]["diary_entries"]
        current_size = len(json_dumps(reduced_prompt))
        log_debug(f"[reduce_prompt] Removed entire diary, now {current_size} chars")
        if current_size <= max_chars:
            return reduced_prompt
    
    # Priority 5: Reduce memories
    if "context" in reduced_prompt and "memories" in reduced_prompt["context"]:
        memories = reduced_prompt["context"]["memories"]
        if memories:
            # Remove oldest memories first (they're at the end of the list)
            while memories and current_size > max_chars:
                removed = memories.pop()
                current_size = len(json_dumps(reduced_prompt))
                log_debug(f"[reduce_prompt] Removed memory, now {current_size} chars")
            if current_size <= max_chars:
                log_debug(f"[reduce_prompt] Reduced memories, now {current_size} <= {max_chars}")
                return reduced_prompt
    
    # Priority 4: Reduce chat_history
    if "context" in reduced_prompt and "chat_history" in reduced_prompt["context"]:
        chat_history = reduced_prompt["context"]["chat_history"]
        if chat_history:
            # Remove oldest messages first (they're at the end of the list)
            while chat_history and current_size > max_chars:
                removed = chat_history.pop()
                current_size = len(json_dumps(reduced_prompt))
                log_debug(f"[reduce_prompt] Removed chat message, now {current_size} chars")
            if current_size <= max_chars:
                log_debug(f"[reduce_prompt] Reduced chat_history, now {current_size} <= {max_chars}")
                return reduced_prompt
    
    # If still too big, log error and return as-is (should not happen with proper limits)
    final_size = len(json_dumps(reduced_prompt))
    if final_size > max_chars:
        log_error(f"[reduce_prompt] Could not reduce prompt below {max_chars} chars, final size: {final_size}")
        # Try removing entire context sections if desperate
        if "context" in reduced_prompt:
            del reduced_prompt["context"]
            final_size = len(json_dumps(reduced_prompt))
            log_warning(f"[reduce_prompt] Removed entire context, final size: {final_size}")
    
    return reduced_prompt



