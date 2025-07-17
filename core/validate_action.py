from typing import List, Dict
from core.logging_utils import log_debug
from core.interface_loader import get_interface


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
        if not isinstance(target, str) or "/" not in target:
            errors.append(
                f"Action {idx} -> message.target must be 'interface/id'"
            )
        else:
            iface_name = target.split("/", 1)[0]
            if not get_interface(iface_name):
                errors.append(
                    f"Action {idx} -> unknown interface '{iface_name}'"
                )
    log_debug(f"[validate_action] errors: {errors}")
    return errors
