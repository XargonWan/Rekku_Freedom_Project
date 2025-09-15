# validation_system_examples.py
"""
Examples of how to use the new Dynamic Component Validation System.

This file shows practical examples of how components can register validation rules
using the new system, replacing hardcoded validation in the corrector.

Updated with real examples from the Rekku codebase.
"""

# Example 1: Standard Weather Plugin (existing - no changes needed)
class WeatherPlugin:
    """Weather plugin using the standard pattern - automatically discovered."""
    
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

# Example 2: Enhanced Event Plugin (updated to use new system)
class EventPlugin:
    """Event plugin with enhanced custom validation using the new system."""
    
    def __init__(self):
        from core.core_initializer import register_plugin
        register_plugin("event", self)
        
        # Register custom validation with the new system
        self._register_custom_validation()
    
    def _register_custom_validation(self):
        """Register custom validation rules with the new validation system."""
        from core.validation_registry import ValidationRule, get_validation_registry
        
        def validate_event_payload(payload):
            """Enhanced validation for event actions."""
            errors = []
            
            # Validate date format and logic
            date_str = payload.get("date")
            if date_str:
                try:
                    from datetime import datetime
                    event_date = datetime.strptime(date_str, "%Y-%m-%d")
                    # Check if date is not in the past
                    today = datetime.now().date()
                    if event_date.date() < today:
                        errors.append("Event date cannot be in the past")
                except Exception:
                    errors.append("payload.date must be in format YYYY-MM-DD")
            
            # Validate time format if provided
            time_str = payload.get("time")
            if time_str:
                try:
                    from datetime import datetime
                    datetime.strptime(time_str, "%H:%M")
                except Exception:
                    errors.append("payload.time must be in format HH:MM")
            
            # Validate repeat options
            repeat = payload.get("repeat")
            if repeat and repeat not in ["none", "daily", "weekly", "monthly", "always"]:
                errors.append("payload.repeat must be one of: none, daily, weekly, monthly, always")
            
            return errors
        
        # Create and register custom validation rule
        rule = ValidationRule(
            action_type="event",
            required_fields=["date", "description"],
            custom_validator=validate_event_payload,
            component_name="event"
        )
        
        registry = get_validation_registry()
        registry.register_component_rules("event", [rule])
    
    def get_supported_actions(self):
        """Standard action declaration - works with both old and new systems."""
        return {
            "event": {
                "required_fields": ["date", "description"],
                "optional_fields": ["time", "repeat", "created_by"],
                "description": "Create or schedule a future event",
            }
        }

# Example 3: Enhanced Discord Interface (updated to use new system)
class DiscordInterface:
    """Discord interface with enhanced validation using the new system."""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        
        # Register custom validation with the new system
        self._register_custom_validation()
    
    def _register_custom_validation(self):
        """Register custom validation rules with the new validation system."""
        from core.validation_registry import ValidationRule, get_validation_registry
        
        def validate_discord_message(payload):
            """Enhanced validation for Discord message actions."""
            errors = []
            
            # Validate text content
            text = payload.get("text")
            if text:
                if len(text) > 2000:  # Discord message limit
                    errors.append("Message text cannot exceed 2000 characters")
                if not text.strip():
                    errors.append("Message text cannot be empty or only whitespace")
            
            # Validate target (channel_id)
            target = payload.get("target")
            if target is not None:
                if isinstance(target, str) and not target.isdigit():
                    errors.append("Channel ID must be numeric")
                elif isinstance(target, int) and target <= 0:
                    errors.append("Channel ID must be positive")
            
            return errors
        
        # Create and register custom validation rule
        rule = ValidationRule(
            action_type="message_discord_bot",
            required_fields=["text", "target"],
            custom_validator=validate_discord_message,
            component_name="discord_interface"
        )
        
        registry = get_validation_registry()
        registry.register_component_rules("discord_interface", [rule])
    
    @staticmethod
    def get_supported_actions():
        """Standard action declaration."""
        return {
            "message_discord_bot": {
                "description": "Send a text message to a Discord channel.",
                "required_fields": ["text", "target"],
                "optional_fields": ["reply_to_message_id"],
            }
        }

# Example 4: Existing Telegram Interface (no changes needed)
class TelegramInterface:
    """Telegram interface - existing pattern works automatically."""
    
    @staticmethod
    def get_supported_actions():
        return {
            "message_telegram_bot": {
                "required_fields": ["text"],
                "optional_fields": ["target", "chat_name", "message_thread_id"],
                "description": "Send a text message via Telegram",
            },
            "audio_telegram_bot": {
                "required_fields": ["audio"],
                "optional_fields": ["target", "chat_name", "message_thread_id"],
                "description": "Send a voice message via Telegram",
            },
        }

# Example 5: Advanced Plugin with Multiple Validation Rules
class AdvancedPlugin:
    """Plugin demonstrating multiple action types with different validation rules."""
    
    def __init__(self):
        from core.core_initializer import register_plugin
        register_plugin("advanced", self)
        self._register_custom_validation()
    
    def _register_custom_validation(self):
        """Register multiple custom validation rules."""
        from core.validation_registry import ValidationRule, get_validation_registry
        
        def validate_file_operation(payload):
            """Custom validation for file operations."""
            errors = []
            file_path = payload.get("file_path", "")
            
            # Security checks
            if ".." in file_path or file_path.startswith("/"):
                errors.append("File path security violation")
            
            return errors
        
        def validate_api_call(payload):
            """Custom validation for API calls."""
            errors = []
            url = payload.get("url", "")
            
            if not url.startswith(("http://", "https://")):
                errors.append("URL must start with http:// or https://")
            
            return errors
        
        # Register multiple rules
        rules = [
            ValidationRule("file_operation", ["file_path", "operation"], validate_file_operation, "advanced"),
            ValidationRule("api_call", ["url", "method"], validate_api_call, "advanced"),
            ValidationRule("simple_action", ["message"], None, "advanced"),  # Simple required fields only
        ]
        
        registry = get_validation_registry()
        registry.register_component_rules("advanced", rules)
    
    def get_supported_actions(self):
        """Multiple action types with different validation needs."""
        return {
            "file_operation": {
                "required_fields": ["file_path", "operation"],
                "optional_fields": ["backup"],
            },
            "api_call": {
                "required_fields": ["url", "method"],
                "optional_fields": ["headers", "timeout"],
            },
            "simple_action": {
                "required_fields": ["message"],
                "optional_fields": ["priority"],
            }
        }

"""
Key Benefits Demonstrated:

✅ **Backward Compatibility**: All existing components work without changes
✅ **Auto-Discovery**: The system automatically finds and registers rules
✅ **Enhanced Validation**: Support for complex custom validation logic
✅ **Clean Architecture**: No hardcoded rules in the corrector
✅ **Easy Migration**: Components can be enhanced gradually

Migration Summary:
- ✅ WeatherPlugin: No changes needed (already compliant)
- ✅ EventPlugin: Enhanced with custom validation (date logic, time format)
- ✅ DiscordInterface: Enhanced with Discord-specific validation (message limits)
- ✅ TelegramInterface: No changes needed (already compliant)
- ✅ AdvancedPlugin: New plugin demonstrating complex validation

The corrector now automatically validates:
- ✅ Action type exists (existing behavior maintained)
- ✅ Required fields are present and not empty (new)
- ✅ Custom validation rules pass (new, enhanced)
- ❌ No more hardcoded component-specific rules in corrector
"""
