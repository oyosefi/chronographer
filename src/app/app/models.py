import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SINGLE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("task_type IN ('reminder','one_time','recurring')", name="ck_task_type"),
        CheckConstraint("recurrence_anchor IN ('calendar','completion')", name="ck_anchor"),
        CheckConstraint("status IN ('active','archived')", name="ck_task_status"),
        CheckConstraint(
            "expire_after_seconds IS NULL OR expire_after_seconds > 0", name="ck_expiry"
        ),
        Index("idx_tasks_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, default=SINGLE_USER_ID
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    timezone: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recurrence_rrule: Mapped[str | None] = mapped_column(Text)
    recurrence_anchor: Mapped[str] = mapped_column(String(20), nullable=False, default="calendar")
    remind_until_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expire_after_seconds: Mapped[int | None] = mapped_column(Integer)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    completions: Mapped[list["Completion"]] = relationship(back_populates="task")


class Completion(Base):
    __tablename__ = "completions"
    __table_args__ = (
        UniqueConstraint("task_id", "idempotency_key", name="uq_completion_idempotency"),
        Index("idx_completions_task", "task_id"),
        Index("idx_completions_occurrence", "task_id", "occurrence_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    occurrence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurrence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    task: Mapped[Task] = relationship(back_populates="completions")
    edits: Mapped[list["CompletionEdit"]] = relationship(back_populates="completion")


class CompletionEdit(Base):
    __tablename__ = "completion_edits"
    __table_args__ = (Index("idx_completion_edits_completion", "completion_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    completion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("completions.id"), nullable=False
    )
    previous_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_notes: Mapped[str | None] = mapped_column(Text)
    previous_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False)
    edited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    edited_by: Mapped[str] = mapped_column(Text, nullable=False, default="api-key")

    completion: Mapped[Completion] = relationship(back_populates="edits")
