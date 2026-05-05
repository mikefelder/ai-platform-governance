"""Human approval router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from governance_api.auth import CallerIdentity, get_caller_identity
from governance_api.models.approval import ApprovalRequest, ApprovalResponseRequest
from governance_api.services.approval_service import ApprovalRoleError, ApprovalService

router = APIRouter()
_service = ApprovalService()


@router.get("", response_model=list[ApprovalRequest])
async def list_approvals(
    incident_id: str | None = Query(None),
    pending_only: bool = Query(True),
):
    """List approval requests."""
    return await _service.list_approvals(incident_id=incident_id, pending_only=pending_only)


@router.get("/{approval_id}", response_model=ApprovalRequest)
async def get_approval(approval_id: str):
    """Get a single approval request."""
    approval = await _service.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found.")
    return approval


@router.post("/{approval_id}/respond", response_model=ApprovalRequest)
async def respond_to_approval(
    approval_id: str,
    response: ApprovalResponseRequest,
    caller: CallerIdentity = Depends(get_caller_identity),
):
    """Submit an approval decision (approved/rejected/escalated).

    Approver identity is taken from the validated Entra JWT (TC-9). The
    optional ``approver`` field in the request body is ignored when a token
    is present.
    """
    try:
        approval = await _service.respond(approval_id, response, caller=caller)
    except ApprovalRoleError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found.")
    return approval
