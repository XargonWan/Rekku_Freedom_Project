"""Dummy plugin used for unit tests of action_parser."""

executed_actions = []

class TestActionPlugin:
    def get_supported_actions(self):
        # Use built-in 'command' type so validation succeeds
        return ["command"]

    async def execute_action(self, action, context, bot, original_message):
        executed_actions.append(action)
