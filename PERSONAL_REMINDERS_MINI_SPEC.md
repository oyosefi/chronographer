# Personal Reminders — Mini-spec

Status: draft

## Summary

This service is a small backend that stores reminders, one-time tasks, recurring tasks, and completion journal entries so an agent (openclaw / chronographer skill) can poll for upcoming work and log completions deterministically. It is single-user, poll-only (no outbound notifications), uses RFC5545 RRULE for recurrence, and supports both calendar-anchored and completion-anchored recurrence. Timezone is per-user (default) and timestamps are stored in UTC with timezone-aware conversion.

Hosting target: Start with a local docker-compose deployment (web + PostgreSQL with a persistent volume) on your VM; optionally migrate to Azure App Service/Containers with Azure Database for PostgreSQL later. Authentication: single static API key (Bearer token) provisioned manually.

Goals:
- Deterministic recurrence handling (RRULE + anchored-to-last-completion support)
- Simple REST API for agent to poll upcoming occurrences and log completions
- Free-text context on tasks and per-completion notes
- Editable completions with audit trail
- Export capabilities (JSON/CSV)

Out of scope (initial): push notifications (Telegram/SMS), attachments (files/images), multi-tenant access control (single-user only), tag system (deferred)

---

## Key concepts

- Task: persistent object describing something to do.
  - Types: `reminder` (one-time, time set), `one_time` (task scheduled once), `recurring` (repeats by rule).
  - Fields include: title, description, start_at, due_at, timezone, recurrence_rrule (RFC5545), recurrence_anchor (`calendar` | `completion`), remind_until_done (bool), metadata (json), status.

- Occurrence: a computed scheduled instance of a Task (not stored persistently by default). For `calendar`-anchored recurrences it is generated from the task's DTSTART + RRULE. For `completion`-anchored tasks, occurrences are generated using the task's last_completed_at (or start_at if none) as DTSTART.

- Completion (journal entry): a record that a user executed an occurrence (or otherwise recorded an action). Contains completed_at, notes (free text), metadata (json). Completions are editable but edits are recorded in an audit/history table.

- User-level timezone: tasks and occurrence computation default to the user's timezone. The API accepts timezone-aware ISO-8601 timestamps.

---

## Data model (PostgreSQL sketch)

Note: include `user_id` to allow future multi-user; current deployment may use a single user.

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name text,
  timezone text NOT NULL DEFAULT 'America/Los_Angeles',
  created_at timestamptz DEFAULT now()
);

CREATE TABLE tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id) NOT NULL,
  title text NOT NULL,
  description text,
  task_type text NOT NULL CHECK (task_type IN ('reminder','one_time','recurring')),
  timezone text,
  start_at timestamptz,
  due_at timestamptz,
  recurrence_rrule text,
  recurrence_anchor text NOT NULL CHECK (recurrence_anchor IN ('calendar','completion')) DEFAULT 'calendar',
  remind_until_done boolean DEFAULT false,
  last_completed_at timestamptz NULL,
  metadata jsonb DEFAULT '{}'::jsonb,
  status text DEFAULT 'active',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE completions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid REFERENCES tasks(id) NOT NULL,
  completed_at timestamptz NOT NULL DEFAULT now(),
  notes text,
  metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now(),
  edited boolean DEFAULT false,
  deleted boolean DEFAULT false
);

CREATE TABLE completion_edits (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  completion_id uuid REFERENCES completions(id) NOT NULL,
  previous_notes text,
  previous_metadata jsonb,
  edited_at timestamptz DEFAULT now(),
  edited_by text
);

