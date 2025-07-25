"""Selenium-based interface to post messages to X (formerly Twitter)."""

import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from core.logging_utils import log_info, log_error


class XInterface:
    """Interface for posting tweets using an existing Selenium driver."""

    def __init__(self, driver):
        self.driver = driver

    def handle_action(self, action: dict):
        """Handle an action dictionary.

        Supported action:
        - type: "x_post" with keys:
          - text (str): content of the tweet
          - screenshot (bool, optional): save screenshot after posting
        """
        if not isinstance(action, dict):
            log_error("[x_interface] Action must be a dictionary")
            return

        if action.get("type") != "x_post":
            log_error(f"[x_interface] Unsupported action type: {action.get('type')}")
            return

        text = action.get("text")
        if not text:
            log_error("[x_interface] 'text' field is required for x_post")
            return

        screenshot = action.get("screenshot", False)

        try:
            self.driver.get("https://x.com/home")
            wait = WebDriverWait(self.driver, 30)

            textarea = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]'))
            )
            textarea.click()
            textarea.send_keys(text)

            post_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="tweetButtonInline"]'))
            )
            post_btn.click()
            log_info("[x_interface] Tweet posted successfully")

            if screenshot:
                os.makedirs("screenshots", exist_ok=True)
                fname = f"screenshots/tweet_{int(time.time())}.png"
                self.driver.save_screenshot(fname)
                log_info(f"[x_interface] Saved screenshot to {fname}")
        except Exception as e:
            log_error(f"[x_interface] Failed to post tweet: {repr(e)}", e)

    @staticmethod
    def get_interface_instructions() -> str:
        """Return instructions for using this interface."""
        return (
            'Use actions like {"type": "x_post", "text": "Hello world", "screenshot": true}'
        )


INTERFACE_CLASS = XInterface
