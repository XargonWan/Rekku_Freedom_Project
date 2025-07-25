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
    """Create an empty bio entry if the user is missing."""
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
    with get_db() as db:
        db.execute(f"UPDATE bio SET {key}=? WHERE id=?", (json.dumps(value), user_id))


def _update_json_field(user_id: str, key: str, update_fn: Callable[[Any], Any]) -> None:
    _ensure_user_exists(user_id)
    with get_db() as db:
        row = db.execute(f"SELECT {key} FROM bio WHERE id=?", (user_id,)).fetchone()
        current = _load_json_field(row[key], key, DEFAULTS.get(key))
        try:
            updated = update_fn(current)
        except Exception as e:  # pragma: no cover - logic error
            log_error(f"[bio_manager] Error updating {key}: {e}")
            return
        _save_json_field(user_id, key, updated)


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
            "known_as": _load_json_field(row["known_as"], "known_as", DEFAULTS["known_as"]),
            "likes": _load_json_field(row["likes"], "likes", DEFAULTS["likes"]),
            "not_likes": _load_json_field(row["not_likes"], "not_likes", DEFAULTS["not_likes"]),
            "feelings": _load_json_field(row["feelings"], "feelings", DEFAULTS["feelings"]),
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
            result[key] = _load_json_field(row[key], key, DEFAULTS[key])
        return result


def update_bio_fields(user_id: str, updates: dict) -> None:
    """Safely merge ``updates`` into an existing bio."""

    if not updates:
        return

    _ensure_user_exists(user_id)
    current = get_bio_full(user_id)
    if not current:
        current = {**DEFAULTS, "information": ""}

    for key, value in updates.items():
        if key not in DEFAULTS and key != "information":
            # Ignore fields outside the schema
            continue

        if key in JSON_LIST_FIELDS:
            existing = current.get(key, [])
            if not isinstance(existing, list):
                existing = []
            if isinstance(value, list):
                for item in value:
                    if item not in existing:
                        existing.append(item)
            else:
                if value not in existing:
                    existing.append(value)
            current[key] = existing
        elif key in JSON_DICT_FIELDS:
            existing = current.get(key, {})
            if not isinstance(existing, dict):
                existing = {}
            if isinstance(value, dict):
                for sub_k, sub_v in value.items():
                    if isinstance(sub_v, list):
                        cur_list = existing.get(sub_k, [])
                        if not isinstance(cur_list, list):
                            cur_list = []
                        for item in sub_v:
                            if item not in cur_list:
                                cur_list.append(item)
                        existing[sub_k] = cur_list
                    else:
                        existing[sub_k] = sub_v
            else:
                existing = value
            current[key] = existing
        else:  # information or any simple field
            current[key] = value

    with get_db() as db:
        db.execute(
            """
            REPLACE INTO bio (
                id, known_as, likes, not_likes, information, past_events, feelings, contacts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                json.dumps(current.get("known_as", [])),
                json.dumps(current.get("likes", [])),
                json.dumps(current.get("not_likes", [])),
                current.get("information", ""),
                json.dumps(current.get("past_events", [])),
                json.dumps(current.get("feelings", [])),
                json.dumps(current.get("contacts", {})),
            ),
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
