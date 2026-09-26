"""
mcp-servers/wardro-weather/server.py — weather MCP tools, HAND-ROLLED (no FastMCP).

Same 6 tools as before, but the MCP protocol is implemented from scratch in
shared/mcp_server.py so you can see what FastMCP was doing for you.

RUN: python mcp-servers/wardro-weather/server.py   ->  http://127.0.0.1:8000/mcp
     (hand-rolled Streamable HTTP via shared/mcp_server.py — no FastMCP)
CORE LOGIC lives in shared/wardro_core.py; this file is only the MCP "front door".
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from shared.mcp_server import MiniMCP          # <-- our from-scratch MCP server (no `mcp` lib)
from shared import wardro_core as Wardro

mcp = MiniMCP("wardro")
Wardro.init_db()


@mcp.tool()
def geocode(location: str, method: str = "city") -> dict:
    """Convert a location string into geographic coordinates (1 API call).

    Args:
        location: A US city (e.g. "Austin, TX") when method is "city",
            or a US ZIP code (e.g. "78701") when method is "zip".
        method: Either "city" or "zip".
    Returns: dict with lat, lon, and a human-readable label.
    """
    try:
        if method == "zip":
            lat, lon, label = Wardro.geocode_zip(location)
        else:
            city, state = (location.split(",", 1) + [""])[:2] if "," in location else (location, "")
            lat, lon, label = Wardro.geocode_city(city.strip(), state.strip())
        return {"lat": lat, "lon": lon, "label": label}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Geocoding failed: {e}"}


@mcp.tool()
def get_weather(lat: float, lon: float) -> dict:
    """Fetch CURRENT weather for coordinates (1 API call).

    Args: lat (e.g. 30.27), lon (e.g. -97.74).
    Returns: dict with temp_f, feels_like_f, humidity, wind_mph, sky.
    """
    try:
        cur = Wardro.get_current_weather(lat, lon)
        return {
            "temp_f": cur["temperature_2m"],
            "feels_like_f": cur.get("apparent_temperature", cur["temperature_2m"]),
            "humidity": cur.get("relative_humidity_2m"),
            "wind_mph": cur.get("wind_speed_10m"),
            "sky": Wardro.WEATHER_CODES.get(cur.get("weather_code"), "Unknown"),
        }
    except Exception as e:
        return {"error": f"Weather fetch failed: {e}"}


@mcp.tool()
def get_forecast(lat: float, lon: float, date: str, hour: int) -> dict:
    """Fetch FORECAST weather for a future date/hour (1 API call).

    Use this instead of get_weather when the user asks about a future time.
    Args:
        lat, lon: coordinates. date: ISO date "2026-06-17" (up to 7 days out).
        hour: 0-23 (9 = 9AM, 17 = 5PM).
    Returns: dict with temp_f, feels_like_f, humidity, wind_mph, sky.
    """
    try:
        fc = Wardro.get_hourly_forecast(lat, lon, date, hour)
        return {
            "temp_f": fc["temperature_2m"],
            "feels_like_f": fc.get("apparent_temperature", fc["temperature_2m"]),
            "humidity": fc.get("relative_humidity_2m"),
            "wind_mph": fc.get("wind_speed_10m"),
            "sky": Wardro.WEATHER_CODES.get(fc.get("weather_code"), "Unknown"),
        }
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Forecast fetch failed: {e}"}


@mcp.tool()
def outfit_advice(temp_f: float) -> str:
    """Get a clothing recommendation from a temperature (pure logic, no API).

    Args: temp_f (Fahrenheit). Returns: a short outfit recommendation string.
    """
    return Wardro.outfit_advice(temp_f)


@mcp.tool()
def save_search(location: str, temp_f: float, advice: str) -> dict:
    """Save one outfit lookup to the database (1 DB write).

    Args: location label, temp_f, advice string. Returns: confirmation dict.
    """
    try:
        Wardro.save_search(location, temp_f, advice)
        return {"status": "saved", "location": location}
    except Exception as e:
        return {"error": f"Failed to save: {e}"}


@mcp.tool()
def get_search_history(limit: int = 10) -> list:
    """Return the most recent outfit lookups, newest first (1 DB read).

    Args: limit (default 10). Returns: list of dicts (searched_at, location, temp_f, advice).
    """
    return [dict(row) for row in Wardro.get_history(limit)]


if __name__ == "__main__":
    # Same tools, two transports:
    #   python server.py          -> Streamable HTTP at http://127.0.0.1:8000/mcp  (used by host/backend.py)
    #   python server.py --stdio  -> stdio pipes  (used by Claude Desktop, which launches this script itself)
    if "--stdio" in sys.argv:
        mcp.run()
    else:
        mcp.run_http(port=8000)
