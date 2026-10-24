# Configuration

Configuration is environment-driven. **Non-secret** settings live in `.env`; **secrets** live in `./secrets/*` and are mounted as Docker file secrets.

## The `NAME_FILE` convention

Any secret variable `NAME` can be given as `NAME_FILE=/path/to/file`; the file content (trimmed) wins over `NAME`. `docker-compose.yml` uses this for every secret, so nothing sensitive appears in `docker inspect`, `/proc/<pid>/environ` of other containers, or shell history.

```sh
scripts/init-secrets.sh            # postgres_password, secrets_key (Fernet), empty placeholders for the optional ones
scripts/init-secrets.sh --vapid    # also generate Web Push (VAPID) keys
```

| Secret file | Used for | Required |
|---|---|---|
| `postgres_password` | database password (also read by `db`) | yes (generated) |
| `secrets_key` | Fernet key encrypting Garmin tokens at rest | yes if you use Garmin (generated) |
| `llm_api_key` | key of the chosen LLM provider | no — empty = AI disabled |
| `ntfy_token` | ntfy access token | no |
| `smtp_password` | weekly e-mail digest | no |
| `vapid_private_key` | Web Push signing key | no |

> Back up `secrets_key`: losing it makes stored Garmin tokens unreadable (users simply reconnect). Rotating `postgres_password` requires changing it inside Postgres too.

## Environment variables

### Core
| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_DB`, `POSTGRES_USER` | `coach` | database name / role created by the `db` container on first start |
| `DATABASE_URL` | – | full DSN; alternative to `DB_HOST`/`DB_NAME`/`DB_USER`/`DB_PASSWORD(_FILE)`. Empty everywhere = in-memory storage (demo, tests) |
| `REGISTRATION` | `first` | `first`: open until the first account exists · `open` · `closed` |
| `COOKIE_SECURE` | `0` | `1` forces the `Secure` cookie flag (auto-enabled when HTTPS is detected) |
| `TRUST_PROXY` | `0` (compose sets `1`) | read the client IP from `X-Forwarded-For` (last hop) for login throttling. Enable **only** behind a proxy/tunnel you control |
| `ALLOWED_HOSTS` | – | comma list of accepted `Host` headers (`coach.example.org,localhost`); recommended once exposed |
| `ENABLE_DOCS` | `0` | `1` serves `/docs` and `/openapi.json` (development only) |
| `LOG_LEVEL` | `info` | |
| `OFF_ENABLED` | `1` | `0` disables the barcode lookup (Open Food Facts). Only the barcode is sent, with a `COACH-selfhosted` user agent and a 6 s timeout; nothing else leaves your server |
| `OFF_BASE_URL` | `https://world.openfoodfacts.org` | alternative Open Food Facts address (mirror) |
| `WEATHER_ENABLED` | `1` | `0` disables the weather feature for the whole server (no call to Open-Meteo, whatever users choose). Even when `1`, it stays off for a user until they enter a city in Profile > Preferences |
| `WEATHER_BASE_URL`, `WEATHER_GEOCODE_URL` | `https://api.open-meteo.com`, `https://geocoding-api.open-meteo.com` | alternative Open-Meteo addresses (self-hosted instance, mirror) |
| `APP_BIND`, `APP_PORT` | `127.0.0.1`, `8000` | host port mapping (compose) |

### Weather of outdoor sessions (optional, rules W1 to W8)

