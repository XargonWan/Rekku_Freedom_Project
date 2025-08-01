# core/action_router.py
"""
New Action Router with Context-Aware Interface Detection.
Replaces the need for explicit 'interface' field in actions.
"""

from typing import Dict, Any, Optional, List, Tuple
from core.logging_utils import log_debug, log_info, log_warning, log_error


class ActionRouter:
    """Smart router that infers interface from context rather than requiring explicit declaration."""
    
    def __init__(self):
        self.interface_registry = {}
        self.plugin_registry = {}
        self.context_map = {}  # Maps context types to default interfaces
        
    def register_interface(self, interface_id: str, interface_instance, supported_actions: List[str]):
        """Register an interface with its supported actions."""
        self.interface_registry[interface_id] = {
            'instance': interface_instance,
            'supported_actions': set(supported_actions)
        }
        log_debug(f"[action_router] Registered interface: {interface_id}")
        
    def register_plugin(self, plugin_id: str, plugin_instance, supported_actions: List[str]):
        """Register a plugin with its supported actions."""
        self.plugin_registry[plugin_id] = {
            'instance': plugin_instance,
            'supported_actions': set(supported_actions)
        }
        log_debug(f"[action_router] Registered plugin: {plugin_id}")
        
    def set_context_mapping(self, context_type: str, default_interface: str):
        """Map a context type to a default interface."""
        self.context_map[context_type] = default_interface
        
    def infer_interface_from_context(self, context: Dict[str, Any], original_message=None) -> str:
        """
        Intelligently infer the interface from context without requiring explicit declaration.
        
        Priority:
        1. Context hint (e.g., 'telegram_context', 'reddit_context')
        2. Original message source
        3. Active session interface
        4. Default fallback
        """
        
        # Method 1: Direct context hint
        for key in context.keys():
            if key.endswith('_context') or key.endswith('_interface'):
                interface_name = key.replace('_context', '').replace('_interface', '')
                if interface_name in self.interface_registry:
                    log_debug(f"[action_router] Interface inferred from context key: {interface_name}")
                    return interface_name
                    
        # Method 2: Original message source
        if original_message:
            if hasattr(original_message, 'chat_id'):
                log_debug("[action_router] Interface inferred from message: telegram")
                return "telegram"
            elif hasattr(original_message, 'subreddit'):
                log_debug("[action_router] Interface inferred from message: reddit")
                return "reddit"
                
        # Method 3: Context type mapping
        context_type = context.get('type', 'unknown')
        if context_type in self.context_map:
            interface = self.context_map[context_type]
            log_debug(f"[action_router] Interface inferred from context type: {interface}")
            return interface
            
        # Method 4: Default fallback
        if 'telegram' in self.interface_registry:
            log_debug("[action_router] Using default interface: telegram")
            return "telegram"
            
        # If all else fails, use the first available interface
        if self.interface_registry:
            fallback = list(self.interface_registry.keys())[0]
            log_warning(f"[action_router] No interface inference possible, using fallback: {fallback}")
            return fallback
            
        raise ValueError("No interfaces available for routing")
        
    def enhance_action_with_interface(self, action: Dict[str, Any], context: Dict[str, Any], original_message=None) -> Dict[str, Any]:
        """
        Enhance an action with the inferred interface, making the explicit field optional.
        """
        action_copy = action.copy()
        
        # If interface is already specified, validate and keep it
        if 'interface' in action_copy:
            specified_interface = action_copy['interface']
            if specified_interface not in self.interface_registry:
                log_warning(f"[action_router] Specified interface '{specified_interface}' not available, inferring instead")
                action_copy['interface'] = self.infer_interface_from_context(context, original_message)
        else:
            # Infer and inject the interface
            inferred_interface = self.infer_interface_from_context(context, original_message)
            action_copy['interface'] = inferred_interface
            log_debug(f"[action_router] Injected interface: {inferred_interface}")
            
        return action_copy
        
    def route_action(self, action: Dict[str, Any], context: Dict[str, Any], original_message=None) -> Tuple[Any, Any]:
        """
        Route an action to the appropriate interface and plugin.
        
        Returns:
            Tuple[interface_instance, plugin_instance]
        """
        
        # Enhance action with interface if needed
        enhanced_action = self.enhance_action_with_interface(action, context, original_message)
        
        action_type = enhanced_action.get('type')
        interface_id = enhanced_action.get('interface')
        
        if not action_type:
            raise ValueError("Action missing 'type' field")
        if not interface_id:
            raise ValueError("Could not determine interface for action")
            
        # Find interface
        interface_info = self.interface_registry.get(interface_id)
        if not interface_info:
            raise ValueError(f"Interface '{interface_id}' not registered")
            
        if action_type not in interface_info['supported_actions']:
            # Try to find a plugin that can handle this action type
            for plugin_id, plugin_info in self.plugin_registry.items():
                if action_type in plugin_info['supported_actions']:
                    log_debug(f"[action_router] Routing {action_type} to plugin: {plugin_id}")
                    return interface_info['instance'], plugin_info['instance']
                    
            raise ValueError(f"No handler found for action type '{action_type}' on interface '{interface_id}'")
            
        log_debug(f"[action_router] Routing {action_type} to interface: {interface_id}")
        return interface_info['instance'], None


# Global router instance
action_router = ActionRouter()
