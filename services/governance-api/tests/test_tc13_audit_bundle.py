"""TC-13: one-shot audit bundle composition tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_audit_bundle_not_found(client: AsyncClient):
    resp = await client.get("/api/incidents/inc-does-not-exist/audit-bundle")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_audit_bundle_minimal_incident(client: AsyncClient):
    create = await client.post(
        "/api/incidents",
        json={"title": "Audit bundle minimal", "severity": "p3"},
    )
    incident_id = create.json()["incident_id"]

    resp = await client.get(f"/api/incidents/{incident_id}/audit-bundle")
    assert resp.status_code == 200
    bundle = resp.json()

    assert bundle["schema_version"] == "1.0"
    assert bundle["incident"]["incident_id"] == incident_id
    assert bundle["reported_by"] is not None  # AUTH_MODE=disabled seeds dev caller
    assert bundle["policy_applied"] is not None  # TC-2 seeded for every severity
    assert bundle["policy_applied"]["policy_id"] == "POL-INCIDENT-RESPONSE"
    assert bundle["workflow_state"] is not None
    assert isinstance(bundle["workflow_events"], list)
    assert len(bundle["workflow_events"]) >= 2  # incident.created + policy.applied
    event_types = {e["event_type"] for e in bundle["workflow_events"]}
    assert "incident.created" in event_types
    assert "policy.applied" in event_types
    assert bundle["votes"] == []
    assert bundle["decision"] is None
    assert bundle["approvals"] == []
    assert "kql_traces" in bundle["trace_links"]
    assert incident_id in bundle["trace_links"]["kql_traces"]


@pytest.mark.asyncio
async def test_audit_bundle_full_lifecycle(client: AsyncClient):
    """End-to-end bundle: incident → vote → decide → approve → bundle."""
    create = await client.post(
        "/api/incidents",
        json={"title": "Audit bundle full", "severity": "p1"},
    )
    incident_id = create.json()["incident_id"]

    # Cast two agent votes
    for agent in ("knowledge-agent", "compliance-agent"):
        await client.post(
            f"/api/incidents/{incident_id}/votes",
            json={
                "agent_name": agent,
                "recommendation": "remediate",
                "confidence": 0.9,
                "reasoning": "looks safe to apply",
            },
        )

    # Run the decision engine
    decide_resp = await client.post(
        f"/api/incidents/{incident_id}/decide?strategy=weighted_majority"
    )
    assert decide_resp.status_code == 200

    # Mint and respond to an approval (auth disabled → dev caller)
    apr_resp = await client.post(
        f"/api/incidents/{incident_id}/approvals",
        json={
            "workflow_step": "DECIDING",
            "proposed_action": {"path": "rolling-restart"},
            "confidence_score": 0.9,
            "rationale": "p1 severity requires sign-off",
        },
    )
    assert apr_resp.status_code == 201
    approval_id = apr_resp.json()["approval_id"]

    # Pull the bundle
    bundle_resp = await client.get(f"/api/incidents/{incident_id}/audit-bundle")
    assert bundle_resp.status_code == 200
    bundle = bundle_resp.json()

    assert len(bundle["votes"]) == 2
    vote_agents = {v["agent_name"] for v in bundle["votes"]}
    assert vote_agents == {"knowledge-agent", "compliance-agent"}
    assert bundle["decision"] is not None
    assert bundle["decision"]["incident_id"] == incident_id
    assert len(bundle["approvals"]) == 1
    assert bundle["approvals"][0]["approval_id"] == approval_id
    assert bundle["approvals"][0]["status"] == "pending"
    # policy_decision is written when the threshold is met or rejected fast
    assert bundle["policy_applied"]["policy_id"] == "POL-INCIDENT-RESPONSE"
