"""Simple bio management placeholder."""

from typing import Dict

_bios: Dict[str, Dict] = {}


def set_bio(name: str, bio: Dict):
    _bios[name] = bio


def get_bio(name: str) -> Dict | None:
    return _bios.get(name)
