"""Canonical telemetry schema — Pydantic models.

These models define the normalised telemetry schema that the Governance Hub
uses to unify observability data from Azure, AWS, and OCI providers.

Based on OpenTelemetry Semantic Conventions for GenAI:
https://opentelemetry.io/docs/specs/semconv/gen-ai/
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CloudProvider(str, Enum):
    AZURE = "azure"
    AWS = "aws"
    OCI = "oci"


class AgentType(str, Enum):
    RAG = "rag"
    SUPERVISOR = "supervisor"
    LLM = "llm"
    TOOL = "tool"
    INCIDENT = "incident"
    GOVERNANCE = "governance"


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


class TokenUsage(BaseModel):
    """Token usage for a single LLM invocation."""

    prompt_tokens: int = Field(0, description="Number of tokens in the prompt.")
    completion_tokens: int = Field(0, description="Number of tokens in the completion.")
    total_tokens: int = Field(0, description="Total tokens (prompt + completion).")


class AgentSpan(BaseModel):
    """Canonical representation of a single agent execution span.

    Maps to OpenTelemetry span with GenAI semantic conventions.
    """

    trace_id: str = Field(..., description="W3C trace ID (32 hex chars).")
    span_id: str = Field(..., description="Span ID (16 hex chars).")
    parent_span_id: str | None = Field(None, description="Parent span ID if nested.")
    timestamp: datetime = Field(..., description="Span start time (UTC).")
    duration_ms: float = Field(..., description="Span duration in milliseconds.")
    status: SpanStatus = Field(SpanStatus.UNSET)

    # Agent identity
    agent_name: str = Field(..., description="Agent service name (e.g. uc1-rag-agent).")
    agent_type: AgentType = Field(..., description="Agent type classification.")

    # Cloud / provider context
    cloud_provider: CloudProvider = Field(..., description="Cloud provider hosting this agent.")
    cloud_region: str | None = Field(None, description="Cloud region (e.g. australiaeast, us-east-1).")

    # GenAI attributes (optional — only set for LLM invocations)
    gen_ai_system: str | None = Field(None, description="AI system (openai, anthropic, etc).")
    gen_ai_model: str | None = Field(None, description="Model ID (e.g. gpt-4o, claude-3-sonnet).")
    token_usage: TokenUsage | None = Field(None, description="Token usage for LLM calls.")

    # Error details
    error_type: str | None = Field(None, description="Error type if status is ERROR.")
    error_message: str | None = Field(None, description="Error message if status is ERROR.")

    # Arbitrary attributes
    attributes: dict[str, Any] = Field(default_factory=dict, description="Additional span attributes.")


class AgentTrace(BaseModel):
    """A complete trace — a collection of related spans forming one workflow execution."""

    trace_id: str = Field(..., description="W3C trace ID shared by all spans.")
    root_agent: str = Field(..., description="Agent that initiated the trace.")
    spans: list[AgentSpan] = Field(default_factory=list)
    total_duration_ms: float = Field(0, description="End-to-end duration of the entire trace.")
    total_tokens: int = Field(0, description="Sum of all token usage across spans.")
    span_count: int = Field(0, description="Number of spans in this trace.")
    has_errors: bool = Field(False, description="Whether any span in the trace has an error.")


class AgentHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AgentHealth(BaseModel):
    """Health status for a single agent."""

    agent_name: str
    agent_type: AgentType
    cloud_provider: CloudProvider
    status: AgentHealthStatus = AgentHealthStatus.UNKNOWN
    error_rate_pct: float = Field(0.0, description="Error rate over the evaluation window.")
    p50_latency_ms: float = Field(0.0, description="P50 latency in ms.")
    p95_latency_ms: float = Field(0.0, description="P95 latency in ms.")
    request_count: int = Field(0, description="Request count over the evaluation window.")
    last_seen: datetime | None = Field(None, description="Last time this agent reported telemetry.")
