"""Action plugin loader."""

import importlib
from typing import Callable, Dict

_plugins: Dict[str, Callable] = {}


def load_action(name: str) -> Callable:
    if name in _plugins:
        return _plugins[name]
    module = importlib.import_module(f"plugins.{name}")
    if not hasattr(module, "run"):
        raise ValueError(f"Plugin {name} missing 'run' function")
    _plugins[name] = module.run
    return module.run
