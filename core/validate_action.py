from typing import List, Dict
from core.logging_utils import log_debug


def validate_action(output_json: Dict) -> List[str]:
    """Validate LLM JSON output describing actions.

    Returns a list of error strings. Empty list means valid.
    """
    errors: List[str] = []

    actions = output_json.get("actions")
    if not isinstance(actions, list):
        errors.append("'actions' must be a list")
        return errors

    for idx, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"Action {idx} must be a dict")
            continue
        if list(action.keys()) != ["message"]:
            errors.append(f"Action {idx} must contain only 'message'")
            continue
        message = action.get("message")
        if not isinstance(message, dict):
            errors.append(f"Action {idx} -> 'message' must be a dict")
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            errors.append(f"Action {idx} -> message.content must be a non-empty string")
        target = message.get("target")
        if not isinstance(target, str) or not target.startswith("Telegram/"):
            errors.append(
                f"Action {idx} -> message.target must be a string starting with 'Telegram/'"
            )
    log_debug(f"[validate_action] errors: {errors}")
    return errors
