from __future__ import annotations

"""Core bio manager for persistent user profiles.

This module stores and retrieves user biographies from the SQLite database
``rekku_memories.db``. It provides helpers to fetch public or full bios,
update individual fields, and manage lists such as likes or past events.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.db import get_db
from core.logging_utils import log_warning

# ---------------------------------------------------------------------------
# Constants and defaults
# ---------------------------------------------------------------------------

LIST_FIELDS = {
    "known_as",
    "likes",
    "not_likes",
    "past_events",
    "feelings",
    "social_accounts",
}

DICT_FIELDS = {"contacts", "privacy"}

STRING_FIELDS = {"information"}

ALL_FIELDS = LIST_FIELDS | DICT_FIELDS | STRING_FIELDS | {"created_at", "last_accessed"}

DEFAULT_PRIVACY = {"level": "public", "visible_to": [], "note": ""}

DEFAULTS: Dict[str, Any] = {
    "known_as": [],
    "likes": [],
    "not_likes": [],
    "information": "",
    "past_events": [],
    "feelings": [],
    "contacts": {},
    "social_accounts": [],
    "privacy": DEFAULT_PRIVACY,
    "created_at": None,
    "last_accessed": None,
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_table_exists(db) -> None:
    """Create the ``bio`` table if missing."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS bio (
            id TEXT PRIMARY KEY,
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


def _load_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        if isinstance(value, str):
            return json.loads(value)
        return value
    except Exception:
        return default


