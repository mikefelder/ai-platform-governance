"""Remediation option model — TC-8.

A typed option proposed by an agent (or composed by the supervisor) that the
human approver may select before the workflow proceeds to remediation. The
shape is intentionally narrow: every field maps to evidence the audit bundle
must capture so the chosen path is reconstructable post-incident.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _new_option_id() -> str:
    return f"opt-{uuid.uuid4().hex[:10]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RemediationOption(BaseModel):
    """One candidate remediation path for an incident."""

    option_id: str = Field(default_factory=_new_option_id)
    path: str = Field(..., min_length=1, max_length=256, description="Short, human-readable identifier (e.g. 'restart-pod', 'failover-region').")
    description: str | None = None
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Normalised risk 0=safe, 1=destructive.")
    compliance_profile: str = Field(..., min_length=1, max_length=64, description="Policy bucket the option satisfies (e.g. 'iso-27001', 'hipaa-safe', 'unrestricted').")
    estimated_cost_usd: float | None = Field(None, ge=0.0)
    estimated_duration_seconds: float | None = Field(None, ge=0.0)
    prerequisites: list[str] = Field(default_factory=list)
    proposed_by: str | None = Field(None, max_length=128, description="Agent or human that proposed the option.")
    created_at: datetime = Field(default_factory=_now)


class RemediationOptionCreateRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    risk_score: float = Field(..., ge=0.0, le=1.0)
    compliance_profile: str = Field(..., min_length=1, max_length=64)
    estimated_cost_usd: float | None = Field(None, ge=0.0)
    estimated_duration_seconds: float | None = Field(None, ge=0.0)
    prerequisites: list[str] = Field(default_factory=list)
    proposed_by: str | None = Field(None, max_length=128)


class RemediationSelection(BaseModel):
    incident_id: str
    selected_option_id: str
    selected_at: datetime
    selected_by: str | None = None
