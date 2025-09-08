"""Core actions for managing chat link metadata."""

from core.logging_utils import log_info, log_warning, log_error
from core.core_initializer import register_plugin, PLUGIN_REGISTRY
from core.chat_link_store import ChatLinkStore

# Global flag to avoid multiple registrations when the module is re-imported
_REGISTERED = False


class ChatLinkActions:
    """Expose actions for updating chat and thread names."""

    def __init__(self) -> None:
        global _REGISTERED

        # Check both the global flag and the registry to prevent duplicates
        if _REGISTERED:
            log_info("[chat_link_actions] chat_link actions already registered (global flag)")
            return
            
        if "chat_link" in PLUGIN_REGISTRY:
            log_info("[chat_link_actions] chat_link actions already registered (in registry)")
            _REGISTERED = True
            return

        self.store = ChatLinkStore()
        register_plugin("chat_link", self)
        _REGISTERED = True
        log_info("[chat_link_actions] Registered core chat_link actions")

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
                "optional_fields": ["message_thread_id", "interface"],
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
        interface = payload.get("interface")
        
        if not interface:
            log_error("No interface specified in chat_link_actions payload")
            return {"error": "Interface required"}
            
        try:
            updated = await self.store.update_names_from_resolver(
                chat_id,
                message_thread_id,
                interface=interface,
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


# Instantiate and register on import - but only if not already done
if not _REGISTERED and "chat_link" not in PLUGIN_REGISTRY:
    ChatLinkActions()

__all__ = ["ChatLinkActions"]
