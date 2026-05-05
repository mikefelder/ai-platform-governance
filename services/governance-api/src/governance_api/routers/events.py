"""Event ingestion router — receives webhooks from Event Grid and monitoring tools."""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from governance_api.events.schemas import InboundEvent
from governance_api.services.orchestration_service import OrchestrationService

router = APIRouter()
_service = OrchestrationService()


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(request: Request):
    """Accept an inbound event (Event Grid CloudEvent or custom envelope).

    Responds 200 to Event Grid validation handshake automatically.
    """
    body = await request.json()

    # Handle Event Grid subscription validation challenge
    if isinstance(body, list) and body and body[0].get("eventType") == "Microsoft.EventGrid.SubscriptionValidationEvent":
        return JSONResponse({"validationResponse": body[0]["data"]["validationCode"]})

    event = InboundEvent.model_validate(body if isinstance(body, dict) else body[0])
    await _service.handle_inbound_event(event)
    return {"status": "accepted"}
