"""Decision / voting models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentVote(BaseModel):
    agent_name: str
    recommendation: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str | None = None
    timestamp: datetime


class VotingStrategy(str):
    WEIGHTED_MAJORITY = "weighted_majority"
    UNANIMOUS = "unanimous"
    QUORUM = "quorum"


class Decision(BaseModel):
    incident_id: str
    outcome: str
    confidence: float
    strategy: str
    votes: list[AgentVote] = Field(default_factory=list)
    requires_approval: bool
    decided_at: datetime
    reasoning: str | None = None
    # TC-8: foreign-key to the RemediationOption the human selected (or the
    # decision engine auto-selected). Set via
    # ``POST /api/incidents/{id}/remediation-options/{option_id}/select``.
    selected_option_id: str | None = None
