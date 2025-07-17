"""Registry for interface handlers."""

REGISTERED_INTERFACES: dict[str, object] = {}


def register_interface(name: str, handler: object) -> None:
    """Register an interface handler under a given name."""
    REGISTERED_INTERFACES[name.lower()] = handler


def get_interface(name: str):
    """Retrieve a registered interface handler by name."""
    return REGISTERED_INTERFACES.get(name.lower())


def list_interfaces() -> list[str]:
    """Return the list of registered interface names."""
    return list(REGISTERED_INTERFACES.keys())
