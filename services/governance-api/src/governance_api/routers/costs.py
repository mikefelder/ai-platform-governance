"""Cost management router — aggregates AI spend across agents and providers."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from governance_api.models.cost import CostGranularity, CostSummary, CostTrend
from governance_api.services.cost_aggregator import CostAggregatorService

router = APIRouter()
_service = CostAggregatorService()


@router.get("/summary", response_model=CostSummary)
async def cost_summary(
    hours: int = Query(24, ge=1, le=720, description="Lookback window in hours."),
):
    """Return aggregated cost summary across all agents for the given period."""
    return await _service.get_summary(hours=hours)


@router.get("/by-agent", response_model=list[CostSummary])
async def cost_by_agent(
    hours: int = Query(24, ge=1, le=720),
):
    """Return cost breakdown per agent."""
    return await _service.get_by_agent(hours=hours)


@router.get("/trends", response_model=CostTrend)
async def cost_trends(
    granularity: CostGranularity = Query(CostGranularity.HOURLY),
    hours: int = Query(24, ge=1, le=720),
    agent_name: str | None = Query(None, description="Filter to a specific agent."),
):
    """Return cost trend data for charting."""
    return await _service.get_trends(
        granularity=granularity, hours=hours, agent_name=agent_name
    )
