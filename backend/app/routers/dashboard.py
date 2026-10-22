"""Dashboard router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas import DashboardRead
from app.services import commitments as svc

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardRead)
async def dashboard(
    tz: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DashboardRead:
    try:
        tz_name = svc.resolve_timezone(tz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    data = await svc.dashboard(session, user.id, tz_name=tz_name)
    return DashboardRead(**data)
