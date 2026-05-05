"""Workflow status and control router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from governance_api.models.workflow import WorkflowState
from governance_api.services.orchestration_service import OrchestrationService

router = APIRouter()
_service = OrchestrationService()


@router.get("/{incident_id}", response_model=WorkflowState)
async def get_workflow_state(incident_id: str):
    """Get current workflow state for an incident."""
    state = await _service.get_workflow_state(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No workflow found for incident {incident_id}.")
    return state


@router.get("/{incident_id}/history", response_model=list[dict])
async def get_workflow_history(incident_id: str):
    """Get the full event history for an incident workflow."""
    return await _service.get_workflow_history(incident_id)
