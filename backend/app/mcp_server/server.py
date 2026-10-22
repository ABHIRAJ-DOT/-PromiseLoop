"""PromiseLoop MCP server.

Exposes the commitment tools over the Model Context Protocol. The same server
runs in three ways:

* ``python -m app.mcp_server.server``         - stdio (Claude Desktop, MCP Inspector)
* ``python -m app.mcp_server.server --http``  - streamable HTTP
* imported in-process by the assistant (in-memory transport)

Every tool authenticates the caller through the API key in the session context
and scopes every query to that user, so the model can never reach data it
should not see.
"""

import argparse
import os
import uuid
from datetime import datetime, time, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.config import get_settings
from app.db import SessionLocal
from app.mcp_server.auth import current_api_key, resolve_user
from app.schemas import CommitmentCreate, CommitmentUpdate
from app.services import commitments as svc
from app.services.timeparse import parse_deadline

PRIORITIES = {"low", "normal", "high"}
PRECISIONS = {"exact", "day", "vague", "none"}
STATUSES = {"pending", "in_progress", "completed", "cancelled"}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid date (expected YYYY-MM-DD): {value}") from exc


def _parse_time(value: str | None):
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid time (expected HH:MM): {value}") from exc


def _uuid_list(values: list[str] | None) -> list[uuid.UUID]:
    result: list[uuid.UUID] = []
    for value in values or []:
        try:
            result.append(uuid.UUID(value))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"Invalid UUID: {value}") from exc
    return result


