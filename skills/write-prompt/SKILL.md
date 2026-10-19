---
name: write-prompt
description: Create or change an LLM prompt or add an LLM-powered feature in COACH while keeping the safety boundary (bounded outputs, no identity, server-side validation, cost cap).
---

# Write or change a prompt

Read `docs/prompts.md` fully. Summary of the contract:

## Steps
1. State the job in one sentence and the **worst case if the model is adversarial**. If it can change an engine-owned number, add a validator or drop the idea.
2. Prompt = role/language/length → hard prohibitions → closed action vocabulary with bounds → strict JSON output contract → how to cite rules/sources (only from provided lists).
3. Context = built by the server as JSON with the minimum fields; **no name, e-mail, ids of accounts**; user free text only inside data fields with length caps.
4. Call through `llm.complete`/`converse`; set `max_tokens`; pick `default_model()` or `fast_model()`; log with `repo.log_llm_call(...)` so the budget cap sees it; handle `LLMError` (feature degrades, core keeps working).
5. Parse with `service.parse_json`, validate each field (closed sets, numeric ranges, existence of referenced rows, ownership by the current user), reject with reasons, never apply unvalidated output.
6. Tests with `FakeLLM`: (a) prompt contains required context and no identity, (b) adversarial outputs are rejected, (c) provider failure → graceful message, (d) budget exhausted → refusal.
7. Try it on two providers (one Anthropic-style, one OpenAI-compatible) or a local model.

## Pitfalls
- Don’t paraphrase data by hand into the prompt; serialise JSON.
- Don’t ask the model to compute (sums, volumes, calories): compute in code and pass results.
- Don’t put secrets or raw logs in prompts.
- Medical content: the prompt must forbid diagnosis and redirect pain/red flags to a professional.
