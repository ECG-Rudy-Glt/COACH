---
name: add-api-route
description: Add an HTTP endpoint to COACH that respects authentication, per-user isolation, input limits and the same-origin policy.
---

# Add an API route

## Steps
1. Put the router in the feature package (`app/<feature>/api.py`) as `build_router(get_repo, require_user)`; mount it in `app/main.py`.
2. User data routes live under `/users/{user_id}/…` and depend on `require_user` (it enforces `path user_id == session user`). Non-user routes depend on `current_user`. Only `/healthz`, `/version` and `/auth/*` are public.
3. Validate input with Pydantic models: `Field(max_length=…)`, numeric bounds, `Literal` for closed sets. Cap list sizes and request bodies; never build file paths or URLs from user input.
4. Return explicit dicts (no ORM rows); never include secrets or other users’ ids. User-facing errors in the product language, no stack traces.
5. State-changing = POST/PUT/PATCH/DELETE (the same-origin middleware protects them). No state change on GET.
6. Rate-limit expensive actions (LLM, imports) with per-day counters like `MAX_ESTIMATES_PER_DAY`.
7. Tests with `TestClient`: success, 401 unauthenticated, 403/404 for another user’s id, 422 invalid input, quota exceeded.

## Verify
`pytest -q`; confirm the route is absent from `/docs` (docs are off by default) and that `tests/test_security.py` still passes.
