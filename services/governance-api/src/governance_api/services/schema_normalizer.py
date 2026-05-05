"""Schema normalizer — transforms provider-specific telemetry
into the canonical AgentSpan / AgentTrace models.

This service will be used in Phase 2 when real KQL query results
need to be mapped from AppInsights/AppDependencies table rows
into the canonical Pydantic models.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from governance_api.models.telemetry import (
    AgentSpan,
    AgentType,
    CloudProvider,
    SpanStatus,
    TokenUsage,
)


class SchemaNormalizer:
    """Normalises raw telemetry rows into canonical models."""

    # Map known service names → agent type
    _AGENT_TYPE_MAP: dict[str, AgentType] = {
        "rag-agent": AgentType.RAG,
        "supervisor-agent": AgentType.SUPERVISOR,
        "bedrock-gateway": AgentType.LLM,
        "incident-agent": AgentType.INCIDENT,
        "governance-api": AgentType.GOVERNANCE,
    }

    # Map known service names → cloud provider
    _PROVIDER_MAP: dict[str, CloudProvider] = {
        "rag-agent": CloudProvider.AZURE,
        "supervisor-agent": CloudProvider.AZURE,
        "bedrock-gateway": CloudProvider.AWS,
        "incident-agent": CloudProvider.AZURE,
        "uc3-governance-api": CloudProvider.AZURE,
    }

    def normalize_row(self, row: dict[str, Any]) -> AgentSpan:
        """Convert a Log Analytics query row to an AgentSpan.

        Expected columns: TraceId, SpanId, ParentId, TimeGenerated,
        DurationMs, StatusCode, Name, Properties (JSON).
        """
        props = row.get("Properties", {})
        if isinstance(props, str):
            import json

            props = json.loads(props)

        agent_name = props.get("service.name", row.get("Name", "unknown"))
        prompt_tokens = int(props.get("gen_ai.usage.prompt_tokens", 0))
        completion_tokens = int(props.get("gen_ai.usage.completion_tokens", 0))

        token_usage = None
        if prompt_tokens or completion_tokens:
            token_usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )

        status_code = row.get("StatusCode", "UNSET")
        status = SpanStatus.ERROR if status_code == "ERROR" else SpanStatus.OK

        return AgentSpan(
            trace_id=row.get("TraceId", ""),
            span_id=row.get("SpanId", ""),
            parent_span_id=row.get("ParentId") or None,
            timestamp=row.get("TimeGenerated", datetime.now(timezone.utc)),
            duration_ms=float(row.get("DurationMs", 0)),
            status=status,
            agent_name=agent_name,
            agent_type=self._AGENT_TYPE_MAP.get(agent_name, AgentType.LLM),
            cloud_provider=self._PROVIDER_MAP.get(agent_name, CloudProvider.AZURE),
            gen_ai_system=props.get("gen_ai.system"),
            gen_ai_model=props.get("gen_ai.request.model"),
            token_usage=token_usage,
            error_type=props.get("error.type"),
            error_message=props.get("error.message"),
        )
