"""Incident lifecycle endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_incident(client: AsyncClient):
    response = await client.post(
        "/api/incidents",
        json={
            "title": "API gateway timeout on prod",
            "severity": "p2",
            "category": "infrastructure",
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["incident_id"].startswith("inc-")
    assert data["title"] == "API gateway timeout on prod"
    assert data["severity"] == "p2"
    # After creation the mock service advances to TRIAGING
    assert data["status"] in ("received", "triaging")


@pytest.mark.asyncio
async def test_list_incidents(client: AsyncClient):
    # Create one first
    await client.post("/api/incidents", json={"title": "List test incident"})
    response = await client.get("/api/incidents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_incident(client: AsyncClient):
    create_resp = await client.post(
        "/api/incidents", json={"title": "Get-by-ID test"}
    )
    incident_id = create_resp.json()["incident_id"]

    response = await client.get(f"/api/incidents/{incident_id}")
    assert response.status_code == 200
    assert response.json()["incident_id"] == incident_id


@pytest.mark.asyncio
async def test_get_incident_not_found(client: AsyncClient):
    response = await client.get("/api/incidents/nonexistent-id")
    assert response.status_code == 404
