"""Cost tracking models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from governance_api.models.telemetry import CloudProvider


class CostGranularity(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class AgentCost(BaseModel):
    """Cost breakdown for a single agent over a time period."""

    agent_name: str
    cloud_provider: CloudProvider
    model: str | None = None
    total_tokens: int = 0
    estimated_cost_usd: float = Field(0.0, description="Estimated cost in USD based on token pricing.")
    request_count: int = 0
    period_start: datetime
    period_end: datetime


class CostSummary(BaseModel):
    """Aggregated cost summary across all agents."""

    total_estimated_cost_usd: float = 0.0
    total_tokens: int = 0
    total_requests: int = 0
    by_agent: list[AgentCost] = Field(default_factory=list)
    by_provider: dict[str, float] = Field(default_factory=dict, description="Cost by cloud provider.")
    by_model: dict[str, float] = Field(default_factory=dict, description="Cost by model.")
    period_start: datetime
    period_end: datetime


class CostTrendPoint(BaseModel):
    """A single data point in a cost trend series."""

    timestamp: datetime
    cost_usd: float
    tokens: int
    request_count: int


class CostTrend(BaseModel):
    """Cost trend over time for a given granularity."""

    agent_name: str | None = Field(None, description="Agent name, or None for aggregate.")
    granularity: CostGranularity
    data_points: list[CostTrendPoint] = Field(default_factory=list)
