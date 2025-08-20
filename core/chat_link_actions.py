"""Core actions for managing chat link metadata."""

from core.logging_utils import log_info, log_warning, log_error
from core.core_initializer import register_plugin
from core.chat_link_store import ChatLinkStore


class ChatLinkActions:
    """Expose actions for updating chat and thread names."""

    def __init__(self) -> None:
        self.store = ChatLinkStore()
        register_plugin("chat_link", self)
        log_info("[chat_link_actions] Registered core chat_link actions")

    # --------------------------------------------------------------
    @staticmethod
    def get_supported_action_types():
        return ["update_chat_name"]

    @staticmethod
    def get_supported_actions():
        return {
            "update_chat_name": {
                "description": "Aggiorna il nome della chat o del thread per un chat link esistente.",
                "required_fields": ["chat_id"],
                "optional_fields": ["message_thread_id", "chat_name", "message_thread_name"],
            }
        }

    @staticmethod
    def validate_payload(action_type: str, payload: dict):
        errors = []
        if action_type == "update_chat_name":
            if not payload.get("chat_id"):
                errors.append("chat_id is required")
            if not payload.get("chat_name") and not payload.get("message_thread_name"):
                errors.append("chat_name or message_thread_name required")
        return errors

    async def execute_action(self, action: dict, context: dict, bot, original_message):
        action_type = action.get("type")
        if action_type != "update_chat_name":
            return None

        payload = action.get("payload", {})
        chat_id = payload.get("chat_id")
        message_thread_id = payload.get("message_thread_id")
        chat_name = payload.get("chat_name")
        thread_name = payload.get("message_thread_name")

        try:
            updated = await self.store.update_names(
                chat_id,
                message_thread_id,
                chat_name=chat_name,
                message_thread_name=thread_name,
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
