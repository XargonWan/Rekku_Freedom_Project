from __future__ import annotations

import os
import calendar
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from core.db import (
    get_due_events,
    mark_event_delivered,
    insert_scheduled_event,
)
from core import plugin_instance, message_queue
from core.logging_utils import log_debug, log_warning


async def dispatch_pending_events(bot):
    """Dispatch events that are due and handle repeats."""
    tz = ZoneInfo(os.getenv("TZ", "UTC"))
    now_local = datetime.now(tz)
    now_utc = now_local.astimezone(timezone.utc)

    events = get_due_events(now_utc)
    if not events:
        return 0

    dispatched = 0
    for ev in events:
        prompt = {
            "context": [],
            "memories": [],
            "input": {
                "type": "event",
                "payload": {
                    "date": ev["date"],
                    "time": ev["time"],
                    "repeat": ev["repeat"],
                    "description": ev["description"],
                },
                "meta": {
                    "now_date": now_local.strftime("%Y-%m-%d"),
                    "now_time": now_local.strftime("%H:%M:%S"),
                },
            },
            "actions": [],
        }

        summary = f"{ev['date']}"
        if ev["time"]:
            summary += f" {ev['time']}"
        summary += f" → {ev['description']}"

        try:
            await message_queue.enqueue_event(bot, prompt)
            mark_event_delivered(ev["id"])
            log_debug(f"[DISPATCH] Queued event with priority: {summary}")
            dispatched += 1
        except Exception as exc:
            log_warning(
                f"[event_dispatcher] Failed to dispatch event {ev['id']}: {exc}"
            )
            continue

        repeat = (ev.get("repeat") or "none").lower()
        if repeat not in {"none", "daily", "weekly", "monthly"}:
            log_warning(
                f"[REPEAT] Unknown repeat value: '{repeat}' for event ID {ev['id']} — skipped."
            )
            repeat = "none"

        if repeat != "none":
            try:
                dt = datetime.strptime(
                    f"{ev['date']} {ev['time'] or '00:00'}",
                    "%Y-%m-%d %H:%M",
                ).replace(tzinfo=tz)

                if repeat == "daily":
                    new_dt = dt + timedelta(days=1)
                elif repeat == "weekly":
                    new_dt = dt + timedelta(days=7)
                elif repeat == "monthly":
                    year = dt.year + (dt.month // 12)
                    month = dt.month % 12 + 1
                    day = min(dt.day, calendar.monthrange(year, month)[1])
                    new_dt = dt.replace(year=year, month=month, day=day)
                else:
                    new_dt = None

                if new_dt is not None:
                    insert_scheduled_event(
                        new_dt.strftime("%Y-%m-%d"),
                        ev["time"],
                        repeat,
                        ev["description"],
                        ev.get("created_by", "rekku"),
                    )
                    repeat_summary = new_dt.strftime("%Y-%m-%d")
                    if ev["time"]:
                        repeat_summary += f" {ev['time']}"
                    repeat_summary += f" → {ev['description']}"
                    log_debug(f"[REPEAT] Rescheduled event: {repeat_summary}")
            except Exception as exc:
                log_warning(
                    f"[event_dispatcher] Failed to reschedule event {ev['id']}: {exc}"
                )

    log_debug(f"[event_dispatcher] Dispatched {dispatched} event(s)")
    return dispatched
