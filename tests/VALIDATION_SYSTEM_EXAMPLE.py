# validation_system_examples.py
"""
Examples of how to use the new Dynamic Component Validation System.

This file shows practical examples of how components can register validation rules
using the new system, replacing hardcoded validation in the corrector.
"""

# Example 1: Existing Weather Plugin (automatically supported)
class WeatherPlugin:
    """Weather plugin using the standard pattern - no changes needed."""
    
    def get_supported_actions(self):
        return {
            "static_inject": {
                "description": "Inject static contextual data into every prompt",
                "required_fields": [],  # Auto-registered by the new system
                "optional_fields": [],
            },
            "weather_request": {
                "description": "Request current weather for a location",
                "required_fields": ["location"],  # System will enforce this automatically
                "optional_fields": ["units", "forecast_days"],
            }
        }

# Example 2: Enhanced Plugin with Advanced Validation
class AdvancedWeatherPlugin:
    """Advanced weather plugin with manual registration for complex rules."""
    
    def __init__(self):
        from core.core_initializer import register_plugin
        register_plugin("weather", self)
        
        # Register validation rules using the new system
        from core.component_registry import register_component_validation
        register_component_validation("weather", "plugin", {
            "actions": {
                "weather_request": {
                    "required_fields": ["location"],
                },
                "weather_forecast": {
                    "required_fields": ["location", "days"],
                },
                "weather_alert": {
                    "required_fields": ["location", "alert_type", "threshold"],
                }
            }
        })

# Example 3: Telegram Interface (existing pattern - no changes needed)
class TelegramInterface:
    """Telegram interface - existing pattern works automatically."""
    
    def get_supported_actions(self):
        return {
            "send_message": {
                "description": "Send a message to a Telegram chat",
                "required_fields": ["text", "chat_id"],  # System enforces these automatically
                "optional_fields": ["parse_mode", "reply_markup", "disable_notification"],
            },
            "send_photo": {
                "description": "Send a photo to a Telegram chat", 
                "required_fields": ["photo", "chat_id"],
                "optional_fields": ["caption", "parse_mode"],
            },
            "edit_message": {
                "description": "Edit an existing message",
                "required_fields": ["chat_id", "message_id", "text"],
                "optional_fields": ["parse_mode", "reply_markup"],
            }
        }

# Example 4: Custom Validation with Complex Rules
class DatabasePlugin:
    """Plugin with custom validation logic."""
    
    def __init__(self):
        from core.core_initializer import register_plugin
        from core.validation_registry import ValidationRule, get_validation_registry
        
        register_plugin("database", self)
        
        # Define custom validator function
        def validate_query_action(payload):
            errors = []
            query = payload.get("query", "")
            
            # Check for dangerous SQL operations
            dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER"]
            if any(keyword in query.upper() for keyword in dangerous_keywords):
                errors.append("Dangerous SQL operations are not allowed")
            
            # Check query length
            if len(query) > 1000:
                errors.append("Query too long (max 1000 characters)")
                
            return errors
        
        # Register custom validation rule
        rule = ValidationRule(
            action_type="execute_query",
            required_fields=["query", "database"],
            custom_validator=validate_query_action,
            component_name="database"
        )
        
        registry = get_validation_registry()
        registry.register_component_rules("database", [rule])

# Example 5: LLM Engine with Validation
class CustomLLMEngine:
    """LLM engine with parameter validation."""
    
    def get_supported_actions(self):
        return {
            "generate_text": {
                "description": "Generate text using the LLM",
                "required_fields": ["prompt"],
                "optional_fields": ["max_tokens", "temperature", "model"],
            },
            "analyze_sentiment": {
                "description": "Analyze sentiment of text",
                "required_fields": ["text"],
                "optional_fields": ["language"],
            }
        }

"""
Key Benefits Demonstrated:

1. **No Breaking Changes**: Existing components work without modification
2. **Automatic Discovery**: The system finds and registers rules automatically  
3. **Flexible Validation**: Support for simple required fields and complex custom logic
4. **Clean Separation**: No hardcoded rules in the corrector
5. **Easy Testing**: Clear patterns for validation testing

The corrector now automatically validates:
- ✅ Action type exists (existing behavior)
- ✅ Required fields are present and not empty (new)
- ✅ Custom validation rules pass (new)
- ❌ No more hardcoded component-specific rules in corrector
"""
