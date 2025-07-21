# llm_engines/event_plugin.py

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

    async def handle_incoming_message(self, bot, message, prompt):
        tz = ZoneInfo(os.getenv("TZ", "UTC"))
        allowed_repeats = {"none", "daily", "weekly", "monthly"}
        saved: list[str] = []
        actions = prompt.get("actions", [])

        for action in actions:
            if not isinstance(action, dict) or action.get("type") != "event":
                continue

            payload = action.get("payload", {})
            date_str = payload.get("date")
            desc = payload.get("description")
            if not date_str or not desc:
                continue

            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=(
                        f"❌ Invalid date format: '{date_str}'. Use YYYY-MM-DD.\n"
                        "Please rewrite the whole event snippet correctly to ensure it gets saved."
                    ),
                    reply_to_message_id=message.message_id,
                )
                continue

            time_val = payload.get("time")
            if time_val:
                try:
                    datetime.strptime(time_val, "%H:%M")
                except ValueError:
                    await bot.send_message(
                        chat_id=message.chat_id,
                        text=(
                            f"❌ Invalid time format: '{time_val}'. Use HH:MM in 24h format.\n"
                            "Please rewrite the whole event snippet correctly to ensure it gets saved."
                        ),
                        reply_to_message_id=message.message_id,
                    )
                    continue

            repeat = payload.get("repeat", "none")
            if repeat not in allowed_repeats:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=(
                        f"❌ Invalid repeat value: '{repeat}'.\n"
                        "Allowed values: none, daily, weekly, monthly.\n"
                        "Please rewrite the whole event snippet correctly to ensure it gets saved."
                    ),
                    reply_to_message_id=message.message_id,
                )
                continue

            # parse into timezone to ensure correctness
            _ = datetime.strptime(f"{date_str} {time_val or '00:00'}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)

            try:
                insert_scheduled_event(date_str, time_val, repeat, desc)
            except sqlite3.IntegrityError:
                summary = f"{date_str}"
                if time_val:
                    summary += f" {time_val}"
                summary += f" → {desc}"
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=(
                        f"⚠️ Event already exists: {summary}.\n"
                        "Please rewrite the whole event snippet correctly if this was a mistake."
                    ),
                    reply_to_message_id=message.message_id,
                )
                continue

            summary = f"{date_str}"
            if time_val:
                summary += f" {time_val}"
            summary += f" → {desc}"
            saved.append(summary)
            log_debug(f"[event] Saved event: {summary}")

        if not saved:
            await bot.send_message(
                chat_id=message.chat_id,
                text="⚠️ No valid event actions in this prompt.",
                reply_to_message_id=message.message_id,
            )
            return None

        lines = "\n".join(f"• {s}" for s in saved)
        await bot.send_message(
            chat_id=message.chat_id,
            text=f"📅 Event(s) saved:\n{lines}",
            reply_to_message_id=message.message_id,
        )
        return None

    async def generate_response(self, messages):
        return "This plugin does not generate text."

    def get_target(self, trainer_message_id):
        return self.reply_map.get(trainer_message_id)

    def clear(self, trainer_message_id):
        self.reply_map.pop(trainer_message_id, None)

    def get_supported_actions(self):
        return [
            {
                "name": "event",
                "description": "Used to set an event that will activate Rekku",
                "usage": {
                    "type": "event",
                    "payload": {
                        "date": "YYYY-MM-DD (in local timezone)",
                        "time": "HH:MM (24h, optional)",
                        "repeat": "none, daily, weekly, monthly (optional)",
                        "description": "What should happen or be remembered",
                    },
                },
            }
        ]


PLUGIN_CLASS = EventPlugin
