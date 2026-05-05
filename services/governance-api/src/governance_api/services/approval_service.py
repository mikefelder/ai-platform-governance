"""Approval service — manages HITL approval requests.

Phase 1: in-memory. Phase 2: Cosmos DB persistence + Service Bus notifications.

TC-2 enforcement: ``respond()`` consults the policy snapshot embedded on the
incident at creation time (``incident.attributes['policy_applied']``) to:

  * verify the caller carries the role required by the active severity rule
    (``approver_role``); and
  * tally distinct approvers and only mark the incident-level decision as
    cleared when ``required_approvals`` is met.

The snapshot is read from the incident — never re-resolved from the live
registry — so a v1.0.1 publish does not retroactively change the threshold
applied to in-flight incidents.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from governance_api.auth import CallerIdentity
from governance_api.models.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponseRequest,
    ApprovalStatus,
)
from governance_api.models.workflow import WorkflowEvent

logger = logging.getLogger("uc3.approvals")


class ApprovalRoleError(PermissionError):
    """Caller lacks the role required by the incident's policy snapshot."""

_TIMEOUT_MINUTES = int(os.environ.get("APPROVAL_TIMEOUT_MINUTES", "60"))

# In-memory store
_approvals: dict[str, ApprovalRequest] = {}

# Seed a mock pending approval for testing
_now = datetime.now(timezone.utc)
_seed = ApprovalRequest(
    approval_id="apr-seed-001",
    incident_id="inc-mock-001",
    workflow_step="DECIDING",
    proposed_action={"action": "restart_service", "target": "api-gateway-prod"},
    agent_analysis=[
        {"agent": "root_cause", "recommendation": "restart_service", "confidence": 0.85},
        {"agent": "knowledge", "recommendation": "restart_service", "confidence": 0.72},
    ],
    confidence_score=0.79,
    severity="p2",
    status=ApprovalStatus.PENDING,
    created_at=_now,
    expires_at=_now + timedelta(minutes=_TIMEOUT_MINUTES),
)
_approvals[_seed.approval_id] = _seed


class ApprovalService:
    """Manages human-in-the-loop approval requests."""

    async def list_approvals(
        self,
        incident_id: str | None = None,
        pending_only: bool = True,
    ) -> list[ApprovalRequest]:
        approvals = list(_approvals.values())
        if incident_id:
            approvals = [a for a in approvals if a.incident_id == incident_id]
        if pending_only:
            approvals = [a for a in approvals if a.status == ApprovalStatus.PENDING]
        return approvals

    async def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        return _approvals.get(approval_id)

    async def create_approval(
        self,
        incident_id: str,
        workflow_step: str,
        proposed_action: dict,
        agent_analysis: list[dict],
        confidence_score: float,
        severity: str = "p3",
        rationale: str | None = None,
        requested_by_agent: str | None = None,
        requested_by_caller: CallerIdentity | None = None,
    ) -> ApprovalRequest:
        now = datetime.now(timezone.utc)
        approval = ApprovalRequest(
            approval_id=f"apr-{uuid.uuid4().hex[:12]}",
            incident_id=incident_id,
            workflow_step=workflow_step,
            proposed_action=proposed_action,
            agent_analysis=agent_analysis,
            confidence_score=confidence_score,
            severity=severity,
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(minutes=_TIMEOUT_MINUTES),
            rationale=rationale,
            requested_by_agent=requested_by_agent,
            requested_by_upn=requested_by_caller.upn if requested_by_caller else None,
            requested_by_oid=requested_by_caller.oid if requested_by_caller else None,
        )
        _approvals[approval.approval_id] = approval
        # TODO Phase 2: publish to Service Bus approval-requests topic
        return approval

    async def respond(
        self,
        approval_id: str,
        response: ApprovalResponseRequest,
        caller: CallerIdentity | None = None,
    ) -> ApprovalRequest | None:
        approval = _approvals.get(approval_id)
        if approval is None:
            return None

        # TC-2: enforce role gating before recording the vote so a missing
        # role surfaces as 403 rather than a silent count toward the
        # threshold.
        snapshot = _policy_snapshot_for(approval.incident_id)
        if snapshot is not None and caller is not None:
            required_role = (
                snapshot.get("severity_rule", {}).get("approver_role")
            )
            if (
                required_role
                and caller.auth_mode != "disabled"
                and required_role not in (caller.roles or [])
            ):
                raise ApprovalRoleError(
                    f"Approver role '{required_role}' required by policy "
                    f"{snapshot.get('policy_id')} v{snapshot.get('version')}; "
                    f"caller {caller.upn or caller.oid} has roles "
                    f"{list(caller.roles or [])}."
                )

        now = datetime.now(timezone.utc)
        approval.decision = response.decision
        approval.comments = response.comments
        # TC-9: prefer the validated JWT identity over any request-body value.
        if caller is not None:
            approval.approver = caller.upn
            approval.approver_oid = caller.oid
            approval.approver_tenant_id = caller.tenant_id
            approval.approver_auth_mode = caller.auth_mode
        else:
            approval.approver = response.approver
        approval.completed_at = now
        approval.status = ApprovalStatus.COMPLETED

        # TC-2: tally distinct approvers for the incident and, when the
        # snapshot's required_approvals is met, write the aggregate
        # decision onto the incident and emit a workflow event.
        if snapshot is not None:
            _evaluate_incident_decision(approval.incident_id, snapshot, now)

        # TODO Phase 2: publish response to Service Bus approval-responses topic
        return approval


