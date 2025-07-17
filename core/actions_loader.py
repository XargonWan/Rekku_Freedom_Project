import glob
import importlib
import os
from core.logging_utils import log_debug, log_error


def load_available_actions() -> list:
    """Scan plugins for supported actions definitions."""
    actions: list = []

    for path in glob.glob(os.path.join("plugins", "**", "*.py"), recursive=True):
        module_name = os.path.relpath(path, ".")[:-3].replace(os.sep, ".")
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            log_error(f"[actions_loader] Failed to import {module_name}: {e}")
            continue

        if hasattr(module, "get_supported_actions"):
            try:
                plugin_actions = module.get_supported_actions()
                if isinstance(plugin_actions, list):
                    actions.extend(plugin_actions)
                else:
                    log_debug(
                        f"[actions_loader] {module_name}.get_supported_actions returned non-list"
                    )
            except Exception as e:
                log_error(
                    f"[actions_loader] Error calling {module_name}.get_supported_actions: {e}"
                )
    log_debug(f"[actions_loader] Loaded actions: {actions}")
    return actions
