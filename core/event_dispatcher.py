from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.db import (
    get_due_events,
    mark_event_delivered,
)
from core import message_queue
from core.logging_utils import log_debug, log_warning


async def dispatch_pending_events(bot):
    """Dispatch events that are due and handle repeats."""
    tz = ZoneInfo(os.getenv("TZ", "UTC"))
    now_local = datetime.now(tz)
    now_utc = now_local.astimezone(timezone.utc)

    events = await get_due_events(now_utc)
    if not events:
        return 0

    log_debug(f"[event_dispatcher] Retrieved {len(events)} events from the database")
    dispatched = 0
    for ev in events:
        log_debug(f"[event_dispatcher] Processing event: {ev}")

        scheduled_val = ev.get("next_run") or ev["scheduled"]
        if isinstance(scheduled_val, datetime):
            scheduled_dt = scheduled_val
        else:
            scheduled_dt = datetime.fromisoformat(str(scheduled_val).replace("Z", "+00:00"))
        if scheduled_dt.tzinfo is None:
            scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)

        prompt = {
            "context": [],
            "memories": [],
            "input": {
                "type": "event",
                "payload": {
                    "scheduled": scheduled_val,
                    "recurrence_type": ev["recurrence_type"],
                    "description": ev["description"],
                },
                "meta": {
                    "now_date": now_local.strftime("%Y-%m-%d"),
                    "now_time": now_local.strftime("%H:%M:%S"),
                },
            },
            "actions": [],
        }

        summary = scheduled_dt.strftime('%Y-%m-%d %H:%M') + " → " + str(ev['description'])

        try:
            await message_queue.enqueue_event(bot, prompt)
            log_debug(f"[DISPATCH] Event queued with priority: {summary}")
            await mark_event_delivered(ev["id"])
            dispatched += 1
        except Exception as exc:
            log_warning(f"[event_dispatcher] Error while processing event {ev['id']}: {exc}")
            continue

    log_debug(f"[event_dispatcher] Dispatched {dispatched} event(s)")
    return dispatched
