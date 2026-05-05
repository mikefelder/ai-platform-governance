"""Cost endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cost_summary(client: AsyncClient):
    response = await client.get("/api/costs/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_estimated_cost_usd" in data
    assert "by_agent" in data
    assert isinstance(data["by_agent"], list)


@pytest.mark.asyncio
async def test_cost_by_agent(client: AsyncClient):
    response = await client.get("/api/costs/by-agent")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_cost_trends(client: AsyncClient):
    response = await client.get("/api/costs/trends?granularity=hourly&hours=6")
    assert response.status_code == 200
    data = response.json()
    assert "data_points" in data
    assert data["granularity"] == "hourly"
