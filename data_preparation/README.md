# Data preparation

Pull APIs, clean ranking JSON, load Cosmos, and query cheap flights.

| File | Role |
|---|---|
| [DATA_PIPELINE.md](DATA_PIPELINE.md) | How pull → fill → check → Cosmos works |
| [COSMOS.md](COSMOS.md) | How ranking/frontend should query Cosmos |
| `destination_pipeline.py` | Travelpayouts + Open-Meteo + REST Countries |
| `fill_missing_data.py` | Offline fill of reconstructable holes |
| `check_missing_data.py` | Offline ranking quality check |
| `load_to_cosmos.py` | JSON → `origins` + `flights` |
| `query_cosmos.py` | Demo: city + country → cheapest trips |

`.env`, `mock_data/`, and `Real_data/` stay at the **repo root**. Run scripts from there:

```powershell
python data_preparation/destination_pipeline.py
python data_preparation/fill_missing_data.py Real_data
python data_preparation/check_missing_data.py Real_data
python data_preparation/load_to_cosmos.py Real_data
python data_preparation/query_cosmos.py
```
