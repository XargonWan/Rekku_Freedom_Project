from typing import Optional


def truncate_message(text: Optional[str], limit: int = 4000) -> str:
    """Return ``text`` truncated to fit within Telegram limits."""
    if not text:
        return text or ""
    if len(text) > limit:
        return text[:limit] + "\n... (truncated)"
    return text
