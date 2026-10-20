# Onboarding: essential questions, then the coach decides what is missing

A new account sees, in this order:

1. **Welcome** screen (what the app does, where the data lives).
2. **Essential questions** (13 at most, fewer when a sport is not practised): sports, goals, age, sex, height, weight, the health notice and red flags, training days, session length, injuries, current running volume and strength level. They are marked `essential: true` in [`questions/*.yaml`](../questions). Every one can be skipped except the health notice.
3. **Loading page**: "Your information is being sent to your coach" while the intake analysis runs.
4. Either the app (nothing missing) or **"Your coach asks"**: the missing questions, each with the reason it matters, then the first plan is generated.

The rest of the bank (97 questions in all) is never forced: the home screen keeps the optional questionnaire, and the coach can ask more in its weekly review.

## The intake analysis (`app/coach/intake.py`)

`POST /users/{id}/coach/intake` returns `{"status": "ready" | "questions", "message", "source", "questions", "clarifications"}`.

- The LLM receives the known facts (never a name or an e-mail), the active goals, the facts **measured by the watch** (so they are never asked again) and the list of still-unanswered questions with their ids. It answers JSON (`json_mode`).
- **The server decides what is accepted**: only ids from that list, no duplicates, at most 6 questions and 2 free-text clarifications, texts truncated. Nothing the model invents reaches the screen as a structured question.
- Free-text clarifications are stored as facts `coach.clarification.N` and given back to the coach in its context (`precisions_declarees`).
- **No LLM** (no key, monthly budget reached, error, unreadable answer): the rule applies: the visible questions flagged `required` that remain (6 at most). The onboarding never depends on the AI.
- The result is stored (`coach_memory`, kind `intake`): reopening the app does not call the model again; `force` redoes it at most 3 times a day. Calls are logged and counted in the monthly budget.

## Existing accounts

The onboarding is driven by a local flag set when the welcome screen is shown, so an account created before this feature is never sent back to it.

## Adding or changing essential questions

Keep the path short (about a dozen screens), put safety and injuries early, and add a test in `tests/test_intake.py` if the count or the order changes.
