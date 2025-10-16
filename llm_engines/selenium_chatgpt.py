# Import the base Selenium LLM library
from core.selenium_llm_base import SeleniumLLMBase
from core.logging_utils import log_debug, log_info, log_warning, log_error

# Selenium ChatGPT-specific configuration
# Model-specific character limits (based on official documentation and testing)
CHATGPT_MODEL_LIMITS = {
    "gpt-4o": 128000,        # GPT-4o: 128k tokens context (~400k characters)
    "gpt-4o-mini": 128000,   # GPT-4o-mini: 128k tokens context (~400k characters)
    "gpt-4-turbo": 128000,   # GPT-4 Turbo: 128k tokens context (~400k characters)
    "gpt-4": 8000,           # GPT-4: 8k tokens context (~24k characters)
    "gpt-3.5-turbo": 16000,  # GPT-3.5 Turbo: 16k tokens context (~48k characters)
    "o1-preview": 128000,    # o1-preview: 128k tokens context (~400k characters)
    "o1-mini": 128000,       # o1-mini: 128k tokens context (~400k characters)
    "unlogged": 1000,        # Unlogged state: very limited context
    "default": 128000        # Safe default for unknown models (assume newer models)
}

SELENIUM_CONFIG = {
    "max_prompt_chars": 128000,  # Default to gpt-4o limit
    "max_response_chars": 4000,
    "supports_images": True,
    "supports_functions": False,  # Browser-based doesn't support functions
    "model_name": "gpt-4o",
    "default_model": "gpt-4o",
    "browser_timeout": 30,
    "page_load_timeout": 60,
    "element_wait_timeout": 10,
    "retry_attempts": 3,
    "retry_delay": 2
}

def get_model_char_limit(model_name: str) -> int:
    """Get the character limit for a specific ChatGPT model."""
    # Normalize model name (lowercase, strip)
    normalized = model_name.lower().strip()
    
    # Check direct match first
    if normalized in CHATGPT_MODEL_LIMITS:
        return CHATGPT_MODEL_LIMITS[normalized]
    
    # Try to match partial names (e.g., "chatgpt-4o" -> "gpt-4o")
    for key in CHATGPT_MODEL_LIMITS.keys():
        if key in normalized or normalized.endswith(key):
            return CHATGPT_MODEL_LIMITS[key]
    
    # Special case: check for model variants
    if "4o" in normalized:
        if "mini" in normalized:
            return CHATGPT_MODEL_LIMITS["gpt-4o-mini"]
        return CHATGPT_MODEL_LIMITS["gpt-4o"]
    elif "turbo" in normalized:
        if "3.5" in normalized or "3-5" in normalized:
            return CHATGPT_MODEL_LIMITS["gpt-3.5-turbo"]
        return CHATGPT_MODEL_LIMITS["gpt-4-turbo"]
    elif "o1" in normalized:
        if "mini" in normalized:
            return CHATGPT_MODEL_LIMITS["o1-mini"]
        return CHATGPT_MODEL_LIMITS["o1-preview"]
    elif "gpt-4" in normalized:
        return CHATGPT_MODEL_LIMITS["gpt-4"]
    
    # Return default if no match found
    from core.logging_utils import log_warning
    log_warning(f"[selenium_chatgpt] Unknown model '{model_name}', using default limit of {CHATGPT_MODEL_LIMITS['default']} chars")
    return CHATGPT_MODEL_LIMITS["default"]

def get_interface_limits() -> dict:
    """Get the limits and capabilities for Selenium ChatGPT interface."""
    # Get current model and its specific limit
    from core.config_manager import config_registry
    CHATGPT_MODEL = config_registry.get_value("CHATGPT_MODEL", "")
    model_name = CHATGPT_MODEL or SELENIUM_CONFIG.get("default_model", "gpt-4o")
    max_chars = get_model_char_limit(model_name)
    
    from core.logging_utils import log_info
    log_info(f"[selenium_chatgpt] Interface limits for model '{model_name}': max_prompt_chars={max_chars}, supports_images={SELENIUM_CONFIG['supports_images']}")
    return {
        "max_prompt_chars": max_chars,
        "max_response_chars": SELENIUM_CONFIG["max_response_chars"],
        "supports_images": SELENIUM_CONFIG["supports_images"],
        "supports_functions": SELENIUM_CONFIG["supports_functions"],
        "model_name": model_name
    }

