# Chronographer

Chronographer is a single-user reminders and completion-journal API. It computes
one-time and RFC5545 recurring occurrences server-side, supports calendar- and
completion-anchored schedules, and exposes a small poll-only API for agents.

## Run locally

Requirements: Docker with Compose.

```bash
cp .env.example .env
# Replace both secrets in .env, then:
docker compose up --build -d
docker compose ps
curl http://localhost:8000/healthz
```

The web container applies Alembic migrations before starting. PostgreSQL data is
kept in the `db_data` named volume. The interactive API documentation is at
`http://localhost:8000/docs`; `/api/v1/**` requires
`Authorization: Bearer $API_KEY`.

## Common operations

Create a calendar-anchored task:

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"title":"Take out trash","task_type":"recurring","start_at":"2026-07-15T19:00:00-07:00","timezone":"America/Los_Angeles","recurrence_rrule":"FREQ=WEEKLY;BYDAY=WE","recurrence_anchor":"calendar"}'
```

Poll and complete an occurrence:

```bash
curl -G http://localhost:8000/api/v1/upcoming \
  -H "Authorization: Bearer $API_KEY" \
  --data-urlencode "start=2026-07-15T00:00:00-07:00" \
  --data-urlencode "end=2026-07-16T00:00:00-07:00" \
  --data-urlencode "include_overdue=true"

curl -X POST http://localhost:8000/api/v1/tasks/TASK_ID/completions \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"occurrence_id":"OCCURRENCE_ID","notes":"done","idempotency_key":"unique-agent-key"}'
```

Export JSON or flattened CSV:

```bash
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/v1/export?format=json" -o chronographer.json
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8000/api/v1/export?format=csv" -o chronographer.csv
```

Back up the database with `pg_dump`:

```bash
docker compose exec -T db pg_dump -U postgres chronographer > chronographer.sql
```

Run a migration manually with `docker compose run --rm web alembic upgrade head`.
For a clean local reset, stop the stack and deliberately remove its named volume.

## Development

```bash
python -m venv .venv
.venv/Scripts/pip install -e "src/app[dev]"  # Windows
pytest src/app/tests
ruff check src/app/app src/app/tests scripts
python scripts/export_openapi.py --check
```

PostgreSQL integration tests use `DATABASE_URL` and skip when it is unavailable.
The default test database URL is
`postgresql+asyncpg://postgres:postgres@localhost:5432/chronographer_test`.

The generated [OpenAPI contract](openapi.yaml) is committed. Regenerate it with
`python scripts/export_openapi.py` after changing API models or routes.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | Async PostgreSQL connection URL | Compose database |
| `API_KEY` | Static API Bearer secret | Required by Compose |
| `DEFAULT_TIMEZONE` | Single-user/default task timezone | `America/Los_Angeles` |
| `USER_DISPLAY_NAME` | Seeded user display name | `Chronographer User` |
| `OCCURRENCE_LIMIT` | Maximum generated occurrences per task/query | `500` |

See [Azure deployment notes](docs/azure.md) for a future cloud migration. The
original requirements remain in [PERSONAL_REMINDERS_MINI_SPEC.md](PERSONAL_REMINDERS_MINI_SPEC.md).

## Troubleshooting

- `401`: verify the API and client use the same `API_KEY`.
- Database unhealthy: inspect `docker compose logs db`; changing the password in
  `.env` does not change credentials already initialized in the persistent volume.
- API startup failure: inspect `docker compose logs web`; migration errors are
  emitted before Uvicorn starts.
- `422` occurrence-limit error: query a smaller window or raise
  `OCCURRENCE_LIMIT` deliberately.

