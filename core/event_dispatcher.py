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

    log_debug(f"[event_dispatcher] Retrieved {len(events)} events from the database")
    dispatched = 0
    for ev in events:
        log_debug(f"[event_dispatcher] Processing event: {ev}")

        prompt = {
            "context": [],
            "memories": [],
            "input": {
                "type": "event",
                "payload": {
                    "scheduled": ev["scheduled"],
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

        # Create a summary using the scheduled timestamp
        scheduled_dt = datetime.fromisoformat(ev['scheduled'])
        summary = f"{scheduled_dt.strftime('%Y-%m-%d %H:%M')} → {ev['description']}"

        # Check to avoid duplicate messages in the queue
        if not mark_event_delivered(ev["id"]):
            log_warning(f"[event_dispatcher] Event already marked as delivered: {ev['id']}")
            continue

        log_debug(f"[event_dispatcher] Event marked as delivered: {ev['id']}")

        try:
            await message_queue.enqueue_event(bot, prompt)
            log_debug(f"[DISPATCH] Event queued with priority: {summary}")
            dispatched += 1
        except Exception as exc:
            log_warning(f"[event_dispatcher] Error while queuing event {ev['id']}: {exc}")
            continue

        log_debug(f"[event_dispatcher] Processing repetition for event: {ev['id']}")
        repeat = (ev.get("repeat") or "none").lower()
        if repeat not in {"none", "daily", "weekly", "monthly"}:
            log_warning(
                f"[REPEAT] Unknown repeat value: '{repeat}' for event ID {ev['id']} — skipped."
            )
            repeat = "none"

        if repeat != "none":
            try:
                dt = datetime.fromisoformat(ev['scheduled'])

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
                        new_dt.isoformat(),
                        repeat,
                        ev["description"],
                        ev.get("created_by", "rekku"),
                    )
                    repeat_summary = f"{new_dt.strftime('%Y-%m-%d %H:%M')} → {ev['description']}"
                    log_debug(f"[REPEAT] Rescheduled event: {repeat_summary}")
            except Exception as exc:
                log_warning(
                    f"[event_dispatcher] Failed to reschedule event {ev['id']}: {exc}"
                )
        log_debug(f"[event_dispatcher] Repetition completed for event: {ev['id']}")

    log_debug(f"[event_dispatcher] Dispatched {dispatched} event(s)")
    return dispatched
