from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas import TaskCreate


def test_recurring_task_requires_rule_and_start():
    with pytest.raises(ValidationError):
        TaskCreate(title="Missing schedule", task_type="recurring")


def test_one_time_requires_a_time():
    with pytest.raises(ValidationError):
        TaskCreate(title="Missing time", task_type="one_time")


def test_completion_anchor_rejected_for_non_recurring():
    with pytest.raises(ValidationError):
        TaskCreate(
            title="Invalid",
            task_type="reminder",
            due_at=datetime(2026, 1, 1),
            recurrence_anchor="completion",
        )


def test_metadata_remains_opaque():
    task = TaskCreate(
        title="Opaque",
        task_type="reminder",
        due_at=datetime(2026, 1, 1),
        metadata={"cycle": {"anything": "is accepted"}},
    )
    assert task.metadata["cycle"]["anything"] == "is accepted"
