from zoneinfo import ZoneInfo
import os
from datetime import datetime

from core.logging_utils import log_warning


def get_local_timezone() -> ZoneInfo:
    """Return the local timezone defined by the TZ env variable or UTC.

    Logs a warning and falls back to UTC if the variable is missing or
    points to an invalid timezone.
    """
    tz_name = os.environ.get("TZ", "UTC")
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
    """Return a human-readable location using a dedicated environment variable.

    The location is primarily sourced from the PROMPT_LOCATION environment
    variable. If it is not set, a best-effort location name is derived from the
    TZ environment variable. This keeps timezone and location as separate
    configuration options while providing a sensible fallback.
    """

    location = os.environ.get("PROMPT_LOCATION")
    if location:
        return location

    tz_name = os.environ.get("TZ", "UTC")
    # Typically in the form Region/City; use the last part as location
    if "/" in tz_name:
        location = tz_name.split("/")[-1]
    else:
        location = tz_name
    return location.replace("_", " ")