def build_server() -> FastMCP:
    """Create the MCP server with all commitment tools bound."""
    settings = get_settings()
    mcp = FastMCP(
        "promiseloop",
        instructions=(
            "Manage the user's commitments. Always read the real records with the tools "
            "instead of guessing, and always scope deadlines to the user's timezone."
        ),
    )

    @mcp.tool(
        description=(
            "Create a new commitment. Use due_text for a natural deadline such as "
            "'tomorrow evening' - it is resolved in the user's timezone. "
            "Returns the created commitment."
        )
    )
    async def create_commitment(
        title: str,
        recipient: str | None = None,
        details: str | None = None,
        due_text: str | None = None,
        due_at: str | None = None,
        due_local_date: str | None = None,
        due_local_time: str | None = None,
        deadline_precision: str | None = None,
        timezone: str = "UTC",
        priority: str = "normal",
        depends_on_ids: list[str] | None = None,
        source: str = "chat",
        original_text: str | None = None,
    ) -> dict[str, Any]:
        if not title or not title.strip():
            raise ValueError("title must not be empty")
        if len(title) > 500:
            raise ValueError("title must be 500 characters or fewer")
        if priority not in PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(PRIORITIES)}")
        if deadline_precision is not None and deadline_precision not in PRECISIONS:
            raise ValueError(f"deadline_precision must be one of {sorted(PRECISIONS)}")
        svc.resolve_timezone(timezone)

        instant = _parse_instant(due_at)
        local_date = _parse_date(due_local_date)
        local_time = _parse_time(due_local_time)
        precision = deadline_precision

        if instant is None and due_text:
            deadline = parse_deadline(due_text, timezone)
            if deadline is not None:
                instant = deadline.as_utc(timezone)
                local_date = deadline.date
                local_time = deadline.time
                precision = precision or deadline.precision
        if precision is None:
            precision = "exact" if instant else "none"

        payload = CommitmentCreate(
            title=title.strip(),
            recipient=recipient.strip() if recipient else None,
            details=details,
            due_at=instant,
            due_local_date=local_date,
            due_local_time=local_time,
            deadline_precision=precision,
            timezone=timezone,
            priority=priority,
            source=source,
            original_text=original_text,
            depends_on_ids=_uuid_list(depends_on_ids),
        )

        async with SessionLocal() as session:
            user = await resolve_user(session)
            created = await svc.create_commitment(session, user.id, payload, source=source)
        return _commitment_dict(created)

    @mcp.tool(
        description=(
            "List the user's commitments. Filter by status, recipient, a time period "
            "(today, week, month, overdue, all) or a text search."
        )
    )
    async def list_commitments(
        status: str | None = None,
        recipient: str | None = None,
        period: str | None = None,
        search: str | None = None,
        timezone: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        if status is not None and status not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        if period is not None and period not in {"today", "week", "month", "overdue", "all"}:
            raise ValueError("period must be one of today, week, month, overdue, all")
        limit = max(1, min(int(limit), 200))
        tz_name = svc.resolve_timezone(timezone or settings.default_timezone)

        async with SessionLocal() as session:
            user = await resolve_user(session)
            items = await svc.list_commitments(
                session,
                user.id,
                status=status,
                recipient=recipient,
                period=period,
                search=search,
                tz_name=tz_name,
                limit=limit,
            )
        return {"count": len(items), "commitments": [_commitment_dict(item) for item in items]}

    @mcp.tool(description="Update fields of an existing commitment. Only the given fields change.")
    async def update_commitment(
        id: str,
        title: str | None = None,
        recipient: str | None = None,
        details: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        due_at: str | None = None,
        due_text: str | None = None,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        if status is not None and status not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        if priority is not None and priority not in PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(PRIORITIES)}")
        try:
            commitment_id = uuid.UUID(id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"Invalid UUID: {id}") from exc

        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if recipient is not None:
            updates["recipient"] = recipient
        if details is not None:
            updates["details"] = details
        if status is not None:
            updates["status"] = status
        if priority is not None:
            updates["priority"] = priority

        tz_name = timezone or settings.default_timezone
        if due_at is not None:
            updates["due_at"] = _parse_instant(due_at)
            updates["deadline_precision"] = "exact"
        elif due_text is not None:
            deadline = parse_deadline(due_text, tz_name)
            if deadline is not None:
                updates["due_at"] = deadline.as_utc(tz_name)
                updates["due_local_date"] = deadline.date
                updates["due_local_time"] = deadline.time
                updates["deadline_precision"] = deadline.precision
        if timezone is not None:
            svc.resolve_timezone(timezone)
            updates["timezone"] = timezone

        async with SessionLocal() as session:
            user = await resolve_user(session)
            try:
                updated = await svc.update_commitment(
                    session, user.id, commitment_id, CommitmentUpdate(**updates)
                )
            except svc.NotFoundError as exc:
                return {"error": str(exc)}
            except svc.ConflictError as exc:
                return {"error": str(exc)}
        return _commitment_dict(updated)

    @mcp.tool(
        description=(
            "Make a commitment depend on another one. The dependent commitment is "
            "blocked until the prerequisite is completed."
        )
    )
    async def add_dependency(commitment_id: str, depends_on_id: str) -> dict[str, Any]:
        try:
            target = uuid.UUID(commitment_id)
            prerequisite = uuid.UUID(depends_on_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("commitment_id and depends_on_id must be UUIDs") from exc

        async with SessionLocal() as session:
            user = await resolve_user(session)
            try:
                updated = await svc.add_dependency(session, user.id, target, prerequisite)
            except svc.NotFoundError as exc:
                return {"error": str(exc)}
            except svc.ConflictError as exc:
                return {"error": str(exc)}
        return _commitment_dict(updated)

    @mcp.tool(
        description=(
            "Suggest what the user should do next. Returns the most urgent, unblocked "
            "commitments with the reason for each suggestion."
        )
    )
    async def get_next_actions(limit: int = 5) -> dict[str, Any]:
        limit = max(1, min(int(limit), 20))
        async with SessionLocal() as session:
            user = await resolve_user(session)
            actions = await svc.compute_next_actions(session, user.id, limit=limit)
        return {
            "count": len(actions),
            "next_actions": [
                {
                    "commitment": _commitment_dict(action.commitment),
                    "reason": action.reason,
                    "blocked": action.blocked,
                    "score": action.score,
                }
                for action in actions
            ],
        }

    @mcp.tool(description="Mark a commitment as completed and record it in the activity history.")
    async def complete_commitment(id: str) -> dict[str, Any]:
        try:
            commitment_id = uuid.UUID(id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"Invalid UUID: {id}") from exc

        async with SessionLocal() as session:
            user = await resolve_user(session)
            try:
                completed = await svc.complete_commitment(session, user.id, commitment_id)
            except svc.NotFoundError as exc:
                return {"error": str(exc)}
        return _commitment_dict(completed)

    return mcp


def _commitment_dict(item) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "title": item.title,
        "recipient": item.recipient,
        "details": item.details,
        "status": item.status,
        "priority": item.priority,
        "due_at": _iso(item.due_at),
        "due_local_date": item.due_local_date.isoformat() if item.due_local_date else None,
        "due_local_time": item.due_local_time.isoformat() if item.due_local_time else None,
        "deadline_precision": item.deadline_precision,
        "timezone": item.timezone,
        "source": item.source,
        "original_text": item.original_text,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
        "completed_at": _iso(item.completed_at),
        "depends_on_ids": [str(value) for value in item.depends_on_ids],
        "blocked_by": [str(value) for value in item.blocked_by],
    }


class ApiKeyMiddleware:
    """Pure ASGI middleware that carries the caller's API key into the session.

    Kept as raw ASGI (not BaseHTTPMiddleware) so the context variable is set
    in the very task that later runs the tool handlers.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode(): value.decode() for key, value in scope.get("headers", [])}
        token = current_api_key.set(headers.get("x-api-key"))
        try:
            await self.app(scope, receive, send)
        finally:
            current_api_key.reset(token)


def main() -> None:
    parser = argparse.ArgumentParser(description="PromiseLoop MCP server")
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = build_server()

    if args.http:
        import uvicorn

        uvicorn.run(
            ApiKeyMiddleware(server.streamable_http_app()), host=args.host, port=args.port
        )
        return

    key = os.environ.get("PL_API_KEY")
    if key:
        current_api_key.set(key)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
