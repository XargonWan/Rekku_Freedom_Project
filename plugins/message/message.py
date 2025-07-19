from core.ai_plugin_base import AIPluginBase

class MessagePlugin(AIPluginBase):
    """
    Plugin to handle the "message" action in the Rekku system.
    """

    async def handle_incoming_message(self, bot, message, prompt):
        """
        Handles incoming messages and processes "message" type actions.
        """
        actions = prompt.get("actions", [])
        for action in actions:
            if action.get("type") == "message":
                payload = action.get("payload", {})
                text = payload.get("text")
                target = payload.get("target")

                if text:
                    await bot.send_message(target, text)

    async def generate_response(self, messages):
        """
        Dummy method for generating responses, not needed for this plugin.
        """
        return None

    def get_target(self, trainer_message_id):
        """
        Returns the target associated with a training message.
        """
        # Specific implementation if needed
        return None

    def clear(self, trainer_message_id):
        """
        Clears the data associated with a training message.
        """
        # Specific implementation if needed
        pass

    def get_supported_actions(self):
        """
        Declaration of actions supported by the plugin.
        """
        return [{
            "name": "message",
            "description": "Used to send a message through an interface",
            "usage": {
                "type": "message",
                "payload": {
                    "text": "Text to send",
                    "target": "optional target id or channel"
                }
            }
        }]

PLUGIN_CLASS = MessagePlugin
