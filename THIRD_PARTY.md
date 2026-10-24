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

## Front-end libraries (self-hosted in `app/static/vendor/`, no CDN, loaded only when the barcode scanner opens)
| Component | Version / integrity | Licence |
|---|---|---|
| [`barcode-detector`](https://github.com/Sec-ant/barcode-detector) (Barcode Detection API ponyfill, `dist/iife/ponyfill.js` -> `barcode-detector.js`, 43 KB) | 3.2.3, npm sha512 `PLinpWGiOQoQH4X+YObWZ6iXeffXKDM3d4vnOD86481SvukIfvkf7jEE/tud9oI4HTDxtDdlHaFilA5Kn7Xa7A==`; file sha256 `915a6febe3edd6dab6a7c5a21f69cadd54e1d095cdde9a3eb62605b3db71bf60` | MIT (`LICENSE-barcode-detector.txt`) |
| [`zxing-wasm`](https://github.com/Sec-ant/zxing-wasm) reader build (`zxing_reader.wasm`, 947 KB, ~411 KB gzipped), wrapping [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) | 3.1.6, npm sha512 `mU7UNuvl+hOT+nlSOQTMHZ2tM8lRMsbjDIp5IO/+HmBl/FOq77q0OSZPJ3cm42A9c1MKU6Uve67FiGdkhsrT9g==`; file sha256 `5003fb4b88c4fbd1fd518a2fd8c8ad365c519e183a08c03a322dddfea3cea84e` | MIT wrapper (`LICENSE-zxing-wasm.txt`) + zxing-cpp **Apache-2.0** (compatible with AGPL-3.0) |

The decoder runs entirely on the device: the camera video is never uploaded. Used only when the browser has no native `BarcodeDetector` (Safari on iPhone, desktop Chrome on Linux). To update: download the tarballs from npm, check the integrity above, copy the two files, update this table and bump the service-worker cache.

## Container images
PostgreSQL (PostgreSQL licence), Caddy (Apache-2.0), Ollama (MIT, optional profile), Python (PSF).

## Data
| Data | Source | Licence / terms |
|---|---|---|
| Exercise descriptions and media (imported at first start) | [wger](https://wger.de) API | **CC-BY-SA** (per-item author and licence are stored and displayed in the app) |
| Exercise database | [free-exercise-db](https://github.com/yuhonas/free-exercise-db) | Unlicense (public domain) |
| Custom exercises | `data/custom_exercises.yaml` | AGPL-3.0 with the project |
| Muscle diagram (front/back SVG) | Drawn for the project in `app/static/stats.js` | AGPL-3.0 with the project (no third-party image) |
| Publications metadata and summaries | PubMed / Europe PMC / publishers | Only bibliographic facts and short original summaries are included; cited works remain the property of their authors |
| Inter typeface (`app/static/fonts`) | Rasmus Andersson | SIL OFL 1.1 |

Imported wger media are fetched from wger's servers on demand and cached locally; they are **not** redistributed in this repository.

## Trademarks
Garmin, Coros, Strava, Apple, Samsung, Anthropic, OpenAI, Google, Mistral and others are trademarks of their owners. Mentions describe compatibility only and imply no affiliation or endorsement.
