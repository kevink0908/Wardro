r"""
Description: Wardro.py is a tiny weather-based outfit advisor.
 
Chaining API calls:
  1. A GEOCODING api: turns "Austin, Texas" or zip "78701" into latitude/longitude.
       - City+state  -> Open-Meteo Geocoding:  https://geocoding-api.open-meteo.com/v1/search
       - US zip code -> Zippopotam.us:          https://api.zippopotam.us/us/{zip}
 
  2. A WEATHER api: turns latitude/longitude into the current temperature.
       - Open-Meteo Forecast:  https://api.open-meteo.com/v1/forecast
 
NOTE: The output of the geocoding API call becomes the input to the weather API call.
 
How to Run:   python Wardro.py    (then open the local URL it prints)
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import requests
import gradio as gr
import urllib3
 
# A shared requests.Session reuses the underlying TCP connection across calls —
# a tiny performance win and a good habit. timeout= prevents the app from
# hanging forever if a server is slow.
SESSION = requests.Session()
SESSION.verify = False
TIMEOUT = 10  # seconds
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# The database is a single file that lives right next to this script.
# SQLite is "serverless": there's no separate database program to install or
# run — the whole database is just this one file on disk.
DB_PATH = Path(__file__).with_name("wardro.db")
 
 
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
# LAYER 1.5: THE DATABASE (SQLite) — persist every lookup so we have a history
# ---------------------------------------------------------------------------
# SQLite vocabulary, in the order you use it:
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
    conn = sqlite3.connect(DB_PATH)
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
    conn.execute(
        "INSERT INTO searches (searched_at, location, temp_f, advice) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), location, temp_f, advice),
    )
    conn.commit()  # without this line, nothing is actually saved
    conn.close()


def get_history(limit: int = 10):
    """SELECT the most recent lookups, newest first.

    row_factory = sqlite3.Row lets us read columns by name (row["location"]).
    ORDER BY id DESC = newest first; LIMIT caps how many rows come back.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
 
 
# ---------------------------------------------------------------------------
# LAYER 3: Chaining API Calls + Error Handling
# ---------------------------------------------------------------------------
def recommend(location: str, mode: str) -> str:
    """Top-level handler the Gradio button calls.
 
    'mode' is "City + State" or "Zip code". Returns a Markdown string.
    All network/JSON errors are caught and turned into a friendly message so
    the app never crashes on bad input.
    """
    location = (location or "").strip()
    if not location:
        return "Please enter a location first."
 
    try:
        # Step 1: location text  ->  latitude/longitude
        if mode == "Zip code":
            lat, lon, label = geocode_zip(location)
        else:
            # Allow "Austin, TX" or "Austin, Texas" or just "Austin".
            if "," in location:
                city, state = location.split(",", 1)
            else:
                city, state = location, ""
            lat, lon, label = geocode_city(city.strip(), state.strip())
 
        # Step 2: latitude/longitude  ->  current weather
        cur = get_current_weather(lat, lon)
        temp = cur["temperature_2m"]
        feels = cur.get("apparent_temperature", temp)
        humidity = cur.get("relative_humidity_2m")
        wind = cur.get("wind_speed_10m")
        sky = WEATHER_CODES.get(cur.get("weather_code"), "—")
 
        # Step 3: temperature  ->  outfit advice
        advice = outfit_advice(temp)

        # Step 4: persist this lookup to the database so it shows in history.
        save_search(label, temp, advice)
 
        return (
            f"### \U0001F4CD {label}\n"
            f"**{temp:.0f}°F** (feels like {feels:.0f}°F) · {sky}\n\n"
            f"Humidity {humidity}%  ·  Wind {wind:.0f} mph\n\n"
            f"---\n\n"
            f"### What to wear\n{advice}"
        )
 
    except ValueError as e:
        # Our own "not found" errors — show the message as-is.
        return f"⚠️ {e}"
    except requests.RequestException as e:
        # Network/HTTP problems (no internet, server down, timeout).
        return f"⚠️ Couldn't reach the weather service: {e}"
    except Exception as e:
        return f"⚠️ Something went wrong: {e}"
 
 
def load_history():
    """Read recent searches from the DB and shape them for a Gradio table.

    gr.Dataframe wants a plain list-of-lists (one inner list per row), so we
    convert each sqlite3.Row into [when, location, temp, advice].
    """
    rows = get_history(limit=10)
    return [
        [r["searched_at"], r["location"], f"{r['temp_f']:.0f}°F", r["advice"]]
        for r in rows
    ]


def respond(location: str, mode: str):
    """UI handler: run the recommendation, then return BOTH the advice text and
    the refreshed history table. Gradio sends each returned value to the
    matching component listed in outputs=[...]."""
    md = recommend(location, mode)
    return md, load_history()


# ---------------------------------------------------------------------------
# LAYER 4: Building web interface via Gradio
# ---------------------------------------------------------------------------
def build_ui():
    with gr.Blocks(title="Wardro", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "# \U0001F9E5 Wardro\n"
            "Tell me where you are and I'll tell you what to wear, based on today's weather."
        )
        with gr.Row():
            mode = gr.Radio(
                choices=["City + State", "Zip code"],
                value="City + State",
                label="Look up by",
            )
        location = gr.Textbox(
            label="Location",
            placeholder="e.g. Austin, TX   (or switch to Zip and enter 78701)",
        )
        go = gr.Button("What should I wear?", variant="primary")
        output = gr.Markdown()

        # A collapsible panel showing past lookups pulled from the database.
        with gr.Accordion("📜 Search history (from the database)", open=False):
            history = gr.Dataframe(
                headers=["When", "Location", "Temp", "Advice"],
                interactive=False,
                wrap=True,
            )
            refresh = gr.Button("Refresh history")

        # On click, call respond(location, mode) and send its TWO return values
        # into [output, history]. Pressing Enter in the box does the same.
        go.click(fn=respond, inputs=[location, mode], outputs=[output, history])
        location.submit(fn=respond, inputs=[location, mode], outputs=[output, history])

        # The refresh button just re-reads the DB into the table; demo.load runs
        # once on page open so history is populated at startup.
        refresh.click(fn=load_history, inputs=None, outputs=history)
        demo.load(fn=load_history, inputs=None, outputs=history)
 
        gr.Markdown(
            "<sub>Weather by Open-Meteo · Zip lookup by Zippopotam.us · both free, no API key.</sub>"
        )
    return demo
 
 
if __name__ == "__main__":
    init_db()  # make sure the table exists before the app starts
    build_ui().launch()