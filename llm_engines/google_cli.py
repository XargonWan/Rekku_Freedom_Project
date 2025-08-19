# llm_engines/google_cli.py

import subprocess
import json
from core.ai_plugin_base import AIPluginBase
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.notifier import set_notifier
from core.config import GEMINI_API_KEY

class GoogleCLIPlugin(AIPluginBase):
    """
    LLM plugin to use google-cli as backend.
    """
    def __init__(self, notify_fn=None):
        if notify_fn:
            log_debug("[google-cli] Using custom notification function.")
            set_notifier(notify_fn)
        else:
            log_debug("[google-cli] No notification function provided, using fallback.")
            set_notifier(lambda chat_id, message: log_info(f"[NOTIFY fallback] {message}"))

    async def generate_response(self, messages):
        """
        Sends the request to gemini-cli and returns the response.
        """
        prompt = messages[-1]["content"] if messages else ""
        log_debug(f"[gemini] Sent prompt: {prompt}")
        try:
            result = subprocess.run([
                "gemini", "--token", GEMINI_API_KEY, prompt
            ], capture_output=True, text=True, timeout=30)
            log_debug(f"[gemini] stdout: {result.stdout.strip()}")
            log_debug(f"[gemini] stderr: {result.stderr.strip()}")
            if result.returncode != 0:
                log_error(f"gemini error: {result.stderr}")
                return "gemini error: " + result.stderr
            return result.stdout.strip()
        except Exception as e:
            log_error(f"Exception in gemini: {e}")
            return f"Error: {e}"

    def get_supported_models(self):
        return ["google-cli"]

    def get_current_model(self):
        return "google-cli"

    def set_current_model(self, name):
        if name != "google-cli":
            raise ValueError(f"Unsupported model: {name}")

    async def handle_incoming_message(self, bot, message, prompt: dict):
        """
        Handles an incoming message using google-cli.
        """
        query = prompt.get("query") or prompt.get("text") or ""
        if not query:
            await bot.send_message(message.chat_id, "⚠️ No query provided.")
            return
        response = await self.generate_response([{"role": "user", "content": query}])
        await bot.send_message(message.chat_id, response)
