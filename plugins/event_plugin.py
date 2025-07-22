# plugins/event_plugin.py

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from core.ai_plugin_base import AIPluginBase
from core.db import insert_scheduled_event
from core.logging_utils import log_debug


class EventPlugin(AIPluginBase):
    """Plugin that stores future events without using an LLM."""

    def __init__(self, notify_fn=None):
        self.reply_map: dict[int, tuple[int, int]] = {}
        self.notify_fn = notify_fn

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
