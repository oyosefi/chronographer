import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr

OCCURRENCE_NAMESPACE = uuid.UUID("6b0bb08d-4308-51b6-a6cb-ae2d81503829")


class RecurrenceError(ValueError):
    pass


class OccurrenceLimitError(RecurrenceError):
    pass


@dataclass(frozen=True)
class ScheduledOccurrence:
    occurrence_id: uuid.UUID
    due_at: datetime


def timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise RecurrenceError(f"unknown IANA timezone: {value}") from exc


def normalize_datetime(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone(timezone_name))
    return value.astimezone(UTC)


def occurrence_id(task_id: uuid.UUID, due_at: datetime) -> uuid.UUID:
    due_utc = due_at.astimezone(UTC).isoformat(timespec="microseconds")
    return uuid.uuid5(OCCURRENCE_NAMESPACE, f"{task_id}:{due_utc}")


def validate_rrule(value: str, start_at: datetime, timezone_name: str) -> None:
    try:
        local_start = normalize_datetime(start_at, timezone_name).astimezone(
            timezone(timezone_name)
        )
        rrulestr(value, dtstart=local_start)
    except (ValueError, TypeError) as exc:
        raise RecurrenceError(f"invalid recurrence_rrule: {exc}") from exc


def scheduled_occurrences(
    *,
    task_id: uuid.UUID,
    task_type: str,
    start_at: datetime | None,
    due_at: datetime | None,
    recurrence_rrule: str | None,
    recurrence_anchor: str,
    last_completed_at: datetime | None,
    timezone_name: str,
    window_start: datetime,
    window_end: datetime,
    limit: int = 500,
) -> list[ScheduledOccurrence]:
    start_utc = normalize_datetime(window_start, timezone_name)
    end_utc = normalize_datetime(window_end, timezone_name)
    if end_utc < start_utc:
        raise RecurrenceError("end must be on or after start")

    if task_type != "recurring":
        scheduled = due_at or start_at
        if scheduled is None:
            return []
        scheduled = normalize_datetime(scheduled, timezone_name)
        return (
            [ScheduledOccurrence(occurrence_id(task_id, scheduled), scheduled)]
            if start_utc <= scheduled <= end_utc
            else []
        )

    if start_at is None or not recurrence_rrule:
        raise RecurrenceError("recurring task is missing its schedule")
    tz = timezone(timezone_name)
    initial = normalize_datetime(start_at, timezone_name)

    if recurrence_anchor == "completion":
        if last_completed_at is None:
            values = [initial] if start_utc <= initial <= end_utc else []
        else:
            anchor = normalize_datetime(last_completed_at, timezone_name).astimezone(tz)
            rule = rrulestr(recurrence_rrule, dtstart=anchor)
            candidate = rule.after(anchor, inc=False)
            candidate_utc = candidate.astimezone(UTC) if candidate else None
            values = (
                [candidate_utc] if candidate_utc and start_utc <= candidate_utc <= end_utc else []
            )
    else:
        local_initial = initial.astimezone(tz)
        rule = rrulestr(recurrence_rrule, dtstart=local_initial)
        local_start = start_utc.astimezone(tz)
        local_end = end_utc.astimezone(tz)
        generated = rule.between(local_start, local_end, inc=True)
        if len(generated) > limit:
            raise OccurrenceLimitError(f"task exceeds the {limit}-occurrence query limit")
        values = [item.astimezone(UTC) for item in generated]

    if len(values) > limit:
        raise OccurrenceLimitError(f"task exceeds the {limit}-occurrence query limit")
    return [ScheduledOccurrence(occurrence_id(task_id, value), value) for value in values]


def next_scheduled_occurrence(
    *,
    task_id: uuid.UUID,
    task_type: str,
    start_at: datetime | None,
    due_at: datetime | None,
    recurrence_rrule: str | None,
    recurrence_anchor: str,
    last_completed_at: datetime | None,
    timezone_name: str,
    after: datetime,
) -> ScheduledOccurrence | None:
    """Return one next occurrence without expanding the intervening schedule."""
    after_utc = normalize_datetime(after, timezone_name)
    if task_type != "recurring":
        scheduled = due_at or start_at
        if scheduled is None:
            return None
        scheduled = normalize_datetime(scheduled, timezone_name)
        return (
            ScheduledOccurrence(occurrence_id(task_id, scheduled), scheduled)
            if scheduled >= after_utc
            else None
        )
    if start_at is None or not recurrence_rrule:
        raise RecurrenceError("recurring task is missing its schedule")

    tz = timezone(timezone_name)
    initial = normalize_datetime(start_at, timezone_name)
    if recurrence_anchor == "completion":
        if last_completed_at is None:
            candidate = initial if initial >= after_utc else None
        else:
            anchor = normalize_datetime(last_completed_at, timezone_name).astimezone(tz)
            rule = rrulestr(recurrence_rrule, dtstart=anchor)
            generated = rule.after(anchor, inc=False)
            candidate = generated.astimezone(UTC) if generated else None
            if candidate and candidate < after_utc:
                candidate = None
    else:
        local_initial = initial.astimezone(tz)
        rule = rrulestr(recurrence_rrule, dtstart=local_initial)
        generated = rule.after(after_utc.astimezone(tz), inc=True)
        candidate = generated.astimezone(UTC) if generated else None

    if candidate is None:
        return None
    return ScheduledOccurrence(occurrence_id(task_id, candidate), candidate)
