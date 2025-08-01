"""
A Bash plugin for Rekku Freedom Project.

This plugin executes arbitrary shell commands and returns the output to the
requesting chat.  Additionally, every time a command is executed the
plugin notifies the configured TRAINER_ID via Telegram so that the trainer
can audit the operations being performed.  This design mirrors the
existing `TerminalPlugin` but operates on a per-command basis instead of
maintaining a persistent shell session.  Commands are extracted from
incoming prompts or messages using the same conventions as other
plugins.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from core.ai_plugin_base import AIPluginBase
from core.config import TRAINER_ID
from core.logging_utils import log_debug, log_error, log_info, log_warning
from core.telegram_utils import truncate_message
from telegram.constants import ParseMode


class BashPlugin(AIPluginBase):
    """Execute shell commands and notify the trainer on each invocation."""

    def __init__(self, notify_fn: Optional[callable] = None) -> None:
        self.notify_fn = notify_fn

    async def _run_command(self, cmd: str) -> str:
        """
        Execute a shell command asynchronously and capture its combined
        stdout/stderr output.  The command is executed in a non-interactive
        shell and the full output is returned as a string.  If the command
        fails to execute an empty string is returned and an error is logged.
        """
        if not cmd:
            log_warning("[bash_plugin] Received empty command; nothing to run")
            return ""
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await process.communicate()
            output = stdout.decode(errors="ignore").strip()
            return output
        except Exception as e:
            log_error(f"[bash_plugin] Failed to execute command '{cmd}': {e}")
            return ""

    async def handle_incoming_message(self, bot, message, prompt):
        """
        Handle an incoming Telegram message or system-generated prompt.  The
        command to execute is resolved by checking the `action.input` field
        first and falling back to the raw text of the message.  After
        execution the output is sent back to the user and a notification is
        delivered to the TRAINER_ID.  Output is truncated to avoid hitting
        Telegram limits.
        """
        # Determine the command from the prompt or message
        cmd = (
            prompt.get("action", {}).get("input")
            or prompt.get("message", {}).get("text", "")
        )
        log_debug(f"[bash_plugin] Executing command: {cmd}")
        output = await self._run_command(cmd)

        # Truncate the output for Telegram messaging
        truncated = truncate_message(output)

        # Send the result back to the originating chat as a markdown code block
        if bot and message:
            try:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=f"```\n{truncated}\n```" if truncated else "(no output)",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_to_message_id=getattr(message, "message_id", None),
                )
            except Exception as e:
                log_error(f"[bash_plugin] Failed to send command result: {e}")

        # Notify the trainer about the executed command and its output
        if bot:
            try:
                notification_text = f"[Bash Plugin] Executed:\n{cmd}\n\nOutput:\n{truncated or '(no output)'}"
                await bot.send_message(chat_id=TRAINER_ID, text=notification_text)
                log_debug(
                    f"[bash_plugin] Notification sent to trainer for command: {cmd}"
                )
            except Exception as e:
                log_error(f"[bash_plugin] Failed to notify trainer: {e}")
        return output

    async def generate_response(self, messages):
        """
        For multi-turn conversations, join the provided messages with newlines
        and execute them as a single shell command.  The combined output
        returned from `_run_command` is provided directly to the caller.
        """
        command = "\n".join(messages)
        return await self._run_command(command)

    @staticmethod
    def get_interface_id() -> str:
        """Return the unique identifier for this plugin interface."""
        return "bash"

    def get_supported_actions(self) -> dict:
        """Return schema information for supported actions."""
        return {
            "bash": {
                "required_fields": ["command"],
                "optional_fields": [],
                "description": "Run a bash command and return its output",
            }
        }

    def get_prompt_instructions(self, action_name: str) -> dict:
        """Return prompt instructions for the given action."""
        if action_name != "bash":
            return {}
        return {
            "description": "Run a bash command",
            "payload": {"command": "echo hello", "interface": self.get_interface_id()},  # interface auto-corrected
        }

    def get_rate_limit(self):
        """
        Rate limiting configuration.  The default values mirror other
        plugins: allow 80 requests per 3 hours with a minimum 0.5 second
        spacing between messages.
        """
        return (80, 10800, 0.5)


# Export the plugin class so that the plugin loader can locate it
PLUGIN_CLASS = BashPlugin