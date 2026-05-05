"""TC-11 — live workflow event stream (SSE)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from governance_api.services import event_bus


@pytest.mark.asyncio
async def test_stream_404_for_unknown_incident(client: AsyncClient):
    async with client.stream("GET", "/api/incidents/inc-missing/events/stream") as r:
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_publish_event_fans_out_to_all_subscribers():
    q1 = event_bus.subscribe("inc-bus")
    q2 = event_bus.subscribe("inc-bus")
    try:
        assert event_bus.subscriber_count("inc-bus") == 2
        event_bus.publish_event("inc-bus", {"event_type": "test.ping"})
        assert (await asyncio.wait_for(q1.get(), timeout=1.0))["event_type"] == "test.ping"
        assert (await asyncio.wait_for(q2.get(), timeout=1.0))["event_type"] == "test.ping"
    finally:
        event_bus.unsubscribe("inc-bus", q1)
        event_bus.unsubscribe("inc-bus", q2)
    assert event_bus.subscriber_count("inc-bus") == 0


@pytest.mark.asyncio
async def test_publish_event_no_subscribers_is_noop():
    event_bus.publish_event("inc-orphan", {"event_type": "x"})


@pytest.mark.asyncio
async def test_publish_event_drops_when_queue_full(caplog):
    iid = "inc-slow"
    q = event_bus.subscribe(iid)
    try:
        for i in range(event_bus._QUEUE_MAX):
            q.put_nowait({"event_type": f"e{i}"})
        with caplog.at_level("WARNING"):
            event_bus.publish_event(iid, {"event_type": "drop-me"})
        assert any("queue full" in r.message.lower() for r in caplog.records)
    finally:
        event_bus.unsubscribe(iid, q)


@pytest.mark.asyncio
async def test_orchestration_publishes_escalation_to_bus(client: AsyncClient):
    iid = (
        await client.post("/api/incidents", json={"title": "TC-11 bus", "severity": "p3"})
    ).json()["incident_id"]

    q = event_bus.subscribe(iid)
    try:
        await client.post(
            f"/api/incidents/{iid}/escalations",
            json={
                "type": "sla_breach",
                "source": "test",
                "agent_name": "knowledge",
                "sla_threshold_seconds": 15.0,
                "elapsed_seconds": 22.0,
                "reason": "http_timeout",
            },
        )
        evt = await asyncio.wait_for(q.get(), timeout=1.0)
        assert evt["event_type"] == "escalation.sla_breach"
        assert evt["incident_id"] == iid
    finally:
        event_bus.unsubscribe(iid, q)


@pytest.mark.asyncio
async def test_stream_emits_open_frame_and_live_event(client: AsyncClient):
    """Drive the SSE generator directly so the test does not depend on the
    httpx ASGITransport flushing chunks (which it batches)."""
    iid = (
        await client.post("/api/incidents", json={"title": "TC-11 sse", "severity": "p3"})
    ).json()["incident_id"]

    from governance_api.routers.incidents import stream_incident_events
    from starlette.responses import StreamingResponse as _SR

    response: _SR = await stream_incident_events(iid)  # type: ignore[arg-type]
    gen = response.body_iterator

    # First yielded frame is the synthetic stream.opened event.
    open_frame = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
    if isinstance(open_frame, bytes):
        open_frame = open_frame.decode()
    assert "event: stream.opened" in open_frame
    assert iid in open_frame

    # Publish a live event and assert the generator surfaces it.
    event_bus.publish_event(iid, {"event_type": "test.kick", "incident_id": iid})
    frames = ""
    for _ in range(2):
        f = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        frames += f.decode() if isinstance(f, bytes) else f
    assert "event: test.kick" in frames
    assert iid in frames

    await gen.aclose()
