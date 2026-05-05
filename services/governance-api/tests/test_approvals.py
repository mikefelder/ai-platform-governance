"""Approval endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_approvals(client: AsyncClient):
    response = await client.get("/api/approvals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Seed approval should be present
    assert len(data) >= 1
    assert data[0]["approval_id"].startswith("apr-")


@pytest.mark.asyncio
async def test_get_approval(client: AsyncClient):
    response = await client.get("/api/approvals/apr-seed-001")
    assert response.status_code == 200
    data = response.json()
    assert data["approval_id"] == "apr-seed-001"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_get_approval_not_found(client: AsyncClient):
    response = await client.get("/api/approvals/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_respond_to_approval_approved(client: AsyncClient):
    response = await client.post(
        "/api/approvals/apr-seed-001/respond",
        json={"decision": "approved", "approver": "admin@example.com", "comments": "LGTM"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "approved"
    assert data["status"] == "completed"
    # TC-9: approver identity is taken from the validated caller (dev stub
    # in tests), not the request body.
    assert data["approver"] == "local-dev@uaip.local"
    assert data["approver_oid"] == "00000000-0000-0000-0000-000000000000"
    assert data["approver_auth_mode"] == "dev"


# ---------------------------------------------------------------------------
# Option A: POST /api/incidents/{incident_id}/approvals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_approval_for_incident(client: AsyncClient):
    """Orchestrator can mint an approval bound to an existing incident."""
    inc = await client.post(
        "/api/incidents",
        json={
            "title": "tc2-bind-test",
            "description": "approval bound to a real incident",
            "severity": "p2",
        },
    )
    assert inc.status_code == 202
    incident_id = inc.json()["incident_id"]

    resp = await client.post(
        f"/api/incidents/{incident_id}/approvals",
        json={
            "workflow_step": "DECIDING",
            "proposed_action": {"action": "restart_service", "target": "api-gw"},
            "agent_analysis": [
                {"agent": "root_cause", "recommendation": "restart_service", "confidence": 0.9}
            ],
            "confidence_score": 0.9,
            "rationale": "low confidence triage",
            "requested_by_agent": "supervisor",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["incident_id"] == incident_id
    assert data["severity"] == "p2"  # taken from incident, not body
    assert data["status"] == "pending"
    assert data["rationale"] == "low confidence triage"
    assert data["requested_by_agent"] == "supervisor"
    # Dev caller identity is captured for audit
    assert data["requested_by_upn"] == "local-dev@uaip.local"


@pytest.mark.asyncio
async def test_request_approval_unknown_incident(client: AsyncClient):
    resp = await client.post(
        "/api/incidents/inc-does-not-exist/approvals",
        json={"proposed_action": {"action": "noop"}},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_request_approval_role_gated_when_entra(monkeypatch):
    """When auth_mode=entra and caller lacks orchestrator role, expect 403."""
    from httpx import ASGITransport, AsyncClient as Client

    from governance_api.auth import CallerIdentity, get_caller_identity
    from governance_api.main import app

    async def _entra_caller_no_role() -> CallerIdentity:
        return CallerIdentity(
            oid="11111111-1111-1111-1111-111111111111",
            upn="random.user@example.com",
            name="Random User",
            tenant_id="tnt",
            roles=[],
            scopes=[],
            auth_mode="entra",
        )

    app.dependency_overrides[get_caller_identity] = _entra_caller_no_role
    try:
        async with Client(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            inc = await ac.post(
                "/api/incidents",
                json={"title": "rbac-test", "description": "x", "severity": "p2"},
            )
            assert inc.status_code == 202
            incident_id = inc.json()["incident_id"]

            resp = await ac.post(
                f"/api/incidents/{incident_id}/approvals",
                json={"proposed_action": {"action": "noop"}},
            )
            assert resp.status_code == 403
            assert "workflow-orchestrator" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_caller_identity, None)


@pytest.mark.asyncio
async def test_request_approval_allowed_for_orchestrator_role(monkeypatch):
    """Caller carrying workflow-orchestrator role passes the gate."""
    from httpx import ASGITransport, AsyncClient as Client

    from governance_api.auth import CallerIdentity, get_caller_identity
    from governance_api.main import app

    async def _entra_orchestrator() -> CallerIdentity:
        return CallerIdentity(
            oid="22222222-2222-2222-2222-222222222222",
            upn="orchestrator@example.com",
            name="Orchestrator",
            tenant_id="tnt",
            roles=["workflow-orchestrator"],
            scopes=[],
            auth_mode="entra",
        )

    app.dependency_overrides[get_caller_identity] = _entra_orchestrator
    try:
        async with Client(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            inc = await ac.post(
                "/api/incidents",
                json={"title": "rbac-pass", "description": "x", "severity": "p3"},
            )
            incident_id = inc.json()["incident_id"]

            resp = await ac.post(
                f"/api/incidents/{incident_id}/approvals",
                json={"proposed_action": {"action": "noop"}},
            )
            assert resp.status_code == 201
            assert resp.json()["requested_by_upn"] == "orchestrator@example.com"
    finally:
        app.dependency_overrides.pop(get_caller_identity, None)
