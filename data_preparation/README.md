# Data preparation

Pull APIs, clean ranking JSON, load Cosmos, and query cheap flights. **APIs are only used here.** Ranking, backend, and frontend then **query Cosmos** — not the JSON file.

Still **two containers**: `origins` + `flights`. City pictures were added onto **`origins`**. There is no `destinations` container.

| File | Role |
|---|---|
| `destination_pipeline.py` | Travelpayouts + Open-Meteo + REST Countries |
| `fill_missing_data.py` | Offline fill of reconstructable holes |
| `check_missing_data.py` | Offline ranking quality check |
| `load_city_photos.py` | Pexels photo URLs → `normalized_destinations.json` |
| `load_to_cosmos.py` | JSON → `origins` + `flights` (photos on origins) |
| `query_cosmos.py` | Demo: city + country → cheapest trips |

`.env`, `mock_data/`, and `Real_data/` stay at the **repo root**. Run scripts from there:

```powershell
python data_preparation/destination_pipeline.py
python data_preparation/fill_missing_data.py Real_data
python data_preparation/check_missing_data.py Real_data
python data_preparation/load_city_photos.py Real_data
python data_preparation/load_to_cosmos.py Real_data
python data_preparation/query_cosmos.py
```

---

## City pictures on `origins`

Pexels landscape URLs (`photo_url`, `photo_url_small`) are stored on each **origin city** document. Same city + country as before (`zagreb-hr`, `rome-it`, `london-gb`).

For a flight card, look up the destination city **in `origins`**. A trip to Rome uses `destination_city` + `destination_country_code` (`Rome` / `IT`) against `origins`. Rome is also an origin, so that document has the picture.

### Example: photo for a flight to Rome

Flight document (no photo fields):

```json
{
  "destination_city": "Rome",
  "destination_country": "Italy",
  "destination_country_code": "IT"
}
```

Same query you already use to resolve a departure city:

```sql
SELECT c.photo_url, c.photo_url_small FROM c
WHERE STRINGEQUALS(c.city, @city, true)
  AND (
    STRINGEQUALS(c.country, @country, true)
    OR STRINGEQUALS(c.country_code, @country, true)
  )
```

Parameters: `@city` = `"Rome"`, `@country` = `"IT"` (or `"Italy"`).

Or point-read the slug:

```python
origins.read_item(item="rome-it", partition_key="rome-it")
# item["photo_url"]
# item["photo_url_small"]
```

Do **not** call Pexels from the browser or backend. Origins is small (~1,745); cache it and join in the backend.

---

## Pipeline

```text
Travelpayouts + Open-Meteo + REST Countries
        ↓  destination_pipeline.py
normalized_destinations.json
        ↓  fill_missing_data.py     (offline)
        ↓  check_missing_data.py    (offline)
        ↓  load_city_photos.py      (Pexels URLs on destination in JSON)
        ↓  load_to_cosmos.py
Cosmos: origins + flights
        ↓  query_cosmos.py / backend
App search: city + country → cheap flights
            destination_city → origins.city → photo_url
```

`normalized_destinations.json` is written **on your machine**. It is **not in git**. `Real_data/` and `mock_data/*.json` are gitignored. After a load, the app talks to Cosmos only. Do not download the ~148 MB JSON in the browser (Cosmos item limit is 2 MB).

---

## 1. Pull from APIs — `destination_pipeline.py`

| API | What we take |
|---|---|
| Travelpayouts | Round-trip prices, dates, duration, airline, origin/destination IATA |
| Open-Meteo | Weather **averages** for the travel dates (max/min temp, rain chance, sunshine). No daily arrays, no wind |
| REST Countries | Country name, region, flag |

Writes **`normalized_destinations.json`** (nested records: `origin`, `flight`, `destination`, `weather`, `country`). That is the only JSON the later scripts need.

Optional extra dumps (`travelpayouts_*.json`, `open_meteo_*.json`, `rest_countries.json`) are debug leftovers. Ranking does not use them.

### Setup

`.env` (never commit, never send to the browser):

```env
TRAVELPAYOUTS_TOKEN=
REST_COUNTRIES_API_KEY=

COSMOS_CONNECTION_STRING=AccountEndpoint=https://team4travelcosmos.documents.azure.com:443/;AccountKey=...
COSMOS_DATABASE=TravelPlaner

PEXELS_API_KEY=
PEXELS_API_KEY_2=
PEXELS_API_KEY_3=
PEXELS_API_KEY_4=
PEXELS_API_KEY_5=
PEXELS_API_KEY_6=
PEXELS_API_KEY_7=
PEXELS_API_KEY_8=
PEXELS_API_KEY_9=
PEXELS_API_KEY_10=
```

Copy **PRIMARY CONNECTION STRING** from Cosmos → Keys (the full `AccountEndpoint=...;AccountKey=...` line, not the URL alone).

Optional pipeline knobs:

```env
TRAVEL_ORIGIN=ALL
TRAVEL_DESTINATIONS=BCN,LIS,FCO,ATH,PMI,AGP,NAP,MLA
TRAVEL_CURRENCY=EUR
TRAVEL_DEPARTURE_DATE=2026-09-18
TRAVEL_RETURN_DATE=2026-09-22
TRAVEL_LIMIT=50
MOCK_OUTPUT_DIR=mock_data
```

`TRAVEL_ORIGIN=ALL` (default) uses every flightable city as origin. `TRAVEL_ORIGIN=ZAG` is a small test. Open-Meteo only forecasts about 16 days ahead, so return dates cannot be far in the future.

```powershell
python data_preparation/destination_pipeline.py
```

For the full set, point `MOCK_OUTPUT_DIR` at `Real_data` (or copy the output there). A full pull can take a long time and hits API rate limits.

---

## 2. Fill reconstructable holes — `fill_missing_data.py`

**Offline.** No `.env`, no API calls. Reads the local JSON only.

Does **not** invent prices. Weather `0` is left as a real value.

Fill order:

1. `duration` = outbound + return on the same row
2. Missing outbound/return from duration minus the other leg
3. Reverse origin/destination pair (legs swapped)
4. Other rows with the same origin and destination (prefer same stops)
5. Lat/lon/airport name from the same destination airport IATA
6. Origin city/country from other rows in the same file

```powershell
python data_preparation/fill_missing_data.py mock_data
python data_preparation/fill_missing_data.py Real_data
```

---

## 3. Check ranking quality — `check_missing_data.py`

**Offline.** Prints whether saved flights are usable.

- Required: origin, destination, price, dates, duration, weather averages, coordinates
- Rain/temp/sunshine/stops of **0** are allowed
- Price **0**, duration **0**, or lat+lon both **0** are **not** allowed

```powershell
python data_preparation/check_missing_data.py mock_data
python data_preparation/check_missing_data.py Real_data
python data_preparation/check_missing_data.py Real_data --drop-broken
```

`--drop-broken` removes rows that fail required fields. Last full Real_data check: **87,697** usable flights.

---

## 4. City photos — `load_city_photos.py`

Pexels search for a memorable landscape of each destination city. Writes **`photo_url` and `photo_url_small`** onto each nested `destination` in `normalized_destinations.json`. Then `load_to_cosmos.py` copies those URLs onto matching **`origins`** documents (same city + country).

Needs Pexels keys in `.env` (`PEXELS_API_KEY`, `PEXELS_API_KEY2` or `PEXELS_API_KEY_2`, …). On 429 the script switches key; when every key is limited it saves the JSON and sleeps **1.5 hours**.

```powershell
python data_preparation/load_city_photos.py Real_data
python data_preparation/load_to_cosmos.py Real_data --origins-only
```

Leave off `--max-photos` so every unused Pexels key keeps filling cities. Only add `--max-photos 150` if you want a short test run. Pexels allows about 200 searches per hour.

---

## 5. Load into Cosmos — `load_to_cosmos.py`

Flattens each nested record into:

- **`origins`**: one document per city + country (`zagreb-hr`, `london-gb`), including `photo_url` / `photo_url_small`
- **`flights`**: one document per trip, partition key `/origin_id`

```powershell
python data_preparation/load_to_cosmos.py mock_data
python data_preparation/load_to_cosmos.py Real_data
```

Needs `COSMOS_CONNECTION_STRING` and `COSMOS_DATABASE=TravelPlaner` in `.env`. Demo: `python data_preparation/query_cosmos.py`.

To refresh city photos on `origins` without reloading 87k flights:

```powershell
python data_preparation/load_to_cosmos.py Real_data --origins-only
```

`Real_data` takes on the order of 15–20 minutes (upsert with 429 retry). Upsert **overwrites the same ids**; it does not delete leftover mock ids that never appear in Real_data. For a clean Zagreb set, delete `flights` items for `origin_id = zagreb-hr` then reload, or reload after clearing the containers in the portal.

---

## Cosmos

