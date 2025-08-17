import json
from collections.abc import Mapping, Sequence


def custom_json_encoder(obj):
    """Fallback encoder that converts objects to dictionaries or strings."""
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def dumps(data, **kwargs):
    """Serialize ``data`` to JSON using the custom encoder."""
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(data, default=custom_json_encoder, **kwargs)


def sanitize_for_json(obj):
    """Recursively convert objects into JSON-serializable structures."""
    if isinstance(obj, Mapping):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [sanitize_for_json(v) for v in obj]
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        if hasattr(obj, "__dict__"):
            return sanitize_for_json(obj.__dict__)
        return str(obj)
