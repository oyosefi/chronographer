import uuid
from datetime import UTC, datetime

import pytest

from app.recurrence import (
    OccurrenceLimitError,
    next_scheduled_occurrence,
    normalize_datetime,
    occurrence_id,
    scheduled_occurrences,
)

TASK_ID = uuid.UUID("e0313606-ecb7-48e5-85e4-d3c71f1bd953")


def generate(**overrides):
    values = {
        "task_id": TASK_ID,
        "task_type": "recurring",
        "start_at": datetime.fromisoformat("2026-03-01T09:00:00-08:00"),
        "due_at": None,
        "recurrence_rrule": "FREQ=WEEKLY;COUNT=3",
        "recurrence_anchor": "calendar",
        "last_completed_at": None,
        "timezone_name": "America/Los_Angeles",
        "window_start": datetime.fromisoformat("2026-03-01T00:00:00-08:00"),
        "window_end": datetime.fromisoformat("2026-03-20T23:59:59-07:00"),
        "limit": 500,
    }
    values.update(overrides)
    return scheduled_occurrences(**values)


def test_calendar_recurrence_preserves_wall_clock_across_dst():
    values = generate()
    local = [
        item.due_at.astimezone(__import__("zoneinfo").ZoneInfo("America/Los_Angeles"))
        for item in values
    ]
    assert [item.hour for item in local] == [9, 9, 9]
    assert [item.utcoffset().total_seconds() / 3600 for item in local] == [-8, -7, -7]


def test_completion_anchor_uses_first_rule_value_after_completion():
    values = generate(
        recurrence_rrule="FREQ=MONTHLY;INTERVAL=2",
        recurrence_anchor="completion",
        last_completed_at=datetime.fromisoformat("2026-07-11T18:00:00-07:00"),
        window_start=datetime.fromisoformat("2026-07-11T00:00:00-07:00"),
        window_end=datetime.fromisoformat("2026-10-01T00:00:00-07:00"),
    )
    assert len(values) == 1
    assert values[0].due_at == datetime(2026, 9, 12, 1, 0, tzinfo=UTC)


def test_initial_completion_anchored_occurrence_is_start_at():
    values = generate(recurrence_anchor="completion")
    assert len(values) == 1
    assert values[0].due_at == datetime(2026, 3, 1, 17, 0, tzinfo=UTC)


def test_naive_datetime_uses_configured_timezone():
    value = normalize_datetime(datetime(2026, 1, 1, 9), "America/Los_Angeles")
    assert value == datetime(2026, 1, 1, 17, tzinfo=UTC)


def test_occurrence_id_is_stable_and_time_specific():
    first = occurrence_id(TASK_ID, datetime(2026, 1, 1, tzinfo=UTC))
    assert first == occurrence_id(TASK_ID, datetime(2026, 1, 1, tzinfo=UTC))
    assert first != occurrence_id(TASK_ID, datetime(2026, 1, 2, tzinfo=UTC))


def test_occurrence_generation_is_capped():
    with pytest.raises(OccurrenceLimitError):
        generate(
            recurrence_rrule="FREQ=DAILY",
            window_end=datetime.fromisoformat("2026-03-20T23:59:59-07:00"),
            limit=2,
        )


def test_one_time_prefers_due_at():
    values = generate(
        task_type="one_time",
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        due_at=datetime(2026, 1, 2, tzinfo=UTC),
        recurrence_rrule=None,
        window_start=datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert values[0].due_at == datetime(2026, 1, 2, tzinfo=UTC)


def test_next_does_not_expand_a_long_calendar_schedule():
    value = next_scheduled_occurrence(
        task_id=TASK_ID,
        task_type="recurring",
        start_at=datetime(2000, 1, 1, 9),
        due_at=None,
        recurrence_rrule="FREQ=DAILY",
        recurrence_anchor="calendar",
        last_completed_at=None,
        timezone_name="America/Los_Angeles",
        after=datetime(2026, 7, 11, 18, tzinfo=UTC),
    )
    assert value is not None
    assert value.due_at > datetime(2026, 7, 11, 18, tzinfo=UTC)
