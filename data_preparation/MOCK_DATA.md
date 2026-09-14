# Data files

**Ranking and frontend query Cosmos.** There are no JSON ranking files in git. See [COSMOS.md](COSMOS.md) and [DATA_PIPELINE.md](DATA_PIPELINE.md).

`destination_pipeline.py` writes `normalized_destinations.json` **locally** (`mock_data/` or `Real_data/`). Those folders are gitignored. Use that file only to fill, check, and reload Cosmos.

Each local record still has origin, flight, destination, weather averages, and country. Cosmos stores the flat subset (one origin document, one document per flight).
