"""Incident data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class IncidentSeverity(str, Enum):
    P1 = "p1"  # Critical — immediate action
    P2 = "p2"  # High
    P3 = "p3"  # Medium
    P4 = "p4"  # Low


class IncidentCategory(str, Enum):
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    UNKNOWN = "unknown"


class IncidentStatus(str, Enum):
    RECEIVED = "received"
    TRIAGING = "triaging"
    INVESTIGATING = "investigating"
    DECIDING = "deciding"
    ESCALATED = "escalated"
    AWAITING_APPROVAL = "awaiting_approval"
    REJECTED = "rejected"
    REMEDIATING = "remediating"
    FAILED = "failed"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentSource(str, Enum):
    MONITORING = "monitoring"
    TICKETING = "ticketing"
    API = "api"
    EVENT_GRID = "event_grid"
    MANUAL = "manual"


class Incident(BaseModel):
    incident_id: str
    title: str
    description: str | None = None
    severity: IncidentSeverity = IncidentSeverity.P3
    category: IncidentCategory = IncidentCategory.UNKNOWN
    status: IncidentStatus = IncidentStatus.RECEIVED
    source: IncidentSource = IncidentSource.API
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    assigned_agent: str | None = None
    tags: list[str] = Field(default_factory=list)
    attributes: dict = Field(default_factory=dict)
    # TC-1: caller identity captured at incident creation (Entra OID + UPN).
    reported_by: dict | None = Field(
        default=None,
        description="Caller identity (oid, upn, name, tenant_id, auth_mode, captured_at).",
    )


class IncidentCreateRequest(BaseModel):
    title: str
    description: str | None = None
    severity: IncidentSeverity = IncidentSeverity.P3
    category: IncidentCategory = IncidentCategory.UNKNOWN
    source: IncidentSource = IncidentSource.API
    tags: list[str] = Field(default_factory=list)
    attributes: dict = Field(default_factory=dict)
