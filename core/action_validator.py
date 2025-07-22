# core/action_validator.py

"""Utilities to validate action dictionaries passed between components."""

from typing import Any, List, Tuple

SUPPORTED_TYPES = {"message", "event", "command", "memory"}


def _validate_message_payload(payload: dict, errors: List[str]) -> None:
    """Validate payload for message actions."""
    text = payload.get("text")
    if not isinstance(text, str) or not text:
        errors.append("payload.text must be a non-empty string")

    scope = payload.get("scope")
    if scope not in {"local", "global"}:
        errors.append("payload.scope must be 'local' or 'global'")

    privacy = payload.get("privacy")
    if privacy not in {"default", "private", "public"}:
        errors.append(
            "payload.privacy must be one of ['default', 'private', 'public']"
        )

    target = payload.get("target")
    if target is not None:
        if not isinstance(target, dict):
            errors.append("payload.target must be a dict with chat_id and message_id")
        else:
            chat_id = target.get("chat_id")
            message_id = target.get("message_id")
            if not isinstance(chat_id, int):
                errors.append("payload.target.chat_id must be an int")
            if not isinstance(message_id, int):
                errors.append("payload.target.message_id must be an int")


def _validate_event_payload(payload: dict, errors: List[str]) -> None:
    """Validate payload for event actions."""
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        errors.append("payload.name must be a non-empty string for event action")

    parameters = payload.get("parameters")
    if parameters is not None and not isinstance(parameters, dict):
        errors.append("payload.parameters must be a dict if provided")


def _validate_command_payload(payload: dict, errors: List[str]) -> None:
    """Validate payload for command actions."""
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        errors.append("payload.name must be a non-empty string for command action")

    args = payload.get("args")
    if args is not None and not isinstance(args, list):
        errors.append("payload.args must be a list if provided")


def _validate_memory_payload(payload: dict, errors: List[str]) -> None:
    """Validate payload for memory actions."""
    content = payload.get("content")
    if not isinstance(content, str) or not content:
        errors.append("payload.content must be a non-empty string")

    tags = payload.get("tags")
    if tags is not None:
        if (
            not isinstance(tags, list)
            or not all(isinstance(tag, str) for tag in tags)
        ):
            errors.append("payload.tags must be a list of strings if provided")


def validate_action(action: dict) -> Tuple[bool, List[str]]:
    """Validate an action dictionary.

    Parameters
    ----------
    action : dict
        Dictionary describing an action.

    Returns
    -------
    tuple[bool, list[str]]
        A tuple containing a boolean validity flag and a list of error messages.
    """

    errors: List[str] = []

    if not isinstance(action, dict):
        return False, ["action must be a dict"]

    action_type = action.get("type")
    if not action_type:
        errors.append("Missing 'type'")
    elif action_type not in SUPPORTED_TYPES:
        errors.append(f"Unsupported type '{action_type}'")

    payload = action.get("payload")
    if payload is None:
        errors.append("Missing 'payload'")
    elif not isinstance(payload, dict):
        errors.append("'payload' must be a dict")

    if isinstance(payload, dict) and action_type in SUPPORTED_TYPES:
        if action_type == "message":
            _validate_message_payload(payload, errors)
        elif action_type == "event":
            _validate_event_payload(payload, errors)
        elif action_type == "command":
            _validate_command_payload(payload, errors)
        elif action_type == "memory":
            _validate_memory_payload(payload, errors)

    return len(errors) == 0, errors

__all__ = ["validate_action"]
