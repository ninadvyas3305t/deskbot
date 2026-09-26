"""Real-time information tools for DeskBot (time, date, system metrics, weather)."""

from __future__ import annotations

import datetime
import json
import logging
import platform
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)


def get_current_time() -> str:
    """Return the current local time in human-friendly 12-hour format."""
    now = datetime.datetime.now()
    # Format e.g. "1:45 PM"
    hour = now.hour % 12 or 12
    minute = f"{now.minute:02d}"
    ampm = "AM" if now.hour < 12 else "PM"
    return f"{hour}:{minute} {ampm}"


def get_current_date() -> str:
    """Return the current local date in full format."""
    now = datetime.datetime.now()
    # Format e.g. "Friday, September 25, 2026"
    return now.strftime("%A, %B %d, %Y")


def get_system_info() -> Dict[str, Any]:
    """Return current hardware and OS metrics safely."""
    info: Dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
    }

    if psutil is not None:
        try:
            info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            info["ram_used_gb"] = round((mem.total - mem.available) / (1024 ** 3), 1)
            info["ram_total_gb"] = round(mem.total / (1024 ** 3), 1)
            info["ram_percent"] = mem.percent

            battery = psutil.sensors_battery()
            if battery is not None:
                info["battery_percent"] = int(battery.percent)
                info["power_plugged"] = battery.power_plugged
        except Exception as psutil_err:
            logger.debug("psutil metrics note: %s", psutil_err)

    return info


def get_weather(location: Optional[str] = None) -> Dict[str, Any]:
    """Fetch current weather via Open-Meteo geocoding and forecast API."""
    city = (location or "").strip()
    if not city or city.lower() in ("here", "local", "my location", "current", "current location"):
        city = "Mumbai"  # Default fallback if unspecified

    try:
        # 1. Geocode city name to lat/long
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
        geo_req = urllib.request.Request(
            geo_url,
            headers={"User-Agent": "DeskBot/1.0"},
        )
        with urllib.request.urlopen(geo_req, timeout=4.0) as resp:
            geo_data = json.loads(resp.read().decode("utf-8"))

        results = geo_data.get("results")
        if not results:
            return {"error": f"Could not find coordinates for '{city}'."}

        place = results[0]
        lat = place.get("latitude")
        lon = place.get("longitude")
        name = place.get("name", city)
        country = place.get("country", "")

        # 2. Get current weather forecast
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
        )
        weather_req = urllib.request.Request(
            weather_url,
            headers={"User-Agent": "DeskBot/1.0"},
        )
        with urllib.request.urlopen(weather_req, timeout=4.0) as w_resp:
            w_data = json.loads(w_resp.read().decode("utf-8"))

        current = w_data.get("current", {})
        temp = current.get("temperature_2m")
        feels_like = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        w_code = current.get("weather_code", 0)

        # WMO Weather interpretation codes
        condition = _wmo_code_to_condition(w_code)

        return {
            "city": name,
            "country": country,
            "temperature_c": temp,
            "feels_like_c": feels_like,
            "humidity_percent": humidity,
            "wind_speed_kmh": wind,
            "condition": condition,
        }
    except Exception as err:
        logger.debug("Weather fetch error: %s", err)
        return {"error": f"Failed to retrieve weather: {err}"}


def _wmo_code_to_condition(code: int) -> str:
    """Map WMO weather code to clear English description."""
    if code == 0:
        return "Clear sky"
    elif code in (1, 2, 3):
        return "Mainly clear to overcast"
    elif code in (45, 48):
        return "Foggy"
    elif code in (51, 53, 55):
        return "Drizzle"
    elif code in (61, 63, 65):
        return "Rain"
    elif code in (71, 73, 75):
        return "Snowfall"
    elif code in (80, 81, 82):
        return "Rain showers"
    elif code in (95, 96, 99):
        return "Thunderstorm"
    return "Partly cloudy"
