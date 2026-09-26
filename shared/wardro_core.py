r"""
HTTP client wrapper for the weather functions that uses urllib instead of the 
"requests" library (sends requests out and reads responses).
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import json
import urllib.parse
import urllib.request
import urllib.error
# ── (Optional) corporate SSL — only needed if you hit certificate errors ──
# On a corporate machine behind SSL inspection, Python's bundled certificates
# may not include the company's root CA, so HTTPS calls fail with a cert error.
# If (and only if) that happens: `pip install truststore` and uncomment the two
# lines below — they make Python trust the OS certificate store.
# import truststore
# truststore.inject_into_ssl()
 
# ── Stdlib HTTP (urllib) — replaces the third-party `requests` library ──
# A tiny stand-in for the one requests feature we used: SESSION.get(url, params,
# timeout) returning an object with .json() / .raise_for_status() / .status_code.
# This way the 4 weather functions below stay UNCHANGED, but we depend only on
# Python's built-in urllib — nothing to pip-install.
class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
    def json(self):
        return json.loads(self._body)
    def raise_for_status(self):
        if self.status_code >= 400:
            raise urllib.error.URLError(f"HTTP {self.status_code}")


class _StdlibSession:
    def get(self, url, params=None, timeout=10):
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "wardro/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return _Resp(r.status, r.read().decode())
        except urllib.error.HTTPError as e:            # 404/500/... -> keep the code
            return _Resp(e.code, e.read().decode() if e.fp else "")


SESSION = _StdlibSession()
TIMEOUT = 10  # seconds

# The database is a single file that lives right next to this script.
# SQLite is "serverless": there's no separate database program to install or
# run — the whole database is just this one file on disk.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "wardro.db"
 
 
# ---------------------------------------------------------------------------
# LAYER 1: THE CLOTHING LOGIC
# ---------------------------------------------------------------------------
def outfit_advice(temp_f: float) -> str:
    """Map a temperature in Fahrenheit to an outfit recommendation.
 
    This is a 'pure' function: same input -> same output, no API calls.
    That makes it trivial to test (see test_wardro.py).
    """
    if temp_f < 40:
        return ("\U0001F976 Bundle up. Thick jacket plus accessories to trap heat: "
                "beanie, scarf, and gloves.")
    elif temp_f < 60:
        return "\U0001F9E5 Chilly. Throw on a sweater."
    elif temp_f < 70:
        return "\U0001F9E5 Cool. A long-sleeve shirt or a thin jacket like a windbreaker."
    elif temp_f < 80:
        return "\U0001F455 Mild and pleasant. A t-shirt with a light layer you can take off."
    elif temp_f < 90:
        return "\U0001F455 Warm. Short-sleeve shirt weather."
    elif temp_f < 100:
        return "\U0001FA73 Hot. Short-sleeve shirt and shorts. Stay hydrated."
    else:
        return ("\U0001F975 Dangerously hot (100°F+). Best to skip outdoor activity "
                "and stay cool indoors to avoid heatstroke.")
 
 
# A small lookup so we can show a friendly description of the sky.
# Open-Meteo returns a numeric "weather_code" (WMO standard); these are the common ones.
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Violent rain showers",
    85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ hail",
}
 
 
# ---------------------------------------------------------------------------
# LAYER 1.5: SQLite DB
# ---------------------------------------------------------------------------
# SQLite vocabulary in the order to be used:
#   connection = sqlite3.connect(file)  -> opens (or creates) the database file.
#   .execute("SQL", params)             -> runs one SQL statement.
#   ? placeholders                      -> safe way to insert values (see below).
#   .commit()                           -> SAVE. Without it, writes are discarded.
#   .fetchall()                         -> read all rows a SELECT returned.
#   .close()                            -> release the file.
# The four basic operations (CRUD): CREATE/INSERT (write), SELECT (read),
# UPDATE (change), DELETE (remove). We use CREATE TABLE, INSERT, and SELECT.

def init_db():
    """Create the 'searches' table if it doesn't exist yet.

    Safe to call on every startup: 'IF NOT EXISTS' creates the table the first
    time and does nothing on later runs.
    """
    # sqlite3.connect(DB_PATH) will open/create the .db file.
    conn = sqlite3.connect(DB_PATH)
    # create table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS searches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,  -- unique row id, auto-numbered
            searched_at TEXT    NOT NULL,                   -- timestamp as text
            location    TEXT    NOT NULL,
            temp_f      REAL    NOT NULL,                   -- REAL = a decimal number
            advice      TEXT    NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_search(location: str, temp_f: float, advice: str):
    """INSERT one row recording a lookup.

    SECURITY NOTE — the single most important SQLite habit: pass values as a
    tuple and use ? placeholders. NEVER build SQL with f-strings/+ and user
    input. The ? form lets SQLite handle escaping, preventing SQL injection.
    """
    conn = sqlite3.connect(DB_PATH)
    # stop SQL injection by passing values as a separate tuple without gluing
    # user input into the SQL string. 
    # NOTE: ? are the placeholders.
    conn.execute(
        "INSERT INTO searches (searched_at, location, temp_f, advice) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), location, temp_f, advice),
    )
    # save the write 
    conn.commit() 
    conn.close()


def get_history(limit: int = 10):
    """SELECT the most recent lookups, newest first.

    row_factory = sqlite3.Row lets us read columns by name (row["location"]).
    ORDER BY id DESC = newest first; LIMIT caps how many rows come back.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # read the history.
    rows = conn.execute(
        "SELECT searched_at, location, temp_f, advice FROM searches ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# LAYER 2: THE API CALLS
# ---------------------------------------------------------------------------
def geocode_zip(zip_code: str):
    """US zip code -> (lat, lon, label) using Zippopotam.us.
 
    NOTE the PATH PARAMETER: the zip is part of the URL path itself, not a
    query string. https://api.zippopotam.us/us/78701
    """
    url = f"https://api.zippopotam.us/us/{zip_code}"
    resp = SESSION.get(url, timeout=TIMEOUT)
    if resp.status_code == 404:
        raise ValueError(f"No US location found for zip '{zip_code}'.")
    resp.raise_for_status()  # raise on any other HTTP error (500, etc.)
    data = resp.json()
    place = data["places"][0]
    lat = float(place["latitude"])
    lon = float(place["longitude"])
    label = f"{place['place name']}, {place['state abbreviation']} {data['post code']}"
    return lat, lon, label
 
 
def geocode_city(city: str, state: str = ""):
    """City (+ optional state) -> (lat, lon, label) using Open-Meteo Geocoding.
 
    NOTE the QUERY PARAMETERS: everything after "?" — name, count, language.
    requests builds that query string for us from the params= dict.
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city, "count": 10, "language": "en", "format": "json"}
    resp = SESSION.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        raise ValueError(f"Couldn't find a city called '{city}'.")
 
    # If the user gave a state, prefer the match whose admin1 (state/region)
    # matches it. Otherwise just take the top result.
    chosen = results[0]
    if state:
        s = state.strip().lower()
        for r in results:
            admin1 = (r.get("admin1") or "").lower()
            if s == admin1 or s == (r.get("admin1_id") and "") or admin1.startswith(s):
                chosen = r
                break
 
    lat = chosen["latitude"]
    lon = chosen["longitude"]
    parts = [chosen["name"], chosen.get("admin1", ""), chosen.get("country", "")]
    label = ", ".join(p for p in parts if p)
    return lat, lon, label
 
 
def get_current_weather(lat: float, lon: float):
    """(lat, lon) -> dict of current conditions from Open-Meteo Forecast.
 
    The 'current' query parameter is a COMMA-SEPARATED LIST of the variables we
    want. We also ask the API to do unit conversion for us (Fahrenheit, mph)
    via temperature_unit / wind_speed_unit params — no math needed on our end.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
    }
    resp = SESSION.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["current"]
 
 