| Azure resource | Value |
|---|---|
| API | Azure Cosmos DB for **NoSQL** |
| Account | `team4travelcosmos` (UK South, serverless) |
| Database | **`TravelPlaner`** (spelling and case both matter) |
| Container `origins` | One document per origin **city + country**. Partition key **`/id`**. Includes city `photo_url` |
| Container `flights` | One document per trip. Partition key **`/origin_id`** |

Loaded set: **1,745** origin cities, **87,697** flights.

City names that exist in more than one country are different origins:

- London, United Kingdom → `london-gb`
- London, Canada → `london-ca`
- Zagreb, Croatia → `zagreb-hr`

Every airport in that city sits in the **same** origin (Zagreb / ZAG together). Do not partition by airport code.

Python (same helpers as the load/query scripts):

```python
from azure.cosmos import CosmosClient
from data_preparation.load_to_cosmos import cosmos_settings, ORIGINS_CONTAINER, FLIGHTS_CONTAINER

endpoint, account_key, database_name = cosmos_settings()
client = CosmosClient(url=endpoint, credential=account_key)
database = client.get_database_client(database_name)
origins = database.get_container_client(ORIGINS_CONTAINER)
flights = database.get_container_client(FLIGHTS_CONTAINER)
```

Install: `pip install azure-cosmos`.

The UI must call **your backend**. The backend holds the key and runs the queries below. If the key is in JavaScript, anyone can read or wipe the database.

### 1. Resolve the origin city → `origin_id`

User types a city and a country (name **or** ISO code, e.g. `Zagreb` / `HR` or `Zagreb` / `Croatia`).

```sql
SELECT * FROM c
WHERE STRINGEQUALS(c.city, @city, true)
  AND (
    STRINGEQUALS(c.country, @country, true)
    OR STRINGEQUALS(c.country_code, @country, true)
  )
```

Parameters: `@city`, `@country`. This container is small (~1,745 items). Cross-partition here is fine.

If several Londons match the city but not the country, list them and let the user pick. Autocomplete:

```sql
SELECT TOP 10 * FROM c WHERE CONTAINS(c.city, @city, true)
```

Use the returned `id` as `origin_id` (`zagreb-hr`). Do **not** guess from IATA alone if two cities could share a name.

### 2. Load trips for that origin only

Query **`flights` with the partition key** set to `origin_id`. That is the cheap path the mentors wanted: one city’s trips, not a scan of 87k documents.

```sql
SELECT * FROM c WHERE c.origin_id = @origin_id
```

In the SDK pass `partition_key=origin_id` (see `query_cosmos.py`). Do not set `enable_cross_partition_query` for this query.

Sort **cheapest first** in the backend (or `ORDER BY c.price_eur ASC` in Cosmos):

```python
rows.sort(key=lambda row: (row.get("price_eur") is None, row.get("price_eur") or 0))
```

Optional filters on the same partition (still cheap):

```sql
SELECT * FROM c
WHERE c.origin_id = @origin_id
  AND c.price_eur <= @max_price
  AND c.temp_max_c >= @min_temp
```

```sql
SELECT * FROM c
WHERE c.origin_id = @origin_id
  AND STRINGEQUALS(c.destination_country_code, @cc, true)
```

Point read of one trip (needs both id and partition):

```python
flights.read_item(item="ZAG-ROM-2026-09-18", partition_key="zagreb-hr")
```

### 3. Match a destination city to its photo on `origins`

Same query as step 1. See **City pictures on `origins`** at the top.

### Suggested backend endpoints

Frontend never talks to Cosmos.

1. **`GET /origins?q=zag`** — autocomplete (`CONTAINS` on `city`). Return `id`, `city`, `country`, `country_code`, `photo_url`, `photo_url_small`.
2. **`GET /origins/{origin_id}`** — one origin document (`read_item` with `partition_key=origin_id`).
3. **`GET /flights?origin_id=zagreb-hr&sort=price`** — partition query on `flights`. Default sort: `price_eur` ascending. Optional `max_price`, `min_temp`, `country`.

That is the whole ranking read path. For a flight to Rome, photo = origin `rome-it`.

---

## Document shapes

### `origins` (`partition /id`)

```json
{
  "id": "zagreb-hr",
  "city": "Zagreb",
  "country": "Croatia",
  "country_code": "HR",
  "airports": ["ZAG"],
  "city_iata": ["ZAG"],
  "flight_count": 154,
  "photo_url": "https://images.pexels.com/photos/....jpeg",
  "photo_url_small": "https://images.pexels.com/photos/....jpeg"
}
```

