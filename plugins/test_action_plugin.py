"""Minimal plugin used for tests of action_parser."""

executed_actions = []

class TestActionPlugin:
    def get_supported_action_types(self):
        return ["command"]

    def execute_action(self, action: dict, context: dict, bot, original_message):
        executed_actions.append(action)

PLUGIN_CLASS = TestActionPlugin
