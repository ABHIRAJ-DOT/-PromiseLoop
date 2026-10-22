"""Commitment business logic: CRUD, filters, dependencies, activity, next actions."""

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

from app.models import Activity, Commitment, CommitmentDependency, utcnow
from app.schemas import CommitmentCreate, CommitmentRead, CommitmentUpdate, NextAction, as_utc
from app.services.graph import (
    load_dependency_map,
    unfinished_prerequisites,
    would_create_cycle,
)

OPEN_STATUSES = ("pending", "in_progress")


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def resolve_timezone(tz_name: str | None) -> str:
    """Validate an IANA timezone name, falling back to the configured default."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    if not tz_name:
        return get_settings().default_timezone
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone: {tz_name}")
    return tz_name


def local_today(tz_name: str) -> date:
    tz = timezone.utc if tz_name.upper() == "UTC" else _zoneinfo(tz_name)
    return datetime.now(tz).date()


def _zoneinfo(tz_name: str):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def period_bounds(period: str | None, tz_name: str) -> tuple[datetime | None, datetime | None]:
    """Absolute UTC window for a named period, evaluated in the caller's timezone."""
    if not period or period == "all":
        return None, None
    tz = timezone.utc if tz_name.upper() == "UTC" else _zoneinfo(tz_name)
    now = datetime.now(tz)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "today":
        start, end = start_of_day, start_of_day + timedelta(days=1)
    elif period == "week":
        start, end = start_of_day, start_of_day + timedelta(days=7)
    elif period == "month":
        start, end = start_of_day, start_of_day + timedelta(days=30)
    elif period == "overdue":
        return datetime(1970, 1, 1, tzinfo=timezone.utc), now.astimezone(timezone.utc)
    else:
        return None, None
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


async def record_activity(
    session: AsyncSession,
    user_id: uuid.UUID,
    commitment_id: uuid.UUID,
    action: str,
    detail: dict | None = None,
) -> Activity:
    activity = Activity(
        user_id=user_id,
        commitment_id=commitment_id,
        action=action,
        detail=detail or {},
    )
    session.add(activity)
    return activity


async def _to_read(
    commitment: Commitment,
    prerequisites: dict[uuid.UUID, list[uuid.UUID]],
    blocked_by: dict[uuid.UUID, list[uuid.UUID]],
) -> CommitmentRead:
    read = CommitmentRead.model_validate(commitment)
    read.depends_on_ids = prerequisites.get(commitment.id, [])
    read.blocked_by = blocked_by.get(commitment.id, [])
    return read


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
async def create_commitment(
    session: AsyncSession,
    user_id: uuid.UUID,
    data: CommitmentCreate,
    *,
    source: str | None = None,
) -> CommitmentRead:
    commitment = Commitment(
        user_id=user_id,
        title=data.title.strip(),
        recipient=(data.recipient or None) and data.recipient.strip() or None,
        details=data.details,
        status=data.status,
        priority=data.priority,
        due_at=data.due_at,
        due_local_date=data.due_local_date,
        due_local_time=data.due_local_time,
        deadline_precision=data.deadline_precision,
        timezone=data.timezone or "UTC",
        source=source or data.source,
        original_text=data.original_text,
        completed_at=utcnow() if data.status == "completed" else None,
    )
    session.add(commitment)
    await session.flush()

    for depends_on_id in data.depends_on_ids:
        await _link_dependency(session, user_id, commitment.id, depends_on_id)

    await record_activity(
        session,
        user_id,
        commitment.id,
        "created",
        {"title": commitment.title, "recipient": commitment.recipient, "source": commitment.source},
    )
    await session.commit()
    await session.refresh(commitment)

    prerequisites, _ = await load_dependency_map(session, user_id)
    blocked_by = await unfinished_prerequisites(session, user_id)
    return await _to_read(commitment, prerequisites, blocked_by)


async def get_commitment(
    session: AsyncSession, user_id: uuid.UUID, commitment_id: uuid.UUID
) -> Commitment:
    commitment = await session.scalar(
        select(Commitment).where(Commitment.id == commitment_id, Commitment.user_id == user_id)
    )
    if commitment is None:
        raise NotFoundError(f"Commitment {commitment_id} not found")
    return commitment


