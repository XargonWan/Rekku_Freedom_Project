# llm_engines/google_cli.py

import subprocess
import json
from core.ai_plugin_base import AIPluginBase
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.notifier import set_notifier
from core.config import GEMINI_API_KEY
from core.transport_layer import llm_to_interface

# Google CLI-specific configuration
GOOGLE_CLI_CONFIG = {
    "max_prompt_chars": 20000,  # Google Gemini limits
    "max_response_chars": 3000,
    "supports_images": True,
    "supports_functions": True,
    "model_name": "gemini-pro",
    "default_model": "google-cli",
    "timeout": 30,
    "max_retries": 3,
    "temperature": 0.7
}

def get_google_cli_config() -> dict:
    """Get Google CLI-specific configuration."""
    return GOOGLE_CLI_CONFIG.copy()

def get_max_prompt_chars() -> int:
    """Get maximum prompt characters for Google CLI."""
    return GOOGLE_CLI_CONFIG["max_prompt_chars"]

def get_max_response_chars() -> int:
    """Get maximum response characters for Google CLI."""
    return GOOGLE_CLI_CONFIG["max_response_chars"]

def supports_images() -> bool:
    """Check if Google CLI supports images."""
    return GOOGLE_CLI_CONFIG["supports_images"]

def supports_functions() -> bool:
    """Check if Google CLI supports functions."""
    return GOOGLE_CLI_CONFIG["supports_functions"]

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
        # Correct path to the message text
        query = prompt.get("input", {}).get("payload", {}).get("text", "")
        if not query:
            try:
                from core.transport_layer import interface_to_llm
            except Exception:
                interface_to_llm = None
            if interface_to_llm is None:
                await bot.send_message(message.chat_id, "⚠️ No query provided.")
            else:
                await interface_to_llm(bot.send_message, chat_id=message.chat_id, text="⚠️ No query provided.")
            return
        
        # Include interface in the query for the LLM
        interface = prompt.get("input", {}).get("interface", "unknown")
        full_query = f"Message from {interface} interface: {query}"
        
        response = await self.generate_response([{"role": "user", "content": full_query}])
        # Forward model output through the centralized LLM->interface path
        await llm_to_interface(
            bot.send_message,
            chat_id=message.chat_id,
            text=response,
            interface='telegram' if getattr(bot.__class__, '__module__', '').startswith('telegram') else 'generic',
        )

# Ensure the plugin loader can locate the plugin class
PLUGIN_CLASS = GoogleCLIPlugin
