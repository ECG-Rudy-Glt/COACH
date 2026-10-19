# Prompts: what goes in, what stays out

COACH's LLM calls are small, bounded and audited. This page explains the design so that you (or your coding assistant) can change prompts or add new LLM features without weakening the guarantees. Current prompts are in **French** (the product language); the structure below is language-independent.

## Where the prompts live

| Feature | Prompt | Code |
|---|---|---|
| Weekly review (comment + ≤4 adjustments) | `SYSTEM` | `app/coach/service.py` (`review`, `check_proposal`) |
| Chat | `CHAT_SYSTEM` | `app/coach/chat.py` |
| Push check-in / weekly e-mail digest | `CHECKIN_SYSTEM`, `DIGEST_SYSTEM` | `app/coach/notify.py` |
| Meal estimate (text/photo) | `SYSTEM` | `app/nutrition/analyze.py` |
| Shared rule on citing sources | `SOURCES_RULE` | `app/coach/service.py` |

All calls go through `llm.complete(system, user, max_tokens, model, history=None, image=None)` or `llm.converse(...)` (tools). Providers implement those two methods only (`app/coach/llm.py`), so a prompt works on any provider.

## Anatomy of a good prompt here

1. **Role and audience** — one sentence ("coach of an amateur athlete"), language, register (formal *vous* in French), length limit.
2. **What the model must NOT do** — the hard prohibitions come early and are explicit: no new numbers, no load increase, no medical advice (redirect to a professional on pain or red flags), no invented studies, no internal IDs in user-facing text.
3. **What it MAY do** — a closed list of actions ("reduce", "swap_easy", "move") with parameters and bounds. Closed vocabularies are validated in code.
4. **Output contract** — strict JSON with named fields. Say what to do when there is nothing to say (`[]`, empty string), not "be creative".
5. **Grounding data** — passed as JSON in the *user* message (or after a `CONTEXT:` marker), never paraphrased by hand. Contains only what the task needs.
6. **Citation rule** — the model may cite rule IDs and source IDs **only from the lists provided**; the server rejects anything else.

Skeleton:

```text
You are the coach of an amateur athlete. Write in <language>, warm and concise (<N> sentences max).
You do NOT compute training loads: a deterministic engine already built the plan. You may only propose
at most <K> bounded adjustments on future, still-planned sessions, citing rule ids from "rules" only.
Forbidden: increasing load, inventing a study or a number, medical advice, naming a session by its internal id.
If pain or a red-flag symptom is reported, recommend seeing a professional instead of adjusting.
Answer with JSON only: {"summary": "...", "proposals": [{"session_id": int, "action": "reduce|swap_easy|move",
"factor": 0.5-0.95, "to_day": "YYYY-MM-DD", "reason": "...", "rule_ids": ["..."], "source_ids": ["..."]}]}
```

## What to put in the context

Built by `service.build_context()`; extend it deliberately:

- **Profile snapshot**: age (not birth date), sex, anthropometrics as needed, training age, constraints, goals with dates.
- **Recent facts**: planned vs. done sessions with RPE, adaptations and declared pain; cycle position; lifting trend; compact wearable history (weekly aggregates for 12 weeks, monthly for 24).
- **The rule list** (`rules`) and **evidence digest** (`sources`) the model is allowed to cite.
- **Previous reviews / coach notes** (short summaries, not raw transcripts).
- Keep it under a fixed token budget (≈6 000 input tokens); truncate by recency/relevance, not by cutting JSON in half.

## What to keep out

- **Identity**: name, e-mail, address, device ids, account ids. The user is "the athlete". Tests (`test_coach.py`) fail if the sample name leaks.
- **Secrets**: API keys, tokens, anything from `secrets/`.
- **Raw database rows or free-form logs.** Pass computed, minimal summaries.
- **Unbounded user text** without a length cap. Free text (notes, meal descriptions) is *data*, not instructions — see below.
- **Anything the task does not need.** Less context = lower cost, less leakage, fewer ways to be misled.

## Treat user text as untrusted (prompt injection)

Users (and, via synced data, third parties — an activity name from a watch) can write "ignore your instructions…". Defenses already in place; keep them when you add features:

- The model has **no write access**; it only returns JSON that the server validates (`check_proposal`): IDs must exist, factor ∈ [0.5, 0.95], target session must be future and untouched, blocked days respected, no load increase. A hijacked model can at worst produce a rejected proposal.
- Tools are read-only, scoped to the current user by closure (`run_tool(repo, user_id, …)`) — the model cannot pass a different `user_id`.
- Tool results are size-capped (6 000 chars).
- Put user-provided text in the JSON context or clearly delimited fields, never concatenated into the system prompt.

When adding a feature, ask: *what is the worst thing this output can do if the model is fully adversarial?* If the answer is "change a number the engine owns", add a validator or a rule ID requirement.

## Validate, then trust

For every structured output:

1. `parse_json()` tolerates code fences and prose around the object, then insists on a JSON object.
2. Validate each field against a closed set or numeric bounds; drop (and count) what fails; log the reason.
3. Retry once on invalid JSON in background jobs (`notify._ask`) with a larger `max_tokens`; interactive paths report the error instead.
4. Never let a failed or empty LLM answer block the core feature — the plan and tracking must work without it.

## Cost and reliability

- Set `max_tokens` per call type; prefer the **fast** model (`LLM_MODEL_FAST`) for short extraction (meal estimate).
- Put the **stable prefix** first (system prompt, rules, sources) so providers with prompt caching can reuse it; put volatile data last.
- Every call is recorded in `llm_calls` (model, tokens, estimated cost, ok/error). `LLM_MONTHLY_BUDGET_EUR` refuses calls beyond the cap; add new call kinds to the same accounting (`repo.log_llm_call`).
- Different providers behave differently on JSON strictness and tool calling. Test a new prompt with at least one OpenAI-compatible and one Anthropic model, or with a local model if you target Ollama. Models without vision cannot do the photo estimate; models without tool calling skip history search.

## Testing prompts without a model

`tests/test_coach.py` defines a `FakeLLM` that returns canned text and records the prompts. Assert on:

- what is *in* the prompt (rules present, no identity),
- how the server reacts to adversarial outputs (unknown rule id, factor 1.5, past session) — each must be rejected with a reason,
- degraded behaviour when the provider raises `LLMError`.

For wording changes, keep a few real transcripts as regression fixtures (anonymised) and review them by eye; there is no automatic metric for tone.

## Changing the language

Translate the prompt text and the user-facing strings together; keep identifiers, JSON keys and rule IDs untouched. The format "formal address" instruction only applies to languages that have it. See `skills/add-language/SKILL.md`.
