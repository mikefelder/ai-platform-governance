"""Compliance reporting router — evaluates agents against policies."""

from __future__ import annotations

from fastapi import APIRouter, Query

from governance_api.models.policy import ComplianceReport, PolicyViolation
from governance_api.services.policy_engine import PolicyEngineService

router = APIRouter()
_service = PolicyEngineService()


@router.get("/report", response_model=ComplianceReport)
async def compliance_report(
    hours: int = Query(24, ge=1, le=720, description="Evaluation window in hours."),
):
    """Generate a compliance report evaluating all agents against all active policies."""
    return await _service.evaluate_compliance(hours=hours)


@router.get("/violations", response_model=list[PolicyViolation])
async def compliance_violations(
    hours: int = Query(24, ge=1, le=720),
    agent_name: str | None = Query(None),
    policy_id: str | None = Query(None),
):
    """List policy violations, optionally filtered by agent or policy."""
    return await _service.list_violations(
        hours=hours, agent_name=agent_name, policy_id=policy_id
    )
