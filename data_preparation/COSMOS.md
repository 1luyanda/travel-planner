# Accessing travel data in Cosmos DB

Ranking, backend, and frontend must **query Cosmos**. Do not download `Real_data/normalized_destinations.json` (~148 MB) in the browser or as one Cosmos document (the item limit is 2 MB).

Local JSON is only the **reload source**. `load_to_cosmos.py` splits it into small documents. After a load, the app talks to Cosmos only.

Working demo: `python data_preparation/query_cosmos.py` (city + country → cheapest flights).

---

## What is stored

| Azure resource | Value |
|---|---|
| API | Azure Cosmos DB for **NoSQL** |
| Account | `team4travelcosmos` (UK South, serverless) |
| Database | **`TravelPlaner`** (spelling and case both matter) |
| Container `origins` | One document per origin **city + country**. Partition key **`/id`** |
| Container `flights` | One document per trip. Partition key **`/origin_id`** |

Loaded set: **1,745** origin cities, **87,697** flights.

City names that exist in more than one country are different origins:

- London, United Kingdom → `london-gb`
- London, Canada → `london-ca`
- Zagreb, Croatia → `zagreb-hr`

Every airport in that city sits in the **same** origin (Zagreb / ZAG together). Do not partition by airport code.

---

## Secrets (backend only)

Add to **`.env`** (never commit, never send to the browser):

```env
COSMOS_CONNECTION_STRING=AccountEndpoint=https://team4travelcosmos.documents.azure.com:443/;AccountKey=...
COSMOS_DATABASE=TravelPlaner
```

Copy **PRIMARY CONNECTION STRING** from Cosmos → Keys (the full `AccountEndpoint=...;AccountKey=...` line, not the URL alone).

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

---

## How the app should query

Two steps, always.

### 1. Resolve the origin city → `origin_id`

User types a city and a country (name **or** ISO code, e.g. `Zagreb` / `HR` or `Zagreb` / `Croatia`).

Case-insensitive match on `origins`:

```sql
SELECT * FROM c
WHERE STRINGEQUALS(c.city, @city, true)
  AND (
    STRINGEQUALS(c.country, @country, true)
    OR STRINGEQUALS(c.country_code, @country, true)
  )
```

Parameters: `@city`, `@country`.

This container is small (~1,745 items). Cross-partition here is fine.

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
  "flight_count": 154
}
```

| Field | Meaning |
|---|---|
| `id` | Slug of city + lowercase country code. This **is** `origin_id` on flights |
| `city` | Display / search name |
| `country` | Country name (`Croatia`) |
| `country_code` | ISO alpha-2 (`HR`) |
| `airports` | Airport IATA codes in that city |
| `city_iata` | City IATA codes |
| `flight_count` | Count at last load (informational; query `flights` for the live list) |

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
| `destination_city` / `destination_country` / `destination_country_code` | Result cards |
| `destination_iata` / `destination_airport` / `airport_name` | Airport labels |
| `price_eur` / `currency` | Ranking (cheapest first). `price_eur` is a number |
| `departure_at` / `return_at` | Dates (ISO-8601) |
| `outbound_stops` / `return_stops` | Stops; `0` is a real nonstop |
| `duration_minutes` | Total trip time |
| `airline_code` | Carrier |
| `temp_max_c` / `temp_min_c` / `rain_pct` / `sunshine_hours` | Weather **averages** for the travel dates (not a daily forecast) |
| `latitude` / `longitude` | Map pin |

There is no nested `flight` / `weather` object in Cosmos. Fields are flat. Rain/temp of `0` can be real weather. A price or duration of `0` is not a usable offer.

---

## Suggested backend endpoints

Frontend never talks to Cosmos. Example API:

1. **`GET /origins?q=zag`**  
   Autocomplete from `origins` (`CONTAINS` on `city`). Return `id`, `city`, `country`, `country_code`.

2. **`GET /origins/{origin_id}`**  
   One origin document (`read_item` with `partition_key=origin_id`).

3. **`GET /flights?origin_id=zagreb-hr&sort=price`**  
   Partition query on `flights`. Default sort: `price_eur` ascending. Optional `max_price`, `min_temp`, `country`.

That is the whole ranking read path.

---

## What not to do

- Do not upload `normalized_destinations.json` in Data Explorer.
- Do not `SELECT * FROM c` on `flights` without `origin_id` (cross-partition over 87k items).
- Do not load all origins’ flights to pick one city in the client.
- Do not put `COSMOS_CONNECTION_STRING` in frontend env / git.
- Database name is **`TravelPlaner`**, not `travelplanner`. Wrong name → `Owner resource does not exist`.

---

## Reloading data

From a machine that has the JSON and `.env`:

```powershell
pip install azure-cosmos
python data_preparation/load_to_cosmos.py mock_data
python data_preparation/load_to_cosmos.py Real_data
```

`Real_data` takes on the order of 15–20 minutes (upsert with 429 retry). Upsert **overwrites the same ids**; it does not delete leftover mock ids that never appear in Real_data. For a clean Zagreb set, delete `flights` items for `origin_id = zagreb-hr` then reload, or reload after clearing the containers in the portal.

Try a lookup:

```powershell
python data_preparation/query_cosmos.py
```

Type `Zagreb` then `HR` or `Croatia`. You should see trips from that origin, cheapest first.

---

## Local JSON (reload only)

| File | Role |
|---|---|
| `mock_data/normalized_destinations.json` | Tiny test load |
| `Real_data/normalized_destinations.json` | Full reload (gitignored; keep on disk only) |

Nested source records (`origin`, `flight`, `destination`, `weather`, `country`) are flattened by `load_to_cosmos.py`. Ranking code after a load should not parse that JSON.

See `MOCK_DATA.md` for the nested file shape used by the pipeline.
