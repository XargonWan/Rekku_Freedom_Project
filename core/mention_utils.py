"""Multilingual utilities for detecting mentions of Rekku in free-form text."""

REKKU_ALIASES = [
    # Latin aliases
    "rekku",
    "re-chan",
    "re-cchan",
    "recchan",
    "rekkuchan",
    "rekku-chan",
    "rekuchan",
    "rekku-tan",
    "rekku-san",
    "rekku-sama",
    "rekku-senpai",
    "genietta",
    "genietto",
    "tanukina",
    "tanuki",
    "quella blu",
    "rekuchina",
    # Japanese aliases
    "れっく",
    "れっくう",
    "れっくちゃん",
    "れっくたん",
    "れっくさん",
    "れっく様",
    "レック",
    "レックちゃん",
    "レックたん",
    # Cyrillic aliases
    "рекку",
    "рекка",
    "рекчан",
    "реккун",
    "рекушка",
    # Official handle
    "@the_official_rekku",
]

# Pre-compute a lower-case version for faster checks
REKKU_ALIASES_LOWER = [alias.lower() for alias in REKKU_ALIASES]


from core.logging_utils import log_debug


def is_rekku_mentioned(text: str) -> bool:
    """Return ``True`` if ``text`` contains any alias for Rekku."""
    if not text:
        return False
    lowered = text.lower()
    for alias in REKKU_ALIASES_LOWER:
        if alias in lowered:
            log_debug(f"[mention] Rekku alias matched: '{alias}'")
            return True
    return False
