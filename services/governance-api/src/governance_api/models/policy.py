"""Policy and compliance models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PolicySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DRAFT = "draft"


class PolicyType(str, Enum):
    TOKEN_LIMIT = "token_limit"
    RATE_LIMIT = "rate_limit"
    LATENCY_THRESHOLD = "latency_threshold"
    ERROR_RATE_THRESHOLD = "error_rate_threshold"
    CONTENT_SAFETY = "content_safety"
    COST_THRESHOLD = "cost_threshold"
    ALLOWED_MODELS = "allowed_models"


class PolicyRule(BaseModel):
    """A single governance policy rule."""

    id: str = Field(..., description="Unique policy ID.")
    name: str
    description: str | None = None
    policy_type: PolicyType
    severity: PolicySeverity = PolicySeverity.MEDIUM
    status: PolicyStatus = PolicyStatus.ACTIVE

    # Scope — which agents / providers this applies to
    agent_names: list[str] = Field(default_factory=list, description="Agent names (empty = all).")
    cloud_providers: list[str] = Field(default_factory=list, description="Provider filter (empty = all).")

    # Threshold configuration
    threshold: float | None = Field(None, description="Numeric threshold for the policy.")
    allowed_values: list[str] = Field(default_factory=list, description="Allowed values (e.g. model names).")

    created_at: datetime | None = None
    updated_at: datetime | None = None


class PolicyCreateRequest(BaseModel):
    """Request to create a new policy rule."""

    name: str
    description: str | None = None
    policy_type: PolicyType
    severity: PolicySeverity = PolicySeverity.MEDIUM
    agent_names: list[str] = Field(default_factory=list)
    cloud_providers: list[str] = Field(default_factory=list)
    threshold: float | None = None
    allowed_values: list[str] = Field(default_factory=list)


class PolicyUpdateRequest(BaseModel):
    """Request to update an existing policy rule."""

    name: str | None = None
    description: str | None = None
    severity: PolicySeverity | None = None
    status: PolicyStatus | None = None
    threshold: float | None = None
    allowed_values: list[str] | None = None


class ComplianceStatus(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    WARNING = "warning"
    UNKNOWN = "unknown"


class PolicyViolation(BaseModel):
    """A single policy violation event."""

    policy_id: str
    policy_name: str
    policy_type: PolicyType
    severity: PolicySeverity
    agent_name: str
    cloud_provider: str
    violation_value: float | str | None = Field(None, description="The actual value that violated the policy.")
    threshold_value: float | str | None = Field(None, description="The threshold that was breached.")
    timestamp: datetime
    trace_id: str | None = None


class ComplianceReport(BaseModel):
    """Overall compliance report across all policies."""

    overall_status: ComplianceStatus = ComplianceStatus.UNKNOWN
    total_policies: int = 0
    compliant_count: int = 0
    non_compliant_count: int = 0
    warning_count: int = 0
    violations: list[PolicyViolation] = Field(default_factory=list)
    evaluated_at: datetime
