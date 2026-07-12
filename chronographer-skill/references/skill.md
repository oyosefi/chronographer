# Chronographer skill for Openclaw

Summary

A minimal Openclaw skill that integrates the Chronographer reminders backend with your Openclaw agent. The skill provides helper calls to list upcoming occurrences, create tasks, and record completions.

Configuration

- CHRONO_API_URL — base URL of the Chronographer API (default: http://localhost:8000)
- CHRONO_API_KEY — API key (Bearer token) for the agent

Provided client helpers

- list_upcoming(start_iso, end_iso, display_tz=None)
- get_next(task_id)
- get_last(task_id)
- create_task(payload)
- complete_task(task_id, completed_at_iso, notes, metadata)

Usage

1. Install the skill directory into Openclaw's skills folder or reference it in your skill loader.
2. Configure CHRONO_API_URL and CHRONO_API_KEY in environment or Openclaw secrets.
3. Use the provided client helper functions in the skill handlers to poll /upcoming, surface reminders, and log completions.

Example snippet (pseudocode)

```python
from client import ChronoClient

client = ChronoClient()
upcoming = client.list_upcoming("2026-07-12T00:00:00-07:00","2026-07-12T23:59:59-07:00")
# Process upcoming and send messages via Telegram or otherwise
```

Notes

This skill and the client are intentionally minimal. The implementation in `chronographer-skill/client.py` is a practical example the agent can call directly. Feel free to extend this skill with richer dialogs, triage flows, or interactive confirmation steps.