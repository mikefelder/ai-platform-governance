"""Approval request/response models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class ApprovalRequest(BaseModel):
    approval_id: str
    incident_id: str
    workflow_step: str
    proposed_action: dict = Field(default_factory=dict)
    agent_analysis: list[dict] = Field(default_factory=list)
    confidence_score: float = 0.0
    severity: str = "p3"
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None = None
    approver: str | None = None
    # TC-9: approver identity from validated Entra JWT.
    approver_oid: str | None = None
    approver_tenant_id: str | None = None
    approver_auth_mode: str | None = None
    decision: ApprovalDecision | None = None
    comments: str | None = None
    # Audit context populated when an orchestrator-role caller mints the
    # approval against a specific incident (TC-2 live path).
    rationale: str | None = None
    requested_by_agent: str | None = None
    requested_by_upn: str | None = None
    requested_by_oid: str | None = None


class ApprovalResponseRequest(BaseModel):
    decision: ApprovalDecision
    comments: str | None = None
    # Optional override; if absent, the validated JWT identity is used.
    approver: str | None = Field(
        default=None,
        description="Optional override; ignored when an Entra JWT is present.",
    )


class ApprovalCreateRequest(BaseModel):
    """Request body for ``POST /api/incidents/{incident_id}/approvals``.

    The workflow engine (or another orchestrator-role caller) submits this
    to bind a new HITL approval to an existing incident. ``severity`` is
    NOT accepted from the body — it is read from the incident so the caller
    cannot weaken the policy threshold.
    """

    workflow_step: str = Field(default="DECIDING")
    proposed_action: dict = Field(default_factory=dict)
    agent_analysis: list[dict] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str | None = Field(
        default=None,
        description="Free-form reason the orchestrator is requesting human approval.",
    )
    requested_by_agent: str | None = Field(
        default=None,
        description="Logical agent name that triggered the request (audit only).",
    )
