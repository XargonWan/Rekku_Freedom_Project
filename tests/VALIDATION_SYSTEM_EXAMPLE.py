# Example: How to update a plugin to use the new validation system

# OLD WAY (weather_plugin.py example):
class WeatherPlugin:
    def get_supported_actions(self):
        return {
            "static_inject": {
                "description": "Inject static contextual data into every prompt",
                "required_fields": [],
                "optional_fields": [],
            }
        }

# NEW WAY - Enhanced with detailed validation rules:
class WeatherPlugin:
    def get_supported_actions(self):
        return {
            "static_inject": {
                "description": "Inject static contextual data into every prompt",
                "required_fields": [],  # Auto-registered by the new system
                "optional_fields": [],
            },
            "weather_request": {
                "description": "Request current weather for a location",
                "required_fields": ["location"],  # System will enforce this
                "optional_fields": ["units"],
            }
        }

# ALTERNATIVE NEW WAY - Using the component registration system directly:
class AdvancedWeatherPlugin:
    def __init__(self):
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
                }
            }
        })

# For interfaces (telegram_bot.py example):
class TelegramInterface:
    def get_supported_actions(self):
        return {
            "send_message": {
                "description": "Send a message to a Telegram chat",
                "required_fields": ["text", "chat_id"],  # System will enforce these
                "optional_fields": ["parse_mode", "reply_markup"],
            },
            "send_photo": {
                "description": "Send a photo to a Telegram chat", 
                "required_fields": ["photo", "chat_id"],
                "optional_fields": ["caption"],
            }
        }

# The corrector will now automatically validate:
# - If action type exists (as before)
# - If required fields are present and not empty
# - No hardcoding in corrector for specific components
