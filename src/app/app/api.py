import csv
import hashlib
import hmac
import io
import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .models import SINGLE_USER_ID, Completion, CompletionEdit, Task
from .recurrence import (
    RecurrenceError,
    next_scheduled_occurrence,
    normalize_datetime,
    scheduled_occurrences,
    timezone,
    validate_rrule,
)
from .schemas import (
    CompletionCreate,
    CompletionEditRead,
    CompletionPatch,
    CompletionRead,
    OccurrenceRead,
    TaskCreate,
    TaskPatch,
    TaskRead,
)

router = APIRouter(prefix="/api/v1")
bearer = HTTPBearer(auto_error=False)
Session = Annotated[AsyncSession, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


async def authenticate(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Config,
) -> None:
    valid = credentials and credentials.scheme.lower() == "bearer"
    if not valid or not hmac.compare_digest(credentials.credentials, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


router.dependencies.append(Depends(authenticate))


def task_read(task: Task) -> TaskRead:
    return TaskRead(
        id=task.id,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        timezone=task.timezone,
        start_at=task.start_at,
        due_at=task.due_at,
        recurrence_rrule=task.recurrence_rrule,
        recurrence_anchor=task.recurrence_anchor,
        remind_until_done=task.remind_until_done,
        expire_after_seconds=task.expire_after_seconds,
        last_completed_at=task.last_completed_at,
        metadata=task.metadata_,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def completion_read(completion: Completion) -> CompletionRead:
    return CompletionRead(
        id=completion.id,
        task_id=completion.task_id,
        occurrence_id=completion.occurrence_id,
        occurrence_at=completion.occurrence_at,
        completed_at=completion.completed_at,
        notes=completion.notes,
        metadata=completion.metadata_,
        created_at=completion.created_at,
        edited=completion.edited,
    )


def task_timezone(task: Task, settings: Settings) -> str:
    return task.timezone or settings.default_timezone


def validate_task_payload(
    payload: TaskCreate, settings: Settings
) -> tuple[datetime | None, datetime | None]:
    tz_name = payload.timezone or settings.default_timezone
    try:
        timezone(tz_name)
        start_at = normalize_datetime(payload.start_at, tz_name) if payload.start_at else None
        due_at = normalize_datetime(payload.due_at, tz_name) if payload.due_at else None
        if payload.recurrence_rrule and start_at:
            validate_rrule(payload.recurrence_rrule, start_at, tz_name)
    except RecurrenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return start_at, due_at


async def get_task_or_404(session: AsyncSession, task_id: uuid.UUID, lock: bool = False) -> Task:
    query = select(Task).where(Task.id == task_id, Task.user_id == SINGLE_USER_ID)
    if lock:
        query = query.with_for_update()
    task = await session.scalar(query)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post("/tasks", status_code=201)
async def create_task(payload: TaskCreate, session: Session, settings: Config) -> dict[str, Any]:
    start_at, due_at = validate_task_payload(payload, settings)
    task = Task(
        user_id=SINGLE_USER_ID,
        title=payload.title,
        description=payload.description,
        task_type=payload.task_type,
        timezone=payload.timezone,
        start_at=start_at,
        due_at=due_at,
        recurrence_rrule=payload.recurrence_rrule,
        recurrence_anchor=payload.recurrence_anchor,
        remind_until_done=payload.remind_until_done,
        expire_after_seconds=payload.expire_after_seconds,
        metadata_=payload.metadata,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return {"task": task_read(task)}


@router.get("/tasks")
async def list_tasks(
    session: Session,
    task_type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    recurring: bool | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
) -> dict[str, Any]:
    query = select(Task).where(Task.user_id == SINGLE_USER_ID)
    if task_type:
        query = query.where(Task.task_type == task_type)
    if status_filter:
        query = query.where(Task.status == status_filter)
    if recurring is not None:
        query = query.where(
            Task.task_type == "recurring" if recurring else Task.task_type != "recurring"
        )
    scheduled = func.coalesce(Task.due_at, Task.start_at)
    if due_from:
        query = query.where(scheduled >= due_from)
    if due_to:
        query = query.where(scheduled <= due_to)
    tasks = (await session.scalars(query.order_by(Task.created_at))).all()
    return {"tasks": [task_read(task) for task in tasks]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: uuid.UUID, session: Session) -> dict[str, Any]:
    return {"task": task_read(await get_task_or_404(session, task_id))}


SCHEDULING_FIELDS = {
    "timezone",
    "start_at",
    "due_at",
    "recurrence_rrule",
    "recurrence_anchor",
}


@router.patch("/tasks/{task_id}")
async def patch_task(
    task_id: uuid.UUID, payload: TaskPatch, session: Session, settings: Config
) -> dict[str, Any]:
    async with session.begin():
        task = await get_task_or_404(session, task_id, lock=True)
        changes = payload.model_dump(exclude_unset=True)
        if SCHEDULING_FIELDS.intersection(changes):
            count = await session.scalar(
                select(func.count()).select_from(Completion).where(Completion.task_id == task.id)
            )
            if count:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "scheduling fields cannot change after completions exist; "
                        "archive and recreate the task"
                    ),
                )
        candidate_data = {
            "title": changes.get("title", task.title),
            "description": changes.get("description", task.description),
            "task_type": task.task_type,
            "timezone": changes.get("timezone", task.timezone),
            "start_at": changes.get("start_at", task.start_at),
            "due_at": changes.get("due_at", task.due_at),
            "recurrence_rrule": changes.get("recurrence_rrule", task.recurrence_rrule),
            "recurrence_anchor": changes.get("recurrence_anchor", task.recurrence_anchor),
            "remind_until_done": changes.get("remind_until_done", task.remind_until_done),
            "expire_after_seconds": changes.get("expire_after_seconds", task.expire_after_seconds),
            "metadata": changes.get("metadata", task.metadata_),
        }
        try:
            candidate = TaskCreate.model_validate(candidate_data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        start_at, due_at = validate_task_payload(candidate, settings)
        for key, value in changes.items():
            if key == "metadata":
                task.metadata_ = value
            elif key == "start_at":
                task.start_at = start_at
            elif key == "due_at":
                task.due_at = due_at
            else:
                setattr(task, key, value)
    await session.refresh(task)
    return {"task": task_read(task)}


@router.delete("/tasks/{task_id}")
async def archive_task(task_id: uuid.UUID, session: Session) -> dict[str, Any]:
    async with session.begin():
        task = await get_task_or_404(session, task_id, lock=True)
        task.status = "archived"
    await session.refresh(task)
    return {"task": task_read(task)}


def fingerprint(payload: CompletionCreate) -> str:
    body = payload.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


async def completed_occurrence_ids(session: AsyncSession, task_id: uuid.UUID) -> set[uuid.UUID]:
    values = await session.scalars(
        select(Completion.occurrence_id).where(
            Completion.task_id == task_id,
            Completion.deleted.is_(False),
            Completion.occurrence_id.is_not(None),
        )
    )
    return set(values)


def occurrences_for(
    task: Task,
    settings: Settings,
    start: datetime,
    end: datetime,
):
    return scheduled_occurrences(
        task_id=task.id,
        task_type=task.task_type,
        start_at=task.start_at,
        due_at=task.due_at,
        recurrence_rrule=task.recurrence_rrule,
        recurrence_anchor=task.recurrence_anchor,
        last_completed_at=task.last_completed_at,
        timezone_name=task_timezone(task, settings),
        window_start=start,
        window_end=end,
        limit=settings.occurrence_limit,
    )


def query_error(exc: RecurrenceError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


async def resolve_completion_occurrence(
    session: AsyncSession,
    task: Task,
    settings: Settings,
    completed_at: datetime,
    requested_id: uuid.UUID | None,
) -> tuple[uuid.UUID | None, datetime | None]:
    tz_name = task_timezone(task, settings)
    initial = task.start_at or task.due_at or completed_at
    search_start = normalize_datetime(initial, tz_name)
    search_end = completed_at
    if requested_id and task.recurrence_anchor == "completion":
        search_end = completed_at + timedelta(days=366 * 100)
    try:
        candidates = occurrences_for(task, settings, search_start, search_end)
    except RecurrenceError as exc:
        raise query_error(exc) from exc
    completed = await completed_occurrence_ids(session, task.id)
    available = [item for item in candidates if item.occurrence_id not in completed]
    if requested_id:
        match = next((item for item in candidates if item.occurrence_id == requested_id), None)
        if not match:
            raise HTTPException(
                status_code=422, detail="occurrence_id is not valid for this task schedule"
            )
        if match.occurrence_id in completed:
            raise HTTPException(status_code=409, detail="occurrence is already completed")
        return match.occurrence_id, match.due_at
    due = [item for item in available if item.due_at <= completed_at]
    if not due:
        return None, None
    match = max(due, key=lambda item: item.due_at)
    return match.occurrence_id, match.due_at


@router.post("/tasks/{task_id}/completions", status_code=201)
async def create_completion(
    task_id: uuid.UUID,
    payload: CompletionCreate,
    session: Session,
    settings: Config,
    response: Response,
) -> dict[str, Any]:
    request_fingerprint = fingerprint(payload)
    async with session.begin():
        task = await get_task_or_404(session, task_id, lock=True)
        if payload.idempotency_key:
            existing = await session.scalar(
                select(Completion).where(
                    Completion.task_id == task.id,
                    Completion.idempotency_key == payload.idempotency_key,
                )
            )
            if existing:
                if existing.request_fingerprint != request_fingerprint:
                    raise HTTPException(
                        status_code=409, detail="idempotency key was reused with different content"
                    )
                response.status_code = 200
                return {"completion": completion_read(existing)}
        tz_name = task_timezone(task, settings)
        completed_at = normalize_datetime(payload.completed_at or datetime.now(UTC), tz_name)
        occurrence_id, occurrence_at = await resolve_completion_occurrence(
            session, task, settings, completed_at, payload.occurrence_id
        )
        completion = Completion(
            task_id=task.id,
            occurrence_id=occurrence_id,
            occurrence_at=occurrence_at,
            completed_at=completed_at,
            notes=payload.notes,
            metadata_=payload.metadata,
            idempotency_key=payload.idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        session.add(completion)
        await session.flush()
        if task.recurrence_anchor == "completion" and (
            task.last_completed_at is None or completed_at > task.last_completed_at
        ):
            task.last_completed_at = completed_at
    await session.refresh(completion)
    return {"completion": completion_read(completion)}


@router.get("/tasks/{task_id}/completions")
async def list_completions(task_id: uuid.UUID, session: Session) -> dict[str, Any]:
    await get_task_or_404(session, task_id)
    values = (
        await session.scalars(
            select(Completion)
            .where(Completion.task_id == task_id, Completion.deleted.is_(False))
            .order_by(Completion.completed_at.desc())
        )
    ).all()
    return {"completions": [completion_read(item) for item in values]}


@router.get("/tasks/{task_id}/last")
async def last_completion(task_id: uuid.UUID, session: Session) -> dict[str, Any]:
    await get_task_or_404(session, task_id)
    value = await session.scalar(
        select(Completion)
        .where(Completion.task_id == task_id, Completion.deleted.is_(False))
        .order_by(Completion.completed_at.desc())
        .limit(1)
    )
    return {"completion": completion_read(value) if value else None}


@router.patch("/tasks/{task_id}/completions/{completion_id}")
async def patch_completion(
    task_id: uuid.UUID,
    completion_id: uuid.UUID,
    payload: CompletionPatch,
    session: Session,
    settings: Config,
) -> dict[str, Any]:
    async with session.begin():
        task = await get_task_or_404(session, task_id, lock=True)
        completion = await session.scalar(
            select(Completion)
            .where(Completion.id == completion_id, Completion.task_id == task.id)
            .with_for_update()
        )
        if not completion or completion.deleted:
            raise HTTPException(status_code=404, detail="completion not found")
        changes = payload.model_dump(exclude_unset=True)
        if changes:
            session.add(
                CompletionEdit(
                    completion_id=completion.id,
                    previous_completed_at=completion.completed_at,
                    previous_notes=completion.notes,
                    previous_metadata=completion.metadata_,
                )
            )
            if "completed_at" in changes:
                if changes["completed_at"] is None:
                    raise HTTPException(status_code=422, detail="completed_at cannot be null")
                completion.completed_at = normalize_datetime(
                    changes["completed_at"], task_timezone(task, settings)
                )
            if "notes" in changes:
                completion.notes = changes["notes"]
            if "metadata" in changes:
                completion.metadata_ = changes["metadata"]
            completion.edited = True
            if task.recurrence_anchor == "completion":
                task.last_completed_at = await session.scalar(
                    select(func.max(Completion.completed_at)).where(
                        Completion.task_id == task.id, Completion.deleted.is_(False)
                    )
                )
    await session.refresh(completion)
    return {"completion": completion_read(completion)}


async def occurrence_response(
    session: AsyncSession,
    task: Task,
    item,
    display_tz: str,
    now: datetime,
) -> OccurrenceRead:
    last_id = await session.scalar(
        select(Completion.id)
        .where(Completion.task_id == task.id, Completion.deleted.is_(False))
        .order_by(Completion.completed_at.desc())
        .limit(1)
    )
    return OccurrenceRead(
        occurrence_id=item.occurrence_id,
        task_id=task.id,
        due_at_utc=item.due_at,
        local_due_at=item.due_at.astimezone(timezone(display_tz)),
        is_overdue=item.due_at < now,
        task=task_read(task),
        last_completion_id=last_id,
    )


@router.get("/upcoming")
async def upcoming(
    start: datetime,
    end: datetime,
    session: Session,
    settings: Config,
    include_overdue: bool = False,
    display_tz: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    display_name = display_tz or settings.default_timezone
    try:
        timezone(display_name)
        start_utc = normalize_datetime(start, settings.default_timezone)
        end_utc = normalize_datetime(end, settings.default_timezone)
    except RecurrenceError as exc:
        raise query_error(exc) from exc
    tasks = (
        await session.scalars(
            select(Task).where(Task.user_id == SINGLE_USER_ID, Task.status == "active")
        )
    ).all()
    output = []
    for task in tasks:
        task_start = start_utc
        if include_overdue and task.remind_until_done:
            task_start = normalize_datetime(
                task.start_at or task.due_at or start_utc, task_timezone(task, settings)
            )
            if task.expire_after_seconds:
                task_start = max(task_start, now - timedelta(seconds=task.expire_after_seconds))
        try:
            generated = occurrences_for(task, settings, task_start, end_utc)
        except RecurrenceError as exc:
            raise query_error(exc) from exc
        completed = await completed_occurrence_ids(session, task.id)
        for item in generated:
            if item.occurrence_id in completed:
                continue
            if item.due_at < start_utc and not (include_overdue and task.remind_until_done):
                continue
            output.append(await occurrence_response(session, task, item, display_name, now))
    output.sort(key=lambda item: item.due_at_utc)
    return {"occurrences": output}


@router.get("/tasks/{task_id}/next")
async def next_occurrence(
    task_id: uuid.UUID,
    session: Session,
    settings: Config,
    display_tz: str | None = None,
) -> dict[str, Any]:
    task = await get_task_or_404(session, task_id)
    now = datetime.now(UTC)
    completed = await completed_occurrence_ids(session, task.id)
    cursor = now
    try:
        item = None
        for _ in range(settings.occurrence_limit):
            item = next_scheduled_occurrence(
                task_id=task.id,
                task_type=task.task_type,
                start_at=task.start_at,
                due_at=task.due_at,
                recurrence_rrule=task.recurrence_rrule,
                recurrence_anchor=task.recurrence_anchor,
                last_completed_at=task.last_completed_at,
                timezone_name=task_timezone(task, settings),
                after=cursor,
            )
            if item is None or item.occurrence_id not in completed:
                break
            cursor = item.due_at + timedelta(microseconds=1)
    except RecurrenceError as exc:
        raise query_error(exc) from exc
    if not item:
        return {"occurrence": None}
    display_name = display_tz or settings.default_timezone
    try:
        value = await occurrence_response(session, task, item, display_name, now)
    except RecurrenceError as exc:
        raise query_error(exc) from exc
    return {"occurrence": value}


@router.get("/export")
async def export_data(
    session: Session,
    format: str = Query(pattern="^(json|csv)$"),
    since: date | None = None,
):
    cutoff = datetime.combine(since, time.min, UTC) if since else None
    task_query = select(Task).where(Task.user_id == SINGLE_USER_ID)
    completion_query = select(Completion).join(Task).where(Task.user_id == SINGLE_USER_ID)
    edit_query = (
        select(CompletionEdit).join(Completion).join(Task).where(Task.user_id == SINGLE_USER_ID)
    )
    if cutoff:
        task_query = task_query.where(Task.updated_at >= cutoff)
        completion_query = completion_query.where(
            or_(Completion.created_at >= cutoff, Completion.completed_at >= cutoff)
        )
        edit_query = edit_query.where(CompletionEdit.edited_at >= cutoff)
    tasks = (await session.scalars(task_query)).all()
    completions = (await session.scalars(completion_query)).all()
    edits = (await session.scalars(edit_query)).all()
    if format == "json":
        return {
            "tasks": [task_read(item) for item in tasks],
            "completions": [completion_read(item) for item in completions],
            "completion_edits": [CompletionEditRead.model_validate(item) for item in edits],
        }

    completion_map: dict[uuid.UUID, list[Completion]] = {}
    for completion in completions:
        completion_map.setdefault(completion.task_id, []).append(completion)
    stream = io.StringIO()
    fieldnames = [
        "task_id",
        "title",
        "task_type",
        "task_status",
        "task_timezone",
        "task_metadata",
        "completion_id",
        "occurrence_id",
        "occurrence_at",
        "completed_at",
        "notes",
        "completion_metadata",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for task in tasks:
        task_completions = completion_map.get(task.id) or [None]
        for completion in task_completions:
            writer.writerow(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "task_type": task.task_type,
                    "task_status": task.status,
                    "task_timezone": task.timezone or "",
                    "task_metadata": json.dumps(task.metadata_, sort_keys=True),
                    "completion_id": completion.id if completion else "",
                    "occurrence_id": completion.occurrence_id if completion else "",
                    "occurrence_at": completion.occurrence_at.isoformat()
                    if completion and completion.occurrence_at
                    else "",
                    "completed_at": completion.completed_at.isoformat() if completion else "",
                    "notes": completion.notes if completion else "",
                    "completion_metadata": json.dumps(completion.metadata_, sort_keys=True)
                    if completion
                    else "",
                }
            )
    return Response(
        stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=chronographer-export.csv"},
    )
