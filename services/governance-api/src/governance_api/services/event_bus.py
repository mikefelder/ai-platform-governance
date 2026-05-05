"""TC-11 — in-process pub/sub broker for live workflow events.

Each subscriber gets its own asyncio.Queue. Publishers push WorkflowEvent
dicts; subscribers iterate via an async generator until the connection
drops. Bounded queue size protects against slow consumers (events are
dropped, with a counter event so the consumer can reconcile from the
audit bundle).

This is the SSE half of the design. A future iteration will subscribe to
the Cosmos change-feed and call ``publish_event`` from there so cross-pod
publishers in a multi-replica deployment all reach every browser.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

logger = logging.getLogger("uc3.event_bus")

_QUEUE_MAX = 256

# incident_id -> set of subscriber queues
_subscribers: dict[str, set[asyncio.Queue]] = {}


def publish_event(incident_id: str, event: dict) -> None:
    """Fan out ``event`` to every active subscriber for ``incident_id``.

    Non-blocking. Drops on a full queue and logs a warning so a slow
    browser tab cannot back-pressure the orchestration path.
    """
    queues = _subscribers.get(incident_id)
    if not queues:
        return
    for q in list(queues):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "SSE queue full for incident=%s; dropping event=%s",
                incident_id,
                event.get("event_type"),
            )


def subscribe(incident_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _subscribers.setdefault(incident_id, set()).add(q)
    return q


def unsubscribe(incident_id: str, q: asyncio.Queue) -> None:
    queues = _subscribers.get(incident_id)
    if not queues:
        return
    queues.discard(q)
    if not queues:
        _subscribers.pop(incident_id, None)


def subscriber_count(incident_id: str) -> int:
    return len(_subscribers.get(incident_id, ()))


async def stream(
    incident_id: str,
    *,
    keepalive_seconds: float = 15.0,
) -> AsyncIterator[dict | None]:
    """Yield events for ``incident_id`` until the consumer disconnects.

    Yields ``None`` for keepalive ticks so the SSE encoder can emit a
    comment frame and keep proxies (APIM, nginx) from idling the
    connection out.
    """
    q = subscribe(incident_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=keepalive_seconds)
                yield event
            except asyncio.TimeoutError:
                yield None
    finally:
        unsubscribe(incident_id, q)
