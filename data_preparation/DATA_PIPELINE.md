# Pull, filter, and load ranking data

This is the data path for the travel planner. **APIs are only used here.** Ranking and the frontend then **query Cosmos** ([COSMOS.md](COSMOS.md)).

```text
Travelpayouts + Open-Meteo + REST Countries
        ↓  destination_pipeline.py
normalized_destinations.json
        ↓  fill_missing_data.py     (offline)
        ↓  check_missing_data.py    (offline)
        ↓  load_to_cosmos.py
Cosmos: origins + flights
        ↓  query_cosmos.py / backend
App search: city + country → cheap flights
```

`normalized_destinations.json` is written **on your machine** when you run the pipeline. It is **not in git**. `Real_data/` and `mock_data/*.json` are gitignored. Ranking and the frontend query **Cosmos**, not a JSON file.

---

## 1. Pull from APIs — `destination_pipeline.py`

Calls:

| API | What we take |
|---|---|
| Travelpayouts | Round-trip prices, dates, duration, airline, origin/destination IATA |
| Open-Meteo | Weather **averages** for the travel dates (max/min temp, rain chance, sunshine). No daily arrays, no wind |
| REST Countries | Country name, region, flag |

Writes **`normalized_destinations.json`** (nested records: `origin`, `flight`, `destination`, `weather`, `country`). That is the only JSON the later scripts need.

Optional extra dumps (`travelpayouts_*.json`, `open_meteo_*.json`, `rest_countries.json`) are debug leftovers. Ranking does not use them.

### Setup

`.env` (never commit):

```env
TRAVELPAYOUTS_TOKEN=
REST_COUNTRIES_API_KEY=
```

Optional:

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

## 4. Load into Cosmos — `load_to_cosmos.py`

Flattens each nested record into:

- **`origins`**: one document per city + country (`zagreb-hr`, `london-gb`)
- **`flights`**: one document per trip, partition key `/origin_id`

```powershell
python data_preparation/load_to_cosmos.py mock_data
python data_preparation/load_to_cosmos.py Real_data
```

Needs `COSMOS_CONNECTION_STRING` and `COSMOS_DATABASE=TravelPlaner` in `.env`. How ranking should query after this: **[COSMOS.md](COSMOS.md)**. Demo: `python data_preparation/query_cosmos.py`.

---

## What teammates should ignore

| Path | Why |
|---|---|
| `.env` | Tokens and Cosmos keys |
| `Real_data/` | Local reload JSON; Cosmos already holds the loaded set |
| `mock_data/*.json` | Local pipeline output, not in git |
