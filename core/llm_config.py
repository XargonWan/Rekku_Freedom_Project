"""LLM Interface Configuration

Configuration for different LLM interfaces including character limits,
capabilities and specific settings.
"""

# Character limits for different LLM interfaces
LLM_INTERFACE_LIMITS = {
    "openai_chatgpt": {
        "max_prompt_chars": 32000,  # Conservative estimate for GPT-4
        "max_response_chars": 4000,
        "supports_images": True,
        "supports_functions": True,
        "model_name": "gpt-4o"
    },
    "selenium_chatgpt": {
        "max_prompt_chars": 25000,  # Browser-based, more conservative
        "max_response_chars": 4000,
        "supports_images": True,
        "supports_functions": False,
        "model_name": "gpt-4o"
    },
    "google_cli": {
        "max_prompt_chars": 20000,  # Google Gemini limits
        "max_response_chars": 3000,
        "supports_images": True,
        "supports_functions": True,
        "model_name": "gemini-pro"
    },
    "manual": {
        "max_prompt_chars": 8000,   # Manual input, keep it short
        "max_response_chars": 2000,
        "supports_images": False,
        "supports_functions": False,
        "model_name": "manual"
    }
}

# Priority order for sacrificial injections when running out of space
INJECTION_PRIORITY = [
    "diary",          # Most sacrificial - recent diary entries
    "weather",        # Weather information
    "context",        # Extended context
    "memories",       # Long-term memories
    "participants"    # Participant bios (keep essential ones)
]

def get_interface_limits(interface_name: str) -> dict:
    """Get the limits and capabilities for a specific LLM interface."""
    return LLM_INTERFACE_LIMITS.get(interface_name, LLM_INTERFACE_LIMITS["manual"])
