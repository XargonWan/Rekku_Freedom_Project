from __future__ import annotations

import os
from typing import Any

from core.ai_plugin_base import AIPluginBase
from core.db import insert_scheduled_event, get_conn

VALID_REPEATS = {"none", "daily", "weekly", "monthly", "always"}


class EventPlugin(AIPluginBase):
    """Minimal event plugin used for scheduling tests."""

    async def _ensure_table(self) -> None:
        """Ensure the scheduled_events table exists."""
        conn = await get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scheduled_events (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        `date` TEXT NOT NULL,
                        `time` TEXT DEFAULT '00:00',
                        next_run TEXT NOT NULL,
                        recurrence_type VARCHAR(20) DEFAULT 'none',
                        description TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        delivered BOOLEAN DEFAULT FALSE,
                        created_by VARCHAR(100) DEFAULT 'rekku'
                    )
                    """
                )
        finally:
            conn.close()

    async def handle_incoming_message(self, bot, message, prompt: dict):
        await self._ensure_table()
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

            conn = await get_conn()
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT 1 FROM scheduled_events WHERE date=%s AND time=%s AND description=%s",
                        (date, time_, desc),
                    )
                    row = await cur.fetchone()
                    if row:
                        await bot.notify(message.trainer_id, "⚠️ Event already exists")
                        return
                    await insert_scheduled_event(
                        date=date,
                        time=time_,
                        recurrence_type=repeat,
                        description=desc,
                        created_by="test",
                    )
                    saved = True
            finally:
                conn.close()

        if saved:
            await bot.send_message(message.chat_id, "📅 Event(s) saved")
        else:
            await bot.send_message(message.chat_id, "⚠️ No valid event actions in this prompt.")


PLUGIN_CLASS = EventPlugin