async def update_commitment(
    session: AsyncSession,
    user_id: uuid.UUID,
    commitment_id: uuid.UUID,
    data: CommitmentUpdate,
) -> CommitmentRead:
    commitment = await get_commitment(session, user_id, commitment_id)
    changes = data.model_dump(exclude_unset=True)

    for field, value in changes.items():
        if field == "depends_on_ids":
            continue
        setattr(commitment, field, value)

    if "status" in changes:
        commitment.completed_at = utcnow() if changes["status"] == "completed" else None

    if "depends_on_ids" in changes and changes["depends_on_ids"] is not None:
        current = {
            row.depends_on_id
            for row in (
                await session.scalars(
                    select(CommitmentDependency).where(
                        CommitmentDependency.commitment_id == commitment_id,
                        CommitmentDependency.user_id == user_id,
                    )
                )
            ).all()
        }
        wanted = set(changes["depends_on_ids"])
        for remove_id in current - wanted:
            await session.execute(
                delete_dependency_stmt(remove_id, commitment_id)
            )
        for add_id in wanted - current:
            await _link_dependency(session, user_id, commitment_id, add_id)

    await record_activity(session, user_id, commitment.id, "updated", changes)
    await session.commit()
    await session.refresh(commitment)

    prerequisites, _ = await load_dependency_map(session, user_id)
    blocked_by = await unfinished_prerequisites(session, user_id)
    return await _to_read(commitment, prerequisites, blocked_by)


def delete_dependency_stmt(depends_on_id: uuid.UUID, commitment_id: uuid.UUID):
    from sqlalchemy import delete

    return delete(CommitmentDependency).where(
        CommitmentDependency.commitment_id == commitment_id,
        CommitmentDependency.depends_on_id == depends_on_id,
    )


async def complete_commitment(
    session: AsyncSession, user_id: uuid.UUID, commitment_id: uuid.UUID
) -> CommitmentRead:
    commitment = await get_commitment(session, user_id, commitment_id)
    if commitment.status != "completed":
        commitment.status = "completed"
        commitment.completed_at = utcnow()
        await record_activity(session, user_id, commitment.id, "completed", {"title": commitment.title})
        await session.commit()
        await session.refresh(commitment)

    prerequisites, _ = await load_dependency_map(session, user_id)
    blocked_by = await unfinished_prerequisites(session, user_id)
    return await _to_read(commitment, prerequisites, blocked_by)


# --------------------------------------------------------------------------- #
# dependencies
# --------------------------------------------------------------------------- #
async def _link_dependency(
    session: AsyncSession,
    user_id: uuid.UUID,
    commitment_id: uuid.UUID,
    depends_on_id: uuid.UUID,
) -> None:
    if commitment_id == depends_on_id:
        raise ConflictError("A commitment cannot depend on itself.")

    for target in (commitment_id, depends_on_id):
        exists = await session.scalar(
            select(Commitment.id).where(Commitment.id == target, Commitment.user_id == user_id)
        )
        if exists is None:
            raise NotFoundError(f"Commitment {target} not found")

    prerequisites, _ = await load_dependency_map(session, user_id)
    if would_create_cycle(prerequisites, commitment_id, depends_on_id):
        raise ConflictError("That dependency would create a circular chain.")

    session.add(
        CommitmentDependency(
            user_id=user_id, commitment_id=commitment_id, depends_on_id=depends_on_id
        )
    )
    await session.flush()


async def add_dependency(
    session: AsyncSession,
    user_id: uuid.UUID,
    commitment_id: uuid.UUID,
    depends_on_id: uuid.UUID,
) -> CommitmentRead:
    commitment = await get_commitment(session, user_id, commitment_id)
    existing = await session.scalar(
        select(CommitmentDependency.id).where(
            CommitmentDependency.commitment_id == commitment_id,
            CommitmentDependency.depends_on_id == depends_on_id,
        )
    )
    if existing is None:
        await _link_dependency(session, user_id, commitment_id, depends_on_id)
        await record_activity(
            session,
            user_id,
            commitment_id,
            "dependency_added",
            {"depends_on_id": str(depends_on_id)},
        )
        await session.commit()
        await session.refresh(commitment)

    prerequisites, _ = await load_dependency_map(session, user_id)
    blocked_by = await unfinished_prerequisites(session, user_id)
    return await _to_read(commitment, prerequisites, blocked_by)


async def remove_dependency(
    session: AsyncSession,
    user_id: uuid.UUID,
    commitment_id: uuid.UUID,
    depends_on_id: uuid.UUID,
) -> CommitmentRead:
    commitment = await get_commitment(session, user_id, commitment_id)
    await session.execute(delete_dependency_stmt(depends_on_id, commitment_id))
    await record_activity(
        session, user_id, commitment_id, "dependency_removed", {"depends_on_id": str(depends_on_id)}
    )
    await session.commit()
    await session.refresh(commitment)

    prerequisites, _ = await load_dependency_map(session, user_id)
    blocked_by = await unfinished_prerequisites(session, user_id)
    return await _to_read(commitment, prerequisites, blocked_by)


