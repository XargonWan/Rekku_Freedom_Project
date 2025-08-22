# core/core_initializer.py

import os
import importlib
import inspect
import asyncio
from pathlib import Path
from typing import Optional, Any
from core.logging_utils import log_info, log_error, log_warning, log_debug
from core.config import get_active_llm, list_available_llms


class CoreInitializer:
    """Centralizes the initialization of all Rekku components."""
    
    def __init__(self):
        self.loaded_plugins = []
        self.active_interfaces = []
        self.active_llm = None
        self.startup_errors = []
        self.actions_block = {"available_actions": {}}
        self.interface_actions = {}
    
    async def initialize_all(self, notify_fn=None):
        """Initialize all Rekku components in the correct order."""
        log_info("🚀 Initializing Rekku core components...")

        # Reset state for fresh initialization
        self.loaded_plugins = []
        self.interface_actions = {}
        self.actions_block = {"available_actions": {}}

        # 1. Load LLM engine
        await self._load_llm_engine(notify_fn)

        # 2. Load generic plugins
        self._load_plugins()
        await self._build_actions_block()

        # 3. Auto-discover active interfaces
        self._discover_interfaces()

        return True
    
    async def _load_llm_engine(self, notify_fn=None):
        """Load the active LLM engine."""
        try:
            self.active_llm = await get_active_llm()
            
            # Import here to avoid circular imports
            from core.plugin_instance import load_plugin
            await load_plugin(self.active_llm, notify_fn=notify_fn)
            
            log_debug(f"[core_initializer] Active LLM engine loaded: {self.active_llm}")
        except Exception as e:
            log_error(f"[core_initializer] Failed to load active LLM: {repr(e)}")
            self.startup_errors.append(f"LLM engine error: {e}")
    
    def _load_plugins(self):
        """Auto-discover and load all available plugins for validation and startup."""
        # Note: This now actually loads and starts action providers from
        # plugins, LLM engines and interfaces. Files no longer need to follow a
        # ``*_plugin.py`` naming convention.

        root_dir = Path(__file__).parent.parent
        search_dirs = ["plugins", "llm_engines", "interface"]

        for base in search_dirs:
            base_path = root_dir / base
            if not base_path.exists():
                continue

            for py_file in base_path.rglob("*.py"):
                if py_file.name == "__init__.py" or py_file.name.startswith("_"):
                    continue

                module_name = ".".join(py_file.relative_to(root_dir).with_suffix("").parts)

                try:
                    module = importlib.import_module(module_name)
                except Exception as e:
                    log_warning(f"[core_initializer] ⚠️ Failed to import {module_name}: {e}")
                    self.startup_errors.append(f"Module {module_name}: {e}")
                    continue

                if not hasattr(module, "PLUGIN_CLASS"):
                    continue

                plugin_class = getattr(module, "PLUGIN_CLASS")

                if not (
                    hasattr(plugin_class, "get_supported_action_types")
                    or hasattr(plugin_class, "get_supported_actions")
                ):
                    log_warning(
                        f"[core_initializer] ⚠️ Plugin {module_name} doesn't implement action interface"
                    )
                    self.startup_errors.append(
                        f"Plugin {module_name}: Missing action interface"
                    )
                    continue

                try:
                    init_sig = inspect.signature(plugin_class.__init__)
                    required = [
                        p
                        for name, p in list(init_sig.parameters.items())[1:]
                        if p.default is inspect.Parameter.empty
                        and p.kind
                        in (
                            inspect.Parameter.POSITIONAL_ONLY,
                            inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        )
                    ]
                    if required:
                        log_debug(
                            f"[core_initializer] Skipping {module_name}: constructor requires params"
                        )
                        continue

                    instance = plugin_class()

                    if hasattr(instance, "start"):
                        try:
                            if asyncio.iscoroutinefunction(instance.start):
                                try:
                                    loop = asyncio.get_running_loop()
                                    if loop and loop.is_running():
                                        loop.create_task(instance.start())
                                        log_info(
                                            f"[core_initializer] Started async plugin: {module_name}"
                                        )
                                    else:
                                        log_warning(
                                            f"[core_initializer] No running loop for async plugin: {module_name}"
                                        )
                                        if not hasattr(self, "_pending_async_plugins"):
                                            self._pending_async_plugins = []
                                        self._pending_async_plugins.append(
                                            (module_name, instance)
                                        )
                                except RuntimeError:
                                    log_warning(
                                        f"[core_initializer] No event loop for async plugin: {module_name}"
                                    )
                                    if not hasattr(self, "_pending_async_plugins"):
                                        self._pending_async_plugins = []
                                    self._pending_async_plugins.append(
                                        (module_name, instance)
                                    )
                            else:
                                instance.start()
                                log_info(
                                    f"[core_initializer] Started sync plugin: {module_name}"
                                )
                        except Exception as e:
                            log_error(
                                f"[core_initializer] Error starting plugin {module_name}: {repr(e)}"
                            )
                    else:
                        log_debug(
                            f"[core_initializer] Plugin {module_name} has no start method"
                        )

                except Exception as e:
                    log_error(
                        f"[core_initializer] Failed to start plugin {module_name}: {repr(e)}"
                    )
                    self.startup_errors.append(f"Plugin {module_name}: {e}")
    
    def _discover_interfaces(self):
        """Auto-discover active interfaces by checking running processes/modules."""
        # This would be called by each interface when it starts up
        # For now, we'll just log that interfaces should register themselves
        log_debug("[core_initializer] Interfaces will register themselves when they start")
    
    def register_interface(self, interface_name: str):
        """Register an active interface."""
        log_info(f"[core_initializer] 🔍 Attempting to register interface: {interface_name}")
        if interface_name not in self.active_interfaces:
            self.active_interfaces.append(interface_name)
            log_info(f"[core_initializer] ✅ Interface registered: {interface_name}")

            # Check if the interface exposes action schemas
            interface_instance = INTERFACE_REGISTRY.get(interface_name)
            if interface_instance and hasattr(interface_instance, 'get_supported_actions'):
                log_info(
                    f"[core_initializer] 🔌 Interface {interface_name} supports action registration"
                )
            else:
                log_warning(
                    f"[core_initializer] ⚠️ Interface {interface_name} does not support action registration"
                )

            # Show updated status after interface registration
            self._show_interface_status()
        else:
            log_info(f"[core_initializer] 🔄 Interface {interface_name} is already registered")
    
    def _show_interface_status(self):
        """Show current interface status."""
        if self.active_interfaces:
            interfaces_str = ", ".join(self.active_interfaces)
            log_info(f"📡 Active Interfaces: {interfaces_str}")
        else:
            log_info("📡 Active Interfaces: None")
    
    async def start_pending_async_plugins(self):
        """Start async plugins that were pending due to no event loop."""
        if hasattr(self, '_pending_async_plugins'):
            for plugin_name, instance in self._pending_async_plugins:
                try:
                    await instance.start()
                    log_info(f"[core_initializer] ✅ Started pending async plugin: {plugin_name}")
                except Exception as e:
                    log_error(f"[core_initializer] Error starting pending plugin {plugin_name}: {repr(e)}")
            # Clear the pending list
            self._pending_async_plugins.clear()
            log_info("[core_initializer] All pending async plugins processed")

    async def _build_actions_block(self):
        """Collect and validate action schemas from all plugins and interfaces."""
        from core.core_initializer import PLUGIN_REGISTRY, INTERFACE_REGISTRY

        available_actions = {}

        def _register(action_type: str, owner: str, schema: dict, instr_fn):
            required = schema.get("required_fields", [])
            optional = schema.get("optional_fields", [])
            if not isinstance(required, list) or not isinstance(optional, list):
                raise ValueError(f"Invalid schema for {action_type} in {owner}")

            # Track which component declares each action
            self.interface_actions.setdefault(owner, set()).add(action_type)

            # Simplified structure: no more nested interfaces
            if action_type in available_actions:
                log_debug(f"[core_initializer] Updating existing declaration for {action_type}")
                # Merge required_fields and optional_fields
                existing = available_actions[action_type]
                existing_required = set(existing.get("required_fields", []))
                existing_optional = set(existing.get("optional_fields", []))
                new_required = set(required)
                new_optional = set(optional)
                
                # Merge fields, giving priority to required over optional
                merged_required = list(existing_required.union(new_required))
                merged_optional = list((existing_optional.union(new_optional)) - set(merged_required))
                
                available_actions[action_type] = {
                    "description": schema.get("description", ""),
                    "required_fields": merged_required,
                    "optional_fields": merged_optional,
                }
                log_info(
                    f"[core_initializer] Merged {action_type} fields: required={merged_required}, optional={merged_optional}"
                )
            else:
                available_actions[action_type] = {
                    "description": schema.get("description", ""),
                    "required_fields": required,
                    "optional_fields": optional,
                }

            # Get and add instructions
            instr = instr_fn(action_type) if instr_fn else None
            if instr is None:
                log_warning(f"Missing prompt instructions for {action_type}")
                instr = {}
            if not isinstance(instr, dict):
                log_warning(f"Prompt instructions for {action_type} must be a dict, got {type(instr)}")
                instr = {}
            
            # Add instructions directly to the action
            available_actions[action_type]["instructions"] = instr

        # --- Load action plugins from registry ---
        for name, plugin in PLUGIN_REGISTRY.items():
            if not hasattr(plugin, "get_supported_actions"):
                continue
            try:
                supported = plugin.get_supported_actions()
                if not isinstance(supported, dict):
                    raise ValueError(f"Plugin {name} must return dict from get_supported_actions")
                for act, schema in supported.items():
                    _register(act, name, schema, getattr(plugin, "get_prompt_instructions", None))
            except Exception as e:
                log_error(f"[core_initializer] Error processing plugin {name}: {e}")

        # --- Load interface actions from registry ---
        for name, iface in INTERFACE_REGISTRY.items():
            if not hasattr(iface, "get_supported_actions"):
                continue
            try:
                supported = iface.get_supported_actions()
                if not isinstance(supported, dict):
                    raise ValueError(f"Interface {name} must return dict from get_supported_actions")
                instr_fn = getattr(iface, "get_prompt_instructions", None)
                for act, schema in supported.items():
                    _register(act, name, schema, instr_fn)
            except Exception as e:
                log_error(f"[core_initializer] Error processing interface {name}: {e}")

        # --- Collect static context from registry members ---
        static_context = {}
        for plugin in PLUGIN_REGISTRY.values():
            if hasattr(plugin, "get_static_injection"):
                try:
                    data = plugin.get_static_injection()
                    if inspect.isawaitable(data):
                        data = await data
                    if data:
                        static_context.update(data)
                except Exception as e:
                    log_warning(f"[core_initializer] Errore static injection da plugin {plugin}: {e}")
        for iface in INTERFACE_REGISTRY.values():
            if hasattr(iface, "get_static_injection"):
                try:
                    data = iface.get_static_injection()
                    if inspect.isawaitable(data):
                        data = await data
                    if data:
                        static_context.update(data)
                except Exception as e:
                    log_warning(f"[core_initializer] Errore static injection da interfaccia {iface}: {e}")

        self.actions_block = {
            "available_actions": available_actions,
            "static_context": static_context,
        }
        log_debug(f"[core_initializer] Actions block built with {len(available_actions)} action types, static_context: {list(static_context.keys())}")
    
    def _display_startup_summary(self):
        """Display a comprehensive startup summary."""
        log_info("=" * 60)
        log_info("🚀 Rekku startup summary")
        log_info("=" * 60)

        # --- LLMs ---
        available_llms = list_available_llms()
        if self.active_llm:
            log_info(f"Active LLM: {self.active_llm}")
        else:
            log_info("Active LLM: None")
        if available_llms:
            log_info(f"Available LLMs: {', '.join(sorted(available_llms))}")

        # --- Interfaces and their actions ---
        if self.active_interfaces:
            log_info("Interfaces and actions:")
            for iface in self.active_interfaces:
                actions = sorted(self.interface_actions.get(iface, set()))
                actions_str = ", ".join(actions) if actions else "none"
                log_info(f"  {iface}: {actions_str}")
        else:
            log_info("Interfaces: none")

        # --- Plugins ---
        if self.loaded_plugins:
            plugins_str = ", ".join(sorted(set(self.loaded_plugins)))
            log_info(f"Plugins: {plugins_str}")
        else:
            log_info("Plugins: none")

        # Startup errors
        if self.startup_errors:
            log_warning("⚠️ Startup warnings/errors:")
            for error in self.startup_errors:
                log_warning(f"  - {error}")

        log_info("=" * 60)
        log_info("🎯 System ready for operations")
        log_info("=" * 60)

    def display_startup_summary(self):
        """Public method to log the startup summary on demand."""
        self._display_startup_summary()

    def register_plugin(self, plugin_name: str):
        """Record that a plugin has been loaded and started."""
        if plugin_name not in self.loaded_plugins:
            self.loaded_plugins.append(plugin_name)
            log_info(f"[core_initializer] ✅ Plugin loaded and started: {plugin_name}")
        else:
            log_info(f"[core_initializer] 🔄 Plugin {plugin_name} is already registered")

    def register_action(self, action_type: str, handler: Any) -> None:
        """Expose explicit action registration through the core initializer."""
        register_action(action_type, handler)


