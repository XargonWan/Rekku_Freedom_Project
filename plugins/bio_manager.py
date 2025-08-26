from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable
import asyncio
import aiomysql

from core.db import get_conn
from core.logging_utils import log_error


JSON_LIST_FIELDS = {"known_as", "likes", "not_likes", "past_events", "feelings"}
JSON_DICT_FIELDS = {"contacts", "social_accounts"}

DEFAULTS = {
    "known_as": [],
    "likes": [],
    "not_likes": [],
    "information": "",
    "past_events": [],
    "feelings": [],
    "contacts": {},
    "social_accounts": {},
    "privacy": "default",
    "created_at": "",
    "last_accessed": "",
}


def _run(coro):
    """Run a coroutine safely regardless of event loop state."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                new_loop = asyncio.new_event_loop()
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            return loop.run_until_complete(coro)
        except RuntimeError:
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()


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
    _run(
        _execute(
            """
            CREATE TABLE IF NOT EXISTS bio (
                id VARCHAR(255) PRIMARY KEY,
                known_as TEXT,
                likes TEXT,
                not_likes TEXT,
                information TEXT,
                past_events TEXT,
                feelings TEXT,
                contacts TEXT,
                social_accounts TEXT,
                privacy TEXT,
                created_at TEXT,
                last_accessed TEXT
            )
            """
        )
    )


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
                    privacy, created_at, last_accessed
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    _run(_execute(f"UPDATE bio SET {key}=%s WHERE id=%s", (json.dumps(value), user_id)))


def _update_json_field(user_id: str, key: str, update_fn: Callable[[Any], Any]) -> None:
    _ensure_user_exists(user_id)
    row = _run(_fetchone(f"SELECT {key} FROM bio WHERE id=%s", (user_id,)))
    current = _load_json_field(row.get(key), key, DEFAULTS.get(key))
    try:
        updated = update_fn(current)
    except Exception as e:  # pragma: no cover - logic error
        log_error(f"[bio_manager] Error updating {key}: {e}")
        return
    _save_json_field(user_id, key, updated)


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
    return result


def update_bio_fields(user_id: str, updates: dict) -> None:
    """Safely update multiple fields in the user's bio, preserving existing values."""

    if not updates:
        return

    _ensure_user_exists(user_id)
    current = get_bio_full(user_id)

    merged: dict[str, Any] = {}

    valid_fields = {
        "known_as",
        "likes",
        "not_likes",
        "information",
        "past_events",
        "feelings",
        "contacts",
        "social_accounts",
        "privacy",
        "created_at",
        "last_accessed",
    }

    for field in valid_fields:
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
            old_val.update(new_val)
            merged[field] = old_val
        else:
            merged[field] = new_val

    _run(
        _execute(
            """
            REPLACE INTO bio (
                id, known_as, likes, not_likes, information,
                past_events, feelings, contacts, social_accounts,
                privacy, created_at, last_accessed
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                json.dumps(merged.get("known_as", [])),
                json.dumps(merged.get("likes", [])),
                json.dumps(merged.get("not_likes", [])),
                merged.get("information", ""),
                json.dumps(merged.get("past_events", [])),
                json.dumps(merged.get("feelings", [])),
                json.dumps(merged.get("contacts", {})),
                json.dumps(merged.get("social_accounts", {})),
                merged.get("privacy", "default"),
                merged.get("created_at", datetime.utcnow().isoformat()),
                merged.get("last_accessed", datetime.utcnow().isoformat()),
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

    def get_static_injection(self, message, context_memory) -> dict:
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
            uid = self._resolve_target(target)
            if uid and isinstance(fields, dict):
                update_bio_fields(uid, fields)


PLUGIN_CLASS = BioPlugin

