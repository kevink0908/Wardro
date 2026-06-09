# Wardro

A tiny Gradio app that tells you what to wear based on the current weather at any
location. Built as a hands-on way to learn how APIs actually work before moving
on to MCP servers.

## Run it

```bash
pip install -r requirements.txt
python Wardro.py
```

Gradio prints a local URL (like `http://127.0.0.1:7860`). Open it, enter a
location, and get an outfit recommendation.

```bash
python test_wardro.py   # check the clothing thresholds (no internet needed)
```

## The APIs (all free, no API key)

Wardro calls two kinds of API, in two steps: first turn your location into
coordinates (_geocoding_), then turn coordinates into weather.

| Step                   | API                  | Endpoint                                         |
| ---------------------- | -------------------- | ------------------------------------------------ |
| City + State → lat/lon | Open-Meteo Geocoding | `https://geocoding-api.open-meteo.com/v1/search` |
| US Zip → lat/lon       | Zippopotam.us        | `https://api.zippopotam.us/us/{zip}`             |
| lat/lon → weather      | Open-Meteo Forecast  | `https://api.open-meteo.com/v1/forecast`         |

- **Endpoint** — base URL + path (`/v1/forecast`). The address you send a request to.
- **Path parameter** — a value baked into the URL path. Zippopotam's zip is one:
  `…/us/78701`.
- **Query parameter** — a `key=value` after `?`, joined by `&`. Open-Meteo's
  `latitude`, `longitude`, and `current` are query parameters. In the code,
  `requests` builds this string from the `params={...}` dict.
- **What "calling" it means** — `requests.get()` sends an HTTP request; the
  server responds with a **status code** (200 OK, 404 not found, …) and a JSON
  **body**; `.json()` parses that body into a Python dict.

## How the code is organized

The file is split into four layers so each concept stands alone:

1. **Clothing logic** (`outfit_advice`) — pure function, temperature → advice. No internet, fully testable.
2. **API calls** (`geocode_zip`, `geocode_city`, `get_current_weather`) — the actual HTTP requests.
3. **Glue** (`recommend`) — chains location → coordinates → weather → advice, with friendly error handling.
4. **UI** (`build_ui`) — the Gradio interface.

## Where this is headed (MCP)

Later you can wrap your wardrobe in an MCP server — users register garments (by
link or photo), and the assistant suggests specific items you own for the
weather _and_ the occasion (gym, dinner, festival). Wardro's layered structure
leaves room for that: the outfit logic becomes "given weather + occasion +
available garments, pick an outfit."
