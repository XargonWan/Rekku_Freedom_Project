# core/llm_registry.py

"""
Registry to manage LLM engines without hardcoded dependencies.
"""

import importlib
from typing import Dict, Any, Optional, List
from core.logging_utils import log_debug, log_info, log_warning, log_error

class LLMRegistry:
    """Central registry for all LLM engines."""
    
    def __init__(self):
        self._engines: Dict[str, Any] = {}
        self._engine_modules: Dict[str, str] = {}
        
    def register_engine_module(self, name: str, module_path: str):
        """Register an LLM engine module path."""
        self._engine_modules[name] = module_path
        log_debug(f"[llm_registry] Registered engine module: {name} -> {module_path}")
    
    def get_default_engine(self) -> str:
        """Get the default LLM engine name."""
        available = self.get_available_engines()
        if "manual" in available:
            return "manual"
        elif available:
            return available[0]
        else:
            raise ValueError("No LLM engines are registered")
    
    def get_available_engines(self) -> List[str]:
        """Get list of available engine names."""
        return list(self._engine_modules.keys())
    
    def load_engine(self, name: str, notify_fn=None) -> Any:
        """Load an LLM engine by name."""
        if name not in self._engine_modules:
            raise ValueError(f"Unknown LLM engine: {name}")
        
        module_path = self._engine_modules[name]
        
        try:
            module = importlib.import_module(module_path)
            log_debug(f"[llm_registry] Module {module_path} imported successfully.")
        except ModuleNotFoundError as e:
            log_error(f"[llm_registry] ❌ Unable to import {module_path}: {e}", e)
            raise ValueError(f"Invalid LLM plugin: {name}")

        if not hasattr(module, "PLUGIN_CLASS"):
            raise ValueError(f"Plugin `{name}` does not define `PLUGIN_CLASS`.")

        plugin_class = getattr(module, "PLUGIN_CLASS")

        try:
            plugin_args = plugin_class.__init__.__code__.co_varnames
            if "notify_fn" in plugin_args:
                plugin_instance = plugin_class(notify_fn=notify_fn)
            else:
                plugin_instance = plugin_class()
        except Exception as e:
            log_error(f"[llm_registry] ❌ Error during plugin initialization: {e}", e)
            raise

        self._engines[name] = plugin_instance
        log_debug(f"[llm_registry] Engine initialized: {plugin_instance.__class__.__name__}")
        
        return plugin_instance
    
    def get_engine(self, name: str) -> Optional[Any]:
        """Get a loaded engine instance."""
        return self._engines.get(name)
    
    def unload_engine(self, name: str):
        """Unload an engine instance."""
        if name in self._engines:
            del self._engines[name]
            log_debug(f"[llm_registry] Unloaded engine: {name}")

# Global registry instance
_llm_registry = LLMRegistry()

def get_llm_registry() -> LLMRegistry:
    """Get the global instance of the LLM registry."""
    return _llm_registry

def register_default_engines():
    """Register the default LLM engines."""
    registry = get_llm_registry()
    
    # Register standard LLM engines
    registry.register_engine_module("openai_chatgpt", "llm_engines.openai_chatgpt")
    registry.register_engine_module("selenium_chatgpt", "llm_engines.selenium_chatgpt")
    registry.register_engine_module("google_cli", "llm_engines.google_cli")
    registry.register_engine_module("manual", "llm_engines.manual")
    
    log_debug("[llm_registry] Default engines registered")
