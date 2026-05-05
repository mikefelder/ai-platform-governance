"""Enterprise policy registry models (TC-2).

Distinct from ``policy.py`` (which models per-agent operational rules like
token limits and latency thresholds), this module models *enterprise
governance policies* — versioned, append-only documents that drive how an
incident is handled (required approvals, escalation timers, agent
selection, etc.) for each severity class.

A policy is identified by ``policy_id`` (e.g. ``POL-INCIDENT-RESPONSE``)
and carries an immutable list of versions. Resolving a policy for an
incident always returns the currently active version's snapshot, which is
embedded in the ``policy.applied`` workflow event so the audit trail
records exactly which rules were enforced — even after the policy is
later updated.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from governance_api.models.incident import IncidentSeverity


class EnterprisePolicyStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class SeverityRule(BaseModel):
    """How the platform must handle an incident of a given severity."""

    severity: IncidentSeverity
    required_approvals: int = Field(
        default=0,
        description="Number of human approvals required before remediation.",
    )
    approver_role: str | None = Field(
        default=None,
        description="Entra group / role expected to approve (informational).",
    )
    max_resolution_minutes: int = Field(
        default=1440,
        description="Target time-to-resolve in minutes; SLA breach if exceeded.",
    )
    escalation_minutes: int = Field(
        default=60,
        description="Minutes to wait before escalating to the next on-call tier.",
    )
    auto_remediate: bool = Field(
        default=False,
        description="Whether the platform may remediate without human approval.",
    )
    required_agents: list[str] = Field(
        default_factory=list,
        description="Agents that MUST be invoked (e.g. compliance for p1).",
    )


class EnterprisePolicyVersion(BaseModel):
    """A single immutable version of an enterprise policy."""

    policy_id: str
    version: str = Field(..., description="Semantic version, e.g. 1.0.0.")
    effective_date: datetime
    status: EnterprisePolicyStatus = EnterprisePolicyStatus.ACTIVE
    description: str | None = None
    severity_rules: list[SeverityRule] = Field(default_factory=list)
    approval_thresholds: dict[str, float] = Field(
        default_factory=dict,
        description="Confidence/risk thresholds keyed by name.",
    )
    content_hash: str = Field(
        ...,
        description="SHA-256 hash of the canonical JSON form of this version.",
    )
    published_by: dict | None = Field(
        default=None,
        description="Caller identity that published this version.",
    )
    published_at: datetime
    supersedes_version: str | None = None


class EnterprisePolicy(BaseModel):
    """An enterprise policy with its full version history."""

    policy_id: str
    name: str
    description: str | None = None
    active_version: str
    versions: list[EnterprisePolicyVersion] = Field(default_factory=list)


class PolicyApplied(BaseModel):
    """Embedded snapshot recorded on an incident at creation time.

    This is what gets persisted into ``incident.attributes['policy_applied']``
    and carried in the ``policy.applied`` workflow event payload.
    """

    policy_id: str
    version: str
    content_hash: str
    resolved_at: datetime
    severity_rule: SeverityRule


class PolicyVersionPublishRequest(BaseModel):
    """Request body for publishing a new policy version."""

    version: str = Field(..., description="Semantic version, e.g. 1.1.0.")
    description: str | None = None
    severity_rules: list[SeverityRule]
    approval_thresholds: dict[str, float] = Field(default_factory=dict)
    effective_date: datetime | None = Field(
        default=None,
        description="Defaults to now if omitted.",
    )


class GatewayPolicyDigest(BaseModel):
    """Returned by /api/policies/gateway — a fingerprint of the APIM
    policies currently enforced at the edge. Lets auditors correlate
    incident-time enterprise policy with the gateway-side policy version.
    """

    digest: str
    sources: list[str]
    captured_at: datetime
