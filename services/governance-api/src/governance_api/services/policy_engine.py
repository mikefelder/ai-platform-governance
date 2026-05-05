"""Policy engine service — CRUD + compliance evaluation.

Policies are stored in-memory for the PoC. Phase 3 will add
Key Vault or Cosmos DB persistence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from governance_api.models.policy import (
    ComplianceReport,
    ComplianceStatus,
    PolicyCreateRequest,
    PolicyRule,
    PolicySeverity,
    PolicyStatus,
    PolicyType,
    PolicyUpdateRequest,
    PolicyViolation,
)


# Default seed policies
_DEFAULT_POLICIES: list[PolicyRule] = [
    PolicyRule(
        id="pol-001",
        name="Max tokens per request",
        description="No single agent invocation should consume more than 10,000 tokens.",
        policy_type=PolicyType.TOKEN_LIMIT,
        severity=PolicySeverity.MEDIUM,
        threshold=10000,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
    PolicyRule(
        id="pol-002",
        name="Agent error rate threshold",
        description="Alert when any agent's error rate exceeds 15%.",
        policy_type=PolicyType.ERROR_RATE_THRESHOLD,
        severity=PolicySeverity.HIGH,
        threshold=15.0,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
    PolicyRule(
        id="pol-003",
        name="P95 latency threshold",
        description="Alert when P95 latency exceeds 5 seconds for any agent.",
        policy_type=PolicyType.LATENCY_THRESHOLD,
        severity=PolicySeverity.MEDIUM,
        threshold=5000.0,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
    PolicyRule(
        id="pol-004",
        name="Allowed models",
        description="Only approved models may be used in production.",
        policy_type=PolicyType.ALLOWED_MODELS,
        severity=PolicySeverity.HIGH,
        allowed_values=["gpt-4o", "gpt-4o-mini", "claude-3-sonnet", "claude-3-haiku"],
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
    PolicyRule(
        id="pol-005",
        name="Daily cost threshold",
        description="Alert when estimated daily spend exceeds $100 USD.",
        policy_type=PolicyType.COST_THRESHOLD,
        severity=PolicySeverity.CRITICAL,
        threshold=100.0,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
]


class PolicyEngineService:
    """In-memory policy CRUD and compliance evaluation."""

    def __init__(self) -> None:
        # Copy defaults so each instance is independent (useful for tests)
        self._policies: dict[str, PolicyRule] = {
            p.id: p.model_copy() for p in _DEFAULT_POLICIES
        }

    async def list_policies(self) -> list[PolicyRule]:
        return list(self._policies.values())

    async def create_policy(self, request: PolicyCreateRequest) -> PolicyRule:
        policy = PolicyRule(
            id=f"pol-{uuid.uuid4().hex[:8]}",
            name=request.name,
            description=request.description,
            policy_type=request.policy_type,
            severity=request.severity,
            agent_names=request.agent_names,
            cloud_providers=request.cloud_providers,
            threshold=request.threshold,
            allowed_values=request.allowed_values,
            created_at=datetime.now(timezone.utc),
        )
        self._policies[policy.id] = policy
        return policy

    async def update_policy(
        self, policy_id: str, request: PolicyUpdateRequest
    ) -> PolicyRule | None:
        policy = self._policies.get(policy_id)
        if policy is None:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(policy, field, value)
        policy.updated_at = datetime.now(timezone.utc)
        return policy

    async def delete_policy(self, policy_id: str) -> bool:
        return self._policies.pop(policy_id, None) is not None

    async def evaluate_compliance(self, hours: int = 24) -> ComplianceReport:
        """Evaluate all agents against all active policies.

        For the PoC this returns mock compliance data. Phase 2 will
        query real telemetry and evaluate each policy rule.
        """
        now = datetime.now(timezone.utc)
        active_policies = [
            p for p in self._policies.values() if p.status == PolicyStatus.ACTIVE
        ]

        # Mock: all compliant except one warning
        violations = [
            PolicyViolation(
                policy_id="pol-003",
                policy_name="P95 latency threshold",
                policy_type=PolicyType.LATENCY_THRESHOLD,
                severity=PolicySeverity.MEDIUM,
                agent_name="uc2-bedrock-agent",
                cloud_provider="aws",
                violation_value=5800.0,
                threshold_value=5000.0,
                timestamp=now,
                trace_id="b" * 32,
            ),
        ]

        non_compliant = len(violations)
        compliant = len(active_policies) - non_compliant

        return ComplianceReport(
            overall_status=(
                ComplianceStatus.NON_COMPLIANT if non_compliant > 0
                else ComplianceStatus.COMPLIANT
            ),
            total_policies=len(active_policies),
            compliant_count=compliant,
            non_compliant_count=non_compliant,
            violations=violations,
            evaluated_at=now,
        )

    async def list_violations(
        self,
        hours: int = 24,
        agent_name: str | None = None,
        policy_id: str | None = None,
    ) -> list[PolicyViolation]:
        """List violations, optionally filtered."""
        report = await self.evaluate_compliance(hours)
        violations = report.violations

        if agent_name:
            violations = [v for v in violations if v.agent_name == agent_name]
        if policy_id:
            violations = [v for v in violations if v.policy_id == policy_id]

        return violations
