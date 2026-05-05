"""Workflow state models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from governance_api.models.incident import IncidentStatus


class WorkflowState(BaseModel):
    incident_id: str
    current_status: IncidentStatus
    previous_status: IncidentStatus | None = None
    transition_at: datetime
    agent_results: dict = Field(default_factory=dict)
    decision_confidence: float | None = None
    approval_id: str | None = None
    error: str | None = None


class WorkflowEvent(BaseModel):
    event_id: str
    incident_id: str
    event_type: str
    from_status: IncidentStatus | None = None
    to_status: IncidentStatus
    actor: str
    timestamp: datetime
    payload: dict = Field(default_factory=dict)
