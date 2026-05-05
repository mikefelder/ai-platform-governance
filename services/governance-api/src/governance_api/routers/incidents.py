"""Incident lifecycle router."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from governance_api.auth import CallerIdentity, get_caller_identity
from governance_api.models.incident import Incident, IncidentCreateRequest, IncidentStatus
from governance_api.models.approval import ApprovalCreateRequest, ApprovalRequest
from governance_api.models.decision import AgentVote, Decision
from governance_api.models.remediation import (
    RemediationOption,
    RemediationOptionCreateRequest,
    RemediationSelection,
)
from governance_api.services.approval_service import ApprovalService
from governance_api.services.decision_engine import DecisionEngine
from governance_api.services.event_bus import (
    stream as event_stream,
    subscribe as event_subscribe,
    unsubscribe as event_unsubscribe,
)
from governance_api.services.orchestration_service import OrchestrationService

router = APIRouter()
_service = OrchestrationService()
_decision_engine = DecisionEngine()
_approval_service = ApprovalService()

# Roles permitted to mint a new HITL approval against an incident.
# Workflow orchestrators are the normal path; incident-commanders are the
# emergency-break path so a P1 ICM can request manual sign-off.
_APPROVAL_REQUESTER_ROLES = {"workflow-orchestrator", "incident-commanders"}

# In-memory vote and decision store (Phase 2: Cosmos DB)
_votes: dict[str, list[AgentVote]] = {}
_decisions: dict[str, Decision] = {}


class VoteRequest(BaseModel):
    agent_name: str
    recommendation: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str | None = None


@router.post("", response_model=Incident, status_code=202)
async def create_incident(
    request: IncidentCreateRequest,
    caller: CallerIdentity = Depends(get_caller_identity),
):
    """Create a new incident and start the orchestration workflow."""
    return await _service.create_incident(request, caller=caller)


@router.get("", response_model=list[Incident])
async def list_incidents(
    status: IncidentStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List incidents, optionally filtered by status."""
    return await _service.list_incidents(status=status, limit=limit)


@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str):
    """Get a single incident by ID."""
    incident = await _service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")
    return incident


@router.post("/{incident_id}/resolve", response_model=Incident)
async def resolve_incident(incident_id: str, resolution: dict | None = None):
    """Resolve an incident with optional resolution notes."""
    incident = await _service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")

    from datetime import datetime, timezone
    from governance_api.models.incident import IncidentStatus
    from governance_api.models.workflow import WorkflowEvent

    incident.status = IncidentStatus.RESOLVED
    incident.updated_at = datetime.now(timezone.utc)
    if resolution:
        incident.attributes = incident.attributes or {}
        incident.attributes["resolution"] = resolution

    return incident


@router.post("/{incident_id}/votes", response_model=AgentVote, status_code=201)
async def submit_vote(incident_id: str, vote_req: VoteRequest):
    """Submit an agent vote for incident resolution."""
    incident = await _service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")

    vote = AgentVote(
        agent_name=vote_req.agent_name,
        recommendation=vote_req.recommendation,
        confidence=vote_req.confidence,
        reasoning=vote_req.reasoning,
        timestamp=datetime.now(timezone.utc),
    )
    _votes.setdefault(incident_id, []).append(vote)

    # Transition to DECIDING if first vote
    if incident.status == IncidentStatus.TRIAGING or incident.status == IncidentStatus.INVESTIGATING:
        incident.status = IncidentStatus.DECIDING
        incident.updated_at = datetime.now(timezone.utc)

    return vote


@router.get("/{incident_id}/votes", response_model=list[AgentVote])
async def list_votes(incident_id: str):
    """List all agent votes for an incident."""
    return _votes.get(incident_id, [])


