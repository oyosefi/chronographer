# Chronographer Skill

ID: oyosefi/chronographer-skill
Version: 0.1.0
Specification: agentskills.io-style folder layout (SKILL.md + scripts/ + references/ + assets/)

Summary

Chronographer is a minimal skill that integrates with the Chronographer reminders backend. It provides actions the agent can call to list upcoming occurrences, query a task's next/last occurrence/completion, create tasks, and record completions.

Why

The skill lets an agent (openclaw/chronographer skill) interact with a deterministic reminders backend instead of embedding scheduling logic in freeform LLM prompts. This reduces errors and centralizes recurrence, completion journaling, and timezone handling.

Actions

Action schemas (input/output JSON Schema) live in `references/actions.json`.
Key actions:
- list_upcoming — returns computed occurrences for a time window
- get_next — next occurrence for a single task
- get_last — most recent completion (convenience)
- create_task — create a task
- complete_task — record a completion (journal entry)

Installation

1. Place this folder under Openclaw's skills directory or point the agent's skill loader to it.
2. Install runtime deps for the handler: `pip install -r scripts/requirements.txt` (or bundle in a virtualenv).
3. Configure these environment variables for the skill:
   - CHRONO_API_URL — base URL of the Chronographer API (default: http://localhost:8000)
   - CHRONO_API_KEY — bearer token used by the skill to authenticate

Runtime & Files

- scripts/
  - handler.py — CLI-style handler that accepts an action name and a JSON payload on stdin and returns JSON on stdout. Intended as the invokable entrypoint for the skill runtime.
  - client.py — minimal HTTP client used by the handler to call the Chronographer REST API.
  - requirements.txt — Python dependencies for the handler

- references/
  - actions.json — typed input/output schemas for each action (JSON Schema).
  - skill.yaml (legacy) — previously generated manifest (moved here).
  - skill.md (legacy) — previous human-oriented skill description (moved here).

- assets/ — static templates or other resources (currently empty)

Examples

List upcoming (example using handler):

```bash
echo '{"start":"2026-07-12T00:00:00-07:00","end":"2026-07-12T23:59:59-07:00"}' | python scripts/handler.py list_upcoming
```

Create a task (using client library in scripts/client.py):

```python
from scripts.client import ChronoClient
c = ChronoClient()
c.create_task({"title":"Take out trash","task_type":"recurring","start_at":"2026-07-14T19:00:00-07:00","recurrence_rrule":"FREQ=WEEKLY;BYDAY=WE","recurrence_anchor":"calendar"})
```

Developer notes

- Action schemas are authoritative in `references/actions.json`. The handler expects inputs to match those schemas.
- The skill is intentionally minimal; extend handler.py to add richer validation, interactive dialogs, or a long-running adapter.

Contact

Maintainer: oyosefi
