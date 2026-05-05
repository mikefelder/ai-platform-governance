"""Event ingestion endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_event_grid_validation(client: AsyncClient):
    """Verify the Event Grid subscription validation handshake."""
    response = await client.post(
        "/api/events/ingest",
        json=[
            {
                "id": "val-001",
                "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
                "data": {"validationCode": "abc123"},
            }
        ],
    )
    assert response.status_code == 200
    assert response.json()["validationResponse"] == "abc123"


@pytest.mark.asyncio
async def test_ingest_custom_event(client: AsyncClient):
    response = await client.post(
        "/api/events/ingest",
        json={
            "id": "evt-001",
            "type": "monitoring.alert.fired",
            "source": "azure-monitor",
            "data": {"title": "High CPU on vm-prod-01", "severity": "p2"},
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