@router.post("/{incident_id}/decide", response_model=Decision)
async def decide(
    incident_id: str,
    strategy: str = Query("weighted_majority", description="Voting strategy: weighted_majority, unanimous, or quorum"),
):
    """Run the decision engine on submitted votes."""
    incident = await _service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")

    votes = _votes.get(incident_id, [])
    if not votes:
        raise HTTPException(status_code=400, detail="No votes submitted yet.")

    decision = _decision_engine.evaluate(
        incident_id=incident_id,
        votes=votes,
        severity=incident.severity,
        strategy=strategy,
    )
    _decisions[incident_id] = decision

    # Update incident status based on decision
    if decision.requires_approval:
        incident.status = IncidentStatus.AWAITING_APPROVAL
    elif decision.outcome == "escalate":
        incident.status = IncidentStatus.ESCALATED
    else:
        incident.status = IncidentStatus.REMEDIATING
    incident.updated_at = datetime.now(timezone.utc)
    incident.attributes = incident.attributes or {}
    incident.attributes["decision"] = decision.model_dump(mode="json")

    return decision


@router.get("/{incident_id}/decision", response_model=Decision)
async def get_decision(incident_id: str):
    """Get the decision for an incident."""
    decision = _decisions.get(incident_id)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"No decision for incident {incident_id}.")
    return decision


@router.post(
    "/{incident_id}/approvals",
    response_model=ApprovalRequest,
    status_code=201,
)
async def request_approval(
    incident_id: str,
    request: ApprovalCreateRequest,
    caller: CallerIdentity = Depends(get_caller_identity),
):
    """Mint a new HITL approval bound to this incident.

    Intended caller is the workflow orchestrator (UC2 supervisor or the
    UC3 internal workflow engine) when an incident transitions into a
    state requiring human sign-off. Severity, policy snapshot, and
    required-approvals are taken from the incident — not the request body —
    so a caller cannot weaken the policy threshold.

    Authorization: caller must hold ``workflow-orchestrator`` or
    ``incident-commanders``. The dev/disabled auth modes bypass the role
    gate so the unit suite and local stack remain usable without minting
    JWTs with custom roles.
    """
    incident = await _service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=404, detail=f"Incident {incident_id} not found."
        )

    if caller.auth_mode == "entra" and not (
        _APPROVAL_REQUESTER_ROLES & set(caller.roles or [])
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Caller {caller.upn or caller.oid} lacks a role permitted to "
                f"request approvals (requires one of "
                f"{sorted(_APPROVAL_REQUESTER_ROLES)})."
            ),
        )

    return await _approval_service.create_approval(
        incident_id=incident_id,
        workflow_step=request.workflow_step,
        proposed_action=request.proposed_action,
        agent_analysis=request.agent_analysis,
        confidence_score=request.confidence_score,
        severity=incident.severity.value,
        rationale=request.rationale,
        requested_by_agent=request.requested_by_agent,
        requested_by_caller=caller,
    )


# --- TC-13: one-shot audit bundle ----------------------------------------


class AuditBundle(BaseModel):
    """Composite audit record for a single incident.

    Aggregates every primitive captured during the incident's lifecycle into
    one canonical document — suitable for governance review, regulatory
    submission, and SIEM ingestion. The bundle is assembled on demand from
    the live stores; no separate persistence is introduced.
    """

    schema_version: str = "1.0"
    generated_at: datetime
    incident: Incident
    reported_by: dict | None = None
    policy_applied: dict | None = None
    policy_decision: dict | None = None
    workflow_events: list[dict] = Field(default_factory=list)
    workflow_state: dict | None = None
    votes: list[AgentVote] = Field(default_factory=list)
    decision: Decision | None = None
    approvals: list[ApprovalRequest] = Field(default_factory=list)
    remediation_options: list[dict] = Field(default_factory=list)
    selected_remediation_option_id: str | None = None
    trace_links: dict[str, str] = Field(default_factory=dict)


