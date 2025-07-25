from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from core.db import get_db
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


def _ensure_user_exists(user_id: str) -> None:
    """Insert a blank bio row if missing."""
    with get_db() as db:
        row = db.execute("SELECT 1 FROM bio WHERE id=?", (user_id,)).fetchone()
        if not row:
            db.execute(
                """
                INSERT INTO bio (id, known_as, likes, not_likes, information, past_events, feelings, contacts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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


def _load_json(text: str | None, key: str) -> Any:
    if not text:
        return DEFAULTS[key]
    try:
        return json.loads(text)
    except Exception as e:  # pragma: no cover - corruption
        log_error(f"[bio_manager] Failed to decode {key}: {e}")
        return DEFAULTS[key]


def _update_json_field(user_id: str, key: str, update_fn: Callable[[Any], Any]) -> None:
    _ensure_user_exists(user_id)
    with get_db() as db:
        row = db.execute(f"SELECT {key} FROM bio WHERE id=?", (user_id,)).fetchone()
        current = _load_json(row[key], key)
        try:
            updated = update_fn(current)
        except Exception as e:  # pragma: no cover - logic error
            log_error(f"[bio_manager] Error updating {key}: {e}")
            return
        db.execute(f"UPDATE bio SET {key}=? WHERE id=?", (json.dumps(updated), user_id))


def get_bio_light(user_id: str) -> dict:
    """Return a lightweight bio for the user."""
    with get_db() as db:
        row = db.execute(
            "SELECT known_as, likes, not_likes, feelings, information FROM bio WHERE id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return {}
        return {
            "known_as": _load_json(row["known_as"], "known_as"),
            "likes": _load_json(row["likes"], "likes"),
            "not_likes": _load_json(row["not_likes"], "not_likes"),
            "feelings": _load_json(row["feelings"], "feelings"),
            "information": row["information"] or "",
        }


def get_bio_full(user_id: str) -> dict:
    """Return the full bio for the user."""
    with get_db() as db:
        row = db.execute("SELECT * FROM bio WHERE id=?", (user_id,)).fetchone()
        if not row:
            return {}
        result = {"id": row["id"], "information": row["information"] or ""}
        for key in JSON_LIST_FIELDS | JSON_DICT_FIELDS:
            result[key] = _load_json(row[key], key)
        return result


def update_bio_fields(user_id: str, updates: dict) -> None:
    """Upsert and merge bio fields."""
    _ensure_user_exists(user_id)
    with get_db() as db:
        row = db.execute("SELECT * FROM bio WHERE id=?", (user_id,)).fetchone()

    if not row:
        return

    current = {key: row[key] for key in row.keys()}

    for key, value in updates.items():
        if key in JSON_LIST_FIELDS:
            existing = _load_json(current[key], key)
            if isinstance(value, list):
                for item in value:
                    if item not in existing:
                        existing.append(item)
                current[key] = json.dumps(existing)
            else:  # replace if not list
                current[key] = json.dumps(value)
        elif key in JSON_DICT_FIELDS:
            existing = _load_json(current[key], key)
            if isinstance(value, dict):
                merged = existing | value
                current[key] = json.dumps(merged)
            else:
                current[key] = json.dumps(value)
        elif key == "information":
            current[key] = value
        else:
            # unknown field, store as text
            current[key] = json.dumps(value)

    cols = [k for k in updates.keys()]
    set_clause = ", ".join(f"{c}=?" for c in cols)
    values = [current[c] for c in cols]
    values.append(user_id)
    with get_db() as db:
        db.execute(f"UPDATE bio SET {set_clause} WHERE id=?", values)


def append_to_bio_list(user_id: str, field: str, value: Any) -> None:
    parts = field.split(".")
    if len(parts) == 1:
        key = parts[0]
        def updater(lst):
            if not isinstance(lst, list):
                lst = []
            if value not in lst:
                lst.append(value)
            return lst
        _update_json_field(user_id, key, updater)
    else:
        key, sub = parts[0], parts[1]
        def updater(obj):
            if not isinstance(obj, dict):
                obj = {}
            lst = obj.get(sub, [])
            if value not in lst:
                lst.append(value)
            obj[sub] = lst
            return obj
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
    def updater(feels):
        if not isinstance(feels, list):
            feels = []
        lower = feeling_type.lower()
        for f in feels:
            if isinstance(f, dict) and f.get("type", "").lower() == lower:
                f["intensity"] = intensity
                break
        else:
            feels.append({"type": feeling_type, "intensity": intensity})
        return feels
    _update_json_field(user_id, "feelings", updater)
