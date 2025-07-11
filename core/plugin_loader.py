# plugin_loader.py
"""Dynamic loader for Rekku's optional plugins."""

import importlib
import json
import os
from typing import Dict

from core.plugin_base import PluginBase
from logging_utils import log_debug, log_info, log_warning, log_error

PLUGIN_REGISTRY: Dict[str, PluginBase] = {}


def _discover_plugins(path: str = "plugins") -> list[str]:
    """Return a list of plugin package names found in the given directory."""
    plugins = []
    if not os.path.isdir(path):
        return plugins
    for entry in os.scandir(path):
        if entry.is_dir() and os.path.isfile(os.path.join(entry.path, "__init__.py")):
            plugins.append(entry.name)
    return plugins


def load_plugins(path: str = "plugins") -> Dict[str, PluginBase]:
    """Import and initialize all plugins under the given path."""
    for name in _discover_plugins(path):
        module_name = f"{path.replace(os.sep, '.')}" + f".{name}"
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            log_error(f"[plugin_loader] Failed to import {module_name}: {e}")
            continue

        plugin_cls = getattr(module, "PLUGIN_CLASS", None)
        if plugin_cls is None:
            log_warning(f"[plugin_loader] {name} missing PLUGIN_CLASS, skipping")
            continue

        config = {}
        cfg_path = os.path.join(path, name, "config.json")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                log_warning(f"[plugin_loader] Error reading config for {name}: {e}")

        try:
            plugin = plugin_cls(config=config)
        except TypeError:
            plugin = plugin_cls()

        try:
            plugin.start()
        except Exception as e:
            log_error(f"[plugin_loader] Error starting {name}: {e}")

        PLUGIN_REGISTRY[name] = plugin

    return PLUGIN_REGISTRY


def get_plugin(name: str) -> PluginBase | None:
    """Return a plugin instance by name."""
    return PLUGIN_REGISTRY.get(name)


def stop_plugins() -> None:
    """Call stop() on all loaded plugins."""
    for plugin in PLUGIN_REGISTRY.values():
        try:
            plugin.stop()
        except Exception as e:
            log_error(f"[plugin_loader] Error stopping plugin: {e}")
    PLUGIN_REGISTRY.clear()