| Field | Meaning |
|---|---|
| `id` | Slug of city + lowercase country code. This **is** `origin_id` on flights |
| `city` | Display / search name. Same field used to match a flight's `destination_city` |
| `country` | Country name (`Croatia`) |
| `country_code` | ISO alpha-2 (`HR`) |
| `airports` | Airport IATA codes in that city |
| `city_iata` | City IATA codes |
| `flight_count` | Count at last load (informational; query `flights` for the live list) |
| `photo_url` / `photo_url_small` | City picture. Match a flight's `destination_city` + `destination_country_code` to this origin |

### `flights` (`partition /origin_id`)

```json
{
  "id": "ZAG-ROM-2026-09-18",
  "origin_id": "zagreb-hr",
  "origin_city": "Zagreb",
  "origin_country": "Croatia",
  "origin_country_code": "HR",
  "origin_iata": "ZAG",
  "origin_airport": "ZAG",
  "destination_city": "Rome",
  "destination_country": "Italy",
  "destination_country_code": "IT",
  "destination_iata": "ROM",
  "destination_airport": "FCO",
  "airport_name": "Leonardo da Vinci-Fiumicino Airport",
  "price_eur": 65,
  "currency": "EUR",
  "departure_at": "2026-09-21T15:55:00+02:00",
  "return_at": "2026-09-22T23:50:00+02:00",
  "outbound_stops": 0,
  "return_stops": 0,
  "duration_minutes": 170,
  "outbound_duration_minutes": 85,
  "return_duration_minutes": 85,
  "airline_code": "FR",
  "temp_max_c": 27.8,
  "temp_min_c": 18.75,
  "rain_pct": 13.0,
  "sunshine_hours": 11.96,
  "latitude": 41.794594,
  "longitude": 12.250346
}
```

| Field | Use for |
|---|---|
| `id` | Unique trip id (from the ranking JSON) |
| `origin_id` | **Required** partition key. Always filter on this |
| `origin_*` | Where the user starts |
| `destination_city` / `destination_country` / `destination_country_code` | Result cards. Look this city up in `origins` for `photo_url` |
| `destination_iata` / `destination_airport` / `airport_name` | Airport labels |
| `price_eur` / `currency` | Ranking (cheapest first). `price_eur` is a number |
| `departure_at` / `return_at` | Dates (ISO-8601) |
| `outbound_stops` / `return_stops` | Stops; `0` is a real nonstop |
| `duration_minutes` | Total trip time |
| `airline_code` | Carrier |
| `temp_max_c` / `temp_min_c` / `rain_pct` / `sunshine_hours` | Weather **averages** for the travel dates (not a daily forecast) |
| `latitude` / `longitude` | Map pin |

There is no nested `flight` / `weather` object in Cosmos. Fields are flat. Rain/temp of `0` can be real weather. A price or duration of `0` is not a usable offer. Flight documents do **not** store photos.

---

## Local JSON (reload only)

| File | Role |
|---|---|
| `mock_data/normalized_destinations.json` | Tiny test load |
| `Real_data/normalized_destinations.json` | Full reload (gitignored; keep on disk only) |

Nested source records (`origin`, `flight`, `destination`, `weather`, `country`) are flattened by `load_to_cosmos.py`. Ranking code after a load should not parse that JSON.

Debug leftovers in `mock_data/` (not used by ranking):

| File | What it was |
|---|---|
| `travelpayouts_flights.json` | Raw Travelpayouts offers |
| `travelpayouts_cities.json` | City IATA, coords, timezone |
| `travelpayouts_airports.json` | Airport name, IATA, coords |
| `open_meteo_weather.json` | Daily forecast dump |
| `rest_countries.json` | Country names, codes, flags |

---

## What not to do

- Do not upload `normalized_destinations.json` in Data Explorer.
- Do not `SELECT * FROM c` on `flights` without `origin_id` (cross-partition over 87k items).
- Do not load all origins’ flights to pick one city in the client.
- Do not put `COSMOS_CONNECTION_STRING` or `PEXELS_API_KEY` in frontend env / git.
- Do not query a `destinations` container. Photos are on `origins`. Delete that leftover container in Azure if it is still there.
- Database name is **`TravelPlaner`**, not `travelplanner`. Wrong name → `Owner resource does not exist`.

| Path | Why to ignore |
|---|---|
| `.env` | Tokens and Cosmos keys |
| `Real_data/` | Local reload JSON; Cosmos already holds the loaded set |
| `mock_data/*.json` | Local pipeline output, not in git |
