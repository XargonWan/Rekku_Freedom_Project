import inspect
from typing import Dict

from core.plugin_base import PluginBase
from core.logging_utils import log_info, log_warning, log_error


class MessagePlugin(PluginBase):
    """Generic plugin to dispatch message_* actions to active interfaces."""

    @staticmethod
    def get_interface_id() -> str:
        """Return generic identifier for message-related actions."""
        return "message"

    def get_supported_actions(self) -> Dict[str, dict]:
        """Return message actions declared by any registered interface."""
        try:
            from core.core_initializer import core_initializer

            supported: Dict[str, dict] = {}
            for iface, actions in core_initializer.interface_actions.items():
                for action in actions:
                    if action.startswith("message_"):
                        info = core_initializer.actions_block["available_actions"].get(action, {})
                        supported[action] = {
                            "required_fields": info.get("required_fields", []),
                            "optional_fields": info.get("optional_fields", []),
                            "description": info.get("description", ""),
                        }
            return supported
        except Exception as e:
            log_warning(f"[message_plugin] Failed to gather supported actions: {e}")
            return {}

    def get_prompt_instructions(self, action_name: str) -> dict:
        try:
            from core.core_initializer import core_initializer

            info = core_initializer.actions_block["available_actions"].get(action_name)
            if info:
                return info.get("instructions", {})
        except Exception:
            pass
        return {}

    async def execute_action(self, action: dict, context: dict, bot, original_message):
        """Delegate message actions to the appropriate interface."""
        action_type = action.get("type")
        iface = action.get("interface")
        payload = action.get("payload", {})

        if not iface and action_type and action_type.startswith("message_"):
            iface = action_type[len("message_") :]

        if not iface:
            log_error(f"[message_plugin] Missing interface for action {action_type}")
            return

        try:
            from core.core_initializer import INTERFACE_REGISTRY

            target_iface = INTERFACE_REGISTRY.get(iface)
            if not target_iface or not hasattr(target_iface, "send_message"):
                log_error(f"[message_plugin] Interface '{iface}' cannot handle messages")
                return

            log_info(f"[message_plugin] Sending message via interface '{iface}'")
            result = target_iface.send_message(payload, original_message)
            if inspect.iscoroutine(result):
                await result
        except Exception as e:
            log_error(f"[message_plugin] Error executing {action_type}: {e}")

    # PluginBase requirement
    def get_metadata(self) -> dict:
        return {"name": "message"}


PLUGIN_CLASS = MessagePlugin
