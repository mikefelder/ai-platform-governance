"""TC-2 enforcement tests — policy snapshot drives approval thresholds.

Verifies that ``ApprovalService.respond`` reads
``incident.attributes['policy_applied']`` and:

  * rejects approvers missing the role required by the active severity rule;
  * tallies distinct approvers and only writes the aggregate
    ``policy_decision`` once ``required_approvals`` is met;
  * preserves snapshot immutability — publishing a new version of the
    enterprise policy after an incident is created MUST NOT change the
    threshold applied to that incident.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from governance_api.auth import CallerIdentity
from governance_api.models.approval import (
    ApprovalDecision,
    ApprovalResponseRequest,
)
from governance_api.models.enterprise_policy import (
    PolicyVersionPublishRequest,
    SeverityRule,
)
from governance_api.models.incident import (
    IncidentCategory,
    IncidentCreateRequest,
    IncidentSeverity,
    IncidentSource,
)
from governance_api.services.approval_service import (
    ApprovalRoleError,
    ApprovalService,
)
from governance_api.services.orchestration_service import (
    OrchestrationService,
    _incidents,
    _workflow_events,
)
from governance_api.services.policy_registry import (
    INCIDENT_RESPONSE_POLICY_ID,
    get_policy_registry,
)


def _caller(roles: list[str], oid: str = "oid-1", upn: str = "alice@example.com") -> CallerIdentity:
    return CallerIdentity(
        oid=oid,
        upn=upn,
        name=upn,
        tenant_id="tenant-1",
        roles=roles,
        scopes=["governance.write"],
        auth_mode="required",
    )


@pytest.fixture(autouse=True)
def _isolate_state():
    """Each test starts with empty incident + workflow state."""
    _incidents.clear()
    _workflow_events.clear()
    yield
    _incidents.clear()
    _workflow_events.clear()


@pytest.mark.asyncio
async def test_p1_requires_two_approvers_before_decision_is_written():
    orch = OrchestrationService()
    svc = ApprovalService()

    incident = await orch.create_incident(
        IncidentCreateRequest(
            title="P1 outage",
            description="payments down",
            severity=IncidentSeverity.P1,
            category=IncidentCategory.INFRASTRUCTURE,
            source=IncidentSource.MONITORING,
        ),
        caller=_caller(roles=["governance.admin"]),
    )

    # Snapshot must have been embedded at creation time.
    snap = incident.attributes["policy_applied"]
    assert snap["severity_rule"]["required_approvals"] == 2
    assert snap["severity_rule"]["approver_role"] == "incident-commanders"

    # Two distinct in-role approvers.
    a1 = await svc.create_approval(
        incident_id=incident.incident_id,
        workflow_step="DECIDING",
        proposed_action={"action": "rollback"},
        agent_analysis=[],
        confidence_score=0.9,
        severity="p1",
    )
    a2 = await svc.create_approval(
        incident_id=incident.incident_id,
        workflow_step="DECIDING",
        proposed_action={"action": "rollback"},
        agent_analysis=[],
        confidence_score=0.9,
        severity="p1",
    )

    # First approver: incident-level decision must NOT be finalised yet.
    await svc.respond(
        a1.approval_id,
        ApprovalResponseRequest(decision=ApprovalDecision.APPROVED),
        caller=_caller(roles=["incident-commanders"], oid="oid-A", upn="ic1@example.com"),
    )
    assert "policy_decision" not in (incident.attributes or {})

    # Second distinct approver: threshold met → policy_decision written.
    await svc.respond(
        a2.approval_id,
        ApprovalResponseRequest(decision=ApprovalDecision.APPROVED),
        caller=_caller(roles=["incident-commanders"], oid="oid-B", upn="ic2@example.com"),
    )
    decision = incident.attributes["policy_decision"]
    assert decision["decision"] == "approved"
    assert decision["approvals_count"] == 2
    assert decision["required_approvals"] == 2
    assert decision["policy_id"] == INCIDENT_RESPONSE_POLICY_ID
    assert decision["policy_content_hash"] == snap["content_hash"]

    events = [e.event_type for e in _workflow_events[incident.incident_id]]
    assert "policy.threshold_met" in events


@pytest.mark.asyncio
async def test_role_mismatch_raises_approval_role_error():
    orch = OrchestrationService()
    svc = ApprovalService()

    incident = await orch.create_incident(
        IncidentCreateRequest(
            title="P2 latency",
            description="slow",
            severity=IncidentSeverity.P2,
            category=IncidentCategory.INFRASTRUCTURE,
            source=IncidentSource.MONITORING,
        ),
        caller=_caller(roles=["governance.admin"]),
    )
    a = await svc.create_approval(
        incident_id=incident.incident_id,
        workflow_step="DECIDING",
        proposed_action={"action": "scale-out"},
        agent_analysis=[],
        confidence_score=0.7,
        severity="p2",
    )

    with pytest.raises(ApprovalRoleError):
        await svc.respond(
            a.approval_id,
            ApprovalResponseRequest(decision=ApprovalDecision.APPROVED),
            caller=_caller(roles=["random-role"], oid="oid-X"),
        )

    # No decision written, no event emitted.
    assert "policy_decision" not in (incident.attributes or {})
    assert all(
        e.event_type != "policy.threshold_met"
        for e in _workflow_events[incident.incident_id]
    )


@pytest.mark.asyncio
async def test_same_approver_voting_twice_does_not_satisfy_p1_threshold():
    orch = OrchestrationService()
    svc = ApprovalService()

    incident = await orch.create_incident(
        IncidentCreateRequest(
            title="P1 outage",
            description="db down",
            severity=IncidentSeverity.P1,
            category=IncidentCategory.INFRASTRUCTURE,
            source=IncidentSource.MONITORING,
        ),
        caller=_caller(roles=["governance.admin"]),
    )
    a1 = await svc.create_approval(
        incident_id=incident.incident_id,
        workflow_step="DECIDING",
        proposed_action={"action": "failover"},
        agent_analysis=[],
        confidence_score=0.9,
        severity="p1",
    )
    a2 = await svc.create_approval(
        incident_id=incident.incident_id,
        workflow_step="DECIDING",
        proposed_action={"action": "failover"},
        agent_analysis=[],
        confidence_score=0.9,
        severity="p1",
    )

    same = _caller(roles=["incident-commanders"], oid="oid-SAME")
    await svc.respond(a1.approval_id, ApprovalResponseRequest(decision=ApprovalDecision.APPROVED), caller=same)
    await svc.respond(a2.approval_id, ApprovalResponseRequest(decision=ApprovalDecision.APPROVED), caller=same)

    # Distinct approver count is 1 — threshold of 2 still unmet.
    assert "policy_decision" not in (incident.attributes or {})


@pytest.mark.asyncio
async def test_rejection_short_circuits_to_rejected_decision():
    orch = OrchestrationService()
    svc = ApprovalService()

    incident = await orch.create_incident(
        IncidentCreateRequest(
            title="P2 incident",
            description="x",
            severity=IncidentSeverity.P2,
            category=IncidentCategory.INFRASTRUCTURE,
            source=IncidentSource.MONITORING,
        ),
        caller=_caller(roles=["governance.admin"]),
    )
    a = await svc.create_approval(
        incident_id=incident.incident_id,
        workflow_step="DECIDING",
        proposed_action={"action": "restart"},
        agent_analysis=[],
        confidence_score=0.6,
        severity="p2",
    )
    await svc.respond(
        a.approval_id,
        ApprovalResponseRequest(decision=ApprovalDecision.REJECTED, comments="not approved"),
        caller=_caller(roles=["senior-engineers"], oid="oid-R"),
    )
    decision = incident.attributes["policy_decision"]
    assert decision["decision"] == "rejected"
    assert decision["rejections_count"] == 1
    events = [e.event_type for e in _workflow_events[incident.incident_id]]
    assert "policy.rejected" in events


@pytest.mark.asyncio
async def test_snapshot_immutability_after_policy_republish():
    """Publishing a v1.0.1 with a higher threshold MUST NOT retroactively
    raise the bar for incidents already in flight.
    """
    orch = OrchestrationService()
    svc = ApprovalService()
    registry = get_policy_registry()

    # Create a P2 incident under v1.0.0 (required_approvals = 1).
    incident = await orch.create_incident(
        IncidentCreateRequest(
            title="P2",
            description="x",
            severity=IncidentSeverity.P2,
            category=IncidentCategory.INFRASTRUCTURE,
            source=IncidentSource.MONITORING,
        ),
        caller=_caller(roles=["governance.admin"]),
    )
    snap_before = incident.attributes["policy_applied"]
    assert snap_before["version"] == "1.0.0"
    assert snap_before["severity_rule"]["required_approvals"] == 1

    # Publish v1.0.1 raising P2 to require 3 approvers.
    publisher = _caller(roles=["governance.admin"], oid="oid-P", upn="publisher@example.com")
    new_rules = [
        SeverityRule(
            severity=IncidentSeverity.P1,
            required_approvals=2,
            approver_role="incident-commanders",
            max_resolution_minutes=60,
            escalation_minutes=15,
            auto_remediate=False,
            required_agents=["compliance-agent"],
        ),
        SeverityRule(
            severity=IncidentSeverity.P2,
            required_approvals=3,
            approver_role="senior-engineers",
            max_resolution_minutes=240,
            escalation_minutes=30,
            auto_remediate=False,
            required_agents=[],
        ),
        SeverityRule(
            severity=IncidentSeverity.P3,
            required_approvals=1,
            approver_role="on-call",
            max_resolution_minutes=1440,
            escalation_minutes=120,
            auto_remediate=False,
            required_agents=[],
        ),
        SeverityRule(
            severity=IncidentSeverity.P4,
            required_approvals=0,
            approver_role="on-call",
            max_resolution_minutes=10080,
            escalation_minutes=480,
            auto_remediate=True,
            required_agents=[],
        ),
    ]
    registry.publish_version(
        INCIDENT_RESPONSE_POLICY_ID,
        PolicyVersionPublishRequest(
            version="1.0.1",
            severity_rules=new_rules,
            description="raise P2 bar",
            approval_thresholds={},
        ),
        caller=publisher,
    )

    # In-flight incident: snapshot still says required_approvals=1.
    a = await svc.create_approval(
        incident_id=incident.incident_id,
        workflow_step="DECIDING",
        proposed_action={"action": "scale"},
        agent_analysis=[],
        confidence_score=0.7,
        severity="p2",
    )
    await svc.respond(
        a.approval_id,
        ApprovalResponseRequest(decision=ApprovalDecision.APPROVED),
        caller=_caller(roles=["senior-engineers"], oid="oid-Q"),
    )
    decision = incident.attributes["policy_decision"]
    assert decision["decision"] == "approved"
    assert decision["required_approvals"] == 1
    assert decision["policy_version"] == "1.0.0"

    # Restore v1.0.0 as active so other tests are not affected.
    registry.publish_version(
        INCIDENT_RESPONSE_POLICY_ID,
        PolicyVersionPublishRequest(
            version="1.0.2",
            severity_rules=[
                SeverityRule(
                    severity=IncidentSeverity.P1,
                    required_approvals=2,
                    approver_role="incident-commanders",
                    max_resolution_minutes=60,
                    escalation_minutes=15,
                    auto_remediate=False,
                    required_agents=["compliance-agent", "knowledge-agent"],
                ),
                SeverityRule(
                    severity=IncidentSeverity.P2,
                    required_approvals=1,
                    approver_role="senior-engineers",
                    max_resolution_minutes=240,
                    escalation_minutes=30,
                    auto_remediate=False,
                    required_agents=["knowledge-agent"],
                ),
                SeverityRule(
                    severity=IncidentSeverity.P3,
                    required_approvals=1,
                    approver_role="on-call",
                    max_resolution_minutes=1440,
                    escalation_minutes=120,
                    auto_remediate=False,
                    required_agents=[],
                ),
                SeverityRule(
                    severity=IncidentSeverity.P4,
                    required_approvals=0,
                    approver_role="on-call",
                    max_resolution_minutes=10080,
                    escalation_minutes=480,
                    auto_remediate=True,
                    required_agents=[],
                ),
            ],
            description="restore",
            approval_thresholds={},
        ),
        caller=publisher,
    )


@pytest.mark.asyncio
async def test_p4_zero_approvers_clears_on_first_response():
    orch = OrchestrationService()
    svc = ApprovalService()

    incident = await orch.create_incident(
        IncidentCreateRequest(
            title="P4 housekeeping",
            description="rotate logs",
            severity=IncidentSeverity.P4,
            category=IncidentCategory.INFRASTRUCTURE,
            source=IncidentSource.MONITORING,
        ),
        caller=_caller(roles=["governance.admin"]),
    )
    assert incident.attributes["policy_applied"]["severity_rule"]["required_approvals"] == 0

    a = await svc.create_approval(
        incident_id=incident.incident_id,
        workflow_step="DECIDING",
        proposed_action={"action": "noop"},
        agent_analysis=[],
        confidence_score=0.5,
        severity="p4",
    )
    await svc.respond(
        a.approval_id,
        ApprovalResponseRequest(decision=ApprovalDecision.APPROVED),
        caller=_caller(roles=["on-call"], oid="oid-Z"),
    )
    assert incident.attributes["policy_decision"]["decision"] == "approved"
