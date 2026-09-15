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
  Full Cosmos flight documents for display (airline, coordinates, weather, etc.).
- `GET /api/candidates?origin_id=zagreb-hr&max_price=300&max_changeovers=0`  
  Ranking-ready `candidates` plus `rejected` reasons. Use this from ranking/`test.py`.

Example requests:

```http
GET /api/flights?origin_id=zagreb-hr
GET /api/candidates?origin_id=zagreb-hr&max_price=300&max_changeovers=0
```

## Integration placeholders

- The agent developer can convert user messages into `FlightQuery` fields
  before calling the candidate service.
- The ranking developer can pass `CandidateResponse.candidates` into their
  algorithm.
- A final recommendations endpoint should be added when the agent and ranking
  implementations are merged.
- Authentication and authorization are not implemented yet.