CREATE INDEX idx_tasks_user ON tasks(user_id);
CREATE INDEX idx_completions_task ON completions(task_id);
```

---

## API (HTTP+JSON)

Authentication: API key in `Authorization: Bearer <API_KEY>` header.
Base path: `/api/v1`

- POST /api/v1/tasks
  - Create a task
  - Body (example):
```json
{
  "title":"Replace furnace filter",
  "description":"2-month cadence",
  "task_type":"recurring",
  "start_at":"2026-05-01T09:00:00-07:00",
  "timezone":"America/Los_Angeles",
  "recurrence_rrule":"FREQ=MONTHLY;INTERVAL=2",
  "recurrence_anchor":"completion",
  "remind_until_done":true,
  "metadata":{"note":"Alternating sides"}
}
```

- GET /api/v1/tasks
  - Query/filter tasks by type, status, due range, recurrence, etc.

- GET /api/v1/tasks/{task_id}

- PATCH /api/v1/tasks/{task_id}
  - Update task fields (note changes to recurrence need careful handling)

- DELETE /api/v1/tasks/{task_id}
  - Soft-delete (archive) by default

- POST /api/v1/tasks/{task_id}/completions
  - Log completion / journal entry
  - Body example:
```json
{ "completed_at":"2026-07-11T18:00:00-07:00", "notes":"injected, right side", "metadata":{"side":"right"}, "idempotency_key":"<optional>" }
```
  - Behavior: create completion, append to completions table, create audit record if edited later, and if task.recurrence_anchor == 'completion' update tasks.last_completed_at to completed_at.

- GET /api/v1/tasks/{task_id}/completions
- PATCH /api/v1/tasks/{task_id}/completions/{completion_id}
  - Edits create a completion_edits row and set `edited=true` on completion.

- GET /api/v1/upcoming?start=...&end=...&include_overdue=true
  - Returns computed occurrences for all tasks in the window. Each item contains: occurrence_id, task_id, due_at_utc, local_due_at, is_overdue, task snapshot, last_completion_id (if any). Optional `display_tz` query param requests local conversions for travel (default=user timezone).
  - Implementation: compute server-side using RRULE and anchor rules in the task timezone. Cap occurrences per task (e.g., max 500) to avoid abuse.

- GET /api/v1/tasks/{task_id}/next
  - Returns next occurrence for that task.

- GET /api/v1/export?format=json|csv&since=YYYY-MM-DD
  - Export tasks + completions for backup / analysis.

Notes on idempotency: support idempotency_key on creates to prevent duplicate completions when the client retries.

---

## Recurrence semantics (examples)

- Calendar-anchored (BYDAY-based): `recurrence_anchor = 'calendar'`, `recurrence_rrule = 'FREQ=WEEKLY;BYDAY=WE'` — occurrences generated from the task.start_at / DTSTART; completions do not shift the schedule.

- Completion-anchored: `recurrence_anchor = 'completion'`, `recurrence_rrule = 'FREQ=MONTHLY;INTERVAL=2'` — next due is computed from last_completed_at. When computing the next occurrence, convert last_completed_at (or start_at if null) to the task timezone and use that value as DTSTART for the RRULE generator. If a completion timestamp is naive, interpret it in the user's timezone when recording it.

Example: Replace filter every 2 months — recurrence_anchor=completion with RRULE FREQ=MONTHLY;INTERVAL=2. When a completion is logged, record completed_at (stored in UTC), update tasks.last_completed_at, convert it to the task timezone, and compute the next occurrence via the RRULE library with that DTSTART.

Missed occurrences and per-task policy:
- If `remind_until_done=true`, include overdue occurrences when the agent requests upcoming items until a completion is recorded for that occurrence.
- If `expire_after_seconds` is set, do not return occurrences older than `now - expire_after_seconds`.
- Per-task override should be supported in the task record.

---

## Timezones and DST

- Timestamps are stored in UTC. The API accepts timezone-aware ISO-8601 values; naive datetimes are interpreted in the user's timezone (users.timezone, default America/Los_Angeles).
- Each task may optionally set a timezone; otherwise the user's timezone is used. Occurrence generation uses task.timezone and is timezone-aware so recurrences preserve local wall-clock time across DST.
- The `/upcoming` endpoint accepts an optional `display_tz` query param; responses include both `due_at_utc` and `local_due_at` (converted to the requested display_tz) to support travel-aware display.
- When logging a completion, `completed_at` should be timezone-aware (or will be interpreted in the user's timezone if naive). Store `completed_at` in UTC; for completion-anchored recurrences convert `last_completed_at` to the task timezone and use it as DTSTART for RRULE computation.
- Use `zoneinfo` + `python-dateutil`/`rrule` and thoroughly test DST edge cases.

---

## Implementation notes & libraries (recommended)

- Language: Python + FastAPI (async) — quick to implement and test. DB: PostgreSQL (Azure Database for PostgreSQL).
- Use `python-dateutil.rrule` or `rrule` for RRULE parsing and generation.
- Use `zoneinfo` (stdlib) for timezone conversion.
- Use `asyncpg` + `SQLAlchemy` (async) or `psycopg` for DB access.
- Keep recurrence computation server-side; cache results if load is high.
- For single static API key: server checks header against env var or secret stored in Key Vault.

---

## Tests and acceptance criteria

- Unit tests for: RRULE parsing, calendar vs completion anchoring, DST transitions, overdue behavior when `remind_until_done` is set, idempotent completion creation.
- Integration tests: Create recurring task, log completion, verify next occurrence updated for completion-anchored case.
- API contract: provide OpenAPI spec and sample curl for each endpoint.

---

## Deployment & artifacts

Expected repo artifacts to implement:
- `docs/` or this mini-spec file (this document)
- `openapi.yaml` (API contract)
- `src/app` (FastAPI app) with Dockerfile
- DB migration scripts (e.g., Alembic)
- `chronographer-skill/` — sample client wrapper used by openclaw to call the API (simple functions: list_upcoming, create_task, complete_task)
- `tests/` (unit + integration tests)
- CI workflow (GitHub Actions) to run tests and build image
- Deployment guide for Azure (App Service/Container + Azure Database for PostgreSQL). Include env vars: DATABASE_URL, API_KEY, TZ, etc.

---

## Example curl (quick)

Create task:
```bash
curl -X POST "https://{HOST}/api/v1/tasks" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"title":"Take out trash","task_type":"recurring","start_at":"2026-07-14T19:00:00-07:00","recurrence_rrule":"FREQ=WEEKLY;BYDAY=WE","recurrence_anchor":"calendar","remind_until_done":false}'
```

List upcoming (tomorrow):
```bash
curl -G "https://{HOST}/api/v1/upcoming" \
  -H "Authorization: Bearer ${API_KEY}" \
  --data-urlencode "start=2026-07-12T00:00:00-07:00" \
  --data-urlencode "end=2026-07-13T23:59:59-07:00"
