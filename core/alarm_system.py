"""Placeholder alarm and trigger management."""

from datetime import datetime
from typing import List, Dict, Any

_alarms: List[Dict[str, Any]] = []


def add_alarm(timestamp: datetime, description: str, tags: list[str] | None = None):
    _alarms.append({"time": timestamp, "description": description, "tags": tags or []})


def list_alarms() -> List[Dict[str, Any]]:
    return list(_alarms)
