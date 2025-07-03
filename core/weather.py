import asyncio
import json
import logging
import os
import urllib.parse
import urllib.request

current_weather = None

_logger = logging.getLogger("rekku.weather")


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


async def _fetch_weather() -> None:
    global current_weather

    location = os.getenv("WEATHER_LOCATION", "Kyoto")
    encoded = urllib.parse.quote(location)
    url = f"https://wttr.in/{encoded}?format=j1"
    _logger.info("Fetching weather for %s", location)

    try:
        response = await asyncio.to_thread(urllib.request.urlopen, url)
        status = getattr(response, "status", 200)
        _logger.info("HTTP status: %s", status)
        data_bytes = await asyncio.to_thread(response.read)
    except Exception as e:
        _logger.warning("Failed to fetch weather: %s", e)
        current_weather = "Weather data unavailable."
        return

    try:
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

        _logger.info(
            "Parsed values: desc=%s temp=%s feels=%s humidity=%s wind=%s%s cloud=%s visibility=%s pressure=%s",
            desc,
            temp_c,
            feels_c,
            humidity,
            wind_speed,
            wind_dir,
            cloudcover,
            visibility,
            pressure,
        )

        emoji = _choose_emoji(desc)
        current_weather = (
            f"{location}: {emoji} {desc} +{temp_c}°C ("
            f"Feels like {feels_c}°C, Humidity {humidity}%, "
            f"Wind {wind_speed}km/h {wind_dir}, Visibility {visibility}km, "
            f"Pressure {pressure}hPa, Cloud cover {cloudcover}%"
            ")"
        )
        _logger.info("Weather string: %s", current_weather)
    except Exception as e:
        _logger.warning("Error parsing weather data: %s", e)
        current_weather = "Weather data unavailable."


async def _weather_loop():
    while True:
        await _fetch_weather()
        await asyncio.sleep(1800)


def start_weather_updater():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.create_task(_weather_loop())


def get_current_weather() -> str:
    return current_weather
