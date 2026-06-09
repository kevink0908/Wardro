# Postman Cheat-Sheet (for the Wardro APIs)

Postman lets you call an API by hand — no code — so you can *see* exactly what
a request and response look like. Keep this open while you experiment.

## The 30-second mental model

A request has four parts. Postman has a tab for each:

| Part | Where in Postman | Example |
|------|------------------|---------|
| **Method** | dropdown left of URL | `GET` (read data), `POST` (send data) |
| **Endpoint** | the URL bar | `https://api.open-meteo.com/v1/forecast` |
| **Query params** | **Params** tab | `latitude=30.27`, `longitude=-97.74` |
| **Headers / Body** | **Headers** / **Body** tabs | auth keys, JSON payloads (not needed for Wardro) |

Hit **Send** → the bottom panel shows the **response body** (JSON) plus the
**status code** (200 = OK) and how long it took.

## Do this first (5 minutes)

1. **New → HTTP Request.** Method stays `GET`.
2. Paste into the URL bar: `https://api.open-meteo.com/v1/forecast`
3. Click the **Params** tab. Add three rows:

   | Key | Value |
   |-----|-------|
   | `latitude` | `30.27` |
   | `longitude` | `-97.74` |
   | `current` | `temperature_2m` |

4. Watch the URL bar rewrite itself to
   `...forecast?latitude=30.27&longitude=-97.74&current=temperature_2m`.
   **That is the query string building itself** — Params rows ARE query params.
5. **Send.** Read the JSON. Find `current.temperature_2m`.

## See path params vs query params

- **Query param** (after `?`): `https://geocoding-api.open-meteo.com/v1/search?name=Austin&count=5`
  In Postman these go in the **Params** tab.
- **Path param** (baked into the URL): `https://api.zippopotam.us/us/78701`
  The `78701` is part of the path — there's nothing to put in Params.

Try both. Notice the zip request has an empty Params tab — that's the tell.

## Chaining requests in Postman (the cool part)

Wardro chains in Python: the geocoding response's lat/lon feed the weather
request. You can do the same in Postman so the two requests talk to each other.

1. Open the **geocoding** request. Go to its **Scripts → Post-response** tab
   (older Postman calls this the **Tests** tab) and paste:

   ```javascript
   const data = pm.response.json();
   const place = data.results[0];
   pm.collectionVariables.set("lat", place.latitude);
   pm.collectionVariables.set("lon", place.longitude);
   ```

   This grabs lat/lon from the response and stores them as variables.

2. In the **weather** request's Params, use those variables with `{{ }}`:

   | Key | Value |
   |-----|-------|
   | `latitude` | `{{lat}}` |
   | `longitude` | `{{lon}}` |
   | `current` | `temperature_2m` |

3. Send the geocoding request first, then the weather request. The second one
   automatically uses the coordinates the first one found.

That's "chaining API calls" demonstrated entirely in Postman — the same idea
your `Wardro.py` does in code.

## Handy

- **Save** requests into a **Collection** ("Wardro") so you don't retype them.
- **Pretty / Raw / Preview** toggles (top-right of the response) change how the
  JSON is displayed.
- The **status code** is your first debugging tool: 200 OK, 404 not found,
  400 bad request (usually a missing/typo'd param), 429 too many requests.

## The three requests to save

```
GET https://geocoding-api.open-meteo.com/v1/search?name=Austin&count=5
GET https://api.zippopotam.us/us/78701
GET https://api.open-meteo.com/v1/forecast?latitude=30.27&longitude=-97.74&current=temperature_2m&temperature_unit=fahrenheit
```
