"""Simple emotion management placeholder."""

from typing import Dict

_current: Dict[str, int] = {}


def set_emotion(name: str, intensity: int) -> None:
    _current[name] = intensity


def get_emotions() -> Dict[str, int]:
    return dict(_current)
