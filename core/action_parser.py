"""Simple action parser for Rekku."""

from core.logging_utils import log_debug, log_warning


async def parse_action(action: dict, bot, message):
    """Execute a single action dict.

    Supported structure::
        {
            "type": "message",
            "interface": "telegram",
            "payload": {"text": "hi", "target": "123"}
        }
    """

    log_debug(f"[action_parser] Received action: {action}")

    if not isinstance(action, dict):
        log_warning("[action_parser] action must be a dict")
        return

    if action.get("type") != "message":
        log_warning("[action_parser] unknown action type")
        return

    payload = action.get("payload")
    if not isinstance(payload, dict):
        log_warning("[action_parser] missing payload")
        return

    text = payload.get("text")
    target = payload.get("target")
    if text is None or target is None:
        log_warning("[action_parser] missing text or target in payload")
        return

    reply_id = getattr(message, "message_id", None)
    log_debug(f"[action_parser] Sending message to {target}: {text!r}")
    try:
        await bot.send_message(chat_id=target, text=text, reply_to_message_id=reply_id)
    except Exception as e:
        log_warning(f"[action_parser] failed to send message: {e}")
    else:
        log_debug("[action_parser] message sent")
