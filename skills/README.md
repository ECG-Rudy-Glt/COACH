# Skills for AI coding assistants

Task recipes written so that an LLM-based assistant (or a new contributor) can extend COACH correctly and safely. Each folder has a `SKILL.md` with the goal, files to touch, steps, pitfalls and a verification checklist. They use the `SKILL.md` front-matter convention (`name` + `description`) of Claude Code skills, and read as plain Markdown for any other assistant.

| Skill | Use it to… |
|---|---|
| [add-llm-provider](add-llm-provider/SKILL.md) | register another LLM vendor/model list or a self-hosted endpoint |
| [add-activity-source](add-activity-source/SKILL.md) | ingest data from Coros, Suunto, Polar, Strava, FIT files… |
| [add-training-rule](add-training-rule/SKILL.md) | add or change a plan/nutrition rule with its test |
| [add-evidence](add-evidence/SKILL.md) | add a verified publication to the evidence base |
| [add-question](add-question/SKILL.md) | extend the adaptive questionnaire |
| [write-prompt](write-prompt/SKILL.md) | create or change an LLM prompt safely |
| [add-migration](add-migration/SKILL.md) | change the database schema |
| [add-api-route](add-api-route/SKILL.md) | add an endpoint that respects per-user isolation |
| [add-language](add-language/SKILL.md) | translate the UI, questionnaire and prompts |
| [security-review](security-review/SKILL.md) | review a change before merging |

**Use with Claude Code:** `mkdir -p .claude && ln -s ../skills .claude/skills` (or copy the folders). **Other assistants:** point them at `AGENTS.md` and the relevant `SKILL.md`.
