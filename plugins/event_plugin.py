# plugins/event_plugin.py

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.ai_plugin_base import AIPluginBase
from core.db import insert_scheduled_event, get_due_events, mark_event_delivered
from core.logging_utils import log_debug, log_info, log_error, log_warning
import asyncio
import json
import time


class EventPlugin(AIPluginBase):
    """Plugin that stores future events without using an LLM."""

    def __init__(self, notify_fn=None):
        self.reply_map: dict[int, tuple[int, int]] = {}
        self.notify_fn = notify_fn
        self._scheduler_task = None
        self._running = False
        # Track events currently being processed to mark them as delivered after successful send
        self._pending_events: dict[str, dict] = {}  # message_id -> event_info

    async def start(self):
        """Start the event scheduler."""
        if not self._running:
            self._running = True
            self._scheduler_task = asyncio.create_task(self._event_scheduler())
            log_info("[event_plugin] Event scheduler started")

    async def stop(self):
        """Stop the event scheduler."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            log_info("[event_plugin] Event scheduler stopped")

    def get_supported_action_types(self):
        """Return the action types this plugin supports."""
        return ["event"]

    def get_supported_actions(self):
        """Return ultra-compact instructions for supported actions."""
        return {
            "event": "Create scheduled events: {\"actions\":[{\"type\":\"event\",\"payload\":{\"when\":\"2025-07-22T15:30:00+00:00\",\"action\":{\"type\":\"message\",\"interface\":\"telegram\",\"payload\":{\"text\":\"...\",\"target\":input.payload.source.chat_id,\"thread_id\":input.payload.source.thread_id}}}}]}"
        }

    def execute_action(self, action: dict, context: dict, bot, original_message):
        """Execute an event action using the new plugin interface."""
        action_type = action.get("type")
        payload = action.get("payload", {})
        
        if action_type == "event":
            log_info(f"[event_plugin] Executing event action with payload: {payload}")
            try:
                # Extract the nested action from the payload
                when = payload.get("when")
                action_data = payload.get("action", {})
                
                if when and action_data:
                    # Store the scheduled event
                    self._save_scheduled_event(when, action_data)
                    log_info(f"[event_plugin] Event scheduled for {when}")
                else:
                    log_error("[event_plugin] Invalid event payload: missing 'when' or 'action'")
            except Exception as e:
                log_error(f"[event_plugin] Error executing event action: {e}")
        else:
            log_error(f"[event_plugin] Unsupported action type: {action_type}")

    async def handle_custom_action(self, action_type: str, payload: dict):
        """Handle custom event actions (legacy method - kept for compatibility)."""
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
        """Save a scheduled event to the database in UTC timezone."""
        try:
            # Parse the when timestamp
            event_time = datetime.fromisoformat(when.replace('Z', '+00:00'))
            
            # Convert to UTC for consistent storage
            if event_time.tzinfo is None:
                # If no timezone info, assume it's in the system timezone
                from zoneinfo import ZoneInfo
                import os
                system_tz = ZoneInfo(os.getenv("TZ", "UTC"))
                event_time = event_time.replace(tzinfo=system_tz)
            
            # Convert to UTC for storage
            event_time_utc = event_time.astimezone(timezone.utc)
            
            # Extract date and time parts in UTC
            date_str = event_time_utc.strftime("%Y-%m-%d")
            time_str = event_time_utc.strftime("%H:%M:%S")
            
            # Serialize the action as JSON in the description field
            # Add microsecond timestamp to ensure uniqueness
            unique_id = str(int(time.time() * 1000000))  # microsecond timestamp
            action_json = json.dumps(action, ensure_ascii=False)
            description = f"REKKU_ACTION:{unique_id}:{action_json}"
            
            # Store in database using the correct signature
            insert_scheduled_event(
                date=date_str,
                time_=time_str,
                repeat="none",  # Single execution
                description=description,
                created_by="rekku"
            )
            log_debug(f"[event_plugin] Saved scheduled event for {event_time} (stored as UTC: {event_time_utc})")
        except Exception as e:
            log_error(f"[event_plugin] Failed to save scheduled event: {e}")

    async def _event_scheduler(self):
        """Background task that checks and executes due events."""
        while self._running:
            try:
                await self._check_and_execute_events()
                await asyncio.sleep(30)  # Check every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(f"[event_plugin] Error in event scheduler: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    async def _check_and_execute_events(self):
        """Check for due events and execute them with 5-minute tolerance window."""
        try:
            # Get events that are due (including 5 minutes early)
            due_events = get_due_events(tolerance_minutes=5)
            
            if due_events:
                log_info(f"[event_plugin] Found {len(due_events)} due events to execute (with 5min tolerance)")
                
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
                    await self._execute_scheduled_event(event)
            else:
                log_debug("[event_plugin] No due events to execute (checked with 5min tolerance)")
        except Exception as e:
            log_error(f"[event_plugin] Error checking due events: {e}")

    async def _execute_scheduled_event(self, event: dict):
        """Execute a scheduled event and mark it as consumed if needed."""
        try:
            description = event.get("description", "")
            
            # Check if this is a Rekku action
            if not description.startswith("REKKU_ACTION:"):
                log_debug(f"[event_plugin] Skipping non-action event: {event['id']}")
                return
            
            # Parse the action from description
            # Format: REKKU_ACTION:{timestamp}:{json_action}
            parts = description.split(":", 2)
            if len(parts) < 3:
                log_error(f"[event_plugin] Invalid action format in event {event['id']}")
                return
            
            action_json = parts[2]
            action = json.loads(action_json)
            
            # Log execution with lateness info
            is_late = event.get('is_late', False)
            if is_late:
                minutes_late = event.get('minutes_late', 0)
                log_info(f"[event_plugin] Executing LATE event {event['id']} ({minutes_late} min late): {action.get('type', 'unknown')}")
            else:
                log_info(f"[event_plugin] Executing scheduled event {event['id']}: {action.get('type', 'unknown')}")
            
            # Send the event action back through LLM to generate appropriate response
            # Pass the full event info including lateness data
            # NOTE: The event will be marked as delivered only after successful interface delivery
            await self._delegate_to_active_llm(action, event['id'], event)
            
            # DO NOT mark as delivered here - this will be done by the interface after successful send
            log_debug(f"[event_plugin] Event {event['id']} delegated to LLM, waiting for interface confirmation")
                
        except Exception as e:
            log_error(f"[event_plugin] Error executing event {event.get('id', 'unknown')}: {e}")

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
            log_error(f"[event_plugin] Error executing silent action for event {event_id}: {e}")

    async def _send_scheduled_message(self, payload: dict, event_id: int):
        """Send a scheduled message directly without interface involvement."""
        try:
            text = payload.get("text", "")
            target_chat_id = payload.get("target")
            thread_id = payload.get("thread_id")
            
            if not text or not target_chat_id:
                log_error(f"[event_plugin] Invalid message payload for event {event_id}")
                return
            
            log_info(f"[event_plugin] Sending scheduled message to {target_chat_id}: {text}")
            
            # Get the appropriate transport layer directly
            await self._send_via_transport_layer(target_chat_id, text, thread_id, event_id)
            
        except Exception as e:
            log_error(f"[event_plugin] Error sending scheduled message for event {event_id}: {e}")

    async def _send_via_transport_layer(self, chat_id: int, text: str, thread_id: int = None, event_id: int = None):
        """Send message directly via transport layer, bypassing interfaces."""
        try:
            # Determine the appropriate transport based on chat_id patterns
            if chat_id < 0:
                # Negative IDs are typically Telegram groups/channels
                await self._send_via_telegram_transport(chat_id, text, thread_id, event_id)
            else:
                # Positive IDs could be Telegram private chats or other platforms
                await self._send_via_telegram_transport(chat_id, text, thread_id, event_id)
                
        except Exception as e:
            log_error(f"[event_plugin] Error in transport layer for event {event_id}: {e}")

    async def _send_via_telegram_transport(self, chat_id: int, text: str, thread_id: int = None, event_id: int = None):
        """Send message directly via Telegram transport layer."""
        try:
            # Import the transport layer
            from core.transport_layer import send_telegram_message
            
            # Create message context for the transport layer
            send_kwargs = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"  # Default parse mode
            }
            
            if thread_id:
                send_kwargs["message_thread_id"] = thread_id
            
            # Send directly through transport layer
            await send_telegram_message(**send_kwargs)
            
            log_info(f"[event_plugin] ✅ Scheduled message sent to {chat_id} (event {event_id})")
            
        except ImportError:
            log_error(f"[event_plugin] Telegram transport layer not available for event {event_id}")
            # Fallback: use the bot instance directly if available
            await self._fallback_send_telegram(chat_id, text, thread_id, event_id)
        except Exception as e:
            log_error(f"[event_plugin] Error in Telegram transport for event {event_id}: {e}")

    async def _fallback_send_telegram(self, chat_id: int, text: str, thread_id: int = None, event_id: int = None):
        """Fallback method to send via Telegram bot directly."""
        try:
            # Try to get the Telegram bot instance from the interface
            from interface.telegram_bot import application
            
            if application and application.bot:
                send_kwargs = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown"
                }
                
                if thread_id:
                    send_kwargs["message_thread_id"] = thread_id
                
                await application.bot.send_message(**send_kwargs)
                log_info(f"[event_plugin] ✅ Fallback Telegram send successful for event {event_id}")
            else:
                log_error(f"[event_plugin] No Telegram bot available for fallback send (event {event_id})")
                
        except Exception as e:
            log_error(f"[event_plugin] Fallback Telegram send failed for event {event_id}: {e}")

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
            log_error(f"[event_plugin] Error executing silent action for event {event_id}: {e}")

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
            log_error(f"[event_plugin] Error delegating to active LLM for event {event_id}: {e}")
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
        thread_id = action.get('payload', {}).get('thread_id')
        
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
            _scheduled_thread_id=thread_id,
            # Store lateness info
            _is_late=is_late,
            _minutes_late=minutes_late,
            # Add thread_id if present (for topic support)
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
                lateness_context = f"⚠️ QUESTO MESSAGGIO È IN RITARDO DI {minutes_late} MINUTI! Era programmato per le {scheduled_time}."
            else:
                hours_late = minutes_late // 60
                remaining_minutes = minutes_late % 60
                if remaining_minutes > 0:
                    lateness_context = f"⚠️ QUESTO MESSAGGIO È IN RITARDO DI {hours_late}h {remaining_minutes}m! Era programmato per le {scheduled_time}."
                else:
                    lateness_context = f"⚠️ QUESTO MESSAGGIO È IN RITARDO DI {hours_late} {'ora' if hours_late == 1 else 'ore'}! Era programmato per le {scheduled_time}."
        else:
            lateness_context = f"✅ Messaggio in orario (programmato per le {scheduled_time})"
        
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
EVENT {event_id} {"LATE+" + str(minutes_late) + "m" if is_late else "ON TIME"} | Execute: {json.dumps(action, separators=(',', ':'))} | Reply JSON: {{"type":"message","interface":"telegram","payload":{{"text":"...","target":N,"thread_id":N}}}}
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
                thread_id = kwargs.get('message_thread_id')
                
                log_debug(f"[event_plugin] LLM responded with: {text[:100]}...")
                
                # Parse the JSON response from the LLM
                if text.strip().startswith('{') and text.strip().endswith('}'):
                    try:
                        # Parse the action generated by LLM
                        response_action = json.loads(text.strip())
                        log_info(f"[event_plugin] LLM generated action: {response_action}")
                        
                        # Check if this is a no_action response (event decided not to execute)
                        if response_action.get('type') == 'no_action':
                            log_info(f"[event_plugin] LLM decided not to execute scheduled event: {response_action.get('payload', {}).get('reason', 'No reason given')}")
                            # Find and mark the event as delivered since it was processed (even if not sent)
                            await self._mark_related_event_delivered()
                            return
                        
                        # Send this action through the normal action parser flow
                        from core.action_parser import parse_action
                        
                        # Create a proper message context for the action parser
                        # This ensures the action goes to the right interface
                        action_message = type('ActionMessage', (), {
                            'chat_id': response_action.get('payload', {}).get('target', chat_id),
                            'message_thread_id': response_action.get('payload', {}).get('thread_id', thread_id)
                        })()
                        
                        # Get the real bot instance from the active interface
                        real_bot = await self._get_active_bot()
                        
                        if real_bot:
                            # Create a wrapper bot that will mark the event as delivered after successful send
                            delivery_tracker_bot = self._create_delivery_tracker_bot(real_bot)
                            
                            # Let action parser handle the action normally
                            await parse_action(response_action, delivery_tracker_bot, action_message)
                        else:
                            log_error("[event_plugin] No active bot available for scheduled event execution")
                            
                    except json.JSONDecodeError:
                        log_error(f"[event_plugin] Invalid JSON response from LLM: {text[:100]}...")
                    except Exception as e:
                        log_error(f"[event_plugin] Error processing LLM response: {e}")
                else:
                    log_warning(f"[event_plugin] Non-JSON response from LLM: {text[:100]}...")
            
            def _create_delivery_tracker_bot(self, real_bot):
                """Create a bot wrapper that tracks delivery confirmation."""
                class DeliveryTrackerBot:
                    def __init__(self, real_bot, event_plugin):
                        self.real_bot = real_bot
                        self.event_plugin = event_plugin
                        # Copy all attributes from real bot
                        for attr in dir(real_bot):
                            if not attr.startswith('_') and attr != 'send_message':
                                setattr(self, attr, getattr(real_bot, attr))
                    
                    async def send_message(self, **kwargs):
                        """Send message and mark event as delivered on success."""
                        try:
                            # Send the message through the real bot
                            result = await self.real_bot.send_message(**kwargs)
                            
                            # If we reach here, the message was sent successfully
                            log_info(f"[event_plugin] ✅ Scheduled message sent successfully")
                            
                            # Mark the related event as delivered
                            await self._mark_related_event_delivered()
                            
                            return result
                            
                        except Exception as e:
                            log_error(f"[event_plugin] ❌ Failed to send scheduled message: {e}")
                            # Don't mark as delivered since it failed
                            raise
                    
                    async def _mark_related_event_delivered(self):
                        """Mark the currently processing event as delivered."""
                        try:
                            # Find the current event being processed from the pending events
                            # This is a simplified approach - in practice you might need more sophisticated tracking
                            if hasattr(self.event_plugin, '_current_processing_event_id'):
                                event_id = self.event_plugin._current_processing_event_id
                                mark_event_delivered(event_id)
                                log_info(f"[event_plugin] Event {event_id} marked as delivered after successful send")
                                # Clean up
                                delattr(self.event_plugin, '_current_processing_event_id')
                        except Exception as e:
                            log_error(f"[event_plugin] Error marking event as delivered: {e}")
                
                return DeliveryTrackerBot(real_bot, self.event_plugin)
            
            async def _mark_related_event_delivered(self):
                """Mark the currently processing event as delivered."""
                try:
                    if hasattr(self.event_plugin, '_current_processing_event_id'):
                        event_id = self.event_plugin._current_processing_event_id
                        mark_event_delivered(event_id)
                        log_info(f"[event_plugin] Event {event_id} marked as delivered (no_action)")
                        delattr(self.event_plugin, '_current_processing_event_id')
                except Exception as e:
                    log_error(f"[event_plugin] Error marking no_action event as delivered: {e}")
            
            async def _get_active_bot(self):
                """Get the active bot instance from interfaces."""
                try:
                    # Check which interfaces are active and get the appropriate bot
                    from core.core_initializer import core_initializer
                    
                    if 'telegram_bot' in core_initializer.active_interfaces:
                        # Get the Telegram bot instance
                        from interface.telegram_bot import application
                        if application and application.bot:
                            return application.bot
                        else:
                            log_warning("[event_plugin] Telegram interface active but bot not available")
                    
                    # Add other interface support here if needed
                    # Discord events would typically not be sent via scheduled events
                    # unless explicitly configured
                    
                    log_warning("[event_plugin] No suitable bot interface found for scheduled event")
                    return None
                    
                except Exception as e:
                    log_error(f"[event_plugin] Error getting active bot: {e}")
                    return None
        
        return ScheduledEventBot(self)

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
