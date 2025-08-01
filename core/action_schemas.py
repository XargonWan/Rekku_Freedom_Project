# core/action_schemas.py
"""
Action Schema Definitions and Validation.
Enforces strict structure including mandatory 'interface' field.
"""

from typing import Dict, Any, List, Optional
import json
from core.logging_utils import log_debug, log_warning, log_error


class ActionSchemaValidator:
    """Validates actions against predefined schemas with mandatory interface field."""
    
    BASE_ACTION_SCHEMA = {
        "type": "object",
        "required": ["type", "interface", "payload"],
        "properties": {
            "type": {"type": "string"},
            "interface": {"type": "string"},
            "payload": {"type": "object"}
        },
        "additionalProperties": False
    }
    
    ACTION_SCHEMAS = {
        "message": {
            "type": "object",
            "required": ["type", "interface", "payload"],
            "properties": {
                "type": {"enum": ["message"]},
                "interface": {"type": "string"},
                "payload": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "target": {"oneOf": [
                            {"type": "integer"},
                            {"type": "object", "required": ["chat_id"], "properties": {
                                "chat_id": {"type": "integer"},
                                "message_id": {"type": "integer"}
                            }}
                        ]},
                        "message_thread_id": {"type": "integer"},
                        "scope": {"enum": ["local", "global"]},
                        "privacy": {"enum": ["default", "private", "public"]}
                    },
                    "additionalProperties": False
                }
            },
            "additionalProperties": False
        },
        
        "event": {
            "type": "object", 
            "required": ["type", "interface", "payload"],
            "properties": {
                "type": {"enum": ["event"]},
                "interface": {"type": "string"},
                "payload": {
                    "type": "object",
                    "required": ["date", "description"],
                    "properties": {
                        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                        "time": {"type": "string", "pattern": r"^\d{2}:\d{2}$"},
                        "repeat": {"enum": ["none", "daily", "weekly", "monthly", "always"]},
                        "description": {"type": "string", "minLength": 1},
                        "created_by": {"type": "string"}
                    },
                    "additionalProperties": False
                }
            },
            "additionalProperties": False
        },
        
        "command": {
            "type": "object",
            "required": ["type", "interface", "payload"], 
            "properties": {
                "type": {"enum": ["command"]},
                "interface": {"type": "string"},
                "payload": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "args": {"type": "array", "items": {"type": "string"}}
                    },
                    "additionalProperties": False
                }
            },
            "additionalProperties": False
        }
    }
    
    @classmethod
    def validate_action_structure(cls, action: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate action against strict schema requirements."""
        errors = []
        
        if not isinstance(action, dict):
            return False, ["Action must be a dictionary"]
        
        # Check required top-level fields
        for required_field in ["type", "interface", "payload"]:
            if required_field not in action:
                errors.append(f"Missing required field: '{required_field}'")
        
        if errors:
            return False, errors
            
        action_type = action["type"]
        interface = action["interface"]
        payload = action["payload"]
        
        # Validate types
        if not isinstance(action_type, str) or not action_type:
            errors.append("Field 'type' must be a non-empty string")
        if not isinstance(interface, str) or not interface:
            errors.append("Field 'interface' must be a non-empty string")
        if not isinstance(payload, dict):
            errors.append("Field 'payload' must be an object")
            
        # Type-specific validation
        if action_type in cls.ACTION_SCHEMAS:
            type_errors = cls._validate_against_schema(action, cls.ACTION_SCHEMAS[action_type])
            errors.extend(type_errors)
        else:
            # For unknown types, just ensure basic structure
            basic_errors = cls._validate_against_schema(action, cls.BASE_ACTION_SCHEMA)
            errors.extend(basic_errors)
            
        return len(errors) == 0, errors
    
    @classmethod  
    def _validate_against_schema(cls, data: Any, schema: Dict[str, Any]) -> List[str]:
        """Basic schema validation (simplified jsonschema-like validation)."""
        errors = []
        
        if schema.get("type") == "object":
            if not isinstance(data, dict):
                errors.append(f"Expected object, got {type(data).__name__}")
                return errors
                
            # Check required fields
            required = schema.get("required", [])
            for field in required:
                if field not in data:
                    errors.append(f"Missing required field: '{field}'")
            
            # Check properties
            properties = schema.get("properties", {})
            for field, field_schema in properties.items():
                if field in data:
                    field_errors = cls._validate_field(data[field], field_schema, field)
                    errors.extend(field_errors)
                    
        return errors
    
    @classmethod
    def _validate_field(cls, value: Any, schema: Dict[str, Any], field_name: str) -> List[str]:
        """Validate a single field against its schema."""
        errors = []
        
        # Type validation
        expected_type = schema.get("type")
        if expected_type:
            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"Field '{field_name}' must be a string")
            elif expected_type == "integer" and not isinstance(value, int):
                errors.append(f"Field '{field_name}' must be an integer")
            elif expected_type == "object" and not isinstance(value, dict):
                errors.append(f"Field '{field_name}' must be an object")
            elif expected_type == "array" and not isinstance(value, list):
                errors.append(f"Field '{field_name}' must be an array")
        
        # Enum validation
        enum_values = schema.get("enum")
        if enum_values and value not in enum_values:
            errors.append(f"Field '{field_name}' must be one of: {enum_values}")
            
        # String length validation
        if isinstance(value, str):
            min_length = schema.get("minLength")
            if min_length and len(value) < min_length:
                errors.append(f"Field '{field_name}' must be at least {min_length} characters long")
        
        # Pattern validation (basic)
        pattern = schema.get("pattern")
        if pattern and isinstance(value, str):
            import re
            if not re.match(pattern, value):
                errors.append(f"Field '{field_name}' does not match required pattern")
                
        # Nested object validation
        if schema.get("type") == "object" and isinstance(value, dict):
            nested_errors = cls._validate_against_schema(value, schema)
            errors.extend([f"{field_name}.{err}" for err in nested_errors])
            
        return errors


def enforce_schema_validation(action: Dict[str, Any]) -> tuple[bool, List[str], Dict[str, Any]]:
    """
    Enforce strict schema validation and return enhanced action.
    
    Returns:
        Tuple of (is_valid, errors, enhanced_action)
    """
    
    # Create a copy to avoid modifying the original
    enhanced_action = action.copy()
    
    # Pre-validation cleanup
    if "description" in enhanced_action:
        enhanced_action = {k: v for k, v in enhanced_action.items() if k != "description"}
    
    # Validate structure
    is_valid, errors = ActionSchemaValidator.validate_action_structure(enhanced_action)
    
    if not is_valid:
        log_warning(f"[action_schemas] Schema validation failed: {errors}")
    else:
        log_debug(f"[action_schemas] Action passed schema validation: {enhanced_action.get('type')}")
    
    return is_valid, errors, enhanced_action
