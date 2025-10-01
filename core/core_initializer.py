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
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class ComponentStatus(Enum):
    """Status of a system component."""
    LOADING = "loading"
    SUCCESS = "success"  
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass 
class ComponentInfo:
    """Information about a system component."""
    name: str
    type: str  # "plugin", "interface", "llm", "core"
    status: ComponentStatus = ComponentStatus.LOADING
    actions: List[str] = field(default_factory=list)
    error: str = ""
    details: str = ""


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
        self._building_actions_block = False  # Flag to prevent infinite rebuild loops
        self._initial_initialization = False  # Flag to indicate we're in initial startup phase
        
        # Component tracking system
        self.components: Dict[str, ComponentInfo] = {}
        self.initialization_completed = False
    
    async def initialize_all(self, notify_fn=None):
        """Initialize all Rekku components in the correct order."""
        log_info("🚀 Initializing Rekku core components...")
        
        # Set flag to prevent plugin auto-registration from triggering refreshes
        self._initial_initialization = True
        log_debug("[core_initializer] Set _initial_initialization=True to prevent auto-refresh loops")
        
        try:
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
            log_debug("[core_initializer] 🔍 About to call _register_component_validation_rules()")
            self._register_component_validation_rules()
            log_debug("[core_initializer] ✅ _register_component_validation_rules() completed")
            
            # 3. Load core actions (like chat_link) if not already loaded
            log_debug("[core_initializer] 🔍 About to call _ensure_core_actions()")
            self._ensure_core_actions()
            log_debug("[core_initializer] ✅ _ensure_core_actions() completed")
            
            # 4. Initialize core persona manager
            log_debug("[core_initializer] 🔍 About to call _initialize_persona_manager()")
            self._initialize_persona_manager()
            log_debug("[core_initializer] ✅ _initialize_persona_manager() completed")
        
            log_debug("[core_initializer] About to call _build_actions_block()")
            try:
                await self._build_actions_block()
                log_debug("[core_initializer] 🎯 CRITICAL: SECOND CALL - _build_actions_block() returned successfully!")
                log_debug("[core_initializer] Actions block build completed")
            except Exception as e:
                log_error(f"[core_initializer] Error in _build_actions_block: {e}")
                import traceback
                log_error(f"[core_initializer] Traceback: {traceback.format_exc()}")
                self.startup_errors.append(f"Actions block build failed: {e}")

            log_info("[core_initializer] 🎯 CHECKPOINT: Actions block completed, proceeding to interface discovery")
            
            # 4. Auto-discover active interfaces
            log_debug("[core_initializer] About to call _discover_interfaces()")
            try:
                self._discover_interfaces()
                log_debug("[core_initializer] Interface discovery completed")
            except Exception as e:
                log_error(f"[core_initializer] Error in _discover_interfaces: {e}")
                self.startup_errors.append(f"Interface discovery failed: {e}")

            # Note: Startup summary will be displayed by main.py after all interfaces are started
            log_info("[core_initializer] Core initialization completed successfully")

            # Mark initialization as completed
            self._initial_initialization = False  # Reset flag - plugins can now trigger auto-refresh
            log_debug("[core_initializer] Set _initial_initialization=False - auto-refresh now allowed")
            self.initialization_completed = True
            log_info("[core_initializer] ✅ All core components initialized successfully")
            
            # Display summary at the end of initialization
            self._display_startup_summary()
            return True
            
        except Exception as e:
            log_error(f"[core_initializer] Error during initialization: {e}")
            self.startup_errors.append(f"Initialization error: {e}")
            # Also reset flag in case of error
            self._initial_initialization = False
            log_debug("[core_initializer] Set _initial_initialization=False (after error)")
            # Display summary even if initialization failed
            self.display_startup_summary()
            return False
    
    def track_component(self, name: str, component_type: str, status: ComponentStatus = ComponentStatus.LOADING, 
                       actions: List[str] = None, error: str = "", details: str = ""):
        """Track the status of a system component."""
        self.components[name] = ComponentInfo(
            name=name,
            type=component_type,
            status=status,
            actions=actions or [],
            error=error,
            details=details
        )
        log_debug(f"[core_initializer] Tracking component {name} ({component_type}): {status.value}")

    def mark_component_success(self, name: str, actions: List[str] = None, details: str = ""):
        """Mark a component as successfully loaded."""
        if name in self.components:
            self.components[name].status = ComponentStatus.SUCCESS
            if actions:
                self.components[name].actions = actions
            if details:
                self.components[name].details = details
        else:
            # Create new component entry
            self.track_component(name, "unknown", ComponentStatus.SUCCESS, actions, details=details)
    
    def mark_component_failed(self, name: str, error: str, details: str = ""):
        """Mark a component as failed to load."""
        if name in self.components:
            self.components[name].status = ComponentStatus.FAILED
            self.components[name].error = error
            if details:
                self.components[name].details = details
        else:
            # Create new component entry
            self.track_component(name, "unknown", ComponentStatus.FAILED, error=error, details=details)

    def get_system_resume(self) -> Dict[str, Any]:
        """Generate a complete system status resume."""
        successful = [c for c in self.components.values() if c.status == ComponentStatus.SUCCESS]
        failed = [c for c in self.components.values() if c.status == ComponentStatus.FAILED]
        loading = [c for c in self.components.values() if c.status == ComponentStatus.LOADING]
        
        total_actions = sum(len(c.actions) for c in successful)
        
        return {
            "total_components": len(self.components),
            "successful": len(successful),
            "failed": len(failed),
            "loading": len(loading),
            "total_actions": total_actions,
            "successful_components": successful,
            "failed_components": failed,
            "loading_components": loading,
            "active_llm": self.active_llm,
            "active_interfaces": self.active_interfaces,
            "startup_errors": self.startup_errors,
            "initialization_completed": self.initialization_completed
        }
    
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
            self.track_component(self.active_llm, "llm", ComponentStatus.LOADING, details="Loading LLM engine")
            
            # Import here to avoid circular imports
            from core.plugin_instance import load_plugin
            await load_plugin(self.active_llm, notify_fn=notify_fn)
            
            # Verify plugin was loaded successfully
            from core.plugin_instance import plugin
            if plugin is None:
                error_msg = f"Plugin {self.active_llm} failed to load"
                log_error(f"[core_initializer] {error_msg}!")
                self.startup_errors.append(error_msg)
                self.mark_component_failed(self.active_llm, error_msg, "LLM plugin initialization failed")
            else:
                log_debug(f"[core_initializer] Plugin {self.active_llm} loaded successfully: {plugin.__class__.__name__}")
                self.mark_component_success(self.active_llm, details=f"LLM engine: {plugin.__class__.__name__}")
            
            log_debug(f"[core_initializer] Active LLM engine loaded: {self.active_llm}")
        except Exception as e:
            error_msg = f"Failed to load active LLM: {repr(e)}"
            log_error(f"[core_initializer] {error_msg}")
            self.startup_errors.append(f"LLM engine error: {e}")
            if hasattr(self, 'active_llm') and self.active_llm:
                self.mark_component_failed(self.active_llm, str(e), "LLM loading exception")
            else:
                self.track_component("unknown_llm", "llm", ComponentStatus.FAILED, error=str(e))
    
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
            
            # Check if the interface exposes action schemas and log them
            interface_instance = INTERFACE_REGISTRY.get(interface_name)
            actions = []
            
            if interface_instance and hasattr(interface_instance, 'get_supported_actions'):
                try:
                    supported_actions = interface_instance.get_supported_actions()
                    if isinstance(supported_actions, dict):
                        actions = list(supported_actions.keys())
                except Exception as e:
                    log_debug(f"[core_initializer] Error getting actions for interface {interface_name}: {e}")
            
            if actions:
                log_info(f"🔌 Interface loaded: {interface_name} - Registered actions: {', '.join(sorted(actions))}")
            else:
                log_info(f"🔌 Interface loaded: {interface_name} - No actions registered")

            # After registering, rebuild actions to expose interface capabilities
            # BUT NOT during initial initialization (to avoid triggering rebuild while already building)
            # DISABLED: This causes infinite loops when interfaces register after initialization
            # TODO: Implement a smarter rebuild mechanism that doesn't re-import modules
            if False and not self._initial_initialization:
                try:
                    _schedule_rebuild_actions(self)
                except Exception as e:  # pragma: no cover - defensive
                    log_error(
                        f"[core_initializer] Error scheduling actions rebuild for {interface_name}: {e}"
                    )
            else:
                log_debug(f"[core_initializer] Skipping actions rebuild for {interface_name} (initial initialization in progress)")

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
        # TEMPORARILY DISABLE FLAG FOR TESTING
        # if self._building_actions_block:
        #     log_debug("[core_initializer] Already building actions block, skipping to prevent loop")
        #     return
            
        log_debug("[core_initializer] Starting _build_actions_block")
            
        self._building_actions_block = True
        log_debug("[core_initializer] Starting _build_actions_block")
        from core.core_initializer import PLUGIN_REGISTRY, INTERFACE_REGISTRY

        available_actions = {}
        log_debug("[core_initializer] Initialized available_actions dict")

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
                merged_optional = list((existing_optional.union(new_optional)) - set(merged_required))                # Keep track of original source, append new sources
                existing_source = existing.get("source", "")
                new_source = f"{existing_source}, {owner}" if existing_source else owner
                
                available_actions[action_type] = {
                    "description": schema.get("description", ""),
                    "required_fields": merged_required,
                    "optional_fields": merged_optional,
                    "source": new_source,
                }
                log_info(
                    f"[core_initializer] Merged {action_type} fields: required={merged_required}, optional={merged_optional}, source={new_source}"
                )
            else:
                available_actions[action_type] = {
                    "description": schema.get("description", ""),
                    "required_fields": required,
                    "optional_fields": optional,
                    "source": owner,
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
        log_debug(f"[core_initializer] Loading actions from {len(PLUGIN_REGISTRY)} plugins: {list(PLUGIN_REGISTRY.keys())}")
        log_debug("[core_initializer] Starting plugin loop")
        for name, plugin in PLUGIN_REGISTRY.items():
            log_debug(f"[core_initializer] Processing plugin: {name}")
            if not hasattr(plugin, "get_supported_actions"):
                log_debug(f"[core_initializer] Plugin {name} does not have get_supported_actions method")
                continue
            try:
                supported = plugin.get_supported_actions()
                if not isinstance(supported, dict):
                    raise ValueError(f"Plugin {name} must return dict from get_supported_actions")
                log_debug(f"[core_initializer] Plugin {name} declares actions: {list(supported.keys())}")
                for act, schema in supported.items():
                    _register(act, name, schema, getattr(plugin, "get_prompt_instructions", None))
            except Exception as e:
                log_error(f"[core_initializer] Error processing plugin {name}: {e}")

        # --- Load interface actions from registry ---
        log_debug("[core_initializer] Starting interface loop")
        for name, iface in INTERFACE_REGISTRY.items():
            log_debug(f"[core_initializer] Processing interface: {name}")
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
        log_debug("[core_initializer] Starting static context collection")
        static_context = {}
        log_debug("[core_initializer] Starting static injection from plugins")
        for plugin in PLUGIN_REGISTRY.values():
            log_debug(f"[core_initializer] Checking static injection for plugin: {plugin.__class__.__name__}")
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
                    try:
                        # Add timeout to prevent hanging
                        data = await asyncio.wait_for(data, timeout=5.0)
                    except asyncio.TimeoutError:
                        log_warning(f"[core_initializer] Timeout waiting for static injection from {plugin.__class__.__name__}")
                        continue
                    except Exception as e:
                        log_warning(f"[core_initializer] Error awaiting static injection from {plugin.__class__.__name__}: {e}")
                        continue
                if data:
                    static_context.update(data)
        for iface in INTERFACE_REGISTRY.values():
            if hasattr(iface, "get_static_injection"):
                try:
                    data = iface.get_static_injection()
                    if inspect.isawaitable(data):
                        try:
                            # Add timeout to prevent hanging  
                            data = await asyncio.wait_for(data, timeout=5.0)
                        except asyncio.TimeoutError:
                            log_warning(f"[core_initializer] Timeout waiting for static injection from {iface.__class__.__name__}")
                            continue
                        except Exception as e:
                            log_warning(f"[core_initializer] Error awaiting static injection from {iface.__class__.__name__}: {e}")
                            continue
                    if data:
                        static_context.update(data)
                except Exception as e:
                    log_warning(f"[core_initializer] Errore static injection da interfaccia {iface}: {e}")

        self.actions_block = {
            "available_actions": available_actions,
            "static_context": static_context,
        }
        log_debug(f"[core_initializer] Actions block built with {len(available_actions)} action types, static_context: {list(static_context.keys())}")
        log_debug(f"[core_initializer] Available action types: {sorted(available_actions.keys())}")
        log_debug("[core_initializer] About to reset _building_actions_block flag")
        
        # Reset the flag
        self._building_actions_block = False
        log_debug("[core_initializer] _building_actions_block flag reset, exiting _build_actions_block()")
    
    def _display_startup_summary(self):
        """Display a comprehensive startup summary."""
        # Prevent duplicate summaries
        if self._summary_displayed:
            log_debug("[core_initializer] Startup summary already displayed, skipping")
            return
        
        self._summary_displayed = True
        
        log_debug("[core_initializer] Starting display_startup_summary")
        
        # Get system resume
        log_debug("[core_initializer] Getting system resume...")
        resume = self.get_system_resume()
        log_debug("[core_initializer] System resume obtained successfully")
        
        log_info("=" * 80)
        log_info("🚀 REKKU FREEDOM PROJECT (RFP) - SYSTEM ONLINE")
        log_info("=" * 80)

        # --- System Status ---
        if resume["initialization_completed"]:
            log_info("✅ RFP initialization completed successfully!")
        else:
            log_info("⚠️  RFP initialization in progress...")
        
        # --- Component Summary ---
        log_info(f"📊 COMPONENT STATUS SUMMARY:")
        log_info(f"   • Total components: {resume['total_components']}")
        log_info(f"   • ✅ Successful: {resume['successful']}")
        log_info(f"   • ❌ Failed: {resume['failed']}")
        log_info(f"   • 🔄 Loading: {resume['loading']}")
        log_info(f"   • ⚡ Total actions available: {resume['total_actions']}")
        
        # --- LLM Engine ---
        available_llms = list_available_llms()
        if resume["active_llm"]:
            llm_status = "✅" if any(c.name == resume["active_llm"] and c.status == ComponentStatus.SUCCESS 
                                  for c in resume["successful_components"]) else "❌"
            log_info(f"🧠 Active LLM Engine: {llm_status} {resume['active_llm']}")
        else:
            log_info("🧠 Active LLM Engine: ❌ None")
        if available_llms:
            log_info(f"🧠 Available LLM Engines: {', '.join(sorted(available_llms))}")

        # --- Successful Components ---
        if resume["successful_components"]:
            log_info("✅ SUCCESSFUL COMPONENTS:")
            # Group by type
            by_type = {}
            for comp in resume["successful_components"]:
                if comp.type not in by_type:
                    by_type[comp.type] = []
                by_type[comp.type].append(comp)
            
            for comp_type, components in sorted(by_type.items()):
                type_emoji = {"plugin": "🧩", "interface": "🔌", "llm": "🧠", "core": "⚙️"}.get(comp_type, "📦")
                log_info(f"   {type_emoji} {comp_type.upper()}S ({len(components)}):")
                for comp in sorted(components, key=lambda x: x.name):
                    if comp.actions:
                        actions_list = ', '.join(sorted(comp.actions))
                        log_info(f"      ├─ {comp.name}: {actions_list}")
                    else:
                        log_info(f"      ├─ {comp.name}: no actions")
        
        # --- Failed Components ---
        if resume["failed_components"]:
            log_info("❌ FAILED COMPONENTS:")
            for comp in sorted(resume["failed_components"], key=lambda x: x.name):
                log_info(f"   ├─ {comp.name} ({comp.type}): {comp.error}")
                if comp.details:
                    log_info(f"   │  └─ {comp.details}")
        
        # --- Loading Components ---
        if resume["loading_components"]:
            log_info("🔄 COMPONENTS STILL LOADING:")
            for comp in sorted(resume["loading_components"], key=lambda x: x.name):
                log_info(f"   ├─ {comp.name} ({comp.type})")
                if comp.details:
                    log_info(f"   │  └─ {comp.details}")

        # --- All available actions by category ---
        log_debug("[core_initializer] Checking available actions...")
        if self.actions_block.get("available_actions"):
            log_info("⚡ AVAILABLE SYSTEM ACTIONS:")
            action_categories = {}
            
            log_debug(f"[core_initializer] Processing {len(self.actions_block['available_actions'])} actions...")
            # Group actions by source (interface/plugin)
            for action_type, action_data in self.actions_block["available_actions"].items():
                log_debug(f"[core_initializer] Processing action: {action_type}")
                source = action_data.get("source", "core")
                if source not in action_categories:
                    action_categories[source] = []
                action_categories[source].append(action_type)
            
            log_debug(f"[core_initializer] Action categories: {list(action_categories.keys())}")
            for source, actions in sorted(action_categories.items()):
                log_info(f"   ├─ {source} ({len(actions)} actions)")
                for action in sorted(actions):
                    log_info(f"   │  ├─ {action}")
        else:
            log_debug("[core_initializer] No available_actions in actions_block")

        # Startup errors
        if self.startup_errors:
            log_warning("⚠️  STARTUP WARNINGS/ERRORS:")
            for error in self.startup_errors:
                log_warning(f"   - {error}")

        log_info("=" * 80)
        log_info("🎯 SYSTEM FULLY INITIALIZED AND READY FOR OPERATIONS")
        log_info("=" * 80)
        
        log_debug("[core_initializer] Startup summary completed successfully")

    def display_startup_summary(self):
        """Public method to log the startup summary on demand."""
        self._display_startup_summary()

    def register_plugin(self, plugin_name: str):
        """Record that a plugin has been loaded and started."""
        log_debug(f"[core_initializer] Instance register_plugin called for: {plugin_name}")
        
        if plugin_name not in self.loaded_plugins:
            self.loaded_plugins.append(plugin_name)
            
            # Check if the plugin exposes action schemas and log them
            from core.core_initializer import PLUGIN_REGISTRY
            plugin_obj = PLUGIN_REGISTRY.get(plugin_name)
            actions = []
            
            try:
                if plugin_obj and hasattr(plugin_obj, "get_supported_actions"):
                    supported_actions = plugin_obj.get_supported_actions()
                    if isinstance(supported_actions, dict):
                        actions = list(supported_actions.keys())
                
                # Track successful plugin loading
                self.track_component(plugin_name, "plugin", ComponentStatus.SUCCESS, actions, 
                                   details=f"Plugin with {len(actions)} actions" if actions else "Plugin with no actions")
                
                if actions:
                    log_info(f"🧩 Plugin loaded: {plugin_name} - Registered actions: {', '.join(sorted(actions))}")
                else:
                    log_info(f"🧩 Plugin loaded: {plugin_name} - No actions registered")
            
            except Exception as e:
                error_msg = f"Error getting actions: {e}"
                log_debug(f"[core_initializer] Error getting actions for {plugin_name}: {e}")
                self.mark_component_failed(plugin_name, error_msg, "Plugin loaded but action retrieval failed")
                log_info(f"🧩 Plugin loaded: {plugin_name} - Error getting actions: {e}")
        
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

    def _initialize_persona_manager(self):
        """Initialize the persona manager as a core component."""
        try:
            # Import the module to trigger auto-initialization
            import core.persona_manager  # This will trigger _auto_initialize()
            
            # Get the instance to verify initialization
            from core.persona_manager import get_persona_manager
            persona_manager = get_persona_manager()
            
            if persona_manager:
                log_info("[core_initializer] ✅ Persona Manager initialized successfully")
                
                # Initialize persona asynchronously (load default persona)
                try:
                    import asyncio
                    asyncio.create_task(persona_manager.async_init())
                    log_debug("[core_initializer] Persona async initialization scheduled")
                except Exception as init_e:
                    log_warning(f"[core_initializer] Persona async init failed: {init_e}")
            else:
                log_warning("[core_initializer] ⚠️ Failed to initialize Persona Manager")
                self.startup_errors.append("Persona Manager initialization failed")
        except Exception as e:
            log_error(f"[core_initializer] ❌ Error initializing Persona Manager: {e}")
            self.startup_errors.append(f"Persona Manager error: {e}")


# Global instance
core_initializer = CoreInitializer()

# Registry for action handlers (plugins or interfaces)
ACTION_REGISTRY: dict[str, Any] = {}

def register_action(action_type: str, handler: Any) -> None:
    """Register a single action type with its handling object."""
    existing = ACTION_REGISTRY.get(action_type)
    
    # Special handling for static_inject - allow multiple handlers
    if action_type == "static_inject":
        if existing is not None:
            # If there's already a handler, create a list or extend existing list
            if isinstance(existing, list):
                existing.append(handler)
                log_debug(f"[core_initializer] Added {handler.__class__.__name__} to existing static_inject handlers: {[h.__class__.__name__ for h in existing]}")
            else:
                # Convert single handler to list and add new one
                ACTION_REGISTRY[action_type] = [existing, handler]
                log_debug(f"[core_initializer] Converted static_inject to multi-handler: [{existing.__class__.__name__}, {handler.__class__.__name__}]")
        else:
            # First handler for static_inject
            ACTION_REGISTRY[action_type] = handler
            log_debug(f"[core_initializer] Registered first static_inject handler: {handler.__class__.__name__}")
    else:
        # Normal handling for other actions
        if existing is not None:
            log_warning(
                f"[core_initializer] Action '{action_type}' is already registered by {existing.__class__.__name__}. Overwriting with {handler.__class__.__name__}."
            )
        ACTION_REGISTRY[action_type] = handler
        log_debug(f"[core_initializer] Registered action: {action_type} -> {handler.__class__.__name__}")

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

    # Rebuild actions block to include new plugin's actions (but only if not already building)
    try:
        # Skip auto-refresh during initial initialization - it will be done at the end
        if core_initializer._initial_initialization:
            log_debug(f"[core_initializer] Skipping auto-refresh for plugin {name} during initial initialization")
        elif not core_initializer._building_actions_block:
            import asyncio
            if asyncio.get_event_loop().is_running():
                # If event loop is running, schedule the refresh
                asyncio.create_task(core_initializer.refresh_actions_block())
            else:
                # If no event loop, run it synchronously
                asyncio.run(core_initializer.refresh_actions_block())
            log_debug(f"[core_initializer] Actions block refreshed after registering plugin {name}")
        else:
            # If already building, schedule a retry after a short delay
            log_debug(f"[core_initializer] Actions block building in progress, scheduling retry for plugin {name}")
            import asyncio
            async def retry_refresh():
                await asyncio.sleep(0.1)  # Short delay to allow current build to complete
                try:
                    await core_initializer.refresh_actions_block()
                    log_debug(f"[core_initializer] Actions block refresh completed after retry for plugin {name}")
                except Exception as e:
                    log_warning(f"[core_initializer] Failed to refresh actions block after retry for plugin {name}: {e}")
            
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(retry_refresh())
            else:
                # This shouldn't happen in normal operation, but handle it
                asyncio.run(retry_refresh())
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

