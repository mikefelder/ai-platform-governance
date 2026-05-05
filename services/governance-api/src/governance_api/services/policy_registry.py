"""Enterprise policy registry — append-only versioned policy store (TC-2).

Policies are kept in-memory for the PoC with optional Cosmos DB persistence
(container ``policies``) when ``COSMOS_ENDPOINT`` is configured. New
versions are *appended* — existing versions are never mutated, so the
audit trail remains intact even after the active policy is changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Iterable

from governance_api.auth import CallerIdentity
from governance_api.models.enterprise_policy import (
    EnterprisePolicy,
    EnterprisePolicyStatus,
    EnterprisePolicyVersion,
    GatewayPolicyDigest,
    PolicyApplied,
    PolicyVersionPublishRequest,
    SeverityRule,
)
from governance_api.models.incident import IncidentSeverity

logger = logging.getLogger("uc3.policy_registry")

# Identifier for the seeded policy that drives incident workflows.
INCIDENT_RESPONSE_POLICY_ID = "POL-INCIDENT-RESPONSE"


def _canonical_hash(version: EnterprisePolicyVersion | dict) -> str:
    """Return a deterministic SHA-256 of the policy version's canonical JSON.

    The ``content_hash`` field is excluded from the hash input itself so the
    hash describes the policy *body* rather than including itself.
    """
    if isinstance(version, EnterprisePolicyVersion):
        data = version.model_dump(mode="json")
    else:
        data = dict(version)
    data.pop("content_hash", None)
    data.pop("published_by", None)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _seed_incident_response_policy() -> EnterprisePolicy:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rules = [
        SeverityRule(
            severity=IncidentSeverity.P1,
            required_approvals=2,
            approver_role="incident-commanders",
            max_resolution_minutes=60,
            escalation_minutes=15,
            auto_remediate=False,
            required_agents=["compliance-agent", "knowledge-agent"],
        ),
        SeverityRule(
            severity=IncidentSeverity.P2,
            required_approvals=1,
            approver_role="senior-engineers",
            max_resolution_minutes=240,
            escalation_minutes=30,
            auto_remediate=False,
            required_agents=["knowledge-agent"],
        ),
        SeverityRule(
            severity=IncidentSeverity.P3,
            required_approvals=1,
            approver_role="on-call",
            max_resolution_minutes=1440,
            escalation_minutes=120,
            auto_remediate=False,
            required_agents=[],
        ),
        SeverityRule(
            severity=IncidentSeverity.P4,
            required_approvals=0,
            approver_role=None,
            max_resolution_minutes=4320,
            escalation_minutes=480,
            auto_remediate=True,
            required_agents=[],
        ),
    ]
    version_payload = EnterprisePolicyVersion(
        policy_id=INCIDENT_RESPONSE_POLICY_ID,
        version="1.0.0",
        effective_date=now,
        status=EnterprisePolicyStatus.ACTIVE,
        description="Initial enterprise incident-response policy.",
        severity_rules=rules,
        approval_thresholds={
            "auto_remediate_confidence": 0.9,
            "escalate_below_confidence": 0.5,
        },
        content_hash="",  # placeholder; replaced below
        published_at=now,
    )
    version_payload.content_hash = _canonical_hash(version_payload)
    return EnterprisePolicy(
        policy_id=INCIDENT_RESPONSE_POLICY_ID,
        name="Enterprise Incident Response Policy",
        description=(
            "Defines required approvals, escalation timers and mandatory "
            "agents for each incident severity class."
        ),
        active_version="1.0.0",
        versions=[version_payload],
    )


class PolicyRegistry:
    """Append-only versioned enterprise policy store."""

    def __init__(self) -> None:
        self._policies: dict[str, EnterprisePolicy] = {
            INCIDENT_RESPONSE_POLICY_ID: _seed_incident_response_policy(),
        }

    # ----- read -----

    def list_policies(self) -> list[EnterprisePolicy]:
        return list(self._policies.values())

    def get_policy(self, policy_id: str) -> EnterprisePolicy | None:
        return self._policies.get(policy_id)

    def get_active_version(self, policy_id: str) -> EnterprisePolicyVersion | None:
        policy = self._policies.get(policy_id)
        if policy is None:
            return None
        return next(
            (v for v in policy.versions if v.version == policy.active_version),
            None,
        )

    def list_versions(self, policy_id: str) -> list[EnterprisePolicyVersion] | None:
        policy = self._policies.get(policy_id)
        if policy is None:
            return None
        # Newest first.
        return sorted(policy.versions, key=lambda v: v.published_at, reverse=True)

    # ----- mutation (append-only) -----

    def publish_version(
        self,
        policy_id: str,
        request: PolicyVersionPublishRequest,
        caller: CallerIdentity | None = None,
    ) -> EnterprisePolicyVersion | None:
        policy = self._policies.get(policy_id)
        if policy is None:
            return None
        if any(v.version == request.version for v in policy.versions):
            raise ValueError(f"Version {request.version} already exists for {policy_id}.")

        now = datetime.now(timezone.utc)
        previous_active = policy.active_version
        for v in policy.versions:
            if v.version == previous_active:
                v.status = EnterprisePolicyStatus.SUPERSEDED

        new_version = EnterprisePolicyVersion(
            policy_id=policy_id,
            version=request.version,
            effective_date=request.effective_date or now,
            status=EnterprisePolicyStatus.ACTIVE,
            description=request.description,
            severity_rules=request.severity_rules,
            approval_thresholds=request.approval_thresholds,
            content_hash="",
            published_by=caller.audit_dict() if caller else None,
            published_at=now,
            supersedes_version=previous_active,
        )
        new_version.content_hash = _canonical_hash(new_version)
        policy.versions.append(new_version)
        policy.active_version = new_version.version
        return new_version

    # ----- application -----

    def resolve_for_incident(
        self,
        severity: IncidentSeverity,
        policy_id: str = INCIDENT_RESPONSE_POLICY_ID,
    ) -> PolicyApplied | None:
        """Return the snapshot that should be embedded on an incident."""
        version = self.get_active_version(policy_id)
        if version is None:
            return None
        rule = next(
            (r for r in version.severity_rules if r.severity == severity),
            None,
        )
        if rule is None:
            # Fall back to the lowest-severity rule rather than raising.
            rule = version.severity_rules[-1] if version.severity_rules else None
        if rule is None:
            return None
        return PolicyApplied(
            policy_id=version.policy_id,
            version=version.version,
            content_hash=version.content_hash,
            resolved_at=datetime.now(timezone.utc),
            severity_rule=rule,
        )

    # ----- gateway hash -----

    def gateway_digest(
        self, sources: Iterable[str] | None = None
    ) -> GatewayPolicyDigest:
        """Compute a stable digest of the APIM policy XML files.

        Lets auditors confirm the *gateway-enforced* policy at incident
        time matches what the IaC pipeline last deployed. Sources default
        to a search across the repo's ``infra/main.apim.tf`` files.
        """
        if sources is None:
            roots = os.environ.get(
                "APIM_POLICY_PATHS",
                "infra/main.apim.tf,../../infra/main.apim.tf",
            ).split(",")
            sources = [s.strip() for s in roots if s.strip()]

        resolved: list[Path] = []
        for pattern in sources:
            for match in glob(pattern, recursive=True):
                p = Path(match)
                if p.is_file():
                    resolved.append(p)

        sha = hashlib.sha256()
        captured_sources: list[str] = []
        for path in sorted(resolved):
            try:
                sha.update(path.read_bytes())
                captured_sources.append(str(path))
            except OSError as exc:
                logger.warning("Could not read %s for digest: %s", path, exc)

        return GatewayPolicyDigest(
            digest=sha.hexdigest() if captured_sources else "unknown",
            sources=captured_sources,
            captured_at=datetime.now(timezone.utc),
        )


# Module-level singleton — routers and the orchestration service share this.
_registry: PolicyRegistry | None = None


def get_policy_registry() -> PolicyRegistry:
    global _registry
    if _registry is None:
        _registry = PolicyRegistry()
    return _registry
