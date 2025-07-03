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


async def update_weather() -> None:
    global current_weather

    location = os.getenv("WEATHER_LOCATION", "Kyoto")
    encoded = urllib.parse.quote(location)
    url = f"https://wttr.in/{encoded}?format=j1"
    _logger.info("Fetching weather for %s", location)
    print(f"[DEBUG/weather] Fetching weather for location: {location}")

    try:
        response = await asyncio.to_thread(urllib.request.urlopen, url)
        status = getattr(response, "status", 200)
        _logger.info("HTTP status: %s", status)
        print(f"[DEBUG/weather] HTTP response status: {status}")
        data_bytes = await asyncio.to_thread(response.read)
    except Exception as e:
        _logger.warning("Failed to fetch weather: %s", e)
        print(f"[ERROR/weather] Failed to update weather: {e}")
        current_weather = "Weather data unavailable."
        return

    try:
        data = json.loads(data_bytes.decode())
        print("[DEBUG/weather] Weather JSON fetched successfully.")
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
        weather_string = (
            f"{location}: {emoji} {desc} +{temp_c}°C ("
            f"Feels like {feels_c}°C, Humidity {humidity}%, "
            f"Wind {wind_speed}km/h {wind_dir}, Visibility {visibility}km, "
            f"Pressure {pressure}hPa, Cloud cover {cloudcover}%)"
        )
        print(f"[DEBUG/weather] Final weather string: {weather_string}")
        current_weather = weather_string
        _logger.info("Weather string: %s", current_weather)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERROR/weather] Failed to parse or format weather data: {e}")
        _logger.warning("Error parsing weather data: %s", e)
        current_weather = "Weather data unavailable."


def start_weather_updater():
    async def update_loop():
        await update_weather()
        print("[DEBUG] Weather updater started and initial fetch done.")
        while True:
            await asyncio.sleep(1800)
            await update_weather()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.create_task(update_loop())


def get_current_weather() -> str:
    return current_weather
