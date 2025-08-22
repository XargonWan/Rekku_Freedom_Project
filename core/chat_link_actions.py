"""Core actions for managing chat link metadata."""

from core.logging_utils import log_info, log_warning, log_error
from core.core_initializer import register_plugin, PLUGIN_REGISTRY
from core.chat_link_store import ChatLinkStore


class ChatLinkActions:
    """Expose actions for updating chat and thread names."""

    def __init__(self) -> None:
        self.store = ChatLinkStore()
        if "chat_link" not in PLUGIN_REGISTRY:
            register_plugin("chat_link", self)
            log_info("[chat_link_actions] Registered core chat_link actions")
        else:
            log_info("[chat_link_actions] chat_link actions already registered")

    # --------------------------------------------------------------
    @staticmethod
    def get_supported_action_types():
        return ["update_chat_name"]

    @staticmethod
    def get_supported_actions():
        return {
            "update_chat_name": {
                "description": "Aggiorna i nomi della chat e del thread usando i dati dell'interfaccia.",
                "required_fields": ["chat_id"],
                "optional_fields": ["message_thread_id"],
            }
        }

    @staticmethod
    def validate_payload(action_type: str, payload: dict):
        errors = []
        if action_type == "update_chat_name":
            if not payload.get("chat_id"):
                errors.append("chat_id is required")
        return errors

    async def execute_action(self, action: dict, context: dict, bot, original_message):
        action_type = action.get("type")
        if action_type != "update_chat_name":
            return None

        payload = action.get("payload", {})
        chat_id = payload.get("chat_id")
        message_thread_id = payload.get("message_thread_id")
        try:
            updated = await self.store.update_names_from_resolver(
                chat_id,
                message_thread_id,
                bot=bot,
            )
            if updated:
                log_info(
                    f"[chat_link_actions] Updated chat link names for chat_id={chat_id}, thread_id={message_thread_id}"
                )
            else:
                log_warning("[chat_link_actions] No chat link updated")
        except Exception as e:  # pragma: no cover - logging only
            log_error(f"[chat_link_actions] Error updating chat names: {e}")
            return {"error": str(e)}
        return {"updated": updated}


# Instantiate and register on import
ChatLinkActions()

__all__ = ["ChatLinkActions"]
