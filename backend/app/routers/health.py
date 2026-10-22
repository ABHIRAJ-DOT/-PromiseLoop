"""Health check (no auth required)."""

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.db import SessionLocal
from app.schemas import HealthRead

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthRead)
async def health() -> HealthRead:
    settings = get_settings()
    try:
        async with SessionLocal() as session:
            await session.execute(text("select 1"))
        database = "ok"
    except Exception:  # pragma: no cover - only hit when the DB is down
        database = "unavailable"

    return HealthRead(
        status="ok" if database == "ok" else "degraded",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
        database=database,
        llm_provider=settings.llm_provider,
        mcp_transport=settings.mcp_transport,
    )
