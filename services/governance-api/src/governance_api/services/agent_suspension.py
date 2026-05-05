"""TC-10 — agent suspension state machine.

Demo-grade in-process registry that tracks per-agent suspension state and
records audit events. Triggered by an external webhook (typically a Sentinel
analytics rule or a security operator) when an agent must be quarantined.

Persistence is intentionally omitted — UC3 keeps its working set in memory
for the demo. The contract (event schema + API) is stable so that swapping
the backing store for Cosmos later is a drop-in change.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger("uc3.agent_suspension")

SuspensionStatus = Literal["active", "suspended"]


@dataclass
class AgentSuspensionState:
    agent_name: str
    status: SuspensionStatus = "active"
    reason: str | None = None
    requested_by: str | None = None
    source: str | None = None
    correlation_id: str | None = None
    suspended_at: datetime | None = None
    resumed_at: datetime | None = None
    history: list[dict] = field(default_factory=list)


_STATES: dict[str, AgentSuspensionState] = {}
_LOCK = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_state(agent_name: str) -> AgentSuspensionState:
    async with _LOCK:
        return _STATES.get(agent_name) or AgentSuspensionState(agent_name=agent_name)


async def list_states() -> list[AgentSuspensionState]:
    async with _LOCK:
        return list(_STATES.values())


async def suspend(
    agent_name: str,
    *,
    reason: str,
    requested_by: str | None,
    source: str | None,
    correlation_id: str | None = None,
) -> tuple[AgentSuspensionState, dict]:
    """Mark ``agent_name`` as suspended; return state + audit event."""
    cid = correlation_id or uuid.uuid4().hex
    ts = _now()
    async with _LOCK:
        state = _STATES.setdefault(agent_name, AgentSuspensionState(agent_name=agent_name))
        previous = state.status
        state.status = "suspended"
        state.reason = reason
        state.requested_by = requested_by
        state.source = source
        state.correlation_id = cid
        state.suspended_at = ts
        state.resumed_at = None
        event = {
            "event_id": uuid.uuid4().hex,
            "event_type": "agent.suspended",
            "agent_name": agent_name,
            "previous_status": previous,
            "new_status": "suspended",
            "reason": reason,
            "requested_by": requested_by,
            "source": source,
            "correlation_id": cid,
            "timestamp": ts.isoformat(),
        }
        state.history.append(event)
    logger.warning(
        "agent suspended",
        extra={
            "agent_name": agent_name,
            "reason": reason,
            "source": source,
            "correlation_id": cid,
        },
    )
    return state, event


async def resume(
    agent_name: str,
    *,
    requested_by: str | None,
    note: str | None = None,
) -> tuple[AgentSuspensionState, dict]:
    cid = uuid.uuid4().hex
    ts = _now()
    async with _LOCK:
        state = _STATES.setdefault(agent_name, AgentSuspensionState(agent_name=agent_name))
        previous = state.status
        state.status = "active"
        state.resumed_at = ts
        event = {
            "event_id": uuid.uuid4().hex,
            "event_type": "agent.resumed",
            "agent_name": agent_name,
            "previous_status": previous,
            "new_status": "active",
            "requested_by": requested_by,
            "note": note,
            "correlation_id": cid,
            "timestamp": ts.isoformat(),
        }
        state.history.append(event)
    logger.info(
        "agent resumed",
        extra={"agent_name": agent_name, "requested_by": requested_by, "correlation_id": cid},
    )
    return state, event


def reset() -> None:
    """Test helper — clear all suspension state."""
    _STATES.clear()
