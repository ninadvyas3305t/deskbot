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


def _get_ssl_context() -> ssl.SSLContext:
    """Create a resilient SSL context, falling back to unverified if certificates are missing."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl._create_unverified_context()
    except Exception:
        return ssl.create_default_context()


def get_weather(location: Optional[str] = None) -> Dict[str, Any]:
    """Fetch current weather via Open-Meteo (or wttr.in fallback)."""
    import os
    import ssl
    city = (location or "").strip()
    if not city or city.lower() in ("here", "local", "my location", "current", "current location"):
        configured = os.getenv("DESKBOT_DEFAULT_CITY", "").strip()
        if configured:
            city = configured
        else:
            return {"error": "Which city should I check?", "need_city": True}

    ssl_ctx = _get_ssl_context()

    # 1. Try Open-Meteo API
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
        geo_req = urllib.request.Request(geo_url, headers={"User-Agent": "DeskBot/1.0"})
        
        try:
            with urllib.request.urlopen(geo_req, context=ssl_ctx, timeout=4.0) as resp:
                geo_data = json.loads(resp.read().decode("utf-8"))
        except ssl.SSLError:
            with urllib.request.urlopen(geo_req, context=ssl._create_unverified_context(), timeout=4.0) as resp:
                geo_data = json.loads(resp.read().decode("utf-8"))

        results = geo_data.get("results")
        if results:
            place = results[0]
            lat = place.get("latitude")
            lon = place.get("longitude")
            name = place.get("name", city)
            country = place.get("country", "")

            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
            )
            weather_req = urllib.request.Request(weather_url, headers={"User-Agent": "DeskBot/1.0"})
            try:
                with urllib.request.urlopen(weather_req, context=ssl_ctx, timeout=4.0) as w_resp:
                    w_data = json.loads(w_resp.read().decode("utf-8"))
            except ssl.SSLError:
                with urllib.request.urlopen(weather_req, context=ssl._create_unverified_context(), timeout=4.0) as w_resp:
                    w_data = json.loads(w_resp.read().decode("utf-8"))

            current = w_data.get("current", {})
            temp = current.get("temperature_2m")
            feels_like = current.get("apparent_temperature")
            humidity = current.get("relative_humidity_2m")
            wind = current.get("wind_speed_10m")
            w_code = current.get("weather_code", 0)
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
        logger.debug("Open-Meteo weather fetch error: %s", err)

    # 2. Fallback to wttr.in
    try:
        wttr_url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
        wttr_req = urllib.request.Request(wttr_url, headers={"User-Agent": "DeskBot/1.0"})
        try:
            with urllib.request.urlopen(wttr_req, context=ssl_ctx, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except ssl.SSLError:
            with urllib.request.urlopen(wttr_req, context=ssl._create_unverified_context(), timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

        current = data["current_condition"][0]
        area = data.get("nearest_area", [{}])[0]
        area_name = area.get("areaName", [{}])[0].get("value", city)
        country_name = area.get("country", [{}])[0].get("value", "")

        return {
            "city": area_name,
            "country": country_name,
            "temperature_c": float(current.get("temp_C", 0)),
            "feels_like_c": float(current.get("FeelsLikeC", 0)),
            "humidity_percent": float(current.get("humidity", 0)),
            "wind_speed_kmh": float(current.get("windspeedKmph", 0)),
            "condition": current.get("weatherDesc", [{}])[0].get("value", "Partly cloudy"),
        }
    except Exception as wttr_err:
        logger.debug("wttr.in fallback error: %s", wttr_err)

    return {"error": f"Could not retrieve weather for '{city}'."}


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
