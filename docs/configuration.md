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
| `APP_BIND`, `APP_PORT` | `127.0.0.1`, `8000` | host port mapping (compose) |

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
| `LLM_PRICE_IN_EUR_PER_MTOK`, `LLM_PRICE_OUT_EUR_PER_MTOK` | `3` / `15` (`0` for ollama) | prices used for the cap — set them to your model's real price |

`GET /llm` (authenticated) returns the active provider, model, suggested models and whether the server is configured — never a key. Model ids change often: check your provider's documentation and set `LLM_MODEL` explicitly for production.

Features that need a vision-capable model: meal-photo estimate. Features that need tool calling: history search in chat. A model without tools (catalog `tools: false`, `LLM_TOOLS=off`, or a server that answers 400/422 to the `tools` field) simply answers without the history search: the chat keeps working, the server remembers the refusal and logs it once. The same goes for JSON mode: if a server refuses `response_format` the call is repeated without it. Small local models may still produce invalid JSON: background jobs retry once, interactive calls report the error without changing your plan.

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
