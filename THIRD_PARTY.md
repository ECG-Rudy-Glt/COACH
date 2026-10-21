# Third-party components and data

COACH is licensed AGPL-3.0-only. It uses the following; please respect their terms when redistributing.

## Python dependencies (see `requirements.txt`)
| Package | Licence |
|---|---|
| FastAPI, Starlette | MIT / BSD-3 |
| Uvicorn | BSD-3 |
| Pydantic | MIT |
| PyYAML | MIT |
| psycopg 3 | LGPL-3.0 |
| cryptography | Apache-2.0 / BSD |
| pywebpush | MPL-2.0 |
| fitdecode | MIT (reads FIT activity files; compatible with AGPL-3.0) |
| defusedxml | PSF-2.0 (safe parsing of TCX/GPX: no external entities, no XML bombs) |
| garminconnect | MIT — **unofficial** client for Garmin Connect; not affiliated with or endorsed by Garmin. Using it may be subject to Garmin's terms of service and can break without notice |

Dev only: pytest (MIT), httpx (BSD-3), ruff (MIT).

## Container images
PostgreSQL (PostgreSQL licence), Caddy (Apache-2.0), Ollama (MIT, optional profile), Python (PSF).

## Data
| Data | Source | Licence / terms |
|---|---|---|
| Exercise descriptions and media (imported at first start) | [wger](https://wger.de) API | **CC-BY-SA** (per-item author and licence are stored and displayed in the app) |
| Exercise database | [free-exercise-db](https://github.com/yuhonas/free-exercise-db) | Unlicense (public domain) |
| Custom exercises | `data/custom_exercises.yaml` | AGPL-3.0 with the project |
| Publications metadata and summaries | PubMed / Europe PMC / publishers | Only bibliographic facts and short original summaries are included; cited works remain the property of their authors |
| Inter typeface (`app/static/fonts`) | Rasmus Andersson | SIL OFL 1.1 |

Imported wger media are fetched from wger's servers on demand and cached locally; they are **not** redistributed in this repository.

## Trademarks
Garmin, Coros, Strava, Apple, Samsung, Anthropic, OpenAI, Google, Mistral and others are trademarks of their owners. Mentions describe compatibility only and imply no affiliation or endorsement.
