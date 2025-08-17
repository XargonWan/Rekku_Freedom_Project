# core/core_initializer.py

import os
import importlib
import inspect
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
        # Note: This now actually loads and starts action plugins, not just validates them
        
        plugins_dir = Path(__file__).parent.parent / "plugins"
        
        if not plugins_dir.exists():
            log_warning("[core_initializer] No plugins directory found")
            return
        
        # Find all *_plugin.py files
        plugin_files = list(plugins_dir.glob("*_plugin.py"))
        
        for plugin_file in plugin_files:
            plugin_name = plugin_file.stem.replace("_plugin", "")
            
            # Skip __init__.py and other non-plugin files
            if plugin_name.startswith("_"):
                continue
                
            try:
                # Import and instantiate the plugin
                import importlib
                import asyncio
                module = importlib.import_module(f"plugins.{plugin_name}_plugin")
                
                if hasattr(module, "PLUGIN_CLASS"):
                    plugin_class = getattr(module, "PLUGIN_CLASS")
                    # Basic validation that it's a proper plugin class
                    if hasattr(plugin_class, "get_supported_action_types") or hasattr(plugin_class, "get_supported_actions"):
                        try:
                            # Create instance and start it
                            instance = plugin_class()
                            
                            # Start the plugin if it has a start method
                            if hasattr(instance, "start"):
                                try:
                                    if asyncio.iscoroutinefunction(instance.start):
                                        # Try to get the running loop and schedule start
                                        try:
                                            loop = asyncio.get_running_loop()
                                            if loop and loop.is_running():
                                                loop.create_task(instance.start())
                                                log_info(f"[core_initializer] Started async plugin: {plugin_name}")
                                            else:
                                                log_warning(f"[core_initializer] No running loop for async plugin: {plugin_name}")
                                                # Store for later startup
                                                if not hasattr(self, '_pending_async_plugins'):
                                                    self._pending_async_plugins = []
                                                self._pending_async_plugins.append((plugin_name, instance))
                                        except RuntimeError:
                                            log_warning(f"[core_initializer] No event loop for async plugin: {plugin_name}")
                                            # Store for later startup
                                            if not hasattr(self, '_pending_async_plugins'):
                                                self._pending_async_plugins = []
                                            self._pending_async_plugins.append((plugin_name, instance))
                                    else:
                                        instance.start()
                                        log_info(f"[core_initializer] Started sync plugin: {plugin_name}")
                                except Exception as e:
                                    log_error(f"[core_initializer] Error starting plugin {plugin_name}: {repr(e)}")
                            else:
                                log_debug(f"[core_initializer] Plugin {plugin_name} has no start method")
                                    
                            self.loaded_plugins.append(plugin_name)
                            log_info(f"[core_initializer] ✅ Plugin loaded and started: {plugin_name}")
                        except Exception as e:
                            log_error(f"[core_initializer] Failed to start plugin {plugin_name}: {repr(e)}")
                            self.startup_errors.append(f"Plugin {plugin_name}: {e}")
                    else:
                        log_warning(f"[core_initializer] ⚠️ Plugin {plugin_name} doesn't implement action interface")
                        self.startup_errors.append(f"Plugin {plugin_name}: Missing action interface")
                else:
                    log_warning(f"[core_initializer] ⚠️ Plugin {plugin_name} missing PLUGIN_CLASS")
                    self.startup_errors.append(f"Plugin {plugin_name}: Missing PLUGIN_CLASS")
                    
            except Exception as e:
                log_warning(f"[core_initializer] ⚠️ Failed to load plugin {plugin_name}: {e}")
                self.startup_errors.append(f"Plugin {plugin_name}: {e}")
    
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
        from core.action_parser import _load_action_plugins

        available_actions = {}

        def _register(action_type: str, iface: str, schema: dict, instr_fn):
            required = schema.get("required_fields", [])
            optional = schema.get("optional_fields", [])
            if not isinstance(required, list) or not isinstance(optional, list):
                raise ValueError(f"Invalid schema for {action_type} in {iface}")

            # Track which interface declares each action
            self.interface_actions.setdefault(iface, set()).add(action_type)

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

        # --- Load action plugins ---
        try:
            for plugin in _load_action_plugins():
                if not hasattr(plugin, "get_supported_actions"):
                    continue
                iface = getattr(
                    plugin.__class__, "get_interface_id", lambda: plugin.__class__.__name__.lower()
                )()
                supported = plugin.get_supported_actions()
                if not isinstance(supported, dict):
                    raise ValueError(f"Plugin {iface} must return dict from get_supported_actions")
                for act, schema in supported.items():
                    _register(act, iface, schema, getattr(plugin, "get_prompt_instructions", None))
        except Exception as e:
            log_error(f"[core_initializer] Failed loading plugin actions: {e}")
            self.startup_errors.append(str(e))

        # --- Load interface classes ---
        interface_dir = Path(__file__).parent.parent / "interface"
        for file in interface_dir.glob("*.py"):
            if file.name.startswith("_") or file.name.endswith(".disabled"):
                continue
            mod_name = f"interface.{file.stem}"
            try:
                module = importlib.import_module(mod_name)
            except Exception as e:
                log_warning(f"[core_initializer] Could not import {mod_name}: {e}")
                continue
            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if not hasattr(obj, "get_supported_actions"):
                    continue
                iface = getattr(obj, "get_interface_id", lambda: obj.__name__.lower())()
                try:
                    supported = obj.get_supported_actions()
                    if not isinstance(supported, dict):
                        raise ValueError(f"Interface {iface} must return dict from get_supported_actions")
                    instr_fn = getattr(obj, "get_prompt_instructions", None)
                    for act, schema in supported.items():
                        _register(act, iface, schema, instr_fn)
                except Exception as e:
                    log_error(f"[core_initializer] Error processing interface {iface}: {e}")

        # --- Aggrega dati statici dai plugin/interfacce ---
        static_context = {}
        for plugin in _load_action_plugins():
            if hasattr(plugin, "get_static_injection"):
                try:
                    data = plugin.get_static_injection()
                    if inspect.isawaitable(data):
                        data = await data
                    if data:
                        static_context.update(data)
                except Exception as e:
                    log_warning(f"[core_initializer] Errore static injection da plugin {plugin}: {e}")
        # Interfacce
        interface_dir = Path(__file__).parent.parent / "interface"
        for file in interface_dir.glob("*.py"):
            if file.name.startswith("_") or file.name.endswith(".disabled"):
                continue
            mod_name = f"interface.{file.stem}"
            try:
                module = importlib.import_module(mod_name)
            except Exception:
                continue
            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if hasattr(obj, "get_static_injection"):
                    try:
                        data = obj.get_static_injection()
                        if inspect.isawaitable(data):
                            data = await data
                        if data:
                            static_context.update(data)
                    except Exception as e:
                        log_warning(f"[core_initializer] Errore static injection da interfaccia {obj}: {e}")

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

    def register_action(self, name: str, instance: Any):
        """Register a plugin or interface action with the core system."""
        if name in self.actions_block["available_actions"]:
            log_warning(f"[core_initializer] Action '{name}' is already registered. Overwriting.")
        
        self.actions_block["available_actions"][name] = instance
        log_info(f"[core_initializer] Registered action: {name}")


# Global instance
core_initializer = CoreInitializer()

# Global registry for interface objects
INTERFACE_REGISTRY: dict[str, Any] = {}

def register_interface(name: str, interface_obj: Any) -> None:
    """Register an interface instance for later retrieval."""
    INTERFACE_REGISTRY[name] = interface_obj
    log_debug(f"[core_initializer] Registered interface: {name}")

    # Log detailed information about the interface loading
    log_debug(f"[core_initializer] Loading interface: {name}")

    # Check if the interface provides action schemas
    if hasattr(interface_obj, 'get_supported_actions'):
        log_debug(f"[core_initializer] Interface '{name}' supports action registration")

    # Reset cached interface-action mapping in action parser
    try:
        from core import action_parser

        action_parser._INTERFACE_ACTIONS = None
    except Exception:
        pass
