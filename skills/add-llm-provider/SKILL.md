---
name: add-llm-provider
description: Add an LLM vendor, model list or self-hosted endpoint to COACH (provider catalog, OpenAI-compatible or Anthropic-style). Use when asked to support a new model provider or change default models.
---

# Add an LLM provider

**Goal:** `LLM_PROVIDER=<id>` works end to end (coach, chat with tools, meal photo estimate) or degrades cleanly.

## Decide the protocol
- Almost every vendor offers an **OpenAI-compatible** endpoint (`/chat/completions`): then only a catalog entry is needed — no Python.
- Only if the vendor has a different wire format (like Anthropic Messages) write a new class in `app/coach/llm.py` implementing `configured()`, `complete(system, user, max_tokens, model=None, history=None, image=None) -> LLMResult` and optionally `converse(...)` (tool calling). Register it in `make_llm()` under a new `kind`.

## Steps (catalog only)
1. Edit `data/llm_providers.yaml`: `label`, `kind: openai`, `base_url`, `key_env`, `key_required`, `model` (default), `fast` (cheap model for short tasks), `models[]` with `vision`/`tools` flags. Add `free: true` for local/free servers (price defaults to 0).
2. Model ids change: verify them in the vendor documentation today; never guess. `models` is only a suggestion — `LLM_MODEL` accepts any id.
3. If the vendor needs extra headers or a non-Bearer auth, extend `OpenAICompatLLM._post` behind a catalog field (e.g. `auth_header`), not an `if provider == …`.
4. Add the key name to `docs/configuration.md` (providers table) and `.env.example` comments.
5. Tests in `tests/test_llm_providers.py`: factory returns the right class, `configured()` with/without key, the `NAME_FILE` secret path, request URL/headers/body via a monkeypatched `_http_json`, tool-call loop if supported.

## Pitfalls
- Never hard-code a key or log request bodies (they contain health data).
- `price_eur()` drives the monthly cap: document realistic `LLM_PRICE_*` values for the new provider.
- Models without vision must not break the photo path: `analyze` should surface a clear `LLMError`.
- Keep `base_url` overridable by `LLM_BASE_URL` (gateways, proxies).

## Verify
`ruff check . && pytest -q`; with a real key, call `GET /llm` (shows provider/model/configured) then trigger a review in the UI.
