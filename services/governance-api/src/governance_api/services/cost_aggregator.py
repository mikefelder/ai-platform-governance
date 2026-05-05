"""Cost aggregation service — computes AI spend from telemetry data.

Queries token usage from Log Analytics and applies pricing models
to estimate costs. Falls back to mock data when running locally.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from governance_api.models.cost import (
    AgentCost,
    CostGranularity,
    CostSummary,
    CostTrend,
    CostTrendPoint,
)
from governance_api.models.telemetry import CloudProvider

# Approximate token pricing (USD per 1K tokens) — used for estimation
_PRICING = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
}


class CostAggregatorService:
    """Aggregates AI cost data from telemetry."""

    def __init__(self) -> None:
        self._workspace_id = os.environ.get("LOG_ANALYTICS_WORKSPACE_ID")

    async def get_summary(self, hours: int = 24) -> CostSummary:
        """Get aggregated cost summary."""
        if not self._workspace_id or self._workspace_id == "mock-workspace-id":
            return self._mock_summary(hours)

        # TODO: Implement real KQL query in Phase 2
        return self._mock_summary(hours)

    async def get_by_agent(self, hours: int = 24) -> list[CostSummary]:
        """Get cost breakdown per agent."""
        summary = await self.get_summary(hours)
        # In mock mode, wrap the single summary; real impl will group by agent
        return [summary]

    async def get_trends(
        self,
        granularity: CostGranularity = CostGranularity.HOURLY,
        hours: int = 24,
        agent_name: str | None = None,
    ) -> CostTrend:
        """Get cost trend data."""
        if not self._workspace_id or self._workspace_id == "mock-workspace-id":
            return self._mock_trends(granularity, hours, agent_name)

        # TODO: Implement real KQL query in Phase 2
        return self._mock_trends(granularity, hours, agent_name)

    # --- Mock data ---

    def _mock_summary(self, hours: int) -> CostSummary:
        now = datetime.now(timezone.utc)
        return CostSummary(
            total_estimated_cost_usd=42.50,
            total_tokens=850000,
            total_requests=320,
            by_agent=[
                AgentCost(
                    agent_name="uc1-rag-agent",
                    cloud_provider=CloudProvider.AZURE,
                    model="gpt-4o",
                    total_tokens=400000,
                    estimated_cost_usd=18.00,
                    request_count=150,
                    period_start=now - timedelta(hours=hours),
                    period_end=now,
                ),
                AgentCost(
                    agent_name="uc2-supervisor",
                    cloud_provider=CloudProvider.AZURE,
                    model="gpt-4o-mini",
                    total_tokens=200000,
                    estimated_cost_usd=4.50,
                    request_count=85,
                    period_start=now - timedelta(hours=hours),
                    period_end=now,
                ),
                AgentCost(
                    agent_name="uc2-bedrock-agent",
                    cloud_provider=CloudProvider.AWS,
                    model="claude-3-sonnet",
                    total_tokens=200000,
                    estimated_cost_usd=18.00,
                    request_count=55,
                    period_start=now - timedelta(hours=hours),
                    period_end=now,
                ),
                AgentCost(
                    agent_name="uc4-incident-agent",
                    cloud_provider=CloudProvider.AZURE,
                    model="gpt-4o",
                    total_tokens=50000,
                    estimated_cost_usd=2.00,
                    request_count=30,
                    period_start=now - timedelta(hours=hours),
                    period_end=now,
                ),
            ],
            by_provider={"azure": 24.50, "aws": 18.00},
            by_model={"gpt-4o": 20.00, "gpt-4o-mini": 4.50, "claude-3-sonnet": 18.00},
            period_start=now - timedelta(hours=hours),
            period_end=now,
        )

    def _mock_trends(
        self,
        granularity: CostGranularity,
        hours: int,
        agent_name: str | None,
    ) -> CostTrend:
        now = datetime.now(timezone.utc)
        interval = {
            CostGranularity.HOURLY: timedelta(hours=1),
            CostGranularity.DAILY: timedelta(days=1),
            CostGranularity.WEEKLY: timedelta(weeks=1),
            CostGranularity.MONTHLY: timedelta(days=30),
        }[granularity]

        points = []
        current = now - timedelta(hours=hours)
        while current < now:
            points.append(
                CostTrendPoint(
                    timestamp=current,
                    cost_usd=round(1.5 + (hash(str(current)) % 30) / 10, 2),
                    tokens=35000 + (hash(str(current)) % 20000),
                    request_count=10 + (hash(str(current)) % 20),
                )
            )
            current += interval

        return CostTrend(
            agent_name=agent_name,
            granularity=granularity,
            data_points=points,
        )
