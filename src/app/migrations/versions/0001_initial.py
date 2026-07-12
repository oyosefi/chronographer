"""Initial Chronographer schema."""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.Text()),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        sa.text(
            "INSERT INTO users (id, display_name, timezone) "
            "VALUES (CAST(:id AS uuid), :name, :timezone)"
        ).bindparams(
            id="00000000-0000-0000-0000-000000000001",
            name=os.getenv("USER_DISPLAY_NAME", "Chronographer User"),
            timezone=os.getenv("DEFAULT_TIMEZONE", "America/Los_Angeles"),
        )
    )
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("task_type", sa.String(20), nullable=False),
        sa.Column("timezone", sa.Text()),
        sa.Column("start_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("recurrence_rrule", sa.Text()),
        sa.Column("recurrence_anchor", sa.String(20), nullable=False, server_default="calendar"),
        sa.Column("remind_until_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expire_after_seconds", sa.Integer()),
        sa.Column("last_completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("task_type IN ('reminder','one_time','recurring')", name="ck_task_type"),
        sa.CheckConstraint("recurrence_anchor IN ('calendar','completion')", name="ck_anchor"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_task_status"),
        sa.CheckConstraint(
            "expire_after_seconds IS NULL OR expire_after_seconds > 0", name="ck_expiry"
        ),
    )
    op.create_index("idx_tasks_user", "tasks", ["user_id"])
    op.create_table(
        "completions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=False
        ),
        sa.Column("occurrence_id", postgresql.UUID(as_uuid=True)),
        sa.Column("occurrence_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("idempotency_key", sa.String(255)),
        sa.Column("request_fingerprint", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("task_id", "idempotency_key", name="uq_completion_idempotency"),
    )
    op.create_index("idx_completions_task", "completions", ["task_id"])
    op.create_index("idx_completions_occurrence", "completions", ["task_id", "occurrence_at"])
    op.create_table(
        "completion_edits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "completion_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("completions.id"),
            nullable=False,
        ),
        sa.Column("previous_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_notes", sa.Text()),
        sa.Column("previous_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("edited_by", sa.Text(), nullable=False, server_default="api-key"),
    )
    op.create_index("idx_completion_edits_completion", "completion_edits", ["completion_id"])


def downgrade() -> None:
    op.drop_table("completion_edits")
    op.drop_table("completions")
    op.drop_table("tasks")
    op.drop_table("users")
