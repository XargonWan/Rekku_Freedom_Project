"""actions_loader.py
Scan plugin modules to discover supported action types.
"""

from __future__ import annotations

import importlib
import os
from typing import List, Set

from core.logging_utils import log_debug, log_warning, log_error


_ACTIONS_CACHE: List[str] | None = None


def _iter_plugin_modules(base_dir: str):
    """Yield module names under ``base_dir`` recursively."""
    for root, _dirs, files in os.walk(base_dir):
        for file in files:
            if not file.endswith(".py") or file.startswith("__"):
                continue
            rel_path = os.path.relpath(os.path.join(root, file), os.path.dirname(base_dir))
            module_name = rel_path[:-3].replace(os.sep, ".")
            yield module_name


def load_supported_actions() -> List[str]:
    """Return a list of unique action names supported by plugins."""
    global _ACTIONS_CACHE
    if _ACTIONS_CACHE is not None:
        return _ACTIONS_CACHE

    actions: Set[str] = set()
    base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins")
    log_debug(f"[actions_loader] Scanning plugins in {base_dir}")

    for module_name in _iter_plugin_modules(base_dir):
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            log_error(f"[actions_loader] Failed to import {module_name}: {e}")
            continue

        fn = getattr(module, "get_supported_actions", None)
        if callable(fn):
            try:
                supported = fn()
                log_debug(f"[actions_loader] {module_name} -> {supported}")
                if supported:
                    actions.update(supported)
            except Exception as e:
                log_warning(f"[actions_loader] Error calling {module_name}.get_supported_actions: {e}")

    _ACTIONS_CACHE = sorted(actions)
    log_debug(f"[actions_loader] Available actions: {_ACTIONS_CACHE}")
    return _ACTIONS_CACHE

