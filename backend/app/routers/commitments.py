"""Commitment REST API."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    ActivityRead,
    CommitmentCreate,
    CommitmentRead,
    CommitmentUpdate,
    DashboardRead,
    DependencyCreate,
    NextAction,
)
from app.services import commitments as svc

router = APIRouter(prefix="/commitments", tags=["commitments"])


def _tz(tz: str | None) -> str:
    try:
        return svc.resolve_timezone(tz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("", response_model=CommitmentRead, status_code=status.HTTP_201_CREATED)
async def create_commitment(
    payload: CommitmentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CommitmentRead:
    try:
        return await svc.create_commitment(session, user.id, payload)
    except svc.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except svc.ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("", response_model=list[CommitmentRead])
async def list_commitments(
    status_: str | None = Query(default=None, alias="status"),
    recipient: str | None = None,
    period: str | None = Query(default=None, description="today | week | month | overdue | all"),
    search: str | None = None,
    tz: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[CommitmentRead]:
    return await svc.list_commitments(
        session,
        user.id,
        status=status_,
        recipient=recipient,
        period=period,
        search=search,
        tz_name=_tz(tz),
    )


@router.get("/next-actions", response_model=list[NextAction])
async def next_actions(
    limit: int = Query(default=5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[NextAction]:
    return await svc.compute_next_actions(session, user.id, limit=limit)


@router.get("/{commitment_id}", response_model=CommitmentRead)
async def get_commitment(
    commitment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CommitmentRead:
    try:
        commitment = await svc.get_commitment(session, user.id, commitment_id)
    except svc.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    prerequisites, _ = await svc.load_dependency_map(session, user.id)
    blocked_by = await svc.unfinished_prerequisites(session, user.id)
    return await svc._to_read(commitment, prerequisites, blocked_by)


@router.patch("/{commitment_id}", response_model=CommitmentRead)
async def update_commitment(
    commitment_id: uuid.UUID,
    payload: CommitmentUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CommitmentRead:
    try:
        return await svc.update_commitment(session, user.id, commitment_id, payload)
    except svc.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except svc.ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{commitment_id}/complete", response_model=CommitmentRead)
async def complete_commitment(
    commitment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CommitmentRead:
    try:
        return await svc.complete_commitment(session, user.id, commitment_id)
    except svc.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{commitment_id}/dependencies", response_model=CommitmentRead)
async def add_dependency(
    commitment_id: uuid.UUID,
    payload: DependencyCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CommitmentRead:
    try:
        return await svc.add_dependency(session, user.id, commitment_id, payload.depends_on_id)
    except svc.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except svc.ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.delete("/{commitment_id}/dependencies/{depends_on_id}", response_model=CommitmentRead)
async def remove_dependency(
    commitment_id: uuid.UUID,
    depends_on_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CommitmentRead:
    try:
        return await svc.remove_dependency(session, user.id, commitment_id, depends_on_id)
    except svc.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{commitment_id}/activity", response_model=list[ActivityRead])
async def commitment_activity(
    commitment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ActivityRead]:
    try:
        return await svc.get_activity(session, user.id, commitment_id)
    except svc.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
