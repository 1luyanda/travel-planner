# Travel Planner Backend

## Setup

1. Install dependencies:

   ```powershell
   python3.13.exe -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and configure Cosmos DB:

   - `COSMOS_CONNECTION_STRING` — the PRIMARY CONNECTION STRING.
   - `COSMOS_DATABASE=TravelPlaner` — spelling and case matter.

   The backend uses the fixed `origins` and `flights` container names.

3. Start FastAPI:

   ```powershell
   python3.13.exe -m uvicorn backend.main:app --reload
   ```

API documentation is available at `http://localhost:8000/docs`.

## Endpoints

- `GET /api/health`
- `GET /api/origins?q=zag&country=HR`
- `GET /api/origins/{origin_id}`
- `GET /api/flights?origin_id=zagreb-hr&max_price=300`

Example request:

```http
GET /api/flights?origin_id=zagreb-hr&departure_date=2026-09-18&return_date=2026-09-22&max_price=300&max_changeovers=1
```

## Integration placeholders

- The agent developer can convert user messages into `FlightQuery` fields
  before calling the candidate service.
- The ranking developer can pass `CandidateResponse.candidates` into their
  algorithm.
- A final recommendations endpoint should be added when the agent and ranking
  implementations are merged.
- Authentication and authorization are not implemented yet.