def get_hourly_forecast(lat: float, lon: float, date: str, hour: int) -> dict:
    """Fetch forecast conditions for a specific date and hour.

    Uses the same Open-Meteo endpoint as get_current_weather, but requests
    hourly data instead of current. The API returns arrays of hourly values
    for the next 7 days; we find the matching time slot and return it.

    Args:
        lat: Latitude.
        lon: Longitude.
        date: ISO date string like "2026-06-17".
        hour: Hour of day, 0-23 (e.g. 9 = 9:00 AM), in the LOCAL time of the
            location being queried (see "timezone": "auto" below).

    Returns:
        Dict with temp_f, feels_like_f, humidity, wind_mph, sky — same
        shape as get_current_weather so outfit_advice works on it.

    Raises:
        ValueError: If the requested date/hour isn't in the forecast range.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        # CRITICAL: without this, Open-Meteo returns hourly timestamps in GMT —
        # asking for "12:00" in California would actually fetch 5 AM conditions.
        # "auto" = timestamps in the local timezone of the lat/lon queried.
        "timezone": "auto",
    }
    resp = SESSION.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()["hourly"]

    # Build the target timestamp string: "2026-06-17T09:00"
    target = f"{date}T{hour:02d}:00"

    if target not in data["time"]:
        raise ValueError(
            f"No forecast available for {target}. "
            f"Range: {data['time'][0]} to {data['time'][-1]}"
        )

    idx = data["time"].index(target)
    return {
        "temperature_2m": data["temperature_2m"][idx],
        "apparent_temperature": data["apparent_temperature"][idx],
        "relative_humidity_2m": data["relative_humidity_2m"][idx],
        "weather_code": data["weather_code"][idx],
        "wind_speed_10m": data["wind_speed_10m"][idx],
    }