```

Log completion:
```bash
curl -X POST "https://{HOST}/api/v1/tasks/{task_id}/completions" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"completed_at":"2026-07-11T18:00:00-07:00","notes":"injected, right side"}'
```

---

## Next steps / recommended priorities for implementation

1. Create OpenAPI schema for endpoints above.
2. Implement small FastAPI skeleton and DB migrations for `users`, `tasks`, `completions`, `completion_edits`.
3. Implement recurrence engine utilities with unit tests (RRULE parsing, anchored vs calendar behavior, timezone handling).
4. Implement `upcoming` endpoint and completion logging with audit trail.
5. Add export endpoint and sample `chronographer-skill` client.
6. Deploy to Azure using container or App Service and test with the agent.

---

## Questions / clarifications recorded

- Single-user mode confirmed.
- Cloud-hosted (Azure) confirmed.
- Poll-only model (agent polls `/upcoming`) confirmed.
- RFC5545 RRULE chosen for recurrence.
- Support both calendar-anchored and completion-anchored recurrences; completion-anchored next-due = last_completion + interval.
- Per-task policy controls missed/expired occurrences (no global default required).
- Free-text metadata on tasks and completions is required; cycle-specific fields are not required.
- Completions editable with audit trail.
- No attachments; no inbox; defer tags.
- Single static API key to be provisioned manually.
- Keep history indefinitely; export endpoint required.



*End of mini-spec (draft).*
