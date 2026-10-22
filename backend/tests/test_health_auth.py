"""Health endpoint and authentication behaviour."""

import pytest
from httpx import AsyncClient


async def test_health_is_public_and_reports_ok(anon_client: AsyncClient):
    response = await anon_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["service"] == "PromiseLoop API"


async def test_commitments_require_an_api_key(anon_client: AsyncClient):
    response = await anon_client.get("/api/commitments")
    assert response.status_code == 401
    assert "api key" in response.json()["detail"].lower()


async def test_wrong_api_key_is_rejected(anon_client: AsyncClient):
    response = await anon_client.get(
        "/api/commitments", headers={"X-API-Key": "nope-not-a-real-key"}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/api/commitments", "/api/dashboard", "/api/commitments/next-actions"])
async def test_protected_endpoints_reject_anonymous(client: AsyncClient, path):
    client.headers.pop("X-API-Key")
    response = await client.get(path)
    assert response.status_code == 401
