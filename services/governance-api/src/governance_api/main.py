"""FastAPI application entry point for the Governance API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from governance_api.routers import (
    agents,
    approvals,
    compliance,
    costs,
    events,
    health,
    incidents,
    policies,
    workflows,
)
from governance_api.telemetry import init_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_telemetry()
    yield


app = FastAPI(
    title="AI Governance & Incident Resolution Hub",
    description=(
        "Centralised observability, cost management, policy enforcement, and "
        "AI-driven incident management with human-in-the-loop approvals."
    ),
    version="0.2.1",
    lifespan=lifespan,
)

# Governance routers
app.include_router(health.router)
app.include_router(costs.router, prefix="/api/costs", tags=["costs"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(policies.router, prefix="/api/policies", tags=["policies"])
app.include_router(compliance.router, prefix="/api/compliance", tags=["compliance"])

# Incident orchestration routers (formerly UC4)
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
