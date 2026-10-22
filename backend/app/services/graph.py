"""Dependency graph helpers: blocking detection and cycle prevention."""

import uuid

from sqlalchemy import select

from app.models import Commitment, CommitmentDependency


async def load_dependency_map(
    session, user_id: uuid.UUID
) -> tuple[dict[uuid.UUID, list[uuid.UUID]], dict[uuid.UUID, list[uuid.UUID]]]:
    """Return (prerequisites, dependents) maps for a user.

    prerequisites[c] = ids of commitments that must finish before c can start.
    dependents[c]    = ids of commitments that are waiting on c.
    """
    rows = (
        await session.execute(
            select(CommitmentDependency.commitment_id, CommitmentDependency.depends_on_id)
            .join(Commitment, Commitment.id == CommitmentDependency.commitment_id)
            .where(Commitment.user_id == user_id)
        )
    ).all()

    prerequisites: dict[uuid.UUID, list[uuid.UUID]] = {}
    dependents: dict[uuid.UUID, list[uuid.UUID]] = {}
    for commitment_id, depends_on_id in rows:
        prerequisites.setdefault(commitment_id, []).append(depends_on_id)
        dependents.setdefault(depends_on_id, []).append(commitment_id)
    return prerequisites, dependents


def would_create_cycle(
    prerequisites: dict[uuid.UUID, list[uuid.UUID]], commitment_id: uuid.UUID, depends_on_id: uuid.UUID
) -> bool:
    """True if depending on ``depends_on_id`` closes a loop back to ``commitment_id``."""
    if commitment_id == depends_on_id:
        return True
    stack = [depends_on_id]
    seen: set[uuid.UUID] = set()
    while stack:
        node = stack.pop()
        if node == commitment_id:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(prerequisites.get(node, []))
    return False


async def unfinished_prerequisites(
    session, user_id: uuid.UUID
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Map commitment id -> ids of its unfinished prerequisites (direct or transitive).

    A commitment is blocked when *any* commitment it transitively depends on is
    not finished yet.
    """
    prerequisites, _ = await load_dependency_map(session, user_id)

    finished = set(
        (
            await session.execute(
                select(Commitment.id).where(
                    Commitment.user_id == user_id,
                    Commitment.status.in_(["completed", "cancelled"]),
                )
            )
        ).scalars()
    )

    resolved: dict[uuid.UUID, list[uuid.UUID]] = {}

    def resolve(node: uuid.UUID, seen: frozenset[uuid.UUID]) -> list[uuid.UUID]:
        if node in resolved:
            return resolved[node]
        if node in seen:  # defensive: cycles are rejected on write
            return []
        result: list[uuid.UUID] = []
        for parent in prerequisites.get(node, []):
            if parent not in finished:
                result.append(parent)
            result.extend(resolve(parent, seen | {node}))
        deduped = list(dict.fromkeys(result))
        resolved[node] = deduped
        return deduped

    for commitment_id in prerequisites:
        resolve(commitment_id, frozenset())

    # Only blocked commitments (with unfinished prerequisites) are reported.
    return {k: v for k, v in resolved.items() if v}
