# plugins/event_plugin.py

from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.ai_plugin_base import AIPluginBase
from core.db import insert_scheduled_event, get_due_events, mark_event_delivered
from core.logging_utils import log_debug, log_info, log_error, log_warning
from core.telegram_utils import send_with_thread_fallback
import traceback
import asyncio
import json
import time


class EventPlugin(AIPluginBase):
    """Plugin that stores future events without using an LLM."""

    # Class-level variables to prevent multiple schedulers
    _scheduler_running = False
    _scheduler_task = None

    def __init__(self, notify_fn=None):
        self.reply_map: dict[int, tuple[int, int]] = {}
        self.notify_fn = notify_fn
        # Track events currently being processed to mark them as delivered after successful send
        self._pending_events: dict[str, dict] = {}  # message_id -> event_info
        log_info("[event_plugin] EventPlugin instance created")

    async def start(self):
        """Start the event scheduler."""
        log_info(
            f"[event_plugin] start() called, scheduler_running={EventPlugin._scheduler_running}"
        )
        task = EventPlugin._scheduler_task

        if task and not task.done():
            log_warning(
                "[event_plugin] Scheduler already running globally, ignoring start() call"
            )
            return

        if task and task.done():
            log_warning("[event_plugin] Previous scheduler task was not running; restarting")

        EventPlugin._scheduler_running = True
        EventPlugin._scheduler_task = asyncio.create_task(self._event_scheduler())
        log_info("[event_plugin] Event scheduler started (singleton)")

    async def stop(self):
        """Stop the event scheduler."""
        EventPlugin._scheduler_running = False

        task = EventPlugin._scheduler_task
        if not task:
            log_info("[event_plugin] Event scheduler not running")
            return

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        EventPlugin._scheduler_task = None
        log_info("[event_plugin] Event scheduler stopped")

    def get_supported_action_types(self):
        """Return the action types this plugin supports."""
        return ["event"]

    def get_supported_actions(self):
        """Return structured instructions for supported actions."""
        return {
            "event": {
                "description": "Schedule a reminder or recurring event",
                "interfaces": ["scheduler"],
                "example": {
                    "type": "event",
                    "payload": {
                        "scheduled": "2025-07-22T15:30:00+00:00",
                        "description": "Remind Jay to check the system logs",
                        "recurrence_type": "none"
                    }
                }
            }
        }

    def execute_action(self, action: dict, context: dict, bot, original_message):
        """Execute an event action using the new plugin interface."""
        if action.get("type") == "event":
            log_info("[event_plugin] Executing event action with payload: " + str(action.get('payload')))
            try:
                # Use asyncio.create_task to handle async call from sync context
                import asyncio
                asyncio.create_task(self._handle_event_payload(action.get("payload", {})))
            except Exception as e:
                log_error(f"[event_plugin] Error executing event action: {repr(e)}")
        else:
            log_error(f"[event_plugin] Unsupported action type: {action.get('type')}")

    async def handle_custom_action(self, action_type: str, payload: dict):
        """Handle custom event actions (legacy method - kept for compatibility)."""
        if action_type == "event":
            log_info("[event_plugin] Handling event action with payload: " + str(payload))
            try:
                await self._handle_event_payload(payload)
            except Exception as e:
                log_error(f"[event_plugin] Error handling event action: {repr(e)}")
        else:
            log_error(f"[event_plugin] Unsupported action type: {action_type}")

    async def _handle_event_payload(self, payload: dict):
        """Shared logic for processing an event payload."""
        scheduled = payload.get("scheduled")
        description = payload.get("description", "")
        recurrence_type = payload.get("recurrence_type", "none")

        if scheduled and description:
            await self._save_scheduled_reminder(scheduled, description, recurrence_type)
            log_info(f"[event_plugin] Reminder scheduled for {scheduled} ({recurrence_type}): {description}")
        else:
            log_error("[event_plugin] Invalid event payload: missing 'scheduled' or 'description'")

    async def _save_scheduled_reminder(self, scheduled: str, description: str, recurrence_type: str = "none"):
        """Save a scheduled reminder to the database as natural language."""
        try:
            # Validate recurrence_type
            valid_recurrence_types = {"none", "daily", "weekly", "monthly", "always"}
            if recurrence_type not in valid_recurrence_types:
                log_warning(f"[event_plugin] Invalid recurrence_type '{recurrence_type}', defaulting to 'none'")
                recurrence_type = "none"

            # Parse the scheduled timestamp
            event_time = datetime.fromisoformat(scheduled.replace('Z', '+00:00'))

            # Convert to UTC for consistent storage
            if event_time.tzinfo is None:
                # If no timezone info, assume it's in the system timezone
                from zoneinfo import ZoneInfo
                system_tz = ZoneInfo(os.getenv("TZ", "UTC"))
                event_time = event_time.replace(tzinfo=system_tz)

            # Convert to UTC for storage
            event_time_utc = event_time.astimezone(timezone.utc)

            # Extract date and time parts in UTC
            date_str = event_time_utc.strftime("%Y-%m-%d")
            time_str = event_time_utc.strftime("%H:%M:%S")

            # Store the reminder as natural language description
            # This allows Rekku to freely decide what to do with it
            reminder_description = "REMINDER: " + str(description)

            # TODO: Implement duplicate check with proper async handling
            # For now, we rely on database UNIQUE constraints

            # Store in database using the correct signature
            await insert_scheduled_event(
                scheduled=event_time_utc.isoformat(),
                recurrence_type=recurrence_type,
                description=reminder_description,
                created_by="rekku"
            )
            log_debug(f"[event_plugin] Saved scheduled reminder for {event_time} (stored as UTC: {event_time_utc}, recurrence: {recurrence_type}): {description}")
        except Exception as e:
            log_error(f"[event_plugin] Failed to save scheduled reminder: {repr(e)}")

    async def _event_scheduler(self):
        """Background task that checks and executes due events."""
        log_info("[event_plugin] Event scheduler loop started (singleton)")
        while EventPlugin._scheduler_running:
            try:
                log_debug("[event_plugin] Event scheduler checking for due events...")
                await self._check_and_execute_events()
                await asyncio.sleep(30)  # Check every 30 seconds
            except asyncio.CancelledError:
                log_info("[event_plugin] Event scheduler cancelled")
                break
            except Exception as e:
                log_error(
                    f"[event_plugin] Error in event scheduler: {repr(e)}\n{traceback.format_exc()}"
                )
                await asyncio.sleep(60)  # Wait longer on error
        log_info("[event_plugin] Event scheduler loop ended")

    async def _check_and_execute_events(self):
        """Check for due events and execute them with 5-minute tolerance window."""
        try:
            log_debug("[EventPlugin] Starting due events check...")
            # Get events that are due (including 5 minutes early)
            due_events = await get_due_events(tolerance_minutes=5)

            if due_events:
                log_info(f"[event_plugin] Found {len(due_events)} due events to execute (with 5min tolerance)")
                log_debug(f"[EventPlugin] Found events: {len(due_events)}")
                # Separate on-time and late events for logging
                on_time_events = [e for e in due_events if not e.get('is_late', False)]
                late_events = [e for e in due_events if e.get('is_late', False)]

                if on_time_events:
                    log_info(f"[event_plugin] {len(on_time_events)} events executing on time")
                if late_events:
                    log_warning(f"[event_plugin] {len(late_events)} events executing late!")
                    for event in late_events:
                        minutes_late = event.get('minutes_late', 0)
                        scheduled_time = event.get('scheduled_time', 'unknown')
                        log_warning(f"[event_plugin] Event {event['id']} is {minutes_late} minutes late (scheduled: {scheduled_time})")

                for event in due_events:
                    log_debug(f"[EventPlugin] Checking event: {event}")
                    await self._execute_scheduled_event(event)
            else:
                log_debug("[event_plugin] No due events to execute (checked with 5min tolerance)")
        except Exception as e:
            log_error(f"[event_plugin] Error checking due events: {repr(e)}")

    async def _execute_scheduled_event(self, event: dict):
        """Execute a scheduled event and deliver it to the LLM for processing."""
        try:
            description = event.get("description", "")
            event_id = event.get("id", "unknown")

            # Extract lateness info
            is_late = event.get('is_late', False)
            minutes_late = event.get('minutes_late', 0)
            scheduled_time = event.get('scheduled_time', 'unknown')

            # Log execution with lateness info
            if is_late:
                log_info(f"[event_plugin] Delivering LATE event {event_id} ({minutes_late} min late): {description[:50]}...")
            else:
                log_info(f"[event_plugin] Delivering scheduled event {event_id}: {description[:50]}...")

            log_debug(f"[EventPlugin] Executing event: {event}")
            # Create a structured prompt for the LLM representing this scheduled event
            # The LLM will decide what to do with it
            await self._deliver_event_to_llm(event)

            log_debug(f"[EventPlugin] Event {event['id']} executed successfully")

        except Exception as e:
            log_error(f"[event_plugin] Error delivering event {event.get('id', 'unknown')}: {repr(e)}")

    async def _deliver_event_to_llm(self, event: dict):
        """Deliver the event to the LLM as a structured input."""
        try:
            # Get the active LLM plugin
            import core.plugin_instance as plugin_instance
            active_plugin = plugin_instance.get_plugin()

            if not active_plugin:
                log_error(f"[event_plugin] No active LLM plugin available for event {event['id']}")
                return

            # Create a structured event prompt for the LLM
            event_prompt = self._create_event_prompt(event)

            # Create a special "scheduler" message object
            scheduler_message = self._create_scheduler_message(event)

            log_debug(f"[event_plugin] Delivering event {event['id']} to LLM: {active_plugin.__class__.__name__}")

            # Execute through the active LLM plugin using the message queue
            from core import message_queue

            # Use a dedicated chat ID for all events
            dedicated_chat_id = "CHATGPT_EVENT_CHAT"
            scheduler_message.chat_id = dedicated_chat_id
            event_prompt['input']['payload']['source']['chat_id'] = dedicated_chat_id

            await message_queue.enqueue_event(None, event_prompt)  # No bot needed for events

            # Mark event as delivered since we've successfully queued it
            from core.db import mark_event_delivered
            await mark_event_delivered(event['id'])
            log_info(f"[event_plugin] ✅ Event {event['id']} delivered and marked as processed")

        except Exception as e:
            log_error(f"[event_plugin] Error delivering event {event['id']} to LLM: {repr(e)}")

    def _create_event_prompt(self, event: dict):
        """Create a structured prompt for the event delivery."""

        # Extract event details
        event_id = event.get('id', 'unknown')
        date = event.get('date', '')
        time = event.get('time', '')
        description = event.get('description', '')
        is_late = event.get('is_late', False)
        minutes_late = event.get('minutes_late', 0)
        scheduled_time = event.get('scheduled_time', 'unknown')

        # Create lateness context
        lateness_context = ""
        if is_late:
            if minutes_late < 60:
                lateness_context = f"⚠️ THIS EVENT IS {minutes_late} MINUTES LATE! It was scheduled for {scheduled_time}."
            else:
                hours_late = minutes_late // 60
                remaining_minutes = minutes_late % 60
                if remaining_minutes > 0:
                    lateness_context = f"⚠️ THIS EVENT IS LATE BY {hours_late}h {remaining_minutes}m! It was scheduled for {scheduled_time}."
                else:
                    lateness_context = f"⚠️ THIS EVENT IS LATE BY {hours_late} {'hour' if hours_late == 1 else 'hours'}! It was scheduled for {scheduled_time}."
        else:
            lateness_context = f"✅ Event on time (scheduled for {scheduled_time})"

        return {
            "context": {
                "messages": [],
                "memories": [],
                "location": "",
                "weather": "",
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "time": datetime.utcnow().strftime("%H:%M"),
                "event_status": {
                    "is_late": is_late,
                    "minutes_late": minutes_late,
                    "scheduled_time": scheduled_time,
                    "lateness_context": lateness_context
                }
            },
            "input": {
                "type": "scheduled_event",
                "event_id": event_id,
                "payload": {
                    "text": "Reminder: " + str(description),
                    "event_date": date,
                    "event_time": time,
                    "description": description,
                    "is_late": is_late,
                    "minutes_late": minutes_late,
                    "source": {
                        "chat_id": "SYSTEM_SCHEDULER",
                        "message_id": f"event_{event_id}",
                        "username": "Rekku Scheduler",
                        "usertag": "@rekku_scheduler",
                        "interface": "scheduler"
                    },
                    "timestamp": datetime.utcnow().isoformat() + "+00:00",
                    "privacy": "system",
                    "scope": "global"
                }
            },
            "instructions": f"""
SCHEDULED REMINDER #{event_id} {"(LATE)" if is_late else "(ON TIME)"}

Reminder: """ + str(description) + f"""
Scheduled date: {date} {time}
Status: {lateness_context}

This is a reminder you set for yourself. Freely decide whether and how to act:

1. If it's a reminder that requires action (e.g. "remember Jay"), decide what to do
2. If it's an internal thought, you might decide to do nothing or something else
3. If it's late, deliver it but communicate that it's late
4. You are NOT obliged to send messages - assess if it's really needed

You can respond with any action (message, etc.) or combination of actions.
If you decide to do nothing, the JSON should not contain any action.

Example of a valid JSON structure for an event:
{{
  "type": "event",
  "payload": {{
    "scheduled": "2025-07-22T15:30:00+00:00",
    "description": "Remember to check if Jay replied to the message",
    "recurrence_type": "none"
  }}
}}

For recurring events, you can use:
- "none": single reminder (default)
- "daily": repeat every day
- "weekly": repeat every week
- "monthly": repeat every month
- "always": keep active indefinitely
            """.strip()
        }

    def _create_scheduler_message(self, event: dict):
        """Create a scheduler message object for the event."""
        from types import SimpleNamespace

        return SimpleNamespace(
            message_id=f"event_{event['id']}",
            chat_id="SYSTEM_SCHEDULER",
            text="Reminder: " + str(event.get('description', '')),
            from_user=SimpleNamespace(
                id=-1,  # System user ID
                full_name="Rekku Scheduler",
                username="rekku_scheduler"
            ),
            date=datetime.utcnow(),
            reply_to_message=None,
            chat=SimpleNamespace(
                id="SYSTEM_SCHEDULER",
                type="private",
                title="System Scheduler"
            ),
            message_thread_id=None
        )

    async def _execute_action_silently(self, action: dict, event_id: int):
        """Execute an action silently without involving any interfaces."""
        try:
            action_type = action.get("type")
            payload = action.get("payload", {})

            log_debug(f"[event_plugin] Executing silent action {action_type} for event {event_id}")

            if action_type == "message":
                # For message actions, send directly through the appropriate transport
                await self._send_scheduled_message(payload, event_id)
            else:
                # For other action types, delegate to action plugins
                await self._execute_other_action_silently(action, event_id)

        except Exception as e:
            log_error(f"[event_plugin] Error executing silent action for event {event_id}: {repr(e)}")

    async def _send_scheduled_message(self, payload: dict, event_id: int):
        """Send a scheduled message directly without interface involvement."""
        try:
            text = payload.get("text", "")
            target_chat_id = payload.get("target")
            message_thread_id = payload.get("message_thread_id")

            if not text or not target_chat_id:
                log_error(f"[event_plugin] Invalid message payload for event {event_id}")
                return

            log_info(f"[event_plugin] Sending scheduled message to {target_chat_id}: {text}")

            # Get the appropriate transport layer directly
            await self._send_via_transport_layer(target_chat_id, text, message_thread_id, event_id)

        except Exception as e:
            log_error(f"[event_plugin] Error sending scheduled message for event {event_id}: {repr(e)}")

    async def _send_via_transport_layer(self, chat_id: int, text: str, message_thread_id: int = None, event_id: int = None):
        """Send message directly via transport layer, bypassing interfaces."""
        try:
            # Determine the appropriate transport based on chat_id patterns
            if chat_id < 0:
                # Negative IDs are typically Telegram groups/channels
                await self._send_via_telegram_transport(chat_id, text, message_thread_id, event_id)
            else:
                # Positive IDs could be Telegram private chats or other platforms
                await self._send_via_telegram_transport(chat_id, text, message_thread_id, event_id)

        except Exception as e:
            log_error(f"[event_plugin] Error in transport layer for event {event_id}: {repr(e)}")

    async def _send_via_telegram_transport(self, chat_id: int, text: str, message_thread_id: int = None, event_id: int = None):
        """Send message directly via Telegram transport layer."""
        try:
            from interface.telegram_bot import application
            if not application or not application.bot:
                raise ImportError

            await send_with_thread_fallback(
                application.bot,
                chat_id,
                text,
                message_thread_id=message_thread_id,
                parse_mode="Markdown",
            )

            log_info(
                f"[event_plugin] ✅ Scheduled message sent to {chat_id} (event {event_id})"
            )

        except ImportError:
            log_error(f"[event_plugin] Telegram transport layer not available for event {event_id}")
            # Fallback: use the bot instance directly if available
            await self._fallback_send_telegram(chat_id, text, message_thread_id, event_id)
        except Exception as e:
            log_error(f"[event_plugin] Error in Telegram transport for event {event_id}: {repr(e)}")

    async def _fallback_send_telegram(self, chat_id: int, text: str, message_thread_id: int = None, event_id: int = None):
        """Fallback method to send via Telegram bot directly."""
        try:
            from interface.telegram_bot import application

            if application and application.bot:
                await send_with_thread_fallback(
                    application.bot,
                    chat_id,
                    text,
                    message_thread_id=message_thread_id,
                    parse_mode="Markdown",
                )
                log_info(
                    f"[event_plugin] ✅ Fallback Telegram send successful for event {event_id}"
                )
            else:
                log_error(
                    f"[event_plugin] No Telegram bot available for fallback send (event {event_id})"
                )

        except Exception as e:
            log_error(f"[event_plugin] Fallback Telegram send failed for event {event_id}: {repr(e)}")

    async def _execute_other_action_silently(self, action: dict, event_id: int):
        """Execute non-message actions silently."""
        try:
            # For non-message actions, use the action parser directly
            from core.action_parser import parse_action

            # Create a silent bot that doesn't interact with interfaces
            silent_bot = self._create_silent_bot()

            # Create a minimal message context
            silent_message = type('SilentMessage', (), {
                'chat_id': -999999999,  # Special ID for silent execution
                'message_thread_id': None
            })()

            await parse_action(action, silent_bot, silent_message)

            log_debug(f"[event_plugin] Silent action executed for event {event_id}")

        except Exception as e:
            log_error(f"[event_plugin] Error executing silent action for event {event_id}: {repr(e)}")

    def _create_silent_bot(self):
        """Create a bot that silently logs actions instead of sending them."""
        class SilentBot:
            async def send_message(self, **kwargs):
                text = kwargs.get('text', '')
                chat_id = kwargs.get('chat_id')
                log_debug(f"[event_plugin] Silent bot action: send_message({chat_id}, '{text[:50]}...')")

        return SilentBot()

    async def _delegate_to_active_llm(self, action: dict, event_id: int, event_info: dict = None):
        """Delegate the action execution to the active LLM plugin."""
        try:
            # Get the active LLM plugin
            import core.plugin_instance as plugin_instance
            active_plugin = plugin_instance.get_plugin()

            if not active_plugin:
                log_error(f"[event_plugin] No active LLM plugin available for event {event_id}")
                return

            # Track the current event ID for delivery confirmation
            self._current_processing_event_id = event_id

            # Create a unified message for scheduled events to avoid chat flooding
            # This ensures all scheduled events use the same chat context
            unified_message = self._create_unified_scheduled_message(action, event_id, event_info)

            log_debug(f"[event_plugin] Delegating event {event_id} to active LLM: {active_plugin.__class__.__name__}")

            # Execute through the active LLM plugin
            if hasattr(active_plugin, 'handle_incoming_message'):
                # Create a mock bot for the LLM to send responses
                mock_bot = self._create_mock_bot_for_llm()

                # Create a JSON prompt for the scheduled action with lateness info
                scheduled_prompt = self._create_scheduled_action_prompt(action, event_id, event_info)

                await active_plugin.handle_incoming_message(
                    bot=mock_bot,
                    message=unified_message,
                    prompt=scheduled_prompt
                )
            else:
                log_error(f"[event_plugin] Active LLM plugin {active_plugin.__class__.__name__} doesn't support handle_incoming_message")
                # Clean up the tracking since we can't process
                if hasattr(self, '_current_processing_event_id'):
                    delattr(self, '_current_processing_event_id')

        except Exception as e:
            log_error(f"[event_plugin] Error delegating to active LLM for event {event_id}: {repr(e)}")
            # Clean up the tracking on error
            if hasattr(self, '_current_processing_event_id'):
                delattr(self, '_current_processing_event_id')

    def _create_unified_scheduled_message(self, action: dict, event_id: int, event_info: dict = None):
        """Create a unified message object for scheduled events."""
        # Use a special chat_id for all scheduled events to avoid chat flooding
        # This uses a special negative ID that the chat management system can handle
        SCHEDULED_EVENTS_CHAT_ID = -999999999  # Special ID for scheduled events

        # Extract target info from the action for later routing
        target_chat_id = action.get('payload', {}).get('target', SCHEDULED_EVENTS_CHAT_ID)
        message_thread_id = action.get('payload', {}).get('message_thread_id')

        # Extract lateness info
        is_late = event_info.get('is_late', False) if event_info else False
        minutes_late = event_info.get('minutes_late', 0) if event_info else 0

        # Create message text with lateness indication
        base_text = f"[SCHEDULED_EVENT_{event_id}] Execute planned action"
        if is_late:
            base_text += f" (⚠️ {minutes_late} minutes late)"

        # Create a message-like object that works with the existing chat management
        from types import SimpleNamespace

        message = SimpleNamespace(
            message_id=f"scheduled_event_{event_id}",
            # Use the special scheduled events chat ID - this will be managed by the chat system
            chat_id=SCHEDULED_EVENTS_CHAT_ID,
            text=base_text,
            from_user=SimpleNamespace(
                id=0,  # System user ID
                full_name="Rekku Scheduler",
                username="rekku_scheduler"
            ),
            date=datetime.utcnow(),
            reply_to_message=None,
            chat=SimpleNamespace(
                id=SCHEDULED_EVENTS_CHAT_ID,
                type="private",  # Treat as private chat for management purposes
                title="Rekku Scheduled Events"  # Give it a recognizable title
            ),
            # Store the real target info for final message routing
            _scheduled_target_chat_id=target_chat_id,
            _scheduled_message_thread_id=message_thread_id,
            # Store lateness info
            _is_late=is_late,
            _minutes_late=minutes_late,
            # Add message_thread_id if present (for topic support)
            message_thread_id=None  # Scheduled events don't use threads in their own chat
        )

        return message

    def _create_scheduled_action_prompt(self, action: dict, event_id: int, event_info: dict = None):
        """Create a JSON prompt for the scheduled action with lateness information."""

        # Extract lateness info if available
        is_late = event_info.get('is_late', False) if event_info else False
        minutes_late = event_info.get('minutes_late', 0) if event_info else 0
        scheduled_time = event_info.get('scheduled_time', 'unknown') if event_info else 'unknown'

        # Create lateness context for the LLM
        lateness_context = ""
        if is_late:
            if minutes_late < 60:
                lateness_context = f"⚠️ THIS MESSAGE IS {minutes_late} MINUTES LATE! It was scheduled for {scheduled_time}."
            else:
                hours_late = minutes_late // 60
                remaining_minutes = minutes_late % 60
                if remaining_minutes > 0:
                    lateness_context = f"⚠️ THIS MESSAGE IS LATE BY {hours_late}h {remaining_minutes}m! It was scheduled for {scheduled_time}."
                else:
                    lateness_context = f"⚠️ THIS MESSAGE IS LATE BY {hours_late} {'hour' if hours_late == 1 else 'hours'}! It was scheduled for {scheduled_time}."
        else:
            lateness_context = f"✅ Message on time (scheduled for {scheduled_time})"

        return {
            "context": {
                "messages": [],
                "memories": [],
                "location": "",
                "weather": "",
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "time": datetime.utcnow().strftime("%H:%M"),
                "event_status": {
                    "is_late": is_late,
                    "minutes_late": minutes_late,
                    "scheduled_time": scheduled_time,
                    "lateness_context": lateness_context
                }
            },
            "input": {
                "type": "scheduled_event",
                "event_id": event_id,
                "scheduled_action": action,
                "is_late": is_late,
                "minutes_late": minutes_late,
                "payload": {
                    "text": f"Execute scheduled event {event_id}{' (LATE)' if is_late else ''}",
                    "source": {
                        "chat_id": -999999999,  # Scheduled events chat
                        "message_id": f"scheduled_event_{event_id}",
                        "username": "Rekku Scheduler",
                        "usertag": "@rekku_scheduler"
                    },
                    "timestamp": datetime.utcnow().isoformat() + "+00:00",
                    "privacy": "private",
                    "scope": "local"
                }
            },
            "instructions": f"""
You can use {{"type": "event"}} to schedule a reminder in the future.

IMPORTANT RULES for event actions:
- The payload MUST contain:
    • "scheduled": ISO 8601 UTC timestamp (e.g. "2025-07-22T15:30:00+00:00")
    • "description": natural language reminder (not a command or action)
- The payload CAN optionally contain:
    • "recurrence_type": how often to repeat the event
      - "none" (default): single execution only
      - "daily": repeat every day
      - "weekly": repeat every week  
      - "monthly": repeat every month
      - "always": keep active indefinitely
- DO NOT include nested "action", "message", or any other structure inside the event.
- The plugin will decide later how to handle the reminder.

Valid examples:

Single reminder (default):
{{
  "type": "event",
  "payload": {{
    "scheduled": "2025-07-22T15:30:00+00:00",
    "description": "Remind Jay to check the system logs for errors"
  }}
}}

Daily recurring reminder:
{{
  "type": "event",
  "payload": {{
    "scheduled": "2025-07-22T09:00:00+00:00",
    "description": "Daily standup meeting reminder",
    "recurrence_type": "daily"
  }}
}}

Weekly recurring reminder:
{{
  "type": "event",
  "payload": {{
    "scheduled": "2025-07-22T14:00:00+00:00", 
    "description": "Weekly team sync",
    "recurrence_type": "weekly"
  }}
}}
        """.strip(),
            "interface_instructions": "SCHED: Single JSON reply"
        }

    def _create_mock_bot_for_llm(self):
        """Create a mock bot that delegates LLM responses to action parser."""
        class ScheduledEventBot:
            def __init__(self, event_plugin):
                self.event_plugin = event_plugin

            async def send_message(self, **kwargs):
                """Handle LLM responses and delegate to action parser."""
                text = kwargs.get('text', '')
                chat_id = kwargs.get('chat_id')
                message_thread_id = kwargs.get('message_thread_id')

                log_debug(f"[event_plugin] LLM responded with: {text[:100]}...")

                # Parse the JSON response from the LLM
                if text.strip().startswith('{') and text.strip().endswith('}'):
                    try:
                        # Parse the action generated by LLM
                        response_action = json.loads(text.strip())
                        log_info(f"[event_plugin] LLM generated action: {response_action}")

                        # Send this action through the normal action parser flow
                        from core.action_parser import parse_action

                        # Create a proper message context for the action parser
                        # This ensures the action goes to the right interface
                        action_message = type('ActionMessage', (), {
                            'chat_id': response_action.get('payload', {}).get('target', chat_id),
                            'message_thread_id': response_action.get('payload', {}).get('message_thread_id', message_thread_id)
                        })()

                        # Get the real bot instance from the active interface
                        real_bot = await self._get_active_bot()

                        if real_bot:
                            # Placeholder for the missing logic
                            pass
                    except Exception as e:
                        log_error(f"[event_plugin] Error parsing LLM response action: {repr(e)}")
                else:
                    log_warning(f"[event_plugin] Ignored non-JSON LLM response: {text}")

        return ScheduledEventBot(self)


# Export the plugin class for the loader
PLUGIN_CLASS = EventPlugin
