# core/core_initializer.py

import os
import importlib
import inspect
import asyncio
import threading
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
        self._summary_displayed = False  # Flag to prevent duplicate summaries
    
    async def initialize_all(self, notify_fn=None):
        """Initialize all Rekku components in the correct order."""
        log_info("🚀 Initializing Rekku core components...")

        # Don't reset loaded_plugins as they may have been registered during import
        # Only reset interface state for fresh initialization  
        self.interface_actions = {}
        self.actions_block = {"available_actions": {}}
        
        log_debug(f"[core_initializer] Starting with {len(self.loaded_plugins)} pre-registered plugins: {self.loaded_plugins}")

        # 0. Initialize registries
        self._initialize_registries()

        # 1. Load LLM engine
        await self._load_llm_engine(notify_fn)

        # 2. Load generic plugins (this may load additional plugins)
        self._load_plugins()
        
        # 2.5. Auto-register validation rules from loaded components
        self._register_component_validation_rules()
        
        # 3. Load core actions (like chat_link) if not already loaded
        self._ensure_core_actions()
        
        await self._build_actions_block()

        # 4. Auto-discover active interfaces
        self._discover_interfaces()
        
        # Note: Startup summary will be displayed by main.py after all interfaces are started

        return True
    
    def _initialize_registries(self):
        """Initialize the core registries."""
        try:
            # Initialize LLM registry
            from core.llm_registry import register_default_engines
            register_default_engines()
            log_debug("[core_initializer] LLM registry initialized")
            
            # The interfaces registry is initialized by each interface when it starts
            log_debug("[core_initializer] Registries initialized successfully")
        except Exception as e:
            log_error(f"[core_initializer] Failed to initialize registries: {e}", e)
            self.startup_errors.append(f"Registry initialization failed: {e}")

    def _configure_trainer_ids(self):
        """Configure trainer IDs from environment configuration."""
        from core.interfaces_registry import get_interface_registry
        from core.config import TRAINER_IDS, get_trainer_id
        
        registry = get_interface_registry()
        
        # Set trainer IDs from configuration
        for interface_name, trainer_id in TRAINER_IDS.items():
            registry.set_trainer_id(interface_name, trainer_id)
            log_debug(f"[core_initializer] Configured trainer ID {trainer_id} for {interface_name}")

    async def _load_llm_engine(self, notify_fn=None):
        """Load the active LLM engine."""
        try:
            self.active_llm = await get_active_llm()
            
            # Import here to avoid circular imports
            from core.plugin_instance import load_plugin
            await load_plugin(self.active_llm, notify_fn=notify_fn)
            
            # Verify plugin was loaded successfully
            from core.plugin_instance import plugin
            if plugin is None:
                log_error(f"[core_initializer] Plugin {self.active_llm} failed to load!")
                self.startup_errors.append(f"Plugin {self.active_llm} failed to load")
            else:
                log_debug(f"[core_initializer] Plugin {self.active_llm} loaded successfully: {plugin.__class__.__name__}")
            
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

            # After registering, rebuild actions to expose interface capabilities
            try:
                _schedule_rebuild_actions(self)
            except Exception as e:  # pragma: no cover - defensive
                log_error(
                    f"[core_initializer] Error scheduling actions rebuild for {interface_name}: {e}"
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

    async def refresh_actions_block(self) -> None:
        """Public helper to rebuild the actions block.

        Ensures recently registered plugins or interfaces expose their
        actions immediately to the rest of the system.
        """
        await self._build_actions_block()
    
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
                log_debug(f"Missing prompt instructions for {action_type}")
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
                except TypeError:
                    # Plugin requires parameters; skip during startup
                    continue
                except Exception as e:
                    log_warning(f"[core_initializer] Errore static injection da plugin {plugin}: {e}")
                    continue
                if inspect.isawaitable(data):
                    data = await data
                if data:
                    static_context.update(data)
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
        # Prevent duplicate summaries
        if self._summary_displayed:
            log_debug("[core_initializer] Startup summary already displayed, skipping")
            return
        
        self._summary_displayed = True
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

        # --- Plugins and their actions ---
        if self.loaded_plugins:
            log_info("Plugins and actions:")
            for plugin in sorted(set(self.loaded_plugins)):
                actions = sorted(self.interface_actions.get(plugin, set()))
                actions_str = ", ".join(actions) if actions else "none"
                log_info(f"  {plugin}: {actions_str}")
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
        log_debug(f"[core_initializer] Instance register_plugin called for: {plugin_name}")
        if plugin_name not in self.loaded_plugins:
            self.loaded_plugins.append(plugin_name)
            log_info(f"[core_initializer] ✅ Plugin loaded and started: {plugin_name}")
        else:
            log_info(f"[core_initializer] 🔄 Plugin {plugin_name} is already registered")
        log_debug(f"[core_initializer] Current loaded_plugins: {self.loaded_plugins}")

    def register_action(self, action_type: str, handler: Any) -> None:
        """Expose explicit action registration through the core initializer."""
        register_action(action_type, handler)

    def _register_component_validation_rules(self):
        """Register validation rules from loaded components."""
        try:
            from core.component_auto_registration import auto_register_all_components
            auto_register_all_components()
            log_debug("[core_initializer] Component validation rules registered")
        except Exception as e:
            log_error(f"[core_initializer] Failed to register component validation rules: {e}")
            self.startup_errors.append(f"Component validation registration failed: {e}")

    def _ensure_core_actions(self):
        """Ensure core actions like chat_link are loaded exactly once."""
        if "chat_link" not in PLUGIN_REGISTRY:
            try:
                # Import chat_link_actions to trigger registration
                import core.chat_link_actions  # noqa: F401
                log_debug("[core_initializer] Core chat_link actions loaded")
            except Exception as e:
                log_error(f"[core_initializer] Failed to load core chat_link actions: {e}")
                self.startup_errors.append(f"Core actions error: {e}")


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

    # Invalidate caches - but don't automatically rebuild to avoid loops
    try:
        from core import action_parser

        action_parser._ACTION_HANDLERS = None
        action_parser._INTERFACE_ACTIONS = None
        # Don't auto-rebuild here to prevent infinite loops
        # The rebuild will happen when _build_actions_block() is explicitly called
    except Exception:
        pass

# Global registry for plugin objects
PLUGIN_REGISTRY: dict[str, Any] = {}

def register_plugin(name: str, plugin_obj: Any) -> None:
    """Register a plugin instance and its actions."""
    log_debug(f"[core_initializer] Global register_plugin called for: {name}")
    
    # Avoid re-registering the same plugin by name
    existing = PLUGIN_REGISTRY.get(name)
    if existing is not None:
        log_debug(f"[core_initializer] Plugin {name} already registered; skipping")
        return

    PLUGIN_REGISTRY[name] = plugin_obj
    log_debug(f"[core_initializer] Registered plugin in PLUGIN_REGISTRY: {name}")

    # Automatically register supported actions
    if hasattr(plugin_obj, "get_supported_actions"):
        try:
            supported_actions = plugin_obj.get_supported_actions()
            if isinstance(supported_actions, dict):
                for act in supported_actions.keys():
                    register_action(act, plugin_obj)
            else:
                log_warning(f"[core_initializer] Plugin {name} get_supported_actions() returned non-dict: {type(supported_actions)}")
        except Exception as e:
            log_error(f"[core_initializer] Failed to register actions for plugin {name}: {e}")

    # Record plugin for startup summary
    log_debug(f"[core_initializer] Calling core_initializer.register_plugin({name})")
    core_initializer.register_plugin(name)

    # Reset cached plugin list in action parser
    try:
        from core import action_parser

        action_parser._ACTION_PLUGINS = None
    except Exception:
        pass

    # Rebuild actions block to include new plugin's actions
    try:
        import asyncio
        if asyncio.get_event_loop().is_running():
            # If event loop is running, schedule the refresh
            asyncio.create_task(core_initializer.refresh_actions_block())
        else:
            # If no event loop, run it synchronously
            asyncio.run(core_initializer.refresh_actions_block())
        log_debug(f"[core_initializer] Actions block refreshed after registering plugin {name}")
    except Exception as e:
        log_warning(f"[core_initializer] Failed to refresh actions block after plugin {name} registration: {e}")

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

# NOTE: core actions like chat_link are registered automatically when imported
# by other modules that need them, avoiding circular import issues

# Global variables for debounced rebuild
_ACTION_REBUILD_DEBOUNCE_SEC = 0.8
_action_rebuild_timer = None

def _schedule_rebuild_actions(core_init_instance):
    """Schedule a debounced rebuild of the actions block."""
    global _action_rebuild_timer
    if _action_rebuild_timer:
        _action_rebuild_timer.cancel()
    _action_rebuild_timer = threading.Timer(_ACTION_REBUILD_DEBOUNCE_SEC, lambda: asyncio.run(core_init_instance._build_actions_block()))
    _action_rebuild_timer.start()