def _ensure_user_exists(user_id: str) -> None:
    """Ensure a blank bio record exists for ``user_id``."""
    now = datetime.utcnow().isoformat()
    with get_db() as db:
        _ensure_table_exists(db)
        row = db.execute("SELECT 1 FROM bio WHERE id=?", (user_id,)).fetchone()
        if row:
            return
        db.execute(
            """
            INSERT INTO bio (
                id, known_as, likes, not_likes, information,
                past_events, feelings, contacts, social_accounts,
                privacy, created_at, last_accessed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps([]),
                json.dumps(DEFAULT_PRIVACY),
                now,
                now,
            ),
        )


def _merge_lists(a: Optional[List[Any]], b: List[Any]) -> List[Any]:
    base = list(a or [])
    for item in b:
        if item not in base:
            base.append(item)
    return base


def _merge_dicts(a: Optional[Dict[str, Any]], b: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(a or {})
    merged.update(b)
    return merged


def _resolve_nested(obj: Dict[str, Any], path: List[str]) -> Tuple[Dict[str, Any], str]:
    cur = obj
    for key in path[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    return cur, path[-1]


def resolve_target(target: Any) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a ``target`` specification to ``(user_id, name)``."""
    if isinstance(target, str):
        return target, target
    if isinstance(target, dict):
        uid = target.get("id") or target.get("user_id") or target.get("name")
        name = target.get("name")
        return uid, name
    return None, None

# ---------------------------------------------------------------------------
# Retrieval helpers
# ---------------------------------------------------------------------------

def get_bio_light(user_id: str, viewer_id: Optional[str] = None) -> dict:
    """Return a lightweight bio respecting privacy rules."""
    with get_db() as db:
        _ensure_table_exists(db)
        row = db.execute(
            """
            SELECT known_as, likes, not_likes, feelings, information, privacy
            FROM bio WHERE id=?
            """,
            (user_id,),
        ).fetchone()
        if not row:
            return {}
        privacy = _load_json(row["privacy"], DEFAULT_PRIVACY)
        data = {
            "known_as": _load_json(row["known_as"], []),
            "likes": _load_json(row["likes"], []),
            "not_likes": _load_json(row["not_likes"], []),
            "feelings": _load_json(row["feelings"], []),
            "information": row["information"] or "",
        }
        level = privacy.get("level", "public")
        visible_to = privacy.get("visible_to", []) or []
        if level == "private" and viewer_id not in visible_to:
            result: dict = {}
        elif level == "restricted" and viewer_id not in visible_to:
            result = {
                "known_as": data.get("known_as", []),
                "information": data.get("information", ""),
            }
        else:
            result = data
        now = datetime.utcnow().isoformat()
        db.execute("UPDATE bio SET last_accessed=? WHERE id=?", (now, user_id))
        return result


def get_bio_full(user_id: str) -> dict:
    """Return the full bio for ``user_id`` without enforcing privacy."""
    with get_db() as db:
        _ensure_table_exists(db)
        row = db.execute("SELECT * FROM bio WHERE id=?", (user_id,)).fetchone()
        if not row:
            return {}
        bio = {"id": row["id"]}
        for field in LIST_FIELDS:
            bio[field] = _load_json(row[field], DEFAULTS[field])
        for field in DICT_FIELDS:
            bio[field] = _load_json(row[field], DEFAULTS[field])
        for field in STRING_FIELDS:
            bio[field] = row[field] or ""
        bio["created_at"] = row["created_at"]
        bio["last_accessed"] = row["last_accessed"]
        now = datetime.utcnow().isoformat()
        db.execute("UPDATE bio SET last_accessed=? WHERE id=?", (now, user_id))
        bio["last_accessed"] = now
        return bio

# ---------------------------------------------------------------------------
# Update helpers
# ---------------------------------------------------------------------------

def update_bio_fields(user_id: str, updates: dict) -> None:
    """Merge ``updates`` into the existing record for ``user_id``."""
    if not updates:
        return
    _ensure_user_exists(user_id)
    with get_db() as db:
        _ensure_table_exists(db)
        row = db.execute("SELECT * FROM bio WHERE id=?", (user_id,)).fetchone()
    current = {"id": user_id}
    for field in LIST_FIELDS:
        current[field] = _load_json(row[field], DEFAULTS[field])
    for field in DICT_FIELDS:
        current[field] = _load_json(row[field], DEFAULTS[field])
    for field in STRING_FIELDS:
        current[field] = row[field] or ""
    current["created_at"] = row["created_at"]
    merged = current.copy()
    for field, value in updates.items():
        if field not in ALL_FIELDS:
            continue
        if value is None:
            if field in LIST_FIELDS:
                merged[field] = []
            elif field in DICT_FIELDS:
                merged[field] = {}
            elif field in STRING_FIELDS:
                merged[field] = ""
            continue
        if field in LIST_FIELDS:
            if not isinstance(value, list):
                value = [value]
            merged[field] = _merge_lists(merged.get(field), value)
        elif field in DICT_FIELDS:
            if isinstance(value, dict):
                merged[field] = _merge_dicts(merged.get(field), value)
        elif field in STRING_FIELDS:
            merged[field] = str(value)
    if not merged.get("created_at"):
        merged["created_at"] = datetime.utcnow().isoformat()
    merged["last_accessed"] = datetime.utcnow().isoformat()
    with get_db() as db:
        _ensure_table_exists(db)
        db.execute(
            """
            UPDATE bio SET
                known_as=?, likes=?, not_likes=?, information=?,
                past_events=?, feelings=?, contacts=?, social_accounts=?,
                privacy=?, created_at=?, last_accessed=?
            WHERE id=?
            """,
            (
                json.dumps(merged.get("known_as", [])),
                json.dumps(merged.get("likes", [])),
                json.dumps(merged.get("not_likes", [])),
                merged.get("information", ""),
                json.dumps(merged.get("past_events", [])),
                json.dumps(merged.get("feelings", [])),
                json.dumps(merged.get("contacts", {})),
                json.dumps(merged.get("social_accounts", [])),
                json.dumps(merged.get("privacy", DEFAULT_PRIVACY)),
                merged.get("created_at"),
                merged.get("last_accessed"),
                user_id,
            ),
        )


def append_to_bio_list(user_id: str, field: str, value: Any) -> None:
    """Append ``value`` to a list field, supporting dotted paths."""
    _ensure_user_exists(user_id)
    bio = get_bio_full(user_id)
    parts = field.split(".")
    container, key = _resolve_nested(bio, parts)
    lst = container.get(key, []) if isinstance(container, dict) else []
    if not isinstance(lst, list):
        lst = []
    if value not in lst:
        lst.append(value)
    container[key] = lst
    update_bio_fields(user_id, {parts[0]: bio.get(parts[0])})


def add_past_event(user_id: str, summary: str, dt: Optional[datetime] = None) -> None:
    """Append a past event entry."""
    dt = dt or datetime.utcnow()
    entry = {
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M"),
        "summary": summary,
    }
    append_to_bio_list(user_id, "past_events", entry)


def alter_feeling(user_id: str, feeling_type: str, intensity: int) -> None:
    """Add or replace a feeling entry."""
    _ensure_user_exists(user_id)
    normalized = feeling_type.lower().strip()
    bio = get_bio_full(user_id)
    feelings = bio.get("feelings", [])
    if not isinstance(feelings, list):
        feelings = []
    for f in feelings:
        if isinstance(f, dict) and f.get("type", "").lower() == normalized:
            f["intensity"] = intensity
            break
    else:
        feelings.append({"type": normalized, "intensity": intensity})
    update_bio_fields(user_id, {"feelings": feelings})

# ---------------------------------------------------------------------------
# End of module
# ---------------------------------------------------------------------------
