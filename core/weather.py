import asyncio
import json
import os
import urllib.parse
import urllib.request

current_weather = None

from core.logging_utils import log_debug, log_info, log_warning, log_error


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
    log_info(f"Fetching weather for {location}")
    log_debug(f"Fetching weather for location: {location}")

    try:
        response = await asyncio.to_thread(urllib.request.urlopen, url)
        status = getattr(response, "status", 200)
        log_info(f"HTTP status: {status}")
        log_debug(f"HTTP response status: {status}")
        data_bytes = await asyncio.to_thread(response.read)
    except Exception as e:
        log_warning(f"Failed to fetch weather: {e}")
        log_error("Failed to update weather", e)
        current_weather = "Weather data unavailable."
        return

    try:
        log_debug("Parsing started...")
        data = json.loads(data_bytes.decode())
        log_debug("Weather JSON fetched successfully.")
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
            f"Parsed values: desc={desc} temp={temp_c} feels={feels_c} humidity={humidity} "
            f"wind={wind_speed}{wind_dir} cloud={cloudcover} visibility={visibility} pressure={pressure}"
        )

        emoji = _choose_emoji(desc)
        weather_string = (
            f"{location}: {emoji} {desc} +{temp_c}°C ("
            f"Feels like {feels_c}°C, Humidity {humidity}%, "
            f"Wind {wind_speed}km/h {wind_dir}, Visibility {visibility}km, "
            f"Pressure {pressure}hPa, Cloud cover {cloudcover}%)"
        )
        log_debug(f"Final weather string: {weather_string}")
        current_weather = weather_string
        log_info(f"Weather string: {current_weather}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        log_error("Failed to parse or format weather data", e)
        log_warning(f"Error parsing weather data: {e}")
        current_weather = "Weather data unavailable."


def start_weather_updater():
    async def update_loop():
        await update_weather()
        log_debug("Weather updater started and initial fetch done.")
        while True:
            await asyncio.sleep(1800)
            await update_weather()

    loop = asyncio.get_event_loop()
    loop.create_task(update_loop())


def get_current_weather() -> str:
    return current_weather
