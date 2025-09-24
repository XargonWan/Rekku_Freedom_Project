# core/validation_registry.py
"""Central registry for component validation rules."""

from typing import Dict, List, Set, Any, Optional
from core.logging_utils import log_debug, log_warning, log_error


class ValidationRule:
    """Represents a validation rule for an action type."""
    
    def __init__(self, action_type: str, required_fields: List[str] = None, 
                 custom_validator: callable = None, component_name: str = None):
        self.action_type = action_type
        self.required_fields = required_fields or []
        self.custom_validator = custom_validator
        self.component_name = component_name or "unknown"
    
    def validate(self, payload: Dict[str, Any]) -> List[str]:
        """Validate payload against this rule. Returns list of error messages."""
        errors = []
        
        # Check required fields
        for field in self.required_fields:
            if field not in payload:
                errors.append(f"Missing required field '{field}' for action '{self.action_type}'")
            elif payload[field] is None or payload[field] == "":
                errors.append(f"Field '{field}' cannot be empty for action '{self.action_type}'")
        
        # Run custom validator if provided
        if self.custom_validator and callable(self.custom_validator):
            try:
                custom_errors = self.custom_validator(payload)
                if isinstance(custom_errors, list):
                    errors.extend(custom_errors)
                elif isinstance(custom_errors, str):
                    errors.append(custom_errors)
            except Exception as e:
                log_warning(f"Custom validator for {self.action_type} failed: {e}")
                errors.append(f"Custom validation failed for action '{self.action_type}'")
        
        return errors


class ValidationRegistry:
    """Central registry for component validation rules."""
    
    def __init__(self):
        self._rules: Dict[str, List[ValidationRule]] = {}
        self._registered_components: Set[str] = set()
    
    def register_component_rules(self, component_name: str, rules: List[ValidationRule]):
        """Register validation rules for a component."""
        log_debug(f"[ValidationRegistry] Registering {len(rules)} rules for component '{component_name}'")
        
        self._registered_components.add(component_name)
        
        for rule in rules:
            rule.component_name = component_name
            action_type = rule.action_type
            
            if action_type not in self._rules:
                self._rules[action_type] = []
            
            self._rules[action_type].append(rule)
            log_debug(f"[ValidationRegistry] Registered rule for action '{action_type}' from component '{component_name}'")
    
    def unregister_component(self, component_name: str):
        """Remove all rules for a component."""
        if component_name not in self._registered_components:
            return
        
        log_debug(f"[ValidationRegistry] Unregistering component '{component_name}'")
        
        # Remove all rules from this component
        for action_type in list(self._rules.keys()):
            self._rules[action_type] = [
                rule for rule in self._rules[action_type] 
                if rule.component_name != component_name
            ]
            # Remove empty action types
            if not self._rules[action_type]:
                del self._rules[action_type]
        
        self._registered_components.discard(component_name)
    
    def get_validation_rules(self, action_type: str) -> List[ValidationRule]:
        """Get all validation rules for an action type."""
        return self._rules.get(action_type, [])
    
    def validate_action_payload(self, action_type: str, payload: Dict[str, Any]) -> List[str]:
        """Validate payload against all registered rules for the action type."""
        errors = []
        rules = self.get_validation_rules(action_type)
        
        for rule in rules:
            rule_errors = rule.validate(payload)
            errors.extend(rule_errors)
        
        return errors
    
    def get_supported_action_types(self) -> Set[str]:
        """Get all action types that have validation rules."""
        return set(self._rules.keys())
    
    def get_registered_components(self) -> Set[str]:
        """Get all registered component names."""
        return self._registered_components.copy()
    
    def clear(self):
        """Clear all registered rules (for testing)."""
        self._rules.clear()
        self._registered_components.clear()


# Global validation registry instance
_validation_registry = ValidationRegistry()


def get_validation_registry() -> ValidationRegistry:
    """Get the global validation registry instance."""
    return _validation_registry


def register_component_validation_rules(component_name: str, action_rules: Dict[str, Dict[str, Any]]):
    """Helper function to register validation rules from component JSON configuration.
    
    Args:
        component_name: Name of the component
        action_rules: Dictionary mapping action_type to rule configuration
                     Example: {
                         "send_message": {
                             "required_fields": ["text", "chat_id"],
                             "custom_validator": some_function
                         }
                     }
    """
    rules = []
    
    for action_type, rule_config in action_rules.items():
        required_fields = rule_config.get("required_fields", [])
        custom_validator = rule_config.get("custom_validator")
        
        rule = ValidationRule(
            action_type=action_type,
            required_fields=required_fields,
            custom_validator=custom_validator,
            component_name=component_name
        )
        rules.append(rule)
    
    _validation_registry.register_component_rules(component_name, rules)


__all__ = [
    "ValidationRule",
    "ValidationRegistry", 
    "get_validation_registry",
    "register_component_validation_rules"
]
