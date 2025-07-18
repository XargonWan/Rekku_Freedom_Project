from core.logging_utils import log_debug


def selenium_send_and_wait(prompt_json: str) -> None:
    """Placeholder implementation sending prompt via Selenium.
    In production this should interact with ChatGPT's web UI."""
    log_debug(f"[selenium_core] send called with {len(prompt_json)} chars")
    # Actual sending is environment-specific and omitted here
    return None
