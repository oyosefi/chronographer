import pytest

pytestmark = pytest.mark.asyncio


async def test_authentication_is_required(api_client):
    response = await api_client.get("/api/v1/tasks")
    assert response.status_code == 401


async def test_completion_flow_idempotency_audit_and_export(api_client, auth_headers):
    created = await api_client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "title": "Replace filter",
            "task_type": "recurring",
            "start_at": "2026-05-01T09:00:00-07:00",
            "timezone": "America/Los_Angeles",
            "recurrence_rrule": "FREQ=MONTHLY;INTERVAL=2",
            "recurrence_anchor": "completion",
            "remind_until_done": True,
            "metadata": {"cycle": {"next": "left"}},
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()["task"]

    upcoming = await api_client.get(
        "/api/v1/upcoming",
        headers=auth_headers,
        params={
            "start": "2026-05-01T00:00:00-07:00",
            "end": "2026-05-02T00:00:00-07:00",
        },
    )
    occurrence = upcoming.json()["occurrences"][0]
    payload = {
        "completed_at": "2026-05-01T10:00:00-07:00",
        "occurrence_id": occurrence["occurrence_id"],
        "notes": "done",
        "metadata": {"observed": "right"},
        "idempotency_key": "filter-2026-05",
    }
    first = await api_client.post(
        f"/api/v1/tasks/{task['id']}/completions", headers=auth_headers, json=payload
    )
    assert first.status_code == 201, first.text
    retried = await api_client.post(
        f"/api/v1/tasks/{task['id']}/completions", headers=auth_headers, json=payload
    )
    assert retried.status_code == 200
    assert retried.json() == first.json()

    conflict_payload = {**payload, "notes": "different"}
    conflict = await api_client.post(
        f"/api/v1/tasks/{task['id']}/completions",
        headers=auth_headers,
        json=conflict_payload,
    )
    assert conflict.status_code == 409

    completion_id = first.json()["completion"]["id"]
    edited = await api_client.patch(
        f"/api/v1/tasks/{task['id']}/completions/{completion_id}",
        headers=auth_headers,
        json={"notes": "edited"},
    )
    assert edited.status_code == 200
    assert edited.json()["completion"]["edited"] is True

    refreshed = await api_client.get(f"/api/v1/tasks/{task['id']}", headers=auth_headers)
    assert refreshed.json()["task"]["metadata"] == {"cycle": {"next": "left"}}

    blocked = await api_client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth_headers,
        json={"recurrence_rrule": "FREQ=DAILY"},
    )
    assert blocked.status_code == 409

    export = await api_client.get("/api/v1/export", headers=auth_headers, params={"format": "json"})
    assert len(export.json()["completion_edits"]) == 1
    assert export.json()["completion_edits"][0]["previous_notes"] == "done"

    csv_export = await api_client.get(
        "/api/v1/export", headers=auth_headers, params={"format": "csv"}
    )
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert "Replace filter" in csv_export.text


async def test_one_time_soft_delete_and_filters(api_client, auth_headers):
    created = await api_client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "title": "One thing",
            "task_type": "one_time",
            "start_at": "2026-07-11T09:00:00-07:00",
            "due_at": "2026-07-11T12:00:00-07:00",
        },
    )
    task_id = created.json()["task"]["id"]
    listed = await api_client.get(
        "/api/v1/tasks", headers=auth_headers, params={"task_type": "one_time"}
    )
    assert [item["id"] for item in listed.json()["tasks"]] == [task_id]
    archived = await api_client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert archived.json()["task"]["status"] == "archived"
