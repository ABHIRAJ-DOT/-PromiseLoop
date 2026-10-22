"""Next-action ranking."""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient

BASE = {"title": "Task", "timezone": "UTC"}


async def create(client: AsyncClient, title: str, due_in_days: float | None = None, priority: str = "normal") -> dict:
    payload = {**BASE, "title": title, "priority": priority}
    if due_in_days is not None:
        payload["due_at"] = (datetime.now(timezone.utc) + timedelta(days=due_in_days)).isoformat()
    response = await client.post("/api/commitments", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_overdue_comes_first(client: AsyncClient):
    await create(client, "future", due_in_days=5)
    await create(client, "overdue", due_in_days=-2)

    actions = (await client.get("/api/commitments/next-actions")).json()
    assert actions[0]["commitment"]["title"] == "overdue"
    assert "Overdue" in actions[0]["reason"]


async def test_completed_commitments_are_not_suggested(client: AsyncClient):
    done = await create(client, "done", due_in_days=-5)
    await client.post(f"/api/commitments/{done['id']}/complete")
    await create(client, "open", due_in_days=3)

    actions = (await client.get("/api/commitments/next-actions")).json()
    assert [a["commitment"]["title"] for a in actions] == ["open"]


async def test_blocked_commitments_are_flagged_and_ranked_lower(client: AsyncClient):
    blocker = await create(client, "blocker", due_in_days=1)
    blocked = await create(client, "blocked", due_in_days=1)
    await client.post(
        f"/api/commitments/{blocked['id']}/dependencies", json={"depends_on_id": blocker["id"]}
    )

    actions = (await client.get("/api/commitments/next-actions")).json()
    by_title = {a["commitment"]["title"]: a for a in actions}
    assert by_title["blocked"]["blocked"] is True
    assert by_title["blocker"]["blocked"] is False
    assert by_title["blocker"]["score"] > by_title["blocked"]["score"]


async def test_high_priority_breaks_a_deadline_tie(client: AsyncClient):
    await create(client, "normal", due_in_days=3, priority="normal")
    await create(client, "high", due_in_days=3, priority="high")

    actions = (await client.get("/api/commitments/next-actions")).json()
    assert actions[0]["commitment"]["title"] == "high"


async def test_commitment_without_deadline_still_appears(client: AsyncClient):
    await create(client, "no deadline")
    actions = (await client.get("/api/commitments/next-actions")).json()
    assert actions[0]["commitment"]["title"] == "no deadline"
    assert "deadline" in actions[0]["reason"].lower()
