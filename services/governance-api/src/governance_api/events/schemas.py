"""Inbound event envelope schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InboundEvent(BaseModel):
    """Generic event envelope — normalises Event Grid and custom sources."""

    event_id: str = Field(..., alias="id")
    event_type: str = Field(..., alias="type")
    source: str = Field("unknown", alias="source")
    time: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
