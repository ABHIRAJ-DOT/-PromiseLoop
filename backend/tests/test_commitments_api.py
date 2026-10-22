"""Commitment CRUD, filtering, activity history and authorisation scoping."""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient

BASE = {
    "title": "Send project demo to Abhishek",
    "recipient": "Abhishek",
    "details": "Include the recorded walkthrough.",
    "timezone": "Asia/Kolkata",
    "deadline_precision": "day",
}


async def test_create_commitment_persists_and_returns_utc_deadline(client: AsyncClient):
    due = datetime(2026, 10, 23, 12, 30, tzinfo=timezone.utc)
    response = await client.post("/api/commitments", json={**BASE, "due_at": due.isoformat()})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Send project demo to Abhishek"
    assert body["recipient"] == "Abhishek"
    assert body["status"] == "pending"
    assert body["due_at"].startswith("2026-10-23T12:30")
    assert body["depends_on_ids"] == []


async def test_commitment_is_listed_and_fetchable(client: AsyncClient):
    created = (await client.post("/api/commitments", json=BASE)).json()
    listed = await client.get("/api/commitments")
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [created["id"]]

    fetched = await client.get(f"/api/commitments/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


async def test_update_changes_only_the_given_fields(client: AsyncClient):
    created = (await client.post("/api/commitments", json=BASE)).json()
    response = await client.patch(
        f"/api/commitments/{created['id']}",
        json={"status": "in_progress", "priority": "high"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["priority"] == "high"
    assert body["title"] == BASE["title"]
    assert body["recipient"] == BASE["recipient"]


async def test_complete_marks_commitment_and_writes_activity(client: AsyncClient):
    created = (await client.post("/api/commitments", json=BASE)).json()
    response = await client.post(f"/api/commitments/{created['id']}/complete")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["completed_at"] is not None

    activity = (await client.get(f"/api/commitments/{created['id']}/activity")).json()
    actions = [entry["action"] for entry in activity]
    assert "created" in actions
    assert "completed" in actions


async def test_filters_by_status_recipient_and_search(client: AsyncClient):
    await client.post("/api/commitments", json=BASE)
    await client.post("/api/commitments", json={**BASE, "recipient": "Priya", "title": "Call Priya"})

    by_recipient = (await client.get("/api/commitments", params={"recipient": "priya"})).json()
    assert len(by_recipient) == 1
    assert by_recipient[0]["recipient"] == "Priya"

    by_search = (await client.get("/api/commitments", params={"search": "demo"})).json()
    assert len(by_search) == 1

    completed = (await client.get("/api/commitments", params={"status": "completed"})).json()
    assert completed == []


async def test_period_filter_separates_overdue_from_upcoming(client: AsyncClient):
    now = datetime.now(timezone.utc)
    overdue_due = (now - timedelta(days=2)).isoformat()
    future_due = (now + timedelta(days=3)).isoformat()
    await client.post("/api/commitments", json={**BASE, "title": "Late one", "due_at": overdue_due})
    await client.post("/api/commitments", json={**BASE, "title": "Later one", "due_at": future_due})

    overdue = (await client.get("/api/commitments", params={"period": "overdue"})).json()
    assert [c["title"] for c in overdue] == ["Late one"]

    week = (await client.get("/api/commitments", params={"period": "week"})).json()
    assert [c["title"] for c in week] == ["Later one"]


async def test_unknown_commitment_returns_404(client: AsyncClient):
    response = await client.get("/api/commitments/11111111-1111-1111-1111-111111111111")
    assert response.status_code == 404


async def test_invalid_payload_is_rejected(client: AsyncClient):
    response = await client.post("/api/commitments", json={"title": ""})
    assert response.status_code == 422


async def test_dashboard_groups_commitments(client: AsyncClient):
    now = datetime.now(timezone.utc)
    await client.post("/api/commitments", json={**BASE, "title": "Overdue thing", "due_at": (now - timedelta(days=1)).isoformat()})
    await client.post("/api/commitments", json={**BASE, "title": "Someday thing"})

    response = await client.get("/api/dashboard", params={"tz": "Asia/Kolkata"})
    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["overdue"] == 1
    assert body["counts"]["pending"] == 1
    assert [c["title"] for c in body["overdue"]] == ["Overdue thing"]
    assert body["server_time"]


async def test_one_user_cannot_see_another_users_commitments(client: AsyncClient, anon_client: AsyncClient):
    created = (await client.post("/api/commitments", json=BASE)).json()
    anon_client.headers["X-API-Key"] = "pl_some_other_key"
    response = await anon_client.get(f"/api/commitments/{created['id']}")
    assert response.status_code == 401
