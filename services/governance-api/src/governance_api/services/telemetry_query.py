"""Telemetry query service — reads traces from Log Analytics via KQL.

Uses azure-monitor-query SDK to run KQL queries against the
ALZ Log Analytics Workspace. Falls back to mock data when
LOG_ANALYTICS_WORKSPACE_ID is not set (local dev).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from governance_api.models.telemetry import (
    AgentHealth,
    AgentHealthStatus,
    AgentSpan,
    AgentTrace,
    AgentType,
    CloudProvider,
    SpanStatus,
    TokenUsage,
)


class TelemetryQueryService:
    """Queries Log Analytics for agent telemetry data."""

    def __init__(self) -> None:
        self._workspace_id = os.environ.get("LOG_ANALYTICS_WORKSPACE_ID")
        self._client = None

    def _get_client(self):
        """Lazy-init the LogsQueryClient with managed identity."""
        if self._client is None and self._workspace_id:
            from azure.identity import DefaultAzureCredential
            from azure.monitor.query import LogsQueryClient

            self._client = LogsQueryClient(credential=DefaultAzureCredential())
        return self._client

    async def list_traces(
        self, hours: int = 1, agent_name: str | None = None, limit: int = 50
    ) -> list[AgentTrace]:
        """List recent traces from Log Analytics or return mock data."""
        client = self._get_client()
        if client is None:
            return self._mock_traces(hours, agent_name, limit)

        # TODO: Implement real KQL query in Phase 2
        # query = f"""
        # AppDependencies
        # | where TimeGenerated > ago({hours}h)
        # | where isnotempty(customDimensions.trace_id)
        # | summarize ...
        # """
        return self._mock_traces(hours, agent_name, limit)

    async def get_trace(self, trace_id: str) -> AgentTrace:
        """Get a single trace with all spans."""
        client = self._get_client()
        if client is None:
            return self._mock_single_trace(trace_id)

        # TODO: Implement real KQL query in Phase 2
        return self._mock_single_trace(trace_id)

    async def get_agent_health(self, hours: int = 1) -> list[AgentHealth]:
        """Get health status for all known agents."""
        client = self._get_client()
        if client is None:
            return self._mock_agent_health()

        # TODO: Implement real KQL query in Phase 2
        return self._mock_agent_health()

    # --- Mock data for local development ---

    def _mock_traces(
        self, hours: int, agent_name: str | None, limit: int
    ) -> list[AgentTrace]:
        now = datetime.now(timezone.utc)
        traces = [
            AgentTrace(
                trace_id="a" * 32,
                root_agent="uc1-rag-agent",
                total_duration_ms=1250.0,
                total_tokens=3500,
                span_count=3,
                has_errors=False,
            ),
            AgentTrace(
                trace_id="b" * 32,
                root_agent="uc2-supervisor",
                total_duration_ms=4800.0,
                total_tokens=12000,
                span_count=7,
                has_errors=False,
            ),
            AgentTrace(
                trace_id="c" * 32,
                root_agent="uc4-incident-agent",
                total_duration_ms=2100.0,
                total_tokens=5200,
                span_count=4,
                has_errors=True,
            ),
        ]
        if agent_name:
            traces = [t for t in traces if t.root_agent == agent_name]
        return traces[:limit]

    def _mock_single_trace(self, trace_id: str) -> AgentTrace:
        now = datetime.now(timezone.utc)
        return AgentTrace(
            trace_id=trace_id,
            root_agent="uc1-rag-agent",
            total_duration_ms=1250.0,
            total_tokens=3500,
            span_count=2,
            has_errors=False,
            spans=[
                AgentSpan(
                    trace_id=trace_id,
                    span_id="1" * 16,
                    timestamp=now - timedelta(seconds=2),
                    duration_ms=800.0,
                    status=SpanStatus.OK,
                    agent_name="uc1-rag-agent",
                    agent_type=AgentType.RAG,
                    cloud_provider=CloudProvider.AZURE,
                    gen_ai_system="openai",
                    gen_ai_model="gpt-4o",
                    token_usage=TokenUsage(
                        prompt_tokens=1500, completion_tokens=500, total_tokens=2000
                    ),
                ),
                AgentSpan(
                    trace_id=trace_id,
                    span_id="2" * 16,
                    parent_span_id="1" * 16,
                    timestamp=now - timedelta(seconds=1),
                    duration_ms=450.0,
                    status=SpanStatus.OK,
                    agent_name="uc1-rag-agent",
                    agent_type=AgentType.RAG,
                    cloud_provider=CloudProvider.AZURE,
                    gen_ai_system="openai",
                    gen_ai_model="gpt-4o-mini",
                    token_usage=TokenUsage(
                        prompt_tokens=1000, completion_tokens=500, total_tokens=1500
                    ),
                ),
            ],
        )

    def _mock_agent_health(self) -> list[AgentHealth]:
        now = datetime.now(timezone.utc)
        return [
            AgentHealth(
                agent_name="uc1-rag-agent",
                agent_type=AgentType.RAG,
                cloud_provider=CloudProvider.AZURE,
                status=AgentHealthStatus.HEALTHY,
                error_rate_pct=1.2,
                p50_latency_ms=350.0,
                p95_latency_ms=1200.0,
                request_count=150,
                last_seen=now - timedelta(minutes=2),
            ),
            AgentHealth(
                agent_name="uc2-supervisor",
                agent_type=AgentType.SUPERVISOR,
                cloud_provider=CloudProvider.AZURE,
                status=AgentHealthStatus.HEALTHY,
                error_rate_pct=0.5,
                p50_latency_ms=800.0,
                p95_latency_ms=3200.0,
                request_count=85,
                last_seen=now - timedelta(minutes=1),
            ),
            AgentHealth(
                agent_name="uc2-bedrock-agent",
                agent_type=AgentType.LLM,
                cloud_provider=CloudProvider.AWS,
                status=AgentHealthStatus.DEGRADED,
                error_rate_pct=8.5,
                p50_latency_ms=1200.0,
                p95_latency_ms=5800.0,
                request_count=42,
                last_seen=now - timedelta(minutes=5),
            ),
            AgentHealth(
                agent_name="uc4-incident-agent",
                agent_type=AgentType.INCIDENT,
                cloud_provider=CloudProvider.AZURE,
                status=AgentHealthStatus.HEALTHY,
                error_rate_pct=2.0,
                p50_latency_ms=500.0,
                p95_latency_ms=1800.0,
                request_count=30,
                last_seen=now - timedelta(minutes=3),
            ),
        ]
