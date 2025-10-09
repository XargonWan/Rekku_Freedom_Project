from zoneinfo import ZoneInfo, available_timezones
import os
from datetime import datetime

from core.logging_utils import log_warning
from core.config_manager import config_registry

# Get list of available timezones for dropdown
_AVAILABLE_TIMEZONES = sorted(available_timezones())

# Timezone and location configuration
_TZ = "UTC"
_PROMPT_LOCATION = ""


def _update_tz(value: str | None) -> None:
    """Update global TZ variable."""
    global _TZ
    _TZ = value or "UTC"


def _update_prompt_location(value: str | None) -> None:
    """Update global PROMPT_LOCATION variable."""
    global _PROMPT_LOCATION
    _PROMPT_LOCATION = value or ""


# Register timezone configuration
_TZ = config_registry.get_value(
    "TZ",
    "UTC",
    label="Timezone",
    description="Timezone for scheduled events and time display (e.g., 'Asia/Tokyo', 'Europe/Rome', 'America/New_York')",
    group="core",
    component="core",
    constraints={"choices": _AVAILABLE_TIMEZONES},
)
config_registry.add_listener("TZ", _update_tz)

# Register location configuration
_PROMPT_LOCATION = config_registry.get_value(
    "PROMPT_LOCATION",
    "",
    label="Default Location",
    description="Default location for prompts and plugins (e.g., 'Kyoto,Japan', 'Rome,Italy')",
    group="core",
    component="core",
)
config_registry.add_listener("PROMPT_LOCATION", _update_prompt_location)


def get_local_timezone() -> ZoneInfo:
    """Return the local timezone defined by the TZ config variable or UTC.

    Logs a warning and falls back to UTC if the variable is missing or
    points to an invalid timezone.
    """
    tz_name = _TZ or "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        log_warning(f"Invalid TZ '{tz_name}', falling back to UTC")
        return ZoneInfo("UTC")


def utc_to_local(dt: datetime) -> datetime:
    """Convert a UTC datetime to local time using the local TZ."""
    return dt.astimezone(get_local_timezone())


def parse_local_to_utc(date_str: str, time_str: str) -> datetime:
    """Parse local date and time strings and return a UTC datetime."""
    local_tz = get_local_timezone()
    dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return dt_local.replace(tzinfo=local_tz).astimezone(ZoneInfo("UTC"))


def format_dual_time(dt_utc: datetime) -> str:
    """Return formatted time in local timezone with UTC in parentheses."""
    dt_local = utc_to_local(dt_utc)
    return f"{dt_local.strftime('%H:%M %Z')} ({dt_utc.strftime('%H:%M UTC')})"


def get_local_location() -> str:
    """Return a human-readable location using a dedicated configuration variable.

    The location is primarily sourced from the PROMPT_LOCATION configuration
    variable. If it is not set, a best-effort location name is derived from the
    TZ configuration variable. This keeps timezone and location as separate
    configuration options while providing a sensible fallback.
    """

    location = _PROMPT_LOCATION
    if location:
        return location

    tz_name = _TZ or "UTC"
    # Typically in the form Region/City; use the last part as location
    if "/" in tz_name:
        location = tz_name.split("/")[-1]
    else:
        location = tz_name
    return location.replace("_", " ")
