# plugins/terminal.py

import asyncio
from core.ai_plugin_base import AIPluginBase
from telegram.constants import ParseMode
from core.logging_utils import log_debug, log_info, log_warning, log_error


class TerminalPlugin(AIPluginBase):
    """Plugin providing access to a persistent terminal session."""

    def __init__(self, notify_fn=None):
        self.process = None
        self.notify_fn = notify_fn

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
            log_error(f"[terminal] Failed to write to shell: {e}")
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

    def get_supported_actions(self):
        return ["terminal"]

    def get_target(self, trainer_message_id):
        return None

    def clear(self, trainer_message_id):
        pass


PLUGIN_CLASS = TerminalPlugin