@router.get("/{incident_id}/audit-bundle", response_model=AuditBundle)
async def get_audit_bundle(incident_id: str):
    """Return a composite audit record for a single incident (TC-13).

    Composes:
      - Incident with caller identity (TC-1)
      - Embedded ``policy_applied`` snapshot + ``policy_decision`` aggregate (TC-2)
      - Full ``WorkflowEvent`` history (transitions, policy events, escalations)
      - Latest ``WorkflowState``
      - All agent votes + final ``Decision`` (TC-8)
      - All ``ApprovalRequest`` records with approver identity (TC-9)
      - Remediation options + selected option id (TC-8)
      - Trace correlation hints (App Insights query template)

    No state is mutated. Returns 404 if the incident is unknown.
    """
    incident = await _service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=404, detail=f"Incident {incident_id} not found."
        )

    attributes = incident.attributes or {}
    history = await _service.get_workflow_history(incident_id)
    state = await _service.get_workflow_state(incident_id)
    approvals = await _approval_service.list_approvals(
        incident_id=incident_id, pending_only=False
    )

    # App Insights trace correlation hint — operations engineer can paste
    # this KQL into the AppInsights blade to pull every span tagged with
    # this incident_id across all UCs and clouds.
    trace_links = {
        "kql_traces": (
            "union traces, requests, dependencies, exceptions "
            f"| where customDimensions.incident_id == '{incident_id}' "
            "| order by timestamp asc"
        ),
        "kql_workflow_events": (
            "AppEvents | where Properties.incident_id == "
            f"'{incident_id}' | order by TimeGenerated asc"
        ),
    }

    return AuditBundle(
        generated_at=datetime.now(timezone.utc),
        incident=incident,
        reported_by=incident.reported_by,
        policy_applied=attributes.get("policy_applied"),
        policy_decision=attributes.get("policy_decision"),
        workflow_events=history,
        workflow_state=state.model_dump(mode="json") if state else None,
        votes=_votes.get(incident_id, []),
        decision=_decisions.get(incident_id),
        approvals=approvals,
        remediation_options=attributes.get("remediation_options", []),
        selected_remediation_option_id=attributes.get(
            "selected_remediation_option_id"
        ),
        trace_links=trace_links,
    )


# --- TC-5: agent SLA breach escalation -----------------------------------


class EscalationRequest(BaseModel):
    """Body for ``POST /api/incidents/{id}/escalations``.

    Service-to-service contract used by the UC2 supervisor (and any other
    agent) to flip an incident into ESCALATED state and persist a forensic
    ``escalation.<type>`` workflow event. The default ``type`` is the only
    one the supervisor publishes today (``sla_breach``); the field is left
    open so the same endpoint can absorb future escalation triggers
    (e.g. ``confidence_low``, ``policy_veto``, ``manual``).
    """

    type: str = Field("sla_breach", min_length=1, max_length=64)
    source: str = Field("supervisor", min_length=1, max_length=128)
    agent_name: str | None = Field(None, max_length=128)
    sla_threshold_seconds: float | None = Field(None, ge=0)
    elapsed_seconds: float | None = Field(None, ge=0)
    reason: str | None = None
    details: dict = Field(default_factory=dict)


class EscalationResponse(BaseModel):
    incident_id: str
    status: IncidentStatus
    escalation_type: str
    source: str
    recorded_at: datetime