# --------------------------------------------------------------------------- #
# queries
# --------------------------------------------------------------------------- #
async def list_commitments(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    recipient: str | None = None,
    period: str | None = None,
    search: str | None = None,
    tz_name: str = "UTC",
    limit: int = 200,
) -> list[CommitmentRead]:
    stmt = select(Commitment).where(Commitment.user_id == user_id)

    if status and status != "all":
        stmt = stmt.where(Commitment.status == status)
    if recipient:
        stmt = stmt.where(Commitment.recipient.ilike(f"%{recipient}%"))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Commitment.title.ilike(pattern),
                Commitment.recipient.ilike(pattern),
                Commitment.details.ilike(pattern),
            )
        )

    start, end = period_bounds(period, tz_name)
    if start is not None and end is not None:
        if period == "overdue":
            stmt = stmt.where(
                Commitment.due_at.isnot(None),
                Commitment.due_at < end,
                Commitment.status.notin_(["completed", "cancelled"]),
            )
        else:
            stmt = stmt.where(Commitment.due_at.isnot(None), Commitment.due_at >= start, Commitment.due_at < end)

    stmt = stmt.order_by(Commitment.due_at.is_(None), Commitment.due_at, Commitment.created_at)
    rows = (await session.scalars(stmt.limit(limit))).all()

    prerequisites, _ = await load_dependency_map(session, user_id)
    blocked_by = await unfinished_prerequisites(session, user_id)
    return [await _to_read(row, prerequisites, blocked_by) for row in rows]


async def get_activity(
    session: AsyncSession, user_id: uuid.UUID, commitment_id: uuid.UUID
) -> list[Activity]:
    await get_commitment(session, user_id, commitment_id)
    rows = (
        await session.scalars(
            select(Activity)
            .where(Activity.commitment_id == commitment_id, Activity.user_id == user_id)
            .order_by(Activity.created_at.desc())
        )
    ).all()
    return list(rows)


# --------------------------------------------------------------------------- #
# next actions
# --------------------------------------------------------------------------- #
PRIORITY_WEIGHT = {"high": 15.0, "normal": 5.0, "low": 0.0}


async def compute_next_actions(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 5
) -> list[NextAction]:
    now = datetime.now(timezone.utc)
    open_commitments = (
        await session.scalars(
            select(Commitment).where(
                Commitment.user_id == user_id,
                Commitment.status.in_(OPEN_STATUSES),
            )
        )
    ).all()

    blocked_by = await unfinished_prerequisites(session, user_id)

    scored: list[NextAction] = []
    for commitment in open_commitments:
        blockers = blocked_by.get(commitment.id, [])
        score = PRIORITY_WEIGHT.get(commitment.priority, 0.0)
        if commitment.due_at is None:
            score += 1.0
            reason = "No deadline set - worth clarifying."
        else:
            delta = as_utc(commitment.due_at) - now
            hours = delta.total_seconds() / 3600
            if hours < 0:
                score += 100.0 + min(48.0, -hours / 24 * 2)
                days = max(1, round(-hours / 24))
                reason = f"Overdue by {days} day{'s' if days != 1 else ''}."
            elif hours <= 48:
                score += 30.0 - hours / 2
                reason = "Due within 48 hours."
            else:
                score += max(0.0, 20.0 - hours / 24 * 2)
                reason = f"Due in {round(hours / 24)} days."
        if blockers:
            score -= 50.0
            reason = "Blocked - finish the prerequisite first."

        scored.append(
            NextAction(
                commitment=CommitmentRead.model_validate(commitment),
                score=round(score, 2),
                reason=reason,
                blocked=bool(blockers),
            )
        )

    scored.sort(key=lambda item: (item.blocked, -item.score, item.commitment.due_at or now))
    return scored[:limit]


async def dashboard(session: AsyncSession, user_id: uuid.UUID, tz_name: str = "UTC") -> dict:
    today = local_today(tz_name)
    now = datetime.now(timezone.utc)
    open_items = await list_commitments(session, user_id, status="all", tz_name=tz_name)
    blocked_by = await unfinished_prerequisites(session, user_id)

    pending, overdue, completed, upcoming, blocked = [], [], [], [], []
    for item in open_items:
        if item.status == "completed":
            completed.append(item)
            continue
        if item.status == "cancelled":
            continue
        if item.due_at is not None and item.due_at < now:
            overdue.append(item)
        elif item.due_local_date and item.due_local_date == today:
            upcoming.append(item)
        else:
            pending.append(item)
        if item.blocked_by:
            blocked.append(item)

    counts = {
        "pending": len(pending),
        "overdue": len(overdue),
        "completed": len(completed),
        "upcoming": len(upcoming),
        "blocked": len(blocked),
        "total": len(open_items),
    }
    return {
        "pending": pending,
        "overdue": overdue,
        "completed": completed,
        "upcoming": upcoming,
        "blocked": blocked,
        "counts": counts,
        "next_actions": await compute_next_actions(session, user_id),
        "server_time": now,
    }
