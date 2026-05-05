"""Workflow endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_workflow_state(client: AsyncClient):
    create_resp = await client.post(
        "/api/incidents", json={"title": "Workflow state test"}
    )
    incident_id = create_resp.json()["incident_id"]

    response = await client.get(f"/api/workflows/{incident_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == incident_id
    assert "current_status" in data


@pytest.mark.asyncio
async def test_get_workflow_history(client: AsyncClient):
    create_resp = await client.post(
        "/api/incidents", json={"title": "Workflow history test"}
    )
    incident_id = create_resp.json()["incident_id"]

    response = await client.get(f"/api/workflows/{incident_id}/history")
    assert response.status_code == 200
    history = response.json()
    assert isinstance(history, list)
    assert len(history) >= 1  # At minimum the creation event


@pytest.mark.asyncio
async def test_get_workflow_state_not_found(client: AsyncClient):
    response = await client.get("/api/workflows/nonexistent-id")
    assert response.status_code == 404
