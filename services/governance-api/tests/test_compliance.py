"""Compliance endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_compliance_report(client: AsyncClient):
    response = await client.get("/api/compliance/report")
    assert response.status_code == 200
    data = response.json()
    assert "overall_status" in data
    assert "total_policies" in data
    assert "violations" in data


@pytest.mark.asyncio
async def test_compliance_violations(client: AsyncClient):
    response = await client.get("/api/compliance/violations")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_compliance_violations_filter_by_agent(client: AsyncClient):
    response = await client.get(
        "/api/compliance/violations?agent_name=uc2-bedrock-agent"
    )
    assert response.status_code == 200
    data = response.json()
    for violation in data:
        assert violation["agent_name"] == "uc2-bedrock-agent"
