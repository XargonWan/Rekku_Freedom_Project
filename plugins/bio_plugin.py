"""Bio plugin providing context injection and bio management actions."""

from __future__ import annotations

from typing import Any, Dict, List, Iterable, Optional, Tuple
import json
from datetime import datetime

from core.ai_plugin_base import AIPluginBase
from core.logging_utils import log_debug, log_warning, log_error
from core.db import get_db

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

STRING_FIELDS = {"bio_resume", "bio_extended"}

ALL_FIELDS = LIST_FIELDS | DICT_FIELDS | STRING_FIELDS | {
    "created_at",
    "last_accessed",
}

DEFAULT_PRIVACY = {"level": "public", "visible_to": [], "note": ""}

# Maximum length for the short resume stored in ``bio_resume``
BIO_RESUME_MAX = 200

DEFAULTS: Dict[str, Any] = {
    "known_as": [],
    "likes": [],
    "not_likes": [],
    "bio_resume": "",
    "bio_extended": "",
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
    """Create the ``bio`` table if it does not already exist."""

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS bio (
            id TEXT PRIMARY KEY,
            known_as TEXT,
            likes TEXT,
            not_likes TEXT,
            bio_resume TEXT,
            bio_extended TEXT,
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


def _ensure_user_exists(user_id: str) -> None:
    """Create an empty bio entry if the user does not yet exist."""

    now = datetime.utcnow().isoformat()
    with get_db() as db:
        _ensure_table_exists(db)
        row = db.execute("SELECT 1 FROM bio WHERE id=?", (user_id,)).fetchone()
        if row:
            return

        db.execute(
            """
            INSERT INTO bio (
                id, known_as, likes, not_likes, bio_resume, bio_extended,
                past_events, feelings, contacts, social_accounts,
                privacy, created_at, last_accessed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                json.dumps([]),
                json.dumps([]),
                json.dumps([]),
                "",
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


def _load_json(value: Any, default: Any) -> Any:
    """Safely deserialize *value* as JSON returning *default* on error."""

    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception as exc:  # pragma: no cover - corrupted data
        log_error(f"[bio_plugin] Failed to decode JSON field: {exc}")
        return default


def _merge_lists(a: Iterable[Any] | None, b: Iterable[Any] | None) -> list:
    """Return the union of two iterables preserving order."""

    result: list = list(a or [])
    for item in b or []:
        if item not in result:
            result.append(item)
    return result


def _merge_dicts(a: Dict[str, Any] | None, b: Dict[str, Any] | None) -> Dict[str, Any]:
    """Shallow merge of two dictionaries."""

    merged: Dict[str, Any] = dict(a or {})
    if b:
        merged.update(b)
    return merged


def _resolve_nested(obj: Dict[str, Any], path: Iterable[str]) -> Tuple[Dict[str, Any], str]:
    """Traverse *obj* following *path* returning (container, last_key)."""

    current = obj
    segments = list(path)
    for key in segments[:-1]:
        current = current.setdefault(key, {}) if isinstance(current, dict) else {}
    return current, segments[-1]


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
    """Return a lightweight bio for *user_id* respecting privacy settings."""

    with get_db() as db:
        _ensure_table_exists(db)
        row = db.execute(
            """
            SELECT known_as, likes, not_likes, feelings, bio_resume, privacy
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
            "bio_resume": (row["bio_resume"] or "")[:BIO_RESUME_MAX],
        }

        level = privacy.get("level", "public")
        visible_to = privacy.get("visible_to", []) or []

        if level == "private" and viewer_id not in visible_to:
            result: dict = {}
        elif level == "restricted" and viewer_id not in visible_to:
            result = {
                "known_as": data.get("known_as", []),
                "bio_resume": data.get("bio_resume", ""),
            }
        else:  # public or permitted viewer
            result = data

        now = datetime.utcnow().isoformat()
        db.execute("UPDATE bio SET last_accessed=? WHERE id=?", (now, user_id))
        return result


def get_bio_full(user_id: str) -> dict:
    """Return the full bio for *user_id* without enforcing privacy."""

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
    """Merge *updates* into the bio for *user_id*."""

    if not updates:
        return

    _ensure_user_exists(user_id)

    # Read current values
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
            if field == "bio_extended" and "bio_resume" not in updates:
                merged["bio_resume"] = str(value)[:BIO_RESUME_MAX]
            elif field == "bio_resume":
                value = str(value)[:BIO_RESUME_MAX]
            merged[field] = value

    if not merged.get("created_at"):
        merged["created_at"] = datetime.utcnow().isoformat()
    merged["last_accessed"] = datetime.utcnow().isoformat()

    with get_db() as db:
        _ensure_table_exists(db)
        db.execute(
            """
            UPDATE bio SET
                known_as=?, likes=?, not_likes=?, bio_resume=?, bio_extended=?,
                past_events=?, feelings=?, contacts=?, social_accounts=?,
                privacy=?, created_at=?, last_accessed=?
            WHERE id=?
            """,
            (
                json.dumps(merged.get("known_as", [])),
                json.dumps(merged.get("likes", [])),
                json.dumps(merged.get("not_likes", [])),
                merged.get("bio_resume", ""),
                merged.get("bio_extended", ""),
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
    """Append *value* to a list field, supporting dotted paths for nesting."""

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
    """Append a past event entry to the user's bio."""

    dt = dt or datetime.utcnow()
    entry = {
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M"),
        "summary": summary,
    }
    append_to_bio_list(user_id, "past_events", entry)


def alter_feeling(user_id: str, feeling_type: str, intensity: int) -> None:
    """Add or replace a feeling entry for *user_id*."""

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


def collect_prompt_participants(messages: List[dict], viewer_id: str) -> List[dict]:
    """Return participants with bios for prompt injection.

    Parameters
    ----------
    messages:
        List of recent message dictionaries containing ``user_id``, ``username``
        and ``usertag`` keys.
    viewer_id:
        The id of the user who will view the bios (for privacy enforcement).
    """

    participants: List[dict] = []
    seen: set[str] = set()

    for msg in messages:
        uid = msg.get("user_id")
        if not uid or uid in seen:
            continue
        name = msg.get("username", "")
        usertag = msg.get("usertag", "")

        # Ensure the record exists and update last contact
        update_bio_fields(uid, {})

        bio = get_bio_light(uid, viewer_id=viewer_id)
        participants.append(
            {
                "id": uid,
                "name": name,
                "usertag": usertag,
                "known_as": bio.get("known_as", []),
                "feelings": bio.get("feelings", []),
                "short_bio": bio.get("bio_resume", "")[:BIO_RESUME_MAX],
            }
        )
        seen.add(uid)

    return participants


class BioPlugin(AIPluginBase):
    """Plugin exposing actions to query and update bios."""

    def __init__(self, notify_fn=None):
        self.notify_fn = notify_fn
        log_debug("[bio_plugin] BioPlugin initialized")

    def get_supported_action_types(self) -> List[str]:
        return ["bio_full_request", "bio_update"]

    def get_supported_actions(self) -> Dict[str, Dict[str, Any]]:
        return {
            "bio_full_request": {
                "required_fields": ["targets"],
                "optional_fields": [],
                "description": "Return the full bios for the specified users",
            },
            "bio_update": {
                "required_fields": ["target", "updates"],
                "optional_fields": [],
                "description": "Update or merge fields into a user's bio",
            },
        }

    def get_prompt_instructions(self, action_name: str) -> dict:
        if action_name == "bio_full_request":
            return {
                "description": "Retrieve full bios for users",
                "payload": {"targets": ["user_123", {"id": "user_456", "name": "Jay"}]},
            }
        if action_name == "bio_update":
            return {
                "description": "Update a user's bio fields",
                "payload": {
                    "target": "user_123",
                    "updates": {"likes": ["pizza"], "bio_extended": "Loves coding"},
                },
            }
        return {}

    async def execute_action(self, action: dict, context: dict, bot, original_message):
        action_type = action.get("type")
        payload = action.get("payload", {})

        if action_type == "bio_full_request":
            targets = payload.get("targets", [])
            results = []
            for tgt in targets:
                uid, _ = resolve_target(tgt)
                if uid:
                    results.append(get_bio_full(uid))
            if self.notify_fn:
                try:
                    self.notify_fn(json.dumps({"bio_full_request": results}, ensure_ascii=False))
                except Exception:
                    log_warning("[bio_plugin] notify_fn failed for bio_full_request")
            return

        if action_type == "bio_update":
            target = payload.get("target")
            updates = payload.get("updates", {})
            uid, _ = resolve_target(target)
            if uid and isinstance(updates, dict):
                update_bio_fields(uid, updates)
                if self.notify_fn:
                    try:
                        self.notify_fn(f"bio_update applied for {uid}")
                    except Exception:
                        log_warning("[bio_plugin] notify_fn failed for bio_update")

    # ------------------------------------------------------------------
    # Static injection for prompt context
    # ------------------------------------------------------------------

    def gather_static_injection(self, message, context_memory) -> Dict[str, Any]:
        """Provide participant bios for the current chat."""
        try:
            chat_id = message.chat_id
            messages = list(context_memory.get(chat_id, []))[-10:]
            viewer_id = f"user_{message.from_user.id}"
            participants = collect_prompt_participants(messages, viewer_id)
            if participants:
                return {"participants": participants}
        except Exception as exc:  # pragma: no cover - defensive
            log_warning(f"[bio_plugin] gather_static_injection failed: {exc}")
        return {}


__all__ = [
    "BioPlugin",
    "get_bio_light",
    "get_bio_full",
    "update_bio_fields",
    "append_to_bio_list",
    "add_past_event",
    "alter_feeling",
    "resolve_target",
    "BIO_RESUME_MAX",
]
PLUGIN_CLASS = BioPlugin
