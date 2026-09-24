# Travel Planner documentation

This local documentation describes the repository implementation inspected on 24 September 2026. Source code takes precedence over older README descriptions. It does not certify deployed infrastructure or live provider availability.

## Pages

| Page | Contents |
|---|---|
| [Getting started](Getting-Started.md) | Run the backend and frontend locally |
| [Configuration](Configuration.md) | Implemented environment settings |
| [Architecture](Architecture.md) | Components, dependencies, and request flow |
| [User guide](User-Guide.md) | Planner, Explore, details, and saved items |
| [API reference](API-Reference.md) | HTTP routes, payloads, and errors |
| [Ranking and recommendations](Ranking-and-Recommendations.md) | Validation, flexible dates, scoring, and feedback |
| [Data and persistence](Data-and-Persistence.md) | Cosmos containers, identifiers, and browser storage |
| [Security](Security.md) | API keys, accounts, cookies, and control boundaries |
| [Testing and troubleshooting](Testing-and-Troubleshooting.md) | Local checks and diagnostic steps |

## Scope and navigation

The application combines a React frontend, FastAPI backend, Cosmos DB storage, deterministic Python ranking, an LLM integration, and Google Places activities. Flights and hotels are retrieved from stored data. There is no flight or hotel booking/payment flow or live hotel price/availability integration.

The repository has no `data_preparation/` directory in this checkout, despite references in the root README. These pages do not describe an ingestion pipeline or promise a data refresh schedule.

Pages use ordinary Markdown headings, relative links, tables, and fenced code blocks to support later Azure DevOps Wiki migration. Source links point outside this folder into the repository; adjust those links if migrating only the documentation folder. No Wiki or external publication is configured by this documentation set.

The local `docs/` folder is separate from FastAPI's development `/docs` endpoint. The frontend's `/docs` route redirects to `/planner` and does not render these files.
