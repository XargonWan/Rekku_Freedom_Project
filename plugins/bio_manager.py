from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable
import asyncio
import aiomysql
import threading
from contextlib import asynccontextmanager

from core.db import get_conn
from core.logging_utils import log_error, log_info, log_debug, log_warning
from core.core_initializer import core_initializer, register_plugin


@asynccontextmanager
async def get_db():
    """Context manager for MariaDB database connections."""
    conn = None
    try:
        conn = await get_conn()
        log_debug("[bio_manager] Opened database connection")
        yield conn
    except Exception as e:
        log_error(f"[bio_manager] Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()
            log_debug("[bio_manager] Connection closed")


JSON_LIST_FIELDS = {"known_as", "likes", "not_likes", "past_events", "feelings", "social_accounts"}
JSON_DICT_FIELDS = {"contacts"}

VALID_BIO_FIELDS = {
    "known_as", "likes", "not_likes", "information", "past_events", 
    "feelings", "contacts", "social_accounts", "privacy", "created_at", "last_accessed"
}

DEFAULTS = {
    "known_as": [],
    "likes": [],
    "not_likes": [],
    "information": "",
    "past_events": [],
    "feelings": [],
    "contacts": {},
    "social_accounts": [],  # Changed from {} to []
    "privacy": "default",
    "created_at": "",
    "last_accessed": "",
}


async def init_bio_table():
    """Initialize the bio table if it doesn't exist."""
    async with get_db() as conn:
        cursor = await conn.cursor()
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS bio (
                id VARCHAR(255) PRIMARY KEY,
                known_as TEXT DEFAULT '[]',
                likes TEXT DEFAULT '[]',
                not_likes TEXT DEFAULT '[]',
                information TEXT DEFAULT '',
                past_events TEXT DEFAULT '[]',
                feelings TEXT DEFAULT '[]',
                contacts TEXT DEFAULT '{}',
                social_accounts TEXT DEFAULT '[]',
                privacy TEXT DEFAULT '{}',
                created_at VARCHAR(50),
                last_accessed VARCHAR(50),
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                update_count INT DEFAULT 0
            )
        ''')
        await conn.commit()
        log_info("[bio_manager] Bio table initialized")


def _run(coro):
    """Run a coroutine safely even if an event loop is already running."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        result: Any = None
        exc: Exception | None = None

        def runner() -> None:
            nonlocal result, exc
            try:
                result = asyncio.run(coro)
            except Exception as e:  # pragma: no cover - defensive
                exc = e

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if exc:
            raise exc
        return result


async def _execute(query: str, params: tuple = ()) -> None:
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
    finally:
        conn.close()


async def _fetchone(query: str, params: tuple = ()):
    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params)
            return await cur.fetchone()
    finally:
        conn.close()


def _ensure_table() -> None:
    """Create the bio table if it doesn't exist."""
    _run(init_bio_table())


def _ensure_user_exists(user_id: str) -> None:
    """Create an empty bio entry if the user is missing."""
    _ensure_table()
    row = _run(_fetchone("SELECT 1 FROM bio WHERE id=%s", (user_id,)))
    if not row:
        now = datetime.utcnow().isoformat()
        _run(
            _execute(
                """
                INSERT INTO bio (
                    id, known_as, likes, not_likes, information,
                    past_events, feelings, contacts, social_accounts,
                    privacy, created_at, last_accessed, last_update, update_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps([]),
                    "",
                    json.dumps([]),
                    json.dumps([]),
                    json.dumps({}),
                    json.dumps({}),
                    "default",
                    now,
                    now,
                    now,  # last_update
                    0,    # update_count
                ),
            )
        )


def _load_json_field(value: str | None, key: str, default: Any) -> Any:
    """Safely deserialize a JSON field."""
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception as e:  # pragma: no cover - corruption
        log_error(f"[bio_manager] Failed to decode {key}: {e}")
        return default


def _save_json_field(user_id: str, key: str, value: Any) -> None:
    """Serialize and store a JSON field."""
    if key not in VALID_BIO_FIELDS:
        log_error(f"[bio_manager] Invalid field name: {key}")
        return
    
    # Ensure value is not None and can be serialized
    if value is None:
        value = DEFAULTS.get(key, "")
    
    try:
        json_value = json.dumps(value)
    except (TypeError, ValueError) as e:
        log_error(f"[bio_manager] Failed to serialize {key}: {e}")
        return
    
    # Use parameterized query to prevent SQL injection
    query = "UPDATE bio SET {}=%s WHERE id=%s".format(key)
    _run(_execute(query, (json_value, user_id)))


def _merge_nested_dicts(original: dict, updates: dict) -> dict:
    """Recursively merge dictionaries, concatenating lists without duplicates."""
    for k, v in updates.items():
        if k in original:
            old = original[k]
            if isinstance(old, dict) and isinstance(v, dict):
                original[k] = _merge_nested_dicts(old, v)
            elif isinstance(old, list) and isinstance(v, list):
                unique = {json.dumps(x) for x in old + v}
                original[k] = [json.loads(x) for x in unique]
            else:
                original[k] = v
        else:
            original[k] = v
    return original


def _update_json_field(user_id: str, key: str, update_fn: Callable[[Any], Any]) -> None:
    if key not in VALID_BIO_FIELDS:
        log_error(f"[bio_manager] Invalid field name: {key}")
        return
        
    _ensure_user_exists(user_id)
    # Use parameterized query to prevent SQL injection
    query = "SELECT {} FROM bio WHERE id=%s".format(key)
    row = _run(_fetchone(query, (user_id,)))
    current = _load_json_field(row.get(key), key, DEFAULTS.get(key))
    
    try:
        updated = update_fn(current)
        # Ensure updated value is not None and can be serialized
        if updated is None:
            updated = DEFAULTS.get(key, "")
        
        try:
            json_value = json.dumps(updated)
        except (TypeError, ValueError) as e:
            log_error(f"[bio_manager] Failed to serialize updated {key}: {e}")
            return
            
        _save_json_field(user_id, key, updated)
    except Exception as e:  # pragma: no cover - logic error
        log_error(f"[bio_manager] Error updating {key}: {e}")
        return


def get_bio_light(user_id: str) -> dict:
    """Return a lightweight bio for the user."""
    _ensure_table()
    row = _run(
        _fetchone(
            "SELECT known_as, likes, not_likes, feelings, information FROM bio WHERE id=%s",
            (user_id,),
        )
    )
    if not row:
        return {}
    return {
        "known_as": _load_json_field(row.get("known_as"), "known_as", DEFAULTS["known_as"]),
        "likes": _load_json_field(row.get("likes"), "likes", DEFAULTS["likes"]),
        "not_likes": _load_json_field(row.get("not_likes"), "not_likes", DEFAULTS["not_likes"]),
        "feelings": _load_json_field(row.get("feelings"), "feelings", DEFAULTS["feelings"]),
        "information": row.get("information") or "",
    }


def get_bio_full(user_id: str) -> dict:
    """Return the full bio for the user."""
    _ensure_table()
    row = _run(_fetchone("SELECT * FROM bio WHERE id=%s", (user_id,)))
    if not row:
        return {}
    result = {"id": row.get("id"), "information": row.get("information") or ""}
    for key in JSON_LIST_FIELDS | JSON_DICT_FIELDS:
        result[key] = _load_json_field(row.get(key), key, DEFAULTS[key])
    result["privacy"] = row.get("privacy") or "default"
    result["created_at"] = row.get("created_at") or ""
    result["last_accessed"] = row.get("last_accessed") or ""
    result["last_update"] = row.get("last_update") or ""
    result["update_count"] = row.get("update_count") or 0
    return result


def _validate_bio_consistency(existing_bio: dict, updates: dict) -> tuple[bool, str]:
    """Validate bio updates for consistency with existing data."""
    # Check age consistency
    if 'information' in updates:
        new_info = updates['information'].lower()
        existing_info = existing_bio.get('information', '').lower()
        
        # Check for contradictory age information
        import re
        age_pattern = r'(\d{1,3})\s*(?:anni?|years?|old)'
        new_ages = re.findall(age_pattern, new_info)
        existing_ages = re.findall(age_pattern, existing_info)
        
        if new_ages and existing_ages:
            new_age = int(new_ages[0])
            existing_age = int(existing_ages[0])
            if abs(new_age - existing_age) > 10:  # Age difference too large
                return False, f"Age inconsistency detected: {existing_age} vs {new_age}"
    
    # Check name consistency
    if 'known_as' in updates and existing_bio.get('known_as'):
        new_names = set(updates['known_as'])
        existing_names = set(existing_bio['known_as'])
        if new_names and existing_names and not new_names.intersection(existing_names):
            return False, "Name inconsistency: no matching names with existing bio"
    
    # Check location consistency (if mentioned in information)
    if 'information' in updates:
        new_info = updates['information'].lower()
        existing_info = existing_bio.get('information', '').lower()
        
        # Extract locations (simple heuristic)
        locations = ['tokyo', 'japan', 'osaka', 'kyoto', 'kizugawa', 'italy', 'rome', 'milan']
        new_locations = [loc for loc in locations if loc in new_info]
        existing_locations = [loc for loc in locations if loc in existing_info]
        
        if new_locations and existing_locations:
            if not set(new_locations).intersection(set(existing_locations)):
                return False, f"Location inconsistency: {existing_locations} vs {new_locations}"
    
    return True, ""


def _check_update_limits(user_id: str, updates: dict) -> tuple[bool, str]:
    """Check update frequency and amplitude limits."""
    try:
        # Get current bio data including update tracking
        current = get_bio_full(user_id)
        last_update_str = current.get('last_update', '')
        update_count = current.get('update_count', 0)
        
        # Parse last update time
        if last_update_str:
            try:
                last_update = datetime.fromisoformat(last_update_str.replace('Z', '+00:00'))
            except:
                last_update = datetime.utcnow() - timedelta(hours=2)  # Default to 2 hours ago
        else:
            last_update = datetime.utcnow() - timedelta(hours=2)
        
        now = datetime.utcnow()
        
        # Frequency check: minimum 1 hour between updates
        if (now - last_update) < timedelta(hours=1):
            return False, "Updates too frequent. Please wait at least 1 hour between updates."
        
        # Amplitude check: maximum 3 fields per update
        if len(updates) > 3:
            return False, f"Too many fields updated at once ({len(updates)}). Maximum 3 fields per update."
        
        # Daily limit: maximum 5 updates per day
        if update_count >= 5 and (now - last_update) < timedelta(days=1):
            return False, "Daily update limit reached (5 updates per day)."
        
        return True, ""
        
    except Exception as e:
        log_warning(f"[bio] Error checking update limits: {e}")
        return True, ""  # Allow update on error to avoid blocking legitimate updates


def update_bio_fields(user_id: str, updates: dict) -> None:
    """Safely update multiple fields in the user's bio, preserving existing values."""

    if not updates:
        return

    # Validate update limits
    limits_ok, limit_msg = _check_update_limits(user_id, updates)
    if not limits_ok:
        log_warning(f"[bio] Update rejected for user {user_id}: {limit_msg}")
        raise ValueError(f"Bio update rejected: {limit_msg}")

    _ensure_user_exists(user_id)
    current = get_bio_full(user_id)

    # Validate consistency
    consistency_ok, consistency_msg = _validate_bio_consistency(current, updates)
    if not consistency_ok:
        log_warning(f"[bio] Inconsistent update for user {user_id}: {consistency_msg}")
        raise ValueError(f"Bio update rejected: {consistency_msg}")

    merged: dict[str, Any] = {}

    for field in VALID_BIO_FIELDS:
        old_val = current.get(field)
        new_val = updates.get(field)

        if isinstance(old_val, str) and field != "information":
            try:
                old_val = json.loads(old_val)
            except Exception:
                old_val = []

        if new_val is None:
            merged[field] = old_val
            continue

        if isinstance(old_val, list) and isinstance(new_val, list):
            unique = {json.dumps(x) for x in old_val + new_val}
            merged[field] = [json.loads(x) for x in unique]
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            merged[field] = _merge_nested_dicts(old_val, new_val)
        else:
            merged[field] = new_val

    # Update tracking fields
    now = datetime.utcnow().isoformat()
    merged['last_update'] = now
    merged['update_count'] = (current.get('update_count', 0) + 1) % 6  # Reset after 5 updates

    _run(
        _execute(
            """
            REPLACE INTO bio (
                id, known_as, likes, not_likes, information,
                past_events, feelings, contacts, social_accounts,
                privacy, created_at, last_accessed, last_update, update_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                json.dumps(merged.get("known_as") or []),
                json.dumps(merged.get("likes") or []),
                json.dumps(merged.get("not_likes") or []),
                str(merged.get("information") or ""),
                json.dumps(merged.get("past_events") or []),
                json.dumps(merged.get("feelings") or []),
                json.dumps(merged.get("contacts") or {}),
                json.dumps(merged.get("social_accounts") or []),
                json.dumps(merged.get("privacy") or {}),
                str(merged.get("created_at") or datetime.utcnow().isoformat()),
                str(merged.get("last_accessed") or datetime.utcnow().isoformat()),
                merged.get("last_update"),
                merged.get("update_count"),
            ),
        )
    )


def append_to_bio_list(user_id: str, field: str, value: Any) -> None:
    """Append a value to a list field, supporting dot notation for nesting."""
    parts = field.split(".")
    key = parts[0]

    def updater(data: Any) -> Any:
        if not isinstance(data, (list, dict)):
            data = [] if len(parts) == 1 else {}

        target = data
        for p in parts[1:-1]:
            if not isinstance(target, dict):
                target = {}
            target = target.setdefault(p, {})

        if len(parts) == 1:
            lst = target
        else:
            lst = target.get(parts[-1], [])

        if not isinstance(lst, list):
            lst = []
        if value not in lst:
            lst.append(value)

        if len(parts) == 1:
            return lst
        target[parts[-1]] = lst
        return data

    _update_json_field(user_id, key, updater)


def add_past_event(user_id: str, summary: str, dt: datetime | None = None) -> None:
    dt = dt or datetime.utcnow()
    entry = {
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M"),
        "summary": summary,
    }
    append_to_bio_list(user_id, "past_events", entry)


def alter_feeling(user_id: str, feeling_type: str, intensity: int) -> None:
    normalized = feeling_type.lower().strip()

    def updater(feels: Any) -> list[dict]:
        if not isinstance(feels, list):
            feels = []
        for f in feels:
            if isinstance(f, dict) and f.get("type", "").lower() == normalized:
                f["intensity"] = intensity
                break
        else:
            feels.append({"type": normalized, "intensity": intensity})
        return feels

    _update_json_field(user_id, "feelings", updater)


class BioPlugin:
    """Plugin providing bio storage and retrieval utilities."""

    def __init__(self):
        self._participants: list[dict[str, Any]] = []
        register_plugin("bio_manager", self)
        core_initializer.register_plugin("bio_manager")
        log_info("[bio_manager] BioPlugin initialized and registered")

    def get_supported_action_types(self):
        return ["static_inject", "bio_full_request", "bio_update"]

    def get_supported_actions(self):
        return {
            "static_inject": {
                "description": "Inject short bios and feelings for participants",
                "required_fields": [],
                "optional_fields": [],
            },
            "bio_full_request": {
                "description": "Retrieve full bios for a list of targets",
                "required_fields": ["targets"],
                "optional_fields": [],
            },
            "bio_update": {
                "description": "Update fields inside a user's bio",
                "required_fields": ["target", "fields"],
                "optional_fields": [],
            },
        }

    def get_prompt_instructions(self, action_name: str) -> dict:
        """Provide detailed prompt instructions for LLM on how to use bio actions."""
        if action_name == "bio_update":
            return {
                "description": "Update a user's bio with new information learned from conversation. Use this to store personality traits, preferences, life events, contacts, and feelings about the user.",
                "when_to_use": "When you learn new information about a user through conversation - their likes/dislikes, personality, life events, social connections, or when their emotional state changes.",
                "examples": [
                    {
                        "scenario": "User mentions they love pizza and hate pineapple on it",
                        "payload": {
                            "target": "user_123",
                            "fields": {
                                "likes": ["pizza"],
                                "not_likes": ["pineapple on pizza"]
                            }
                        }
                    },
                    {
                        "scenario": "User shares they got a promotion at work",
                        "payload": {
                            "target": "Jay",
                            "fields": {
                                "past_events": [{"date": "2025-09-10", "time": "14:30", "summary": "Got promoted at work"}],
                                "feelings": [{"type": "excited", "intensity": 9}]
                            }
                        }
                    },
                    {
                        "scenario": "User mentions their nickname and shares contact info",
                        "payload": {
                            "target": "user_456",
                            "fields": {
                                "known_as": ["Jay", "J"],
                                "contacts": {"telegram": ["@jay_username"], "email": ["jay@example.com"]},
                                "information": "Software developer who loves gaming"
                            }
                        }
                    }
                ],
                "field_types": {
                    "known_as": "List of nicknames and aliases",
                    "likes": "List of things the user enjoys",
                    "not_likes": "List of things the user dislikes",
                    "information": "Short descriptive text about the user",
                    "past_events": "List of significant life events with date/time/summary",
                    "feelings": "Current emotional state towards the user with type and intensity (1-10)",
                    "contacts": "Contact information organized by platform",
                    "social_accounts": "Social media handles and usernames"
                },
                "notes": [
                    "Target can be a user ID (numbers) or a name/nickname",
                    "Information should be factual and based on what the user actually shared",
                    "Update your feelings towards the users based on their actions, words and behavior",
                    "Store contact info when users share social handles or contact details",
                    "Record significant life events with proper timestamps"
                ]
            }
        elif action_name == "bio_full_request":
            return {
                "description": "Request complete bio information for one or more users. Use this when you need detailed information about users for context or to answer questions about them.",
                "when_to_use": "When you need to know more about users mentioned in conversation, or when asked directly about someone's preferences, history, or details.",
                "examples": [
                    {
                        "scenario": "User asks 'What do you know about Jay?'",
                        "payload": {
                            "targets": ["Jay"]
                        }
                    },
                    {
                        "scenario": "Planning something and need to know user preferences",
                        "payload": {
                            "targets": ["user_123", "user_456"]
                        }
                    }
                ],
                "notes": [
                    "Targets can be user IDs, names, or nicknames",
                    "Use this to retrieve detailed bio information for context",
                    "The response will contain complete user profiles including preferences, history, and contacts"
                ]
            }
        elif action_name == "static_inject":
            return {
                "description": "Automatically injects basic bio information for conversation participants. This action runs automatically and provides context about who is participating in the current conversation.",
                "when_to_use": "This action runs automatically - you don't need to call it explicitly. It provides background context about conversation participants.",
                "notes": [
                    "This action is automatic and provides lightweight user context",
                    "Gives you basic info about participants: nicknames, short bio, current feelings",
                    "Helps you understand who you're talking to and their general preferences"
                ]
            }
        return {}

    def get_static_injection(self, message=None, context_memory=None) -> dict:
        """Gather participants and inject short bios and feelings."""
        if not message or context_memory is None:
            self._participants = []
            return {}

        participants: list[dict[str, Any]] = []
        seen: set[str] = set()

        if getattr(message, "from_user", None):
            uid = str(message.from_user.id)
            participants.append(
                {
                    "id": uid,
                    "username": message.from_user.full_name,
                    "usertag": f"@{message.from_user.username}" if message.from_user.username else "(no tag)",
                }
            )
            seen.add(uid)

        chat_msgs = context_memory.get(message.chat_id, [])
        for m in chat_msgs:
            uid = str(m.get("user_id"))
            if uid and uid not in seen:
                participants.append(
                    {
                        "id": uid,
                        "username": m.get("username"),
                        "usertag": m.get("usertag"),
                    }
                )
                seen.add(uid)

        self._participants = participants

        if not participants:
            return {}

        data = []
        now = datetime.utcnow().isoformat()
        for p in participants:
            bio = get_bio_light(p["id"])
            short_info = bio.get("information", "")[:200]
            entry = {
                "id": p["id"],
                "usertag": p.get("usertag"),
                "nicknames": bio.get("known_as", []),
                "short_bio": short_info,
                "feelings": bio.get("feelings", []),
            }
            data.append(entry)
            update_bio_fields(p["id"], {"last_accessed": now})

        return {"participants": data}

    def _resolve_target(self, target: Any) -> str | None:
        if target is None:
            return None
        target = str(target)
        if target.isdigit():
            return target
        for p in self._participants:
            if target in {p.get("usertag"), p.get("username")}:
                return p["id"]
            bio = get_bio_light(p["id"])
            if target in bio.get("known_as", []):
                return p["id"]
        return None

    def execute_action(self, action: dict, context: dict, bot, original_message):
        action_type = action.get("type")
        payload = action.get("payload", {}) or {}
        if action_type == "bio_full_request":
            targets = payload.get("targets", [])
            # Fallback per compatibilità con formato vecchio
            if not targets:
                targets = action.get("targets", [])
                
            bios = []
            for t in targets:
                uid = self._resolve_target(t)
                if uid:
                    bios.append(get_bio_full(uid))
            if bios:
                import asyncio

                asyncio.create_task(
                    bot.send_message(
                        original_message.chat_id,
                        json.dumps(bios, ensure_ascii=False),
                    )
                )
        elif action_type == "bio_update":
            target = payload.get("target")
            fields = payload.get("fields", {})
            
            # Fallback per compatibilità con formato vecchio
            if not target:
                target = action.get("target")
            if not fields:
                fields = action.get("fields", {})
                
            uid = self._resolve_target(target)
            if uid and isinstance(fields, dict):
                update_bio_fields(uid, fields)


PLUGIN_CLASS = BioPlugin

