"""Authentication context for MCP tool calls.

The acting user is resolved from an API key that is carried in a context
variable. Whoever opens the session sets it:

* in-process client -> the authenticated key of the current request
* HTTP transport   -> the ``X-API-Key`` header (set by the ASGI middleware)
* stdio transport  -> the ``PL_API_KEY`` environment variable

The key itself never reaches the LLM and never appears in a tool argument.
"""

from contextvars import ContextVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.security import hash_api_key

current_api_key: ContextVar[str | None] = ContextVar("promiseloop_api_key", default=None)


async def resolve_user(session: AsyncSession) -> User:
    """Return the user the current MCP session is acting as."""
    key = current_api_key.get()
    if not key:
        raise PermissionError("This MCP session has no API key - refusing to act.")
    user = await session.scalar(select(User).where(User.api_key_hash == hash_api_key(key)))
    if user is None:
        raise PermissionError("Invalid API key for this MCP session.")
    return user
