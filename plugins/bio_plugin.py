"""Bio plugin providing context injection and bio management actions."""

from __future__ import annotations

from typing import Any, Dict, List
import json

from core.ai_plugin_base import AIPluginBase
from core.logging_utils import log_debug, log_warning
from core.bio_manager import (
    get_bio_light,
    get_bio_full,
    update_bio_fields,
    resolve_target,
    BIO_RESUME_MAX,
)


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


__all__ = ["BioPlugin", "collect_prompt_participants"]
PLUGIN_CLASS = BioPlugin
