from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

import asyncio
from core.db import get_conn
from core.logging_utils import log_error


JSON_LIST_FIELDS = {"known_as", "likes", "not_likes", "past_events", "feelings"}
JSON_DICT_FIELDS = {"contacts"}

DEFAULTS = {
    "known_as": [],
    "likes": [],
    "not_likes": [],
    "information": "",
    "past_events": [],
    "feelings": [],
    "contacts": {},
}


async def _ensure_user_exists(user_id: str) -> None:
    """Create an empty bio entry if the user is missing."""
    conn = await get_conn()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT 1 FROM bio WHERE id=%s", (user_id,))
        row = await cursor.fetchone()
        if not row:
            await cursor.execute(
                """
                INSERT INTO bio (id, known_as, likes, not_likes, information, past_events, feelings, contacts)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
                ),
            )
            await conn.commit()
    conn.close()


def _load_json_field(value: str | None, key: str, default: Any) -> Any:
    """Safely deserialize a JSON field."""
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception as e:  # pragma: no cover - corruption
        log_error(f"[bio_manager] Failed to decode {key}: {e}")
        return default


async def _save_json_field(user_id: str, key: str, value: Any) -> None:
    """Serialize and store a JSON field."""
    conn = await get_conn()
    async with conn.cursor() as cursor:
        await cursor.execute(f"UPDATE bio SET {key}=%s WHERE id=%s", (json.dumps(value), user_id))
        await conn.commit()
    conn.close()


async def _update_json_field(user_id: str, key: str, update_fn: Callable[[Any], Any]) -> None:
    await _ensure_user_exists(user_id)
    conn = await get_conn()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute(f"SELECT {key} FROM bio WHERE id=%s", (user_id,))
        row = await cursor.fetchone()
        current = _load_json_field(row[key], key, DEFAULTS.get(key))
        try:
            updated = update_fn(current)
        except Exception as e:  # pragma: no cover - logic error
            log_error(f"[bio_manager] Error updating {key}: {e}")
            return
        await _save_json_field(user_id, key, updated)
    conn.close()


async def get_bio_light(user_id: str) -> dict:
    """Return a lightweight bio for the user."""
    conn = await get_conn()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute(
            "SELECT known_as, likes, not_likes, feelings, information FROM bio WHERE id=%s",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return {}
        return {
            "known_as": _load_json_field(row["known_as"], "known_as", DEFAULTS["known_as"]),
            "likes": _load_json_field(row["likes"], "likes", DEFAULTS["likes"]),
            "not_likes": _load_json_field(row["not_likes"], "not_likes", DEFAULTS["not_likes"]),
            "feelings": _load_json_field(row["feelings"], "feelings", DEFAULTS["feelings"]),
            "information": row["information"] or "",
        }
    conn.close()


async def get_bio_full(user_id: str) -> dict:
    """Return the full bio for the user."""
    conn = await get_conn()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM bio WHERE id=%s", (user_id,))
        row = await cursor.fetchone()
        if not row:
            return {}
        result = {"id": row["id"], "information": row["information"] or ""}
        for key in JSON_LIST_FIELDS | JSON_DICT_FIELDS:
            result[key] = _load_json_field(row[key], key, DEFAULTS[key])
        return result
    conn.close()


async def update_bio_fields(user_id: str, updates: dict) -> None:
    """Safely update multiple fields in the user's bio, preserving existing values."""

    if not updates:
        return

    await _ensure_user_exists(user_id)
    current = await get_bio_full(user_id)

    merged: dict[str, Any] = {}

    valid_fields = {
        "known_as",
        "likes",
        "not_likes",
        "information",
        "past_events",
        "feelings",
        "contacts",
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

    conn = await get_conn()
    async with conn.cursor() as cursor:
        await cursor.execute(
            """
            REPLACE INTO bio (
                id, known_as, likes, not_likes, information,
                past_events, feelings, contacts
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
            ),
        )
        await conn.commit()
    conn.close()


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
