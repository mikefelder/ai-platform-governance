"""Policy CRUD endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_policies(client: AsyncClient):
    response = await client.get("/api/policies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 5  # Default seed policies


@pytest.mark.asyncio
async def test_create_policy(client: AsyncClient):
    response = await client.post(
        "/api/policies",
        json={
            "name": "Test rate limit",
            "policy_type": "rate_limit",
            "severity": "low",
            "threshold": 100,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test rate limit"
    assert data["id"].startswith("pol-")


@pytest.mark.asyncio
async def test_update_policy(client: AsyncClient):
    response = await client.put(
        "/api/policies/pol-001",
        json={"severity": "high"},
    )
    assert response.status_code == 200
    assert response.json()["severity"] == "high"


@pytest.mark.asyncio
async def test_delete_policy(client: AsyncClient):
    # Create then delete
    create_resp = await client.post(
        "/api/policies",
        json={
            "name": "Temp policy",
            "policy_type": "rate_limit",
            "threshold": 50,
        },
    )
    policy_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/policies/{policy_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_policy_not_found(client: AsyncClient):
    response = await client.delete("/api/policies/nonexistent")
    assert response.status_code == 404
