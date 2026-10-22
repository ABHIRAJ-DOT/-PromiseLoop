"""Shared FastAPI dependencies (authentication + session)."""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.security import extract_api_key, hash_api_key


@dataclass
class AuthContext:
    """The caller: the resolved user plus the raw key the MCP session needs."""

    user: User
    api_key: str


async def get_auth(request: Request, session: AsyncSession = Depends(get_session)) -> AuthContext:
    """Resolve the API key to a user; every query is scoped to that user."""
    raw_key = extract_api_key(
        request.headers.get(request.app.state.api_key_header),
        request.headers.get("authorization"),
    )
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Send it in the X-API-Key header.",
        )
    user = await session.scalar(select(User).where(User.api_key_hash == hash_api_key(raw_key)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
    return AuthContext(user=user, api_key=raw_key)


async def get_current_user(auth: AuthContext = Depends(get_auth)) -> User:
    return auth.user


async def get_current_user_id(user: User = Depends(get_current_user)) -> uuid.UUID:
    return user.id
