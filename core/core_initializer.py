# core/core_initializer.py

import os
import importlib
from pathlib import Path
from core.logging_utils import log_info, log_error, log_warning, log_debug
from core.config import get_active_llm


class CoreInitializer:
    """Centralizes the initialization of all Rekku components."""
    
    def __init__(self):
        self.loaded_plugins = []
        self.active_interfaces = []
        self.active_llm = None
        self.startup_errors = []
    
    async def initialize_all(self, notify_fn=None):
        """Initialize all Rekku components in the correct order."""
        log_info("🚀 Initializing Rekku core components...")
        
        # 1. Load LLM engine
        await self._load_llm_engine(notify_fn)
        
        # 2. Load generic plugins
        self._load_plugins()
        
        # 3. Auto-discover active interfaces
        self._discover_interfaces()
        
        # 4. Final system status report
        self._display_startup_summary()
        
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
        if interface_name not in self.active_interfaces:
            self.active_interfaces.append(interface_name)
            log_info(f"[core_initializer] ✅ Interface registered: {interface_name}")
            
            # Show updated status after interface registration
            self._show_interface_status()
    
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
    
    def _display_startup_summary(self):
        """Display a comprehensive startup summary."""
        log_info("=" * 60)
        log_info("🧞‍♀️ Rekku is online!")
        log_info("=" * 60)
        
        # Active LLM
        if self.active_llm:
            log_info(f"Active LLM: {self.active_llm}")
        else:
            log_info("Active LLM: None")
        
        # Loaded Plugins
        if self.loaded_plugins:
            plugins_str = ", ".join(self.loaded_plugins)
            log_info(f"Available Plugins: {plugins_str}")
        else:
            log_info("Available Plugins: None")
        
        # Active Interfaces (will be populated as interfaces start)
        if self.active_interfaces:
            interfaces_str = ", ".join(self.active_interfaces)
            log_info(f"Loaded Interfaces: {interfaces_str}")
        else:
            log_info("Loaded Interfaces: Will be shown as interfaces start up")
        
        # Startup errors
        if self.startup_errors:
            log_warning("⚠️ Startup warnings/errors:")
            for error in self.startup_errors:
                log_warning(f"  - {error}")
        
        log_info("=" * 60)
        log_info("🎯 System ready for operations")
        log_info("=" * 60)


# Global instance
core_initializer = CoreInitializer()
