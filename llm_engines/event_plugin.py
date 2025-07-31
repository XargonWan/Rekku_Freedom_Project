from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from core.ai_plugin_base import AIPluginBase
from core.db import insert_scheduled_event, get_db

VALID_REPEATS = {"none", "daily", "weekly", "monthly", "always"}


class EventPlugin(AIPluginBase):
    """Minimal event plugin used for scheduling tests."""

    async def handle_incoming_message(self, bot, message, prompt: dict):
        actions = prompt.get("actions", [])
        if not actions:
            await bot.send_message(message.chat_id, "⚠️ No valid event actions in this prompt.")
            return

        saved = False
        for action in actions:
            if action.get("type") != "event":
                continue
            payload = action.get("payload", {})
            date = payload.get("date")
            time_ = payload.get("time")
            repeat = payload.get("repeat", "none")
            desc = payload.get("description")

            if repeat not in VALID_REPEATS:
                await bot.send_message(message.chat_id, "❌ Invalid repeat value")
                return
            if not date or not desc:
                continue

            with get_db() as db:
                row = db.execute(
                    "SELECT 1 FROM scheduled_events WHERE date=? AND time=? AND description=?",
                    (date, time_, desc),
                ).fetchone()
                if row:
                    await bot.send_message(message.chat_id, "⚠️ Event already exists")
                    return
                insert_scheduled_event(date=date, time_=time_, repeat=repeat, description=desc, created_by="test")
                saved = True

        if saved:
            await bot.send_message(message.chat_id, "📅 Event(s) saved")
        else:
            await bot.send_message(message.chat_id, "⚠️ No valid event actions in this prompt.")


PLUGIN_CLASS = EventPlugin
