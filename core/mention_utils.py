"""Utility per rilevare menzioni di Rekku in testo generico."""

from __future__ import annotations


_ALIAS_LIST = [
    # Latin-based
    "rekku",
    "re-chan", "re-cchan", "recchan", "rekkuchan", "rekuchan",
    "rekku-tan", "rekku-san", "rekku-sama", "rekku-senpai", "rekku-kun",
    "genietta", "genietto", "tanukina",
    # Japanese Hiragana
    "れっく", "れっくう", "れっくちゃん", "れっくたん", "れっくさん", "れっく様",
    # Japanese Katakana
    "レック", "レックちゃん", "レックたん",
    # Cyrillic phonetic
    "рекку", "рекка", "реккун", "рекчан", "рекушка",
    # Handles / symbols
    "@the_official_rekku",
]


def is_rekku_mentioned(text: str) -> bool:
    """Return ``True`` if ``text`` contains any alias for Rekku."""
    lower = text.lower()
    return any(alias in lower for alias in _ALIAS_LIST)
