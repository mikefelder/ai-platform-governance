"""Agent observability router — traces, health, and diagnostics."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from governance_api.auth import CallerIdentity, get_caller_identity
from governance_api.models.telemetry import AgentHealth, AgentTrace
from governance_api.services import agent_suspension
from governance_api.services.telemetry_query import TelemetryQueryService

router = APIRouter()
_service = TelemetryQueryService()


@router.get("/traces", response_model=list[AgentTrace])
async def list_traces(
    hours: int = Query(1, ge=1, le=168, description="Lookback window in hours."),
    agent_name: str | None = Query(None, description="Filter by agent name."),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent agent traces."""
    return await _service.list_traces(hours=hours, agent_name=agent_name, limit=limit)


@router.get("/health", response_model=list[AgentHealth])
async def agent_health(
    hours: int = Query(1, ge=1, le=24, description="Evaluation window in hours."),
):
    """Return health status for all known agents."""
    return await _service.get_agent_health(hours=hours)


# --- TC-10: agent suspension webhook ----------------------------------------


class AgentSuspensionEventModel(BaseModel):
    event_id: str
    event_type: str
    agent_name: str
    previous_status: str
    new_status: str
    reason: str | None = None
    requested_by: str | None = None
    source: str | None = None
    note: str | None = None
    correlation_id: str
    timestamp: str


class AgentSuspensionStateModel(BaseModel):
    agent_name: str
    status: Literal["active", "suspended"]
    reason: str | None = None
    requested_by: str | None = None
    source: str | None = None
    correlation_id: str | None = None
    suspended_at: datetime | None = None
    resumed_at: datetime | None = None
    history: list[AgentSuspensionEventModel] = Field(default_factory=list)


class SuspendAgentRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=512)
    source: str | None = Field(default=None, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)
    requested_by: str | None = Field(default=None, max_length=128)


class ResumeAgentRequest(BaseModel):
    note: str | None = Field(default=None, max_length=512)


class SuspendResponse(BaseModel):
    state: AgentSuspensionStateModel
    event: AgentSuspensionEventModel


def _to_state_model(s: agent_suspension.AgentSuspensionState) -> AgentSuspensionStateModel:
    return AgentSuspensionStateModel(
        agent_name=s.agent_name,
        status=s.status,
        reason=s.reason,
        requested_by=s.requested_by,
        source=s.source,
        correlation_id=s.correlation_id,
        suspended_at=s.suspended_at,
        resumed_at=s.resumed_at,
        history=[AgentSuspensionEventModel(**e) for e in s.history],
    )


@router.get("/suspensions", response_model=list[AgentSuspensionStateModel])
async def list_agent_suspensions():
    """List all known agent suspension states (any agent ever observed)."""
    return [_to_state_model(s) for s in await agent_suspension.list_states()]


@router.get("/{agent_name}/suspension", response_model=AgentSuspensionStateModel)
async def get_agent_suspension(agent_name: str):
    state = await agent_suspension.get_state(agent_name)
    return _to_state_model(state)


@router.post(
    "/{agent_name}/suspend",
    response_model=SuspendResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def suspend_agent(
    agent_name: str,
    body: SuspendAgentRequest,
    caller: CallerIdentity = Depends(get_caller_identity),
):
    """Suspend an agent. Webhook entry-point for Sentinel analytics rules.

    The caller must be authenticated; ``source`` should identify the originating
    system (e.g. ``"sentinel:agent_sla_breach"``). The body's optional
    ``correlation_id`` lets a Sentinel incident be tied back to this audit
    record. The full audit event is appended to the agent's history.
    """
    requested_by = body.requested_by or caller.upn or caller.oid
    state, event = await agent_suspension.suspend(
        agent_name,
        reason=body.reason,
        requested_by=requested_by,
        source=body.source,
        correlation_id=body.correlation_id,
    )
    return SuspendResponse(state=_to_state_model(state), event=AgentSuspensionEventModel(**event))


@router.post(
    "/{agent_name}/resume",
    response_model=SuspendResponse,
    status_code=status.HTTP_200_OK,
)
async def resume_agent(
    agent_name: str,
    body: ResumeAgentRequest,
    caller: CallerIdentity = Depends(get_caller_identity),
):
    """Resume a previously suspended agent. Returns 409 if already active."""
    current = await agent_suspension.get_state(agent_name)
    if current.status != "suspended":
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{agent_name}' is not suspended (status={current.status}).",
        )
    state, event = await agent_suspension.resume(
        agent_name,
        requested_by=caller.upn or caller.oid,
        note=body.note,
    )
    return SuspendResponse(state=_to_state_model(state), event=AgentSuspensionEventModel(**event))


@router.get("/{trace_id}", response_model=AgentTrace)
async def get_trace(trace_id: str):
    """Get a single trace with all its spans."""
    return await _service.get_trace(trace_id=trace_id)
