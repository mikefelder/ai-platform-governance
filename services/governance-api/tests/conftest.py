"""Shared test fixtures."""

from __future__ import annotations

import os

# Disable Entra JWT validation for the test suite — routers receive a
# synthetic local-dev identity instead. See governance_api.auth.
os.environ.setdefault("AUTH_MODE", "disabled")

import pytest
from httpx import ASGITransport, AsyncClient

from governance_api.main import app


@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