@router.post(
    "/{incident_id}/escalations",
    response_model=EscalationResponse,
    status_code=202,
)
async def record_escalation(incident_id: str, request: EscalationRequest):
    """Record an SLA-breach (or other) escalation against an incident.

    Wired by the UC2 supervisor's ``record_sla_breach`` helper when the call
    site has an ``incident_id`` in scope. Idempotency is intentionally not
    enforced — every distinct breach event is forensic evidence and is
    appended to the workflow log; UI/SIEM consumers de-duplicate by
    ``event_id``.
    """
    payload = {
        "agent_name": request.agent_name,
        "sla_threshold_seconds": request.sla_threshold_seconds,
        "elapsed_seconds": request.elapsed_seconds,
        "reason": request.reason,
        **(request.details or {}),
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    incident = await _service.record_escalation(
        incident_id,
        escalation_type=request.type,
        source=request.source,
        payload=payload,
    )
    if incident is None:
        raise HTTPException(
            status_code=404,
            detail=f"Incident {incident_id} not found.",
        )

    return EscalationResponse(
        incident_id=incident.incident_id,
        status=incident.status,
        escalation_type=request.type,
        source=request.source,
        recorded_at=incident.updated_at,
    )


# --- TC-8: typed remediation options -------------------------------------


@router.post(
    "/{incident_id}/remediation-options",
    response_model=RemediationOption,
    status_code=201,
)
async def add_remediation_option(
    incident_id: str,
    request: RemediationOptionCreateRequest,
    caller: CallerIdentity = Depends(get_caller_identity),
):
    """Append a typed remediation option to the incident.

    Each option is forensic evidence of a path the system considered. The
    decision engine — or the human approver via the select endpoint — picks
    one as the ``selected_option_id`` recorded on the Decision.
    """
    option = RemediationOption(
        path=request.path,
        description=request.description,
        risk_score=request.risk_score,
        compliance_profile=request.compliance_profile,
        estimated_cost_usd=request.estimated_cost_usd,
        estimated_duration_seconds=request.estimated_duration_seconds,
        prerequisites=list(request.prerequisites),
        proposed_by=request.proposed_by or (caller.upn or caller.oid),
    )
    stored = await _service.add_remediation_option(
        incident_id,
        option=option.model_dump(mode="json"),
        actor=request.proposed_by or (caller.upn or caller.oid or "unknown"),
    )
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")
    return option


@router.get(
    "/{incident_id}/remediation-options",
    response_model=list[RemediationOption],
)
async def list_remediation_options(incident_id: str):
    options = await _service.list_remediation_options(incident_id)
    if options is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")
    return [RemediationOption.model_validate(o) for o in options]


@router.post(
    "/{incident_id}/remediation-options/{option_id}/select",
    response_model=RemediationSelection,
)
async def select_remediation_option(
    incident_id: str,
    option_id: str,
    caller: CallerIdentity = Depends(get_caller_identity),
):
    """Mark ``option_id`` as the chosen remediation path for this incident.

    Side-effect: any existing ``Decision`` is updated in-place to record
    ``selected_option_id`` so the Decision FK and the incident attribute
    stay consistent (they are both surfaced in the audit bundle).
    """
    selected = await _service.select_remediation_option(
        incident_id,
        option_id,
        actor=(caller.upn or caller.oid or "unknown"),
    )
    if selected is None:
        # Differentiate 404 incident vs 404 option for better diagnostics.
        if await _service.get_incident(incident_id) is None:
            raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")
        raise HTTPException(
            status_code=404,
            detail=f"Remediation option {option_id} not found on incident {incident_id}.",
        )

    decision = _decisions.get(incident_id)
    if decision is not None:
        decision.selected_option_id = option_id

    return RemediationSelection(
        incident_id=incident_id,
        selected_option_id=option_id,
        selected_at=datetime.now(timezone.utc),
        selected_by=caller.upn or caller.oid,
    )


# --- TC-11: live workflow event stream (Server-Sent Events) ---------------


@router.get("/{incident_id}/events/stream")
async def stream_incident_events(incident_id: str):
    """Server-Sent Events feed of WorkflowEvents for ``incident_id``.

    Browsers (FlowPage in the UAIP frontend) subscribe with EventSource.
    Each frame is a single JSON-serialised WorkflowEvent. The first frame
    is a synthetic ``stream.opened`` so the client can render an attached
    indicator immediately. Keepalive ``: ping`` comments are emitted every
    15 s so APIM/nginx will not idle-out the connection.

    The response body never ends until the client disconnects; the broker
    cleans up the subscriber queue in the generator's ``finally``.
    """
    incident = await _service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")

    # Subscribe synchronously before yielding the open frame so the client
    # cannot miss events published between connect and first iteration.
    queue = event_subscribe(incident_id)

    async def _gen():
        try:
            yield (
                f'event: stream.opened\ndata: {{"incident_id":"{incident_id}"}}\n\n'
            )
            import asyncio as _asyncio
            import json as _json
            while True:
                try:
                    evt = await _asyncio.wait_for(queue.get(), timeout=15.0)
                except _asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"event: {evt.get('event_type', 'workflow.event')}\n"
                yield f"data: {_json.dumps(evt, default=str)}\n\n"
        finally:
            event_unsubscribe(incident_id, queue)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
