"""TC-2 — versioned enterprise policy registry tests."""

from __future__ import annotations

import pytest

from governance_api.services.policy_registry import (
    INCIDENT_RESPONSE_POLICY_ID,
    PolicyRegistry,
    get_policy_registry,
)


@pytest.fixture(autouse=True)
def _reset_registry(monkeypatch):
    """Each test gets a fresh in-memory registry singleton."""
    import governance_api.services.policy_registry as mod

    monkeypatch.setattr(mod, "_registry", PolicyRegistry())
    yield


# -- registry primitives -----------------------------------------------------


def test_seed_policy_is_active_with_hash():
    reg = get_policy_registry()
    policy = reg.get_policy(INCIDENT_RESPONSE_POLICY_ID)
    assert policy is not None
    assert policy.active_version == "1.0.0"
    active = reg.get_active_version(INCIDENT_RESPONSE_POLICY_ID)
    assert active is not None
    assert len(active.content_hash) == 64  # sha256 hex
    assert {r.severity.value for r in active.severity_rules} == {"p1", "p2", "p3", "p4"}


def test_resolve_for_incident_returns_severity_rule():
    from governance_api.models.incident import IncidentSeverity

    reg = get_policy_registry()
    applied = reg.resolve_for_incident(IncidentSeverity.P1)
    assert applied is not None
    assert applied.severity_rule.required_approvals == 2
    assert applied.severity_rule.auto_remediate is False
    assert applied.policy_id == INCIDENT_RESPONSE_POLICY_ID


def test_publish_version_appends_and_supersedes():
    from governance_api.models.enterprise_policy import (
        PolicyVersionPublishRequest,
        SeverityRule,
    )
    from governance_api.models.incident import IncidentSeverity

    reg = get_policy_registry()
    new = reg.publish_version(
        INCIDENT_RESPONSE_POLICY_ID,
        PolicyVersionPublishRequest(
            version="1.1.0",
            description="Tighten p2 SLA.",
            severity_rules=[
                SeverityRule(severity=s, required_approvals=1) for s in IncidentSeverity
            ],
        ),
    )
    assert new is not None
    assert new.version == "1.1.0"
    assert new.supersedes_version == "1.0.0"

    policy = reg.get_policy(INCIDENT_RESPONSE_POLICY_ID)
    assert policy is not None
    assert policy.active_version == "1.1.0"
    # Append-only: prior version still present, marked superseded.
    prior = next(v for v in policy.versions if v.version == "1.0.0")
    assert prior.status.value == "superseded"


def test_publish_duplicate_version_rejected():
    from governance_api.models.enterprise_policy import (
        PolicyVersionPublishRequest,
        SeverityRule,
    )
    from governance_api.models.incident import IncidentSeverity

    reg = get_policy_registry()
    with pytest.raises(ValueError):
        reg.publish_version(
            INCIDENT_RESPONSE_POLICY_ID,
            PolicyVersionPublishRequest(
                version="1.0.0",
                severity_rules=[
                    SeverityRule(severity=IncidentSeverity.P1, required_approvals=1)
                ],
            ),
        )


# -- HTTP routes -------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_endpoint(client):
    r = await client.get(f"/api/policies/registry/{INCIDENT_RESPONSE_POLICY_ID}/active")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "1.0.0"
    assert body["status"] == "active"


@pytest.mark.asyncio
async def test_versions_endpoint_returns_history(client):
    from governance_api.models.enterprise_policy import (
        PolicyVersionPublishRequest,
        SeverityRule,
    )
    from governance_api.models.incident import IncidentSeverity

    get_policy_registry().publish_version(
        INCIDENT_RESPONSE_POLICY_ID,
        PolicyVersionPublishRequest(
            version="1.2.0",
            severity_rules=[
                SeverityRule(severity=IncidentSeverity.P1, required_approvals=3)
            ],
        ),
    )
    r = await client.get(
        f"/api/policies/registry/{INCIDENT_RESPONSE_POLICY_ID}/versions"
    )
    assert r.status_code == 200
    versions = r.json()
    assert [v["version"] for v in versions][:2] == ["1.2.0", "1.0.0"]


@pytest.mark.asyncio
async def test_publish_version_endpoint(client):
    body = {
        "version": "2.0.0",
        "description": "Major rewrite.",
        "severity_rules": [
            {"severity": "p1", "required_approvals": 3, "auto_remediate": False},
            {"severity": "p2", "required_approvals": 1},
            {"severity": "p3", "required_approvals": 0},
            {"severity": "p4", "required_approvals": 0, "auto_remediate": True},
        ],
        "approval_thresholds": {"auto_remediate_confidence": 0.95},
    }
    r = await client.post(
        f"/api/policies/registry/{INCIDENT_RESPONSE_POLICY_ID}/versions", json=body
    )
    assert r.status_code == 201
    new_version = r.json()
    assert new_version["version"] == "2.0.0"
    assert new_version["supersedes_version"] == "1.0.0"
    # Caller identity (dev mode) recorded as publisher.
    assert new_version["published_by"]["upn"] == "local-dev@uaip.local"


@pytest.mark.asyncio
async def test_gateway_digest_endpoint(client):
    r = await client.get("/api/policies/gateway/digest")
    assert r.status_code == 200
    body = r.json()
    assert "digest" in body
    assert isinstance(body["sources"], list)


# -- incident integration ----------------------------------------------------


@pytest.mark.asyncio
async def test_incident_creation_attaches_policy_snapshot(client):
    r = await client.post(
        "/api/incidents",
        json={
            "title": "Storage account public access",
            "description": "Detected anonymous read on storage container.",
            "severity": "p1",
            "category": "security",
            "source": "monitoring",
        },
    )
    assert r.status_code in (201, 202)
    incident = r.json()
    applied = incident["attributes"]["policy_applied"]
    assert applied["policy_id"] == INCIDENT_RESPONSE_POLICY_ID
    assert applied["version"] == "1.0.0"
    assert applied["severity_rule"]["required_approvals"] == 2
    assert len(applied["content_hash"]) == 64


@pytest.mark.asyncio
async def test_workflow_history_contains_policy_applied_event(client):
    r = await client.post(
        "/api/incidents",
        json={
            "title": "Cost overrun",
            "severity": "p3",
            "category": "financial",
            "source": "monitoring",
        },
    )
    incident_id = r.json()["incident_id"]

    history = (
        await client.get(f"/api/workflows/{incident_id}/history")
    ).json()
    policy_event = next(
        (e for e in history if e["event_type"] == "policy.applied"), None
    )
    assert policy_event is not None
    assert policy_event["actor"] == "policy-registry"
    payload = policy_event["payload"]
    assert payload["policy_applied"]["version"] == "1.0.0"
    # Full snapshot embedded so audit replay is possible after policy changes.
    assert payload["policy_version"]["severity_rules"]
