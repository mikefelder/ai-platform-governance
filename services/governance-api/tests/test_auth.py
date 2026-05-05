"""Auth / caller-identity tests (TC-1 + TC-9)."""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient

from governance_api.auth import (
    DEV_IDENTITY_OID,
    DEV_IDENTITY_UPN,
    _extract_bearer,
    get_caller_identity,
)


def test_extract_bearer_valid():
    assert _extract_bearer("Bearer abc.def.ghi") == "abc.def.ghi"
    assert _extract_bearer("bearer abc.def.ghi") == "abc.def.ghi"


def test_extract_bearer_invalid():
    assert _extract_bearer(None) is None
    assert _extract_bearer("") is None
    assert _extract_bearer("Basic xyz") is None
    assert _extract_bearer("Bearer ") is None


@pytest.mark.asyncio
async def test_disabled_mode_returns_dev_identity(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "disabled")
    identity = await get_caller_identity(authorization=None)
    assert identity.oid == DEV_IDENTITY_OID
    assert identity.upn == DEV_IDENTITY_UPN
    assert identity.auth_mode == "dev"


@pytest.mark.asyncio
async def test_required_mode_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await get_caller_identity(authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_create_incident_captures_reported_by(client: AsyncClient):
    """TC-1: incident records the caller identity at creation."""
    response = await client.post(
        "/api/incidents",
        json={"title": "Identity capture test", "severity": "p3"},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["reported_by"] is not None
    assert data["reported_by"]["upn"] == DEV_IDENTITY_UPN
    assert data["reported_by"]["oid"] == DEV_IDENTITY_OID
    assert data["reported_by"]["auth_mode"] == "dev"


@pytest.mark.asyncio
async def test_workflow_history_includes_identity(client: AsyncClient):
    """TC-1: the seed audit event records who reported the incident."""
    create = await client.post(
        "/api/incidents", json={"title": "Audit identity test"}
    )
    incident_id = create.json()["incident_id"]

    history = await client.get(f"/api/workflows/{incident_id}/history")
    assert history.status_code == 200
    events = history.json()
    created_event = next(
        (e for e in events if e["event_type"] == "incident.created"), None
    )
    assert created_event is not None
    assert created_event["actor"] == DEV_IDENTITY_UPN
    assert created_event["payload"]["reported_by"]["oid"] == DEV_IDENTITY_OID