# Global instance
core_initializer = CoreInitializer()

# Registry for action handlers (plugins or interfaces)
ACTION_REGISTRY: dict[str, Any] = {}

def register_action(action_type: str, handler: Any) -> None:
    """Register a single action type with its handling object."""
    existing = ACTION_REGISTRY.get(action_type)
    if existing is not None:
        log_warning(
            f"[core_initializer] Action '{action_type}' is already registered. Overwriting."
        )
    ACTION_REGISTRY[action_type] = handler
    log_info(f"[core_initializer] Registered action: {action_type}")

    # Invalidate caches and rebuild action block
    try:
        from core import action_parser

        action_parser._ACTION_HANDLERS = None
        action_parser._INTERFACE_ACTIONS = None
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(core_initializer._build_actions_block())
    except Exception:
        pass

# Global registry for plugin objects
PLUGIN_REGISTRY: dict[str, Any] = {}

def register_plugin(name: str, plugin_obj: Any) -> None:
    """Register a plugin instance and its actions."""
    # Avoid re-registering the same plugin by name
    existing = PLUGIN_REGISTRY.get(name)
    if existing is not None:
        log_debug(f"[core_initializer] Plugin {name} already registered; skipping")
        return

    PLUGIN_REGISTRY[name] = plugin_obj
    log_debug(f"[core_initializer] Registered plugin: {name}")

    # Automatically register supported actions
    if hasattr(plugin_obj, "get_supported_actions"):
        try:
            for act in plugin_obj.get_supported_actions().keys():
                register_action(act, plugin_obj)
        except Exception as e:
            log_error(f"[core_initializer] Failed to register actions for plugin {name}: {e}")

    # Record plugin for startup summary
    core_initializer.register_plugin(name)

    # Reset cached plugin list in action parser
    try:
        from core import action_parser

        action_parser._ACTION_PLUGINS = None
    except Exception:
        pass

# Global registry for interface objects
INTERFACE_REGISTRY: dict[str, Any] = {}

def register_interface(name: str, interface_obj: Any) -> None:
    """Register an interface instance and its actions."""
    INTERFACE_REGISTRY[name] = interface_obj
    log_debug(f"[core_initializer] Registered interface: {name}")

    # Log detailed information about the interface loading
    log_debug(f"[core_initializer] Loading interface: {name}")

    # Automatically register supported actions
    if hasattr(interface_obj, "get_supported_actions"):
        log_debug(f"[core_initializer] Interface '{name}' supports action registration")
        try:
            for act in interface_obj.get_supported_actions().keys():
                register_action(act, interface_obj)
        except Exception as e:
            log_error(f"[core_initializer] Failed to register actions for interface {name}: {e}")

    # Record interface for startup summary
    core_initializer.register_interface(name)

    # Flush any queued trainer notifications for this interface
    try:
        from core.notifier import flush_pending_for_interface
        flush_pending_for_interface(name)
    except Exception:
        pass

# Ensure core actions (like chat_link) are registered after core setup
import core.chat_link_actions  # noqa: F401
