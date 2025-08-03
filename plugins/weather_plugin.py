import asyncio
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

from core.logging_utils import log_debug, log_info, log_warning, log_error


class WeatherPlugin:
    """Plugin that provides weather info as a static injection."""

    def __init__(self):
        self._cached_weather: Optional[str] = None
        self._last_fetch: float = 0.0
        try:
            self.cache_minutes = int(os.getenv("WEATHER_CACHE_MINUTES", "30"))
        except ValueError:
            self.cache_minutes = 30

    # Plugin action registration
    def get_supported_action_types(self):
        return ["static_inject"]

    def get_supported_actions(self):
        return {
            "static_inject": {
                "description": "Inject static contextual data into every prompt",
                "required_fields": [],
                "optional_fields": [],
            }
        }

    async def get_static_injection(self) -> dict:
        await self._ensure_weather()
        return {"weather": self._cached_weather or "Weather data unavailable."}

    async def _ensure_weather(self) -> None:
        now = time.time()
        if (
            not self._cached_weather
            or now - self._last_fetch > self.cache_minutes * 60
        ):
            await self._update_weather()

    async def _update_weather(self) -> None:
        location = os.getenv("WEATHER_LOCATION", "Kyoto")
        encoded = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded}?format=j1"
        log_info(f"[weather_plugin] Fetching weather for {location}")
        try:
            response = await asyncio.to_thread(urllib.request.urlopen, url)
            data_bytes = await asyncio.to_thread(response.read)
            data = json.loads(data_bytes.decode())
            cc = data.get("current_condition", [{}])[0]
            desc = cc.get("weatherDesc", [{}])[0].get("value", "N/A")
            temp_c = cc.get("temp_C", "N/A")
            feels_c = cc.get("FeelsLikeC", "N/A")
            humidity = cc.get("humidity", "N/A")
            wind_speed = cc.get("windspeedKmph", "N/A")
            wind_dir = cc.get("winddir16Point", "N/A")
            cloudcover = cc.get("cloudcover", "N/A")
            visibility = cc.get("visibility", "N/A")
            pressure = cc.get("pressure", "N/A")

            log_debug(
                "[weather_plugin] Parsed values: desc=%s temp=%s feels=%s humidity=%s wind=%s%s cloud=%s visibility=%s pressure=%s"%
                (desc, temp_c, feels_c, humidity, wind_speed, wind_dir, cloudcover, visibility, pressure)
            )

            emoji = self._choose_emoji(desc)
            weather_string = (
                f"{location}: {emoji} {desc} +{temp_c}°C ("
                f"Feels like {feels_c}°C, Humidity {humidity}%, "
                f"Wind {wind_speed}km/h {wind_dir}, Visibility {visibility}km, "
                f"Pressure {pressure}hPa, Cloud cover {cloudcover}%)"
            )
            log_debug(f"[weather_plugin] Final weather string: {weather_string}")
            self._cached_weather = weather_string
            self._last_fetch = time.time()
            log_info(f"[weather_plugin] Weather updated: {self._cached_weather}")
        except Exception as e:
            log_warning(f"[weather_plugin] Failed to fetch weather: {e}")
            log_error("[weather_plugin] Weather update error", e)

    @staticmethod
    def _choose_emoji(description: str) -> str:
        if not description:
            return "🌡️"
        desc = description.lower()
        if "thunder" in desc:
            return "⛈️"
        if "snow" in desc:
            return "❄️"
        if "rain" in desc:
            return "🌧️"
        if "fog" in desc or "mist" in desc:
            return "🌫️"
        if "cloud" in desc:
            return "☁️"
        if "sun" in desc or "clear" in desc:
            return "☀️"
        return "🌡️"


PLUGIN_CLASS = WeatherPlugin
