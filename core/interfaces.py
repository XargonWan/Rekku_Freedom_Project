"""Simple registry for active interface instances."""

from typing import Any, Optional

from core.logging_utils import log_debug, log_warning

# Global registry for interface objects
INTERFACE_REGISTRY: dict[str, Any] = {}

# Backwards-compatibility alias
_INTERFACES = INTERFACE_REGISTRY


def register_interface(name: str, interface_obj: Any) -> None:
    """Register an interface instance for later retrieval."""
    _INTERFACES[name] = interface_obj
    log_debug(f"[interfaces] Registered interface: {name}")


def get_interface_by_name(name: str) -> Optional[Any]:
    """Return a previously registered interface by name."""
    iface = _INTERFACES.get(name)
    if iface is None:
        log_warning(f"[interfaces] Interface not found: {name}")
    return iface
