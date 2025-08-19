# plugins/terminal.py

import asyncio
from typing import Optional
from core.ai_plugin_base import AIPluginBase
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.core_initializer import core_initializer, register_plugin

# Import config safely - may fail in test environments
try:
    from core.config import TELEGRAM_TRAINER_ID
except Exception:
    TELEGRAM_TRAINER_ID = None

# Import telegram safely - may fail if not available
try:
    from telegram.constants import ParseMode
except Exception:
    class ParseMode:
        MARKDOWN = "Markdown"

# Import telegram utils safely
try:
    from core.telegram_utils import truncate_message
except Exception:
    def truncate_message(text, max_length=4000):
        return text[:max_length] if len(text) > max_length else text

# Import notifier safely
try:
    from core.notifier import notify_trainer
except Exception:
    def notify_trainer(message: str) -> None:
        log_warning("[terminal] notify_trainer not available")

# Import auto_response safely
try:
    from core.auto_response import request_llm_delivery
except Exception:
    async def request_llm_delivery(*args, **kwargs):
        log_warning("[terminal] Auto-response not available")


class TerminalPlugin(AIPluginBase):
    """Plugin providing access to both single commands (bash) and persistent terminal session."""

    def __init__(self, notify_fn: Optional[callable] = None):
        self.process = None
        self.notify_fn = notify_fn
        register_plugin("terminal", self)
        core_initializer.register_plugin("terminal")
        log_info("[terminal] TerminalPlugin registered successfully")

    async def _run_single_command(self, cmd: str) -> str:
        """
        Execute a single shell command asynchronously and capture its combined
        stdout/stderr output. Used for 'bash' action type.
        """
        if not cmd:
            log_warning("[terminal] Received empty command; nothing to run")
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
            log_error(f"[terminal] Failed to execute single command '{cmd}': {e}")
            return ""

    async def _ensure_process(self):
        """Ensure the background shell is running."""
        if self.process is None or self.process.returncode is not None:
            self.process = await asyncio.create_subprocess_shell(
                "/bin/bash",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            log_debug("[terminal] Shell subprocess started")

    async def _send_command(self, cmd: str) -> str:
        """Send ``cmd`` to the shell and return its output."""
        await self._ensure_process()

        sentinel = "__END__REKKU__"
        full_cmd = f"{cmd}; echo {sentinel}\n"

        try:
            self.process.stdin.write(full_cmd.encode())
            await self.process.stdin.drain()
        except Exception as e:
            log_error(f"[terminal] Failed to write to shell: {e}", e)
            self.process = None
            return "⚠️ Unable to send command to shell."

        output_lines = []
        try:
            while True:
                line = await asyncio.wait_for(
                    self.process.stdout.readline(), timeout=10.0
                )
                if not line:
                    self.process = None
                    return "⚠️ Terminal closed unexpectedly."
                decoded = line.decode()
                if decoded.rstrip() == sentinel:
                    break
                output_lines.append(decoded)
        except asyncio.TimeoutError:
            return "⚠️ Command timeout."

        return "".join(output_lines).strip()

    async def handle_incoming_message(self, bot, message, prompt):
        cmd = (
            prompt.get("action", {}).get("input")
            or prompt.get("message", {}).get("text", "")
        )
        log_debug(f"[terminal] Executing: {cmd}")
        output = await self._send_command(cmd)

        if bot and message:
            truncated = output
            if len(truncated) > 4000:
                truncated = truncated[:4000] + "\n..."
            await bot.send_message(
                chat_id=message.chat_id,
                text=f"```\n{truncated}\n```" if truncated else "(no output)",
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=message.message_id,
            )

        return output

    async def generate_response(self, messages):
        command = "\n".join(messages)
        return await self._send_command(command)

    @staticmethod
    def get_interface_id() -> str:
        """Return the unique identifier for this plugin interface."""
        return "terminal"

    @staticmethod
    def get_supported_action_types() -> list[str]:
        """Return the list of action types this plugin supports."""
        return ["terminal"]

    def get_supported_actions(self) -> dict:
        """Return schema information for supported actions."""
        return {
            "terminal": {
                "required_fields": ["command"],
                "optional_fields": ["persistent_session"],
                "description": "Execute shell commands (bash, python, etc.) in a terminal session. Optionally persistent.",
            }
        }

    def get_prompt_instructions(self, action_name: str) -> dict:
        if action_name == "terminal":
            return {
                "description": "Execute commands in a terminal session (bash, python, etc.). Optionally persistent.",
                "payload": {
                    "command": "df -h",
                    "persistent_session": False,
                    "interface": self.get_interface_id(),
                },
                "example": {
                    "type": "terminal",
                    "payload": {
                        "command": "df -h",
                        "persistent_session": True
                    }
                }
            }
        return {}

    async def execute_action(self, action: dict, context: dict, bot, original_message):
        """Execute terminal actions."""
        action_type = action.get("type")
        payload = action.get("payload", {})
        command = payload.get("command", "")
        persistent_session = payload.get("persistent_session", False)

        if not command:
            log_warning(f"[terminal] No command provided for {action_type} action")
            return

        log_info(f"[terminal] Executing {action_type} command: {command}")

        try:
            if persistent_session:
                # Persistent session execution
                output = await self._send_command(command)
            else:
                # Single command execution
                output = await self._run_single_command(command)

            log_debug(f"[terminal] Command output: {output}")

            # Notify trainer about the executed command and its result
            try:
                summary = truncate_message(output, 1000)
                notify_trainer(
                    f"[terminal] Command: {command}\nOutput:\n{summary}"
                )
            except Exception as e:
                log_warning(f"[terminal] Failed to notify trainer: {e}")

            # Use auto-response system instead of direct Telegram response
            if original_message and hasattr(original_message, 'chat_id'):
                interface_name = context.get('interface', 'telegram_bot')
                if interface_name == 'telegram':
                    interface_name = 'telegram_bot'
                response_context = {
                    'chat_id': original_message.chat_id,
                    'message_id': getattr(original_message, 'message_id', None),
                    'interface_name': interface_name,
                    'original_command': command,
                    'action_type': action_type
                }

                from core.auto_response import request_llm_delivery
                await request_llm_delivery(
                    output=output,
                    original_context=response_context,
                    action_type=action_type,
                    command=command
                )

                log_info(f"[terminal] Requested LLM delivery of {action_type} output to chat {original_message.chat_id}")
            else:
                log_warning("[terminal] No original_message context for auto-response")

        except Exception as e:
            log_error(f"[terminal] Error executing {action_type} command '{command}': {e}")

            try:
                notify_trainer(
                    f"[terminal] Error executing: {command}\nError: {e}"
                )
            except Exception:
                pass

            if original_message and hasattr(original_message, 'chat_id'):
                interface_name = context.get('interface', 'telegram_bot')
                if interface_name == 'telegram':
                    interface_name = 'telegram_bot'
                error_context = {
                    'chat_id': original_message.chat_id,
                    'message_id': getattr(original_message, 'message_id', None),
                    'interface_name': interface_name,
                }

                from core.auto_response import request_llm_delivery
                await request_llm_delivery(
                    output=f"Error executing command '{command}': {str(e)}",
                    original_context=error_context,
                    action_type=f"{action_type}_error",
                    command=command
                )

    def get_target(self, trainer_message_id):
        return None

    def clear(self, trainer_message_id):
        pass

    def get_rate_limit(self):
        return (80, 10800, 0.5)


PLUGIN_CLASS = TerminalPlugin
