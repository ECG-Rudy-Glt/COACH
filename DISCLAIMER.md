# Disclaimer and privacy notice

## Not medical advice
COACH is a general-purpose training and nutrition planner. It is **not a medical device**, does not diagnose, treat or prevent any condition, and is **not dietary or medical advice**. Targets and plans are estimates built from the information you enter and from general sports-science rules whose evidence level is shown in the app. They may be wrong for you.

- Consult a physician before starting or changing an exercise or nutrition programme, especially if you are pregnant, have a medical condition, an eating disorder history, take medication, or are under 18.
- Stop and seek professional help for chest pain, fainting, unusual breathlessness, persistent or sharp pain, or any red-flag symptom.
- The AI coach can make mistakes. It cannot change your plan by itself and is instructed not to give medical advice.

The software is provided "as is", without warranty (see the AGPL-3.0 licence). You are responsible for how you use it.

## Privacy — what an installation stores
You (or whoever hosts your instance) control the data. COACH has **no telemetry** and calls no analytics service.

| Data | Stored | Leaves the server only when… |
|---|---|---|
| Account: name, e-mail, password hash | PostgreSQL | never |
| Questionnaire answers, goals, plan, session logs, weight, meals (+ optional photos) | PostgreSQL / media volume | an LLM provider is configured and the feature runs (see below) |
| Garmin tokens (encrypted); activities and metrics | PostgreSQL | you connect Garmin — the app then talks to Garmin |
| AI call log (model, tokens, cost) | PostgreSQL | never |

**LLM providers.** If you configure one, the context of the call (a JSON snapshot of your training, goals, body data, notes and — for meal estimates — the description or photo) is sent to that provider under *its* terms. Name and e-mail are not sent. Choose `ollama`/a self-hosted model to keep everything on your machine, or `none` to disable AI.

**Your rights (GDPR and similar).** If you host for other people you are their data controller: tell them what is stored, keep the server secure, and honour access/erasure requests. Deleting a user row removes their data (`ON DELETE CASCADE`); a dedicated export/delete screen is on the roadmap. Health data is a special category in the EU — use disk encryption and restrict access.
