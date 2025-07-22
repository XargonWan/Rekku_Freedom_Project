# plugins/event_plugin.py

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from core.ai_plugin_base import AIPluginBase
from core.db import insert_scheduled_event
from core.logging_utils import log_debug, log_info, log_error


class EventPlugin(AIPluginBase):
    """Plugin that stores future events without using an LLM."""

    def __init__(self, notify_fn=None):
        self.reply_map: dict[int, tuple[int, int]] = {}
        self.notify_fn = notify_fn

    def get_supported_action_types(self):
        """Return the action types this plugin supports."""
        return ["event"]

    async def handle_custom_action(self, action_type: str, payload: dict):
        """Handle custom event actions."""
        if action_type == "event":
            log_info(f"[event_plugin] Handling event action with payload: {payload}")
            try:
                # Extract the nested action from the payload
                when = payload.get("when")
                action = payload.get("action", {})
                
                if when and action:
                    # Store the scheduled event
                    self._save_scheduled_event(when, action)
                    log_info(f"[event_plugin] Event scheduled for {when}")
                else:
                    log_error("[event_plugin] Invalid event payload: missing 'when' or 'action'")
            except Exception as e:
                log_error(f"[event_plugin] Error handling event action: {e}")
        else:
            log_error(f"[event_plugin] Unsupported action type: {action_type}")

    def _save_scheduled_event(self, when: str, action: dict):
        """Save a scheduled event to the database."""
        try:
            # Parse the when timestamp
            event_time = datetime.fromisoformat(when.replace('Z', '+00:00'))
            
            # Store in database
            insert_scheduled_event(
                event_time=event_time,
                action_type=action.get("type", "message"),
                action_payload=action.get("payload", {}),
                interface=action.get("interface", "telegram")
            )
            log_debug(f"[event_plugin] Saved scheduled event for {event_time}")
        except Exception as e:
            log_error(f"[event_plugin] Failed to save scheduled event: {e}")

    def _save_event(self, payload: dict) -> None:
        """Validate and store a single event payload."""
        tz = ZoneInfo(os.getenv("TZ", "UTC"))
        allowed_repeats = {"none", "daily", "weekly", "monthly"}

        date_str = payload.get("date")
        desc = payload.get("description")
        if not date_str or not desc:
            return

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return

        time_val = payload.get("time")
        if time_val:
            try:
                datetime.strptime(time_val, "%H:%M")
            except ValueError:
                return

        repeat = payload.get("repeat", "none")
        if repeat not in allowed_repeats:
            return

        try:
            datetime.strptime(f"{date_str} {time_val or '00:00'}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        except ValueError:
            pass


# Definisce la classe plugin per il caricamento automatico
PLUGIN_CLASS = EventPlugin
