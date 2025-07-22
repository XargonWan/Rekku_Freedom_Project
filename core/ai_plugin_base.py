# core/ai_plugin_base.py

from core.prompt_engine import build_prompt

class AIPluginBase:
    """
    Base interface for every AI engine.
    Each plugin (OpenAI, Claude, Manual, etc.) may implement the desired methods.
    """

    async def handle_incoming_message(self, bot, message, prompt):
        """Process a message using a pre-built prompt."""
        raise NotImplementedError("handle_incoming_message not implemented")

    def get_target(self, trainer_message_id):
        """Return the owner of a training message."""
        return None  # Default: does nothing

    def clear(self, trainer_message_id):
        """Remove proxy references once consumed."""
        pass  # Default: does nothing

    async def generate_response(self, messages):
        """Send messages to the LLM engine and receive the response."""
        raise NotImplementedError("generate_response not implemented")

    def get_supported_models(self) -> list[str]:
        """Optional. Return the list of available models."""
        return []
    def get_rate_limit(self):
        return (80, 10800, 0.5)


    def set_notify_fn(self, notify_fn):
        """Optional: dynamically update the notification function."""
        self.notify_fn = notify_fn

    def get_supported_action_types(self) -> list[str]:
        """Return custom action types handled by this plugin."""
        return []

    async def handle_custom_action(self, action_type: str, payload: dict):
        """Handle a plugin-defined custom action."""
        raise NotImplementedError("handle_custom_action not implemented")
