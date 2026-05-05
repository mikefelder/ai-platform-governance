"""Policy management router — CRUD for governance rules."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from governance_api.auth import CallerIdentity, get_caller_identity
from governance_api.models.enterprise_policy import (
    EnterprisePolicy,
    EnterprisePolicyVersion,
    GatewayPolicyDigest,
    PolicyVersionPublishRequest,
)
from governance_api.models.policy import (
    PolicyCreateRequest,
    PolicyRule,
    PolicyUpdateRequest,
)
from governance_api.services.policy_engine import PolicyEngineService
from governance_api.services.policy_registry import (
    INCIDENT_RESPONSE_POLICY_ID,
    get_policy_registry,
)

router = APIRouter()
_service = PolicyEngineService()


@router.get("", response_model=list[PolicyRule])
async def list_policies():
    """List all governance policies."""
    return await _service.list_policies()


@router.post("", response_model=PolicyRule, status_code=201)
async def create_policy(request: PolicyCreateRequest):
    """Create a new governance policy."""
    return await _service.create_policy(request)


@router.put("/{policy_id}", response_model=PolicyRule)
async def update_policy(policy_id: str, request: PolicyUpdateRequest):
    """Update an existing governance policy."""
    policy = await _service.update_policy(policy_id, request)
    if policy is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found.")
    return policy


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(policy_id: str):
    """Delete a governance policy."""
    deleted = await _service.delete_policy(policy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found.")


# ---------------------------------------------------------------------------
# TC-2: Enterprise policy registry (versioned, append-only)
# ---------------------------------------------------------------------------


@router.get("/registry", response_model=list[EnterprisePolicy])
async def list_enterprise_policies():
    """List all enterprise policies (each with full version history)."""
    return get_policy_registry().list_policies()


@router.get("/registry/{policy_id}", response_model=EnterprisePolicy)
async def get_enterprise_policy(policy_id: str):
    """Return a single enterprise policy with its full version history."""
    policy = get_policy_registry().get_policy(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found.")
    return policy


@router.get(
    "/registry/{policy_id}/active",
    response_model=EnterprisePolicyVersion,
)
async def get_active_enterprise_policy_version(policy_id: str):
    """Return the currently active version of an enterprise policy."""
    version = get_policy_registry().get_active_version(policy_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found.")
    return version


@router.get(
    "/registry/{policy_id}/versions",
    response_model=list[EnterprisePolicyVersion],
)
async def list_enterprise_policy_versions(policy_id: str):
    """Return the full append-only version history (newest first)."""
    versions = get_policy_registry().list_versions(policy_id)
    if versions is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found.")
    return versions


@router.post(
    "/registry/{policy_id}/versions",
    response_model=EnterprisePolicyVersion,
    status_code=201,
)
async def publish_enterprise_policy_version(
    policy_id: str,
    request: PolicyVersionPublishRequest,
    caller: CallerIdentity = Depends(get_caller_identity),
):
    """Append a new immutable version and mark it active."""
    try:
        version = get_policy_registry().publish_version(
            policy_id, request, caller=caller
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if version is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found.")
    return version


@router.get("/gateway/digest", response_model=GatewayPolicyDigest)
async def get_gateway_policy_digest():
    """SHA-256 digest of the APIM policy XML/Terraform currently deployed.

    Lets auditors confirm the gateway-enforced policy at incident time
    matches the IaC-tracked policy. Sources are configurable via the
    ``APIM_POLICY_PATHS`` env var (comma-separated globs).
    """
    return get_policy_registry().gateway_digest()


# Convenience alias for the well-known incident-response policy.
@router.get(
    "/registry/incident-response/active",
    response_model=EnterprisePolicyVersion,
    include_in_schema=False,
)
async def get_active_incident_response_policy():
    return await get_active_enterprise_policy_version(INCIDENT_RESPONSE_POLICY_ID)
