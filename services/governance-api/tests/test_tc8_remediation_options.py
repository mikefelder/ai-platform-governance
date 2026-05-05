"""TC-8 — typed remediation options."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


_OPTION_BODY = {
    "path": "restart-pod",
    "description": "Roll the failing pod and let the deployment self-heal.",
    "risk_score": 0.15,
    "compliance_profile": "iso-27001",
    "estimated_cost_usd": 0.0,
    "estimated_duration_seconds": 90.0,
    "prerequisites": ["aks-credentials"],
    "proposed_by": "engineering-agent",
}


@pytest.mark.asyncio
async def test_add_remediation_option_404_for_unknown_incident(client: AsyncClient):
    resp = await client.post(
        "/api/incidents/inc-missing/remediation-options",
        json=_OPTION_BODY,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_and_list_remediation_options(client: AsyncClient):
    iid = (await client.post("/api/incidents", json={"title": "TC-8 add", "severity": "p2"})).json()["incident_id"]

    add = await client.post(f"/api/incidents/{iid}/remediation-options", json=_OPTION_BODY)
    assert add.status_code == 201, add.text
    option = add.json()
    assert option["path"] == "restart-pod"
    assert option["risk_score"] == 0.15
    assert option["compliance_profile"] == "iso-27001"
    assert option["option_id"].startswith("opt-")

    listed = await client.get(f"/api/incidents/{iid}/remediation-options")
    assert listed.status_code == 200
    options = listed.json()
    assert len(options) == 1
    assert options[0]["option_id"] == option["option_id"]


@pytest.mark.asyncio
async def test_select_remediation_option_404_for_unknown_option(client: AsyncClient):
    iid = (await client.post("/api/incidents", json={"title": "TC-8 sel-404", "severity": "p3"})).json()["incident_id"]
    resp = await client.post(f"/api/incidents/{iid}/remediation-options/opt-missing/select")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_select_remediation_option_updates_attribute_and_event(client: AsyncClient):
    iid = (await client.post("/api/incidents", json={"title": "TC-8 select", "severity": "p2"})).json()["incident_id"]
    add = await client.post(f"/api/incidents/{iid}/remediation-options", json=_OPTION_BODY)
    option_id = add.json()["option_id"]

    sel = await client.post(f"/api/incidents/{iid}/remediation-options/{option_id}/select")
    assert sel.status_code == 200, sel.text
    body = sel.json()
    assert body["incident_id"] == iid
    assert body["selected_option_id"] == option_id

    bundle = (await client.get(f"/api/incidents/{iid}/audit-bundle")).json()
    assert bundle["selected_remediation_option_id"] == option_id
    assert any(o["option_id"] == option_id for o in bundle["remediation_options"])
    types = [e["event_type"] for e in bundle["workflow_events"]]
    assert "remediation.option_added" in types
    assert "remediation.option_selected" in types


@pytest.mark.asyncio
async def test_select_updates_decision_fk(client: AsyncClient):
    iid = (await client.post("/api/incidents", json={"title": "TC-8 fk", "severity": "p2"})).json()["incident_id"]

    # Need a Decision in the store. Submit a vote then call /decide.
    await client.post(
        f"/api/incidents/{iid}/votes",
        json={"agent_name": "engineering", "recommendation": "remediate", "confidence": 0.9},
    )
    dec = await client.post(f"/api/incidents/{iid}/decide")
    assert dec.status_code == 200
    assert dec.json().get("selected_option_id") in (None,)

    add = await client.post(f"/api/incidents/{iid}/remediation-options", json=_OPTION_BODY)
    option_id = add.json()["option_id"]
    await client.post(f"/api/incidents/{iid}/remediation-options/{option_id}/select")

    decision = (await client.get(f"/api/incidents/{iid}/decision")).json()
    assert decision["selected_option_id"] == option_id

    bundle = (await client.get(f"/api/incidents/{iid}/audit-bundle")).json()
    assert bundle["decision"]["selected_option_id"] == option_id


@pytest.mark.asyncio
async def test_remediation_option_validation(client: AsyncClient):
    iid = (await client.post("/api/incidents", json={"title": "TC-8 val", "severity": "p3"})).json()["incident_id"]
    bad = {**_OPTION_BODY, "risk_score": 1.5}
    resp = await client.post(f"/api/incidents/{iid}/remediation-options", json=bad)
    assert resp.status_code == 422
