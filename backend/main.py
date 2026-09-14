import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Resolve the repo root from this file so the mock JSON path stays correct
# whether uvicorn is started from backend/ or another working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "mock_data" / "normalized_destinations.json"

app = FastAPI()

# Vite serves the UI on 5173, so only that origin is allowed to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    """Simple liveness check used to confirm the API is running."""
    return {"status": "ok"}


@app.get("/api/destinations")
def destinations():
    """Return the full normalised mock JSON object for the React app."""
    if not DATA_PATH.is_file():
        raise HTTPException(status_code=500, detail="Destination data file is missing.")

    try:
        with DATA_PATH.open(encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Destination data file is invalid JSON.")
    except OSError:
        raise HTTPException(status_code=500, detail="Destination data file could not be read.")
