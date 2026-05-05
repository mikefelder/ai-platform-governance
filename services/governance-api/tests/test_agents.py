"""Agent / traces endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_traces(client: AsyncClient):
    response = await client.get("/api/agents/traces")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "trace_id" in data[0]


@pytest.mark.asyncio
async def test_get_trace_detail(client: AsyncClient):
    trace_id = "a" * 32
    response = await client.get(f"/api/agents/{trace_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["trace_id"] == trace_id
    assert "spans" in data


@pytest.mark.asyncio
async def test_agent_health(client: AsyncClient):
    response = await client.get("/api/agents/health")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "agent_name" in data[0]
    assert "status" in data[0]