# --- TC-2 helpers --------------------------------------------------------
#
# Imports are deferred to avoid an import cycle with orchestration_service,
# which already imports the policy registry but does not import this module.


def _policy_snapshot_for(incident_id: str) -> dict | None:
    """Return the immutable policy snapshot embedded on the incident.

    Reads ``incident.attributes['policy_applied']`` from the orchestration
    in-memory store. Returns ``None`` when the incident or snapshot is
    missing — older incidents predating TC-2 simply skip enforcement.
    """
    from governance_api.services.orchestration_service import _incidents

    incident = _incidents.get(incident_id)
    if incident is None:
        return None
    snapshot = (incident.attributes or {}).get("policy_applied")
    return snapshot if isinstance(snapshot, dict) else None


def _evaluate_incident_decision(
    incident_id: str,
    snapshot: dict,
    now: datetime,
) -> None:
    """Tally per-incident votes and write the aggregate decision.

    Once the count of unique APPROVED approvers reaches the snapshot's
    ``required_approvals``, write a ``policy_decision`` block onto the
    incident and emit a ``policy.threshold_met`` workflow event. The
    aggregate is written exactly once — subsequent approvals leave it
    untouched so the original timestamp / approver list is preserved.

    Any REJECTED vote short-circuits to a rejected decision (single-veto
    semantics), recorded the same way.
    """
    from governance_api.services.orchestration_service import (
        _incidents,
        _workflow_events,
    )

    incident = _incidents.get(incident_id)
    if incident is None:
        return

    rule = snapshot.get("severity_rule") or {}
    required = int(rule.get("required_approvals", 0) or 0)

    # Distinct approvers, preferring oid then upn, then request-body approver.
    incident_approvals = [
        a for a in _approvals.values() if a.incident_id == incident_id
    ]

    def _identity(a: ApprovalRequest) -> str | None:
        return a.approver_oid or a.approver

    approved_ids: dict[str, ApprovalRequest] = {}
    rejected_ids: dict[str, ApprovalRequest] = {}
    for a in incident_approvals:
        ident = _identity(a)
        if not ident or a.decision is None:
            continue
        if a.decision == ApprovalDecision.APPROVED:
            approved_ids.setdefault(ident, a)
        elif a.decision == ApprovalDecision.REJECTED:
            rejected_ids.setdefault(ident, a)

    existing = (incident.attributes or {}).get("policy_decision")

    decision_state: str | None = None
    if rejected_ids:
        decision_state = "rejected"
    elif required > 0 and len(approved_ids) >= required:
        decision_state = "approved"
    elif required == 0:
        # Policy requires no approvers (e.g., p4) — first approval clears.
        if approved_ids:
            decision_state = "approved"

    if decision_state is None:
        return
    if existing and existing.get("decision") == decision_state:
        # Already finalised; do not overwrite the original audit record.
        return

    approver_records = [
        {
            "approval_id": a.approval_id,
            "approver": a.approver,
            "approver_oid": a.approver_oid,
            "decision": a.decision.value if a.decision else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        }
        for a in (
            list(approved_ids.values()) + list(rejected_ids.values())
        )
    ]

    policy_decision = {
        "decision": decision_state,
        "policy_id": snapshot.get("policy_id"),
        "policy_version": snapshot.get("version"),
        "policy_content_hash": snapshot.get("content_hash"),
        "required_approvals": required,
        "approver_role": rule.get("approver_role"),
        "approvals_count": len(approved_ids),
        "rejections_count": len(rejected_ids),
        "approvers": approver_records,
        "decided_at": now.isoformat(),
    }

    attributes = dict(incident.attributes or {})
    attributes["policy_decision"] = policy_decision
    incident.attributes = attributes
    incident.updated_at = now

    events = _workflow_events.setdefault(incident_id, [])
    events.append(
        WorkflowEvent(
            event_id=uuid.uuid4().hex,
            incident_id=incident_id,
            event_type=(
                "policy.threshold_met"
                if decision_state == "approved"
                else "policy.rejected"
            ),
            to_status=incident.status,
            actor="policy-registry",
            timestamp=now,
            payload=policy_decision,
        )
    )
    logger.info(
        "TC-2 enforcement: incident=%s decision=%s approvers=%d/%d policy=%s v%s",
        incident_id,
        decision_state,
        len(approved_ids),
        required,
        snapshot.get("policy_id"),
        snapshot.get("version"),
    )