Outdoor sessions (runs, cycling, walking) of the next 7 days get a weather status (good / to watch / not advised) from the free [Open-Meteo](https://open-meteo.com) forecast, with the rule cited and, when useful, a better day of the same week that keeps the spacing rules. It only **suggests**: the plan never changes without the user pressing *Move to <day>* (the existing move). Not a medical advice. Open-Meteo's free API is for non-commercial use.

What leaves your server, and nothing else:

| Call | Sent to Open-Meteo | Never sent |
|---|---|---|
| City search (Profile > Preferences > *Outing weather*) | the city name typed by the user | account, name, e-mail, session data |
| Forecast | latitude and longitude **rounded to 0.1°** (about 11 km) by the server before the call, hourly variables requested | precise GPS position, identifiers, cookies; the user agent is `COACH-selfhosted/<version>` |

- Off by default: a user must pick a city (the stored position is the rounded one). They can switch it off or delete the city at any time; `WEATHER_ENABLED=0` forbids it server-wide.
- The forecast is cached on the server for 2 h per rounded position; a failure is cached 10 minutes and silent (the plan stays usable, no weather opinion is shown).
- The AI coach receives a short weather summary of the week only if the user enabled the feature.
- Thresholds, sources and known gaps: [rules W1 to W8](rules.md).

### AI coach — providers and models

The catalog is [`data/llm_providers.yaml`](../data/llm_providers.yaml). Pick a provider, optionally a model, add the key to `secrets/llm_api_key`.

| `LLM_PROVIDER` | Protocol | Key | Notes |
|---|---|---|---|
| `anthropic` (default) | Messages API | `ANTHROPIC_API_KEY` or `llm_api_key` | vision + tools |
| `openai` | Chat Completions | `OPENAI_API_KEY` or `llm_api_key` | |
| `gemini` | OpenAI-compatible endpoint | `GEMINI_API_KEY` or `llm_api_key` | |
| `mistral` | OpenAI-compatible | `MISTRAL_API_KEY` or `llm_api_key` | |
| `openrouter` | OpenAI-compatible | `OPENROUTER_API_KEY` or `llm_api_key` | hundreds of models, set `LLM_MODEL` |
| `ollama` | OpenAI-compatible | none | local, free, nothing leaves your machine (`--profile ollama`) |
| `custom` | OpenAI-compatible | optional | any server; `LLM_BASE_URL` required (vLLM, LM Studio, LiteLLM…) |
| `none` | – | – | AI disabled explicitly |

| Variable | Default | Meaning |
|---|---|---|
| `LLM_MODEL` | provider default | model for coach, chat, weekly review. Any id your provider accepts — the catalog only *suggests* |
| `LLM_MODEL_FAST` | provider `fast` model | cheaper model for short tasks (meal estimate) |
| `LLM_BASE_URL` | catalog | override the endpoint (proxy, gateway, self-hosted) |
| `LLM_JSON_MODE` | catalog (`json_mode`) | `on` asks for `response_format: json_object` on the weekly review, notifications and meal estimates; `off` never does. Anthropic has no such mode and ignores it |
| `LLM_TOOLS` | catalog (`tools` per model) | `off` disables tool calling (history search in chat); `on` forces it for a model the catalog marks without tools |
| `LLM_MONTHLY_BUDGET_EUR` | `5` | **hard cap**: calls are refused once the month's estimated cost reaches it |
| `LLM_PRICE_IN_EUR_PER_MTOK`, `LLM_PRICE_OUT_EUR_PER_MTOK` | price of the model (see below) | euro price per million input / output tokens used for the cap. When set they win over the built-in table, each one on its own |
| `LLM_PROMPT_CACHE` | `on` | `off` sends the system prompt as one plain block (no `cache_control`) — for an Anthropic-compatible gateway that rejects it. Anthropic only; see [Prompt cache](#prompt-cache) |
| `LLM_USD_TO_EUR` | `0.90` | rate applied to the built-in USD prices. The default is deliberately a little high (a cap should over- rather than under-estimate); set the current rate if you want exact figures |

**Cost estimate.** The cap is computed from the tokens each reply reports. A model in the built-in table (`PRICES_USD` in `app/coach/llm.py`, public Anthropic prices in USD per million tokens, input / output, as of 2026-10-06) is priced from it and converted with `LLM_USD_TO_EUR`: `claude-haiku-4-5` 1 / 5, `claude-haiku-5-5` 0.10 / 0.50, `claude-sonnet-5-5` and `claude-sonnet-5` 2 / 10, `claude-sonnet-4-6` 3 / 15, `claude-opus-5-5` 4 / 20, `claude-opus-5`, `claude-opus-4-8`, `-4-7` and `-4-6` 5 / 25, `claude-fable-5` and `claude-fable-5-1` 10 / 50 (a dated id such as `claude-haiku-4-5-20251001` matches its alias). Any other model (OpenAI, Gemini, a gateway id…) is priced at the old default of 3 / 15 euros per million, never at 0; only a local provider (`ollama`) is free. Prices change: check your provider's page and force `LLM_PRICE_*` when it matters. Claude Haiku 5.5's price above 100 000 input tokens is not modelled (the coach's context is far below).

With the Anthropic provider, tokens read from the prompt cache are counted at 0.1 times the input price (0.05 for Claude Opus 5.5, 0.025 for Claude Fable 5.1) and tokens written to it at 1.25 times; see [Prompt cache](#prompt-cache). Other providers report their cached tokens inside the normal input count: they are priced at the full input rate, which slightly over-estimates and is the safe side for a cap.

`GET /llm` (authenticated) returns the active provider, model, suggested models and whether the server is configured — never a key. Model ids change often: check your provider's documentation and set `LLM_MODEL` explicitly for production.

Features that need a vision-capable model: meal-photo estimate. Features that need tool calling: history search in chat. A model without tools (catalog `tools: false`, `LLM_TOOLS=off`, or a server that answers 400/422 to the `tools` field) simply answers without the history search: the chat keeps working, the server remembers the refusal and logs it once. The same goes for JSON mode: if a server refuses `response_format` the call is repeated without it. Small local models may still produce invalid JSON: background jobs retry once, interactive calls report the error without changing your plan.

### Prompt cache

With the Anthropic provider, the chat, the weekly review, the check-in push and the weekly digest mark their **fixed prefix** with `cache_control`: the task's instruction, the citation rule, then the `regles` (rules digest) and `sources` (publications digest) fields — about 7 000 to 10 000 tokens, identical from one call to the next and from one user to the next. It contains no date and no user data. The rest of the context (profile, sessions, nutrition, notes…) follows in a second, unmarked block, and the chat history and the user's message come after. The content sent to the model is the same as before; only the position of `regles` and `sources` changed (they are now read before the user's data, not inside it). For the chat, the marker also covers the history-search tools, which are rendered before the system prompt.

Cached tokens are read at 0.1 times the input price and written at 1.25 times (5-minute lifetime, refreshed by every read), so the chat pays off from the second message of a conversation and tool rounds inside one reply already read the cache. The weekly review, check-in and digest rarely run within five minutes of each other: they mostly pay the one-off write (+25 % on their prefix, a fraction of a cent with Haiku). The cache only starts above a minimum prefix size — 4 096 tokens for Claude Haiku 4.5 (and Opus 4.6 / 4.5), 1 024 or 2 048 for other 4.x models, 512 for the 5.x generation — and silently does nothing below it; the prefix is above it for every task, and `tests/test_prompt_cache.py` checks it. Other providers get the same text in one system message (their automatic prefix caching, if any, benefits from the fixed-first order). `LLM_PROMPT_CACHE=off` disables the markers.

### Wearables
| Variable | Default | Meaning |
|---|---|---|
| `AUTO_SYNC` | `1` (compose) | background Garmin sync for connected users |
| `GARMIN_SYNC_HOURS` | `6` | interval |
| `SYNC_PAUSE_S` | `2` | pause between users (be polite to Garmin) |

### Notifications (all optional)
| Variable | Meaning |
|---|---|
| `AUTO_NOTIFY`, `NOTIFY_HOUR` | enable the daily check-in/weekly digest job and its hour (server local time) |
| `NTFY_URL`, `NTFY_PUBLIC_URL`, `ntfy_token` | ntfy server reachable from the app / address typed in the phone app / access token |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_FROM`, `smtp_password` | weekly e-mail digest |
| `VAPID_PUBLIC_KEY`, `vapid_private_key`, `VAPID_SUBJECT` | Web Push. `VAPID_SUBJECT` must be a real `mailto:` or `https://` contact (Apple rejects others) |

Each user must also switch the channel on in the app.

### Docker profiles
| Profile | Adds |
|---|---|
| `https` | Caddy on 80/443 with automatic certificates (`DOMAIN` in `.env`) |
| `backup` | daily `pg_dump` into the `backups` volume, `BACKUP_KEEP_DAYS` retention |
| `ollama` | local model server (`docker compose exec ollama ollama pull qwen2.5:7b`, then `LLM_PROVIDER=ollama`) |

```sh
docker compose --profile https --profile backup up -d
```

## Exercise library

`exercises-init` runs once after the app is healthy and imports ~1 750 exercises with per-image author/license (wger CC-BY-SA, free-exercise-db Unlicense, plus `data/custom_exercises.yaml`). It skips itself when the table is populated. Refresh: `docker compose run --rm exercises-init python -m app.exercises.importer`.

## Operations

```sh
docker compose logs -f app                 # logs (credentials are never logged by design)
docker compose exec -T db pg_dump -U coach coach -Fc > coach.dump   # manual backup
docker compose up -d --build               # upgrade (migrations run automatically)
scripts/reset_password.sh me@example.org   # temporary password for a forgotten one (shown once, sessions closed)
```
