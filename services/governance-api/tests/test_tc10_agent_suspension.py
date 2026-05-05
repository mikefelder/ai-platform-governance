"""TC-10 — agent suspension webhook."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from governance_api.services import agent_suspension


@pytest.fixture(autouse=True)
def _reset_suspension_state():
    agent_suspension.reset()
    yield
    agent_suspension.reset()


@pytest.mark.asyncio
async def test_get_suspension_returns_active_default(client: AsyncClient):
    r = await client.get("/api/agents/knowledge/suspension")
    assert r.status_code == 200
    body = r.json()
    assert body["agent_name"] == "knowledge"
    assert body["status"] == "active"
    assert body["history"] == []


@pytest.mark.asyncio
async def test_suspend_then_get_reflects_state(client: AsyncClient):
    r = await client.post(
        "/api/agents/knowledge/suspend",
        json={
            "reason": "sla_breach repeated",
            "source": "sentinel:agent_sla_breach",
            "correlation_id": "sentinel-incident-42",
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert body["state"]["status"] == "suspended"
    assert body["state"]["reason"] == "sla_breach repeated"
    assert body["state"]["source"] == "sentinel:agent_sla_breach"
    assert body["event"]["event_type"] == "agent.suspended"
    assert body["event"]["previous_status"] == "active"
    assert body["event"]["correlation_id"] == "sentinel-incident-42"

    g = await client.get("/api/agents/knowledge/suspension")
    assert g.status_code == 200
    state = g.json()
    assert state["status"] == "suspended"
    assert len(state["history"]) == 1


@pytest.mark.asyncio
async def test_suspend_validation_requires_reason(client: AsyncClient):
    r = await client.post("/api/agents/knowledge/suspend", json={"source": "x"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_resume_409_when_not_suspended(client: AsyncClient):
    r = await client.post("/api/agents/knowledge/resume", json={})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_suspend_then_resume_emits_two_events(client: AsyncClient):
    await client.post(
        "/api/agents/knowledge/suspend",
        json={"reason": "for-test", "source": "test"},
    )
    r = await client.post(
        "/api/agents/knowledge/resume",
        json={"note": "rolled out hotfix"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"]["status"] == "active"
    assert body["event"]["event_type"] == "agent.resumed"
    assert body["event"]["previous_status"] == "suspended"
    assert body["event"]["note"] == "rolled out hotfix"

    state = (await client.get("/api/agents/knowledge/suspension")).json()
    types = [e["event_type"] for e in state["history"]]
    assert types == ["agent.suspended", "agent.resumed"]


@pytest.mark.asyncio
async def test_list_suspensions_returns_all_known_agents(client: AsyncClient):
    await client.post(
        "/api/agents/knowledge/suspend", json={"reason": "r1", "source": "test"}
    )
    await client.post(
        "/api/agents/compliance/suspend", json={"reason": "r2", "source": "test"}
    )
    r = await client.get("/api/agents/suspensions")
    assert r.status_code == 200
    rows = r.json()
    names = {row["agent_name"] for row in rows}
    assert names == {"knowledge", "compliance"}
    for row in rows:
        assert row["status"] == "suspended"
