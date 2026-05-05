"""TC-5: agent SLA breach escalation endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_escalation_404_for_unknown_incident(client: AsyncClient):
    resp = await client.post(
        "/api/incidents/inc-missing/escalations",
        json={"type": "sla_breach", "source": "supervisor"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sla_breach_escalation_records_event_and_flips_status(
    client: AsyncClient,
):
    create = await client.post(
        "/api/incidents",
        json={"title": "SLA breach escalation", "severity": "p2"},
    )
    incident_id = create.json()["incident_id"]
    initial_status = create.json()["status"]
    assert initial_status != "escalated"

    resp = await client.post(
        f"/api/incidents/{incident_id}/escalations",
        json={
            "type": "sla_breach",
            "source": "supervisor",
            "agent_name": "knowledge",
            "sla_threshold_seconds": 15.0,
            "elapsed_seconds": 22.4,
            "reason": "http_timeout",
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["incident_id"] == incident_id
    assert body["status"] == "escalated"
    assert body["escalation_type"] == "sla_breach"
    assert body["source"] == "supervisor"

    # Bundle composition should now include the escalation event
    bundle = (
        await client.get(f"/api/incidents/{incident_id}/audit-bundle")
    ).json()
    types = [e["event_type"] for e in bundle["workflow_events"]]
    assert "escalation.sla_breach" in types
    sla_event = next(
        e for e in bundle["workflow_events"]
        if e["event_type"] == "escalation.sla_breach"
    )
    assert sla_event["actor"] == "supervisor"
    assert sla_event["payload"]["agent_name"] == "knowledge"
    assert sla_event["payload"]["sla_threshold_seconds"] == 15.0
    assert sla_event["payload"]["elapsed_seconds"] == 22.4
    assert sla_event["payload"]["reason"] == "http_timeout"
    assert bundle["incident"]["status"] == "escalated"


@pytest.mark.asyncio
async def test_escalation_does_not_demote_terminal_incident(client: AsyncClient):
    create = await client.post(
        "/api/incidents",
        json={"title": "Terminal escalation guard", "severity": "p3"},
    )
    incident_id = create.json()["incident_id"]

    # Force resolved
    resolve = await client.post(f"/api/incidents/{incident_id}/resolve")
    assert resolve.status_code == 200
    assert resolve.json()["status"] == "resolved"

    resp = await client.post(
        f"/api/incidents/{incident_id}/escalations",
        json={"type": "sla_breach", "source": "supervisor"},
    )
    assert resp.status_code == 202
    # status should remain resolved (terminal); event still recorded
    assert resp.json()["status"] == "resolved"

    bundle = (
        await client.get(f"/api/incidents/{incident_id}/audit-bundle")
    ).json()
    types = [e["event_type"] for e in bundle["workflow_events"]]
    assert "escalation.sla_breach" in types
    assert bundle["incident"]["status"] == "resolved"
