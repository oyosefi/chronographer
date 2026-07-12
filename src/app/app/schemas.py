import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TaskType = Literal["reminder", "one_time", "recurring"]
Anchor = Literal["calendar", "completion"]
TaskStatus = Literal["active", "archived"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    task_type: TaskType
    timezone: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    recurrence_rrule: str | None = None
    recurrence_anchor: Anchor = "calendar"
    remind_until_done: bool = False
    expire_after_seconds: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.task_type == "recurring":
            if not self.start_at or not self.recurrence_rrule:
                raise ValueError("recurring tasks require start_at and recurrence_rrule")
        elif not (self.due_at or self.start_at):
            raise ValueError("reminders and one-time tasks require due_at or start_at")
        if self.task_type != "recurring" and self.recurrence_anchor == "completion":
            raise ValueError("completion anchoring is only valid for recurring tasks")
        if self.task_type != "recurring" and self.recurrence_rrule:
            raise ValueError("recurrence_rrule is only valid for recurring tasks")
        return self


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    timezone: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    recurrence_rrule: str | None = None
    recurrence_anchor: Anchor | None = None
    remind_until_done: bool | None = None
    expire_after_seconds: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] | None = None
    status: TaskStatus | None = None


class TaskRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    task_type: TaskType
    timezone: str | None
    start_at: datetime | None
    due_at: datetime | None
    recurrence_rrule: str | None
    recurrence_anchor: Anchor
    remind_until_done: bool
    expire_after_seconds: int | None
    last_completed_at: datetime | None
    metadata: dict[str, Any]
    status: TaskStatus
    created_at: datetime
    updated_at: datetime


class CompletionCreate(BaseModel):
    completed_at: datetime | None = None
    occurrence_id: uuid.UUID | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class CompletionPatch(BaseModel):
    completed_at: datetime | None = None
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class CompletionRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    occurrence_id: uuid.UUID | None
    occurrence_at: datetime | None
    completed_at: datetime
    notes: str | None
    metadata: dict[str, Any]
    created_at: datetime
    edited: bool


class CompletionEditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    completion_id: uuid.UUID
    previous_completed_at: datetime
    previous_notes: str | None
    previous_metadata: dict[str, Any]
    edited_at: datetime
    edited_by: str


class OccurrenceRead(BaseModel):
    occurrence_id: uuid.UUID
    task_id: uuid.UUID
    due_at_utc: datetime
    local_due_at: datetime
    is_overdue: bool
    task: TaskRead
    last_completion_id: uuid.UUID | None