# Global model configuration
from core.config_manager import config_registry
CHATGPT_MODEL = config_registry.get_value("CHATGPT_MODEL", "")

class SeleniumChatGPTPlugin(SeleniumLLMBase):
    display_name = "Selenium ChatGPT"
    
    def __init__(self, notify_fn=None):
        """Initialize the ChatGPT plugin."""
        # ChatGPT-specific configuration
        chatgpt_config = SELENIUM_CONFIG.copy()
        chatgpt_config.update({
            "service_url": "https://chat.openai.com",
            "model": CHATGPT_MODEL or "gpt-4o",
            "interface_name": "chatgpt"
        })
        
        super().__init__(config=chatgpt_config, notify_fn=notify_fn)

    def _ensure_logged_in(self, driver) -> bool:
        """Ensure the user is logged in to ChatGPT."""
        try:
            current_url = driver.current_url
        except Exception:
            current_url = ""
        log_debug(f"[selenium_chatgpt] _ensure_logged_in called, current URL: {current_url}")

        if not current_url.startswith("https://chat.openai.com") and not current_url.startswith("https://chatgpt.com"):
            try:
                log_debug("[selenium_chatgpt] Navigating to ChatGPT home")
                driver.get("https://chat.openai.com")
                current_url = driver.current_url
                log_debug(f"[selenium_chatgpt] Navigated to {current_url}")
            except Exception as e:
                log_warning(f"[selenium_chatgpt] Failed to navigate to ChatGPT home: {e}")
                return False

        if current_url and ("login" in current_url or "auth0" in current_url):
            log_debug("[selenium_chatgpt] Login required, notifying user")
            # Notify user to log in
            if self._notify_fn:
                self._notify_fn("🔐 Login required for ChatGPT. Open UI to log in.")
            return False

        log_debug("[selenium_chatgpt] Logged in and ready")
        return True

    def _locate_prompt_area(self, driver, timeout: int = 10):
        """Locate the ChatGPT prompt input area.
        
        Based on the legacy version that worked, prioritizing the main selectors.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # Primary selectors from legacy version that worked
        primary_selectors = [
            (By.ID, "prompt-textarea"),  # Main ChatGPT textarea ID
            (By.XPATH, "//div[@contenteditable='true' and @id='prompt-textarea']"),  # Fallback for contenteditable div
        ]
        
        # Try primary selectors first (from legacy)
        for by, selector in primary_selectors:
            try:
                log_debug(f"[selenium_chatgpt] Trying primary selector: {by} = '{selector}'")
                element = WebDriverWait(driver, timeout).until(
                    EC.element_to_be_clickable((by, selector))
                )
                log_debug(f"[selenium_chatgpt] Found element with primary selector: {by} = '{selector}'")
                return element
            except Exception as e:
                log_debug(f"[selenium_chatgpt] Primary selector failed: {by} = '{selector}' - {e}")
                continue
        
        # Additional selectors as fallback (from current version)
        fallback_selectors = [
            # ProseMirror editor selectors
            (By.CSS_SELECTOR, "div.ProseMirror.ProseMirror-focused"),
            (By.CSS_SELECTOR, "div.ProseMirror"),
            (By.CSS_SELECTOR, "div[id='prompt-textarea']"),
            (By.CSS_SELECTOR, "p[data-placeholder='Ask anything']"),
            (By.CSS_SELECTOR, "div.ProseMirror p[data-placeholder]"),
            # Additional ChatGPT-specific selectors
            (By.CSS_SELECTOR, "textarea[data-id='prompt-textarea']"),
            (By.CSS_SELECTOR, "#prompt-textarea"),
            (By.CSS_SELECTOR, "textarea[data-testid='prompt-textarea']"),
            (By.CSS_SELECTOR, "div[data-testid='prompt-textarea'][contenteditable='true']"),
            # Rich text editor selectors
            (By.CSS_SELECTOR, "div[data-contents='true']"),
            (By.CSS_SELECTOR, "div.ql-editor"),
            (By.CSS_SELECTOR, "div.ql-editor.ql-blank"),
            # Placeholder-based selectors
            (By.CSS_SELECTOR, "textarea[placeholder*='Message']"),
            (By.CSS_SELECTOR, "textarea[placeholder*='Ask']"),
            (By.CSS_SELECTOR, "textarea[placeholder*='Send a message']"),
            # Contenteditable divs
            (By.CSS_SELECTOR, "div[contenteditable='true'][role='textbox']"),
            (By.CSS_SELECTOR, "div[role='textbox'][contenteditable='true']"),
            # Generic fallbacks
            (By.TAG_NAME, "textarea"),
            (By.CSS_SELECTOR, "div[contenteditable='true']"),
        ]
        
        for by, selector in fallback_selectors:
            try:
                log_debug(f"[selenium_chatgpt] Trying fallback selector: {by} = '{selector}'")
                element = WebDriverWait(driver, timeout).until(
                    EC.element_to_be_clickable((by, selector))
                )
                log_debug(f"[selenium_chatgpt] Found element with fallback selector: {by} = '{selector}'")
                return element
            except Exception as e:
                log_debug(f"[selenium_chatgpt] Fallback selector failed: {by} = '{selector}' - {e}")
                continue
        
        log_error("[selenium_chatgpt] Could not locate ChatGPT prompt input area with any selector")
        return None

    def _send_prompt_with_confirmation(self, textarea, prompt_text: str) -> None:
        """Send the prompt to ChatGPT and confirm it was sent successfully."""
        try:
            # Use the provided textarea instead of locating it again
            if not textarea:
                from core.logging_utils import log_error
                log_error("[selenium] No textarea provided")
                return
            
            # Clear any existing text
            textarea.clear()
            
            # Paste the prompt text
            textarea.send_keys(prompt_text)
            
            # Send the message
            from selenium.webdriver.common.keys import Keys
            textarea.send_keys(Keys.RETURN)
            
            # Wait for confirmation that the prompt was sent
            # Check that the input area is cleared or that a sending indicator appears
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            WebDriverWait(self.driver, 10).until(
                lambda d: (
                    textarea.get_attribute("value") == "" or
                    len(d.find_elements(By.CSS_SELECTOR, "[data-testid*='sending'], .sending, .loading")) > 0
                )
            )
            
            from core.logging_utils import log_debug
            log_debug("[selenium_chatgpt] Prompt sent successfully")
            
        except Exception as e:
            from core.logging_utils import log_error
            log_error(f"[selenium_chatgpt] Failed to send prompt: {e}")
            raise

    def _extract_response_text(self, driver) -> str:
        """Extract the latest response from ChatGPT."""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            # Wait for response to appear
            response_element = WebDriverWait(driver, self.config.get("response_timeout", 60)).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".message-content, [data-testid*='response'], .response-content"))
            )
            
            # Get the text content
            response_text = response_element.text
            
            # Wait for response to stabilize (no more typing indicators)
            self.wait_until_response_stabilizes(driver)
            
            # Get final text after stabilization
            final_response = response_element.text
            
            from core.logging_utils import log_debug
            log_debug(f"[selenium] Extracted response: {len(final_response)} characters")
            return final_response
            
        except Exception as e:
            from core.logging_utils import log_error
            log_error(f"[selenium] Failed to extract response: {e}")
            return ""

    def get_supported_models(self) -> list:
        """Get list of supported ChatGPT models."""
        return list(CHATGPT_MODEL_LIMITS.keys())

    def get_current_model(self) -> str:
        """Get the current ChatGPT model being used."""
        from core.config_manager import config_registry
        CHATGPT_MODEL = config_registry.get_value("CHATGPT_MODEL", "")
        configured_model = CHATGPT_MODEL or self.config.get("default_model", "gpt-4o")
        
        # Check if user is logged in, if not return "unlogged" model
        if not self._is_user_logged_in():
            log_warning(f"[selenium_chatgpt] ⚠️ User not logged in to ChatGPT, using 'unlogged' model with limited context (1000 chars)")
            return "unlogged"
        
        return configured_model

    def _is_user_logged_in(self) -> bool:
        """Check if user is logged in to ChatGPT without initializing driver if not needed."""
        # If driver is not initialized, assume not logged in
        if self.driver is None:
            return False
            
        try:
            current_url = self.driver.current_url
            # If we're on a login/auth page, user is not logged in
            if current_url and ("login" in current_url or "auth0" in current_url):
                return False
            return True
        except Exception:
            # If we can't get the URL, assume not logged in
            return False

PLUGIN_CLASS = SeleniumChatGPTPlugin