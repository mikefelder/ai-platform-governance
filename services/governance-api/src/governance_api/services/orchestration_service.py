"""Orchestration service — coordinates the full incident workflow.

Supports two storage backends:
  - Cosmos DB: when COSMOS_ENDPOINT is configured (production)
  - In-memory: fallback for local development and testing
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from governance_api.auth import CallerIdentity
from governance_api.events.schemas import InboundEvent
from governance_api.models.incident import (
    Incident,
    IncidentCreateRequest,
    IncidentSeverity,
    IncidentCategory,
    IncidentSource,
    IncidentStatus,
)
from governance_api.models.workflow import WorkflowState, WorkflowEvent
from governance_api.services.event_bus import publish_event
from governance_api.services.policy_registry import get_policy_registry

logger = logging.getLogger("uc3.orchestration")

# In-memory stores (fallback when Cosmos DB is not configured)
_incidents: dict[str, Incident] = {}
_workflow_states: dict[str, WorkflowState] = {}
_workflow_events: dict[str, list[WorkflowEvent]] = {}


def _record_event(incident_id: str, event: WorkflowEvent) -> WorkflowEvent:
    """Persist ``event`` to the in-memory log and fan out to SSE subscribers (TC-11)."""
    _workflow_events.setdefault(incident_id, []).append(event)
    publish_event(incident_id, event.model_dump(mode="json"))
    return event

# Cosmos DB client (lazy-initialized)
_cosmos_container = None
_cosmos_enabled = False


def _get_cosmos_container():
    """Lazy-init Cosmos DB container for incident persistence."""
    global _cosmos_container, _cosmos_enabled
    if _cosmos_container is not None:
        return _cosmos_container

    endpoint = os.environ.get("COSMOS_ENDPOINT", "")
    database = os.environ.get("COSMOS_DATABASE", "incidents")
    if not endpoint:
        _cosmos_enabled = False
        return None

    try:
        from azure.cosmos import CosmosClient
        from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        credential = ManagedIdentityCredential(client_id=client_id) if client_id else DefaultAzureCredential()
        client = CosmosClient(endpoint, credential=credential)
        db = client.get_database_client(database)
        _cosmos_container = db.get_container_client("incidents")
        _cosmos_enabled = True
        logger.info("Cosmos DB persistence enabled: %s/%s", endpoint, database)
        return _cosmos_container
    except Exception as e:
        logger.warning("Cosmos DB init failed, using in-memory: %s", e)
        _cosmos_enabled = False
        return None


class OrchestrationService:
    """Coordinates the incident orchestration workflow."""

    async def create_incident(
        self,
        request: IncidentCreateRequest,
        caller: CallerIdentity | None = None,
    ) -> Incident:
        """Create a new incident and kick off the workflow."""
        now = datetime.now(timezone.utc)
        reported_by = caller.audit_dict() if caller is not None else None

        # TC-2: resolve the active enterprise policy version for this severity
        # and embed an immutable snapshot on the incident BEFORE workflow
        # transitions so every downstream actor sees the same rules.
        registry = get_policy_registry()
        policy_applied = registry.resolve_for_incident(request.severity)
        attributes = dict(request.attributes)
        if policy_applied is not None:
            attributes["policy_applied"] = policy_applied.model_dump(mode="json")

        incident = Incident(
            incident_id=f"inc-{uuid.uuid4().hex[:12]}",
            title=request.title,
            description=request.description,
            severity=request.severity,
            category=request.category,
            status=IncidentStatus.RECEIVED,
            source=request.source,
            created_at=now,
            updated_at=now,
            tags=request.tags,
            attributes=attributes,
            reported_by=reported_by,
        )
        _incidents[incident.incident_id] = incident

        # Persist to Cosmos DB if available
        container = _get_cosmos_container()
        if container:
            try:
                doc = incident.model_dump(mode="json")
                doc["id"] = incident.incident_id
                doc["partitionKey"] = incident.incident_id
                container.upsert_item(doc)
            except Exception as e:
                logger.warning("Cosmos write failed (in-memory fallback): %s", e)

        # Initialise workflow state
        state = WorkflowState(
            incident_id=incident.incident_id,
            current_status=IncidentStatus.RECEIVED,
            transition_at=now,
        )
        _workflow_states[incident.incident_id] = state
        actor_label = caller.upn if caller is not None else "system"
        events: list[WorkflowEvent] = [
            WorkflowEvent(
                event_id=uuid.uuid4().hex,
                incident_id=incident.incident_id,
                event_type="incident.created",
                to_status=IncidentStatus.RECEIVED,
                actor=actor_label,
                timestamp=now,
                payload={
                    "source": request.source,
                    "reported_by": reported_by,
                },
            )
        ]
        if policy_applied is not None:
            # TC-2: full policy snapshot in workflow history for audit replay.
            active_version = registry.get_active_version(policy_applied.policy_id)
            events.append(
                WorkflowEvent(
                    event_id=uuid.uuid4().hex,
                    incident_id=incident.incident_id,
                    event_type="policy.applied",
                    to_status=IncidentStatus.RECEIVED,
                    actor="policy-registry",
                    timestamp=now,
                    payload={
                        "policy_applied": policy_applied.model_dump(mode="json"),
                        "policy_version": (
                            active_version.model_dump(mode="json")
                            if active_version is not None
                            else None
                        ),
                    },
                )
            )
        _workflow_events[incident.incident_id] = events
        # TC-11: fan out the initial events to any SSE subscribers attached
        # via reservation (rare on create — most subscribers attach after).
        for evt in events:
            publish_event(incident.incident_id, evt.model_dump(mode="json"))

        # In Phase 2: publish to Service Bus → trigger triage agent
        # For now, advance to TRIAGING immediately in mock mode
        await self._advance_to_triaging(incident)

        return _incidents[incident.incident_id]

    async def list_incidents(
        self,
        status: IncidentStatus | None = None,
        limit: int = 50,
    ) -> list[Incident]:
        incidents = list(_incidents.values())
        if status:
            incidents = [i for i in incidents if i.status == status]
        return incidents[:limit]

    async def get_incident(self, incident_id: str) -> Incident | None:
        # Try in-memory first
        if incident_id in _incidents:
            return _incidents[incident_id]
        # Try Cosmos DB
        container = _get_cosmos_container()
        if container:
            try:
                doc = container.read_item(item=incident_id, partition_key=incident_id)
                incident = Incident(**{k: v for k, v in doc.items() if k not in ("id", "partitionKey", "_rid", "_self", "_etag", "_attachments", "_ts")})
                _incidents[incident_id] = incident  # cache locally
                return incident
            except Exception:
                pass
        return None

    async def get_workflow_state(self, incident_id: str) -> WorkflowState | None:
        return _workflow_states.get(incident_id)

    async def get_workflow_history(self, incident_id: str) -> list[dict]:
        events = _workflow_events.get(incident_id, [])
        return [e.model_dump() for e in events]

    async def record_escalation(
        self,
        incident_id: str,
        *,
        escalation_type: str,
        source: str,
        payload: dict,
    ) -> Incident | None:
        """TC-5 — record an escalation event against an existing incident.

        Appends a ``escalation.<type>`` WorkflowEvent (actor=source) and, unless the
        incident is already in a terminal state, transitions status to ESCALATED.
        Returns the updated incident, or None if the incident does not exist.
        """
        incident = _incidents.get(incident_id)
        if incident is None:
            return None

        now = datetime.now(timezone.utc)
        previous_status = incident.status
        terminal = {IncidentStatus.RESOLVED, IncidentStatus.CLOSED}
        new_status = previous_status if previous_status in terminal else IncidentStatus.ESCALATED

        if new_status != previous_status:
            incident.status = new_status
            incident.updated_at = now

        _record_event(
            incident_id,
            WorkflowEvent(
                event_id=uuid.uuid4().hex,
                incident_id=incident_id,
                event_type=f"escalation.{escalation_type}",
                from_status=previous_status,
                to_status=new_status,
                actor=source,
                timestamp=now,
                payload=payload,
            ),
        )

        state = _workflow_states.get(incident_id)
        if state is not None and new_status != previous_status:
            state.previous_status = previous_status
            state.current_status = new_status
            state.transition_at = now

        return incident

    # --- TC-8: typed remediation options ---------------------------------

    async def add_remediation_option(
        self,
        incident_id: str,
        *,
        option: dict,
        actor: str,
    ) -> dict | None:
        """Append a typed RemediationOption (already-serialised dict) to the
        incident's option list. Records a ``remediation.option_added`` event.
        Returns the stored option, or None if the incident is unknown.
        """
        incident = _incidents.get(incident_id)
        if incident is None:
            return None

        now = datetime.now(timezone.utc)
        incident.attributes = incident.attributes or {}
        options = list(incident.attributes.get("remediation_options") or [])
        options.append(option)
        incident.attributes["remediation_options"] = options
        incident.updated_at = now

        _record_event(
            incident_id,
            WorkflowEvent(
                event_id=uuid.uuid4().hex,
                incident_id=incident_id,
                event_type="remediation.option_added",
                from_status=incident.status,
                to_status=incident.status,
                actor=actor,
                timestamp=now,
                payload={"option_id": option.get("option_id"), "path": option.get("path")},
            ),
        )
        return option

    async def list_remediation_options(self, incident_id: str) -> list[dict] | None:
        incident = _incidents.get(incident_id)
        if incident is None:
            return None
        return list((incident.attributes or {}).get("remediation_options") or [])

    async def select_remediation_option(
        self,
        incident_id: str,
        option_id: str,
        *,
        actor: str,
    ) -> dict | None:
        """Mark ``option_id`` as the selected remediation. Returns the
        selected option dict, or None if either the incident or the option
        is unknown.
        """
        incident = _incidents.get(incident_id)
        if incident is None:
            return None
        attributes = incident.attributes or {}
        options = list(attributes.get("remediation_options") or [])
        match = next((o for o in options if o.get("option_id") == option_id), None)
        if match is None:
            return None

        now = datetime.now(timezone.utc)
        attributes["selected_remediation_option_id"] = option_id
        incident.attributes = attributes
        incident.updated_at = now

        _record_event(
            incident_id,
            WorkflowEvent(
                event_id=uuid.uuid4().hex,
                incident_id=incident_id,
                event_type="remediation.option_selected",
                from_status=incident.status,
                to_status=incident.status,
                actor=actor,
                timestamp=now,
                payload={"option_id": option_id, "path": match.get("path")},
            ),
        )
        return match

    async def handle_inbound_event(self, event: InboundEvent) -> None:
        """Handle an inbound event from Event Grid / Service Bus."""
        # Create an incident from the event
        await self.create_incident(
            IncidentCreateRequest(
                title=event.data.get("title", f"Event: {event.event_type}"),
                description=str(event.data),
                source=IncidentSource.EVENT_GRID,
            )
        )

    # --- Internal workflow helpers ---

    async def _advance_to_triaging(self, incident: Incident) -> None:
        """Advance to TRIAGING using AI-driven analysis via Azure OpenAI."""
        now = datetime.now(timezone.utc)
        incident.status = IncidentStatus.TRIAGING
        incident.updated_at = now

        state = _workflow_states[incident.incident_id]
        state.previous_status = IncidentStatus.RECEIVED
        state.current_status = IncidentStatus.TRIAGING
        state.transition_at = now

        # AI-driven triage analysis (tries UC2 supervisor → AI + UC1 context → rules)
        triage_result = await self._triage(incident)

        _record_event(
            incident.incident_id,
            WorkflowEvent(
                event_id=uuid.uuid4().hex,
                incident_id=incident.incident_id,
                event_type="workflow.transition",
                from_status=IncidentStatus.RECEIVED,
                to_status=IncidentStatus.TRIAGING,
                actor="triage-agent",
                timestamp=now,
                payload=triage_result,
            ),
        )

        # Update incident with AI-determined severity and category
        if triage_result.get("severity"):
            try:
                incident.severity = IncidentSeverity(triage_result["severity"])
            except ValueError:
                pass
        if triage_result.get("category"):
            try:
                incident.category = IncidentCategory(triage_result["category"])
            except ValueError:
                pass
        if triage_result.get("recommended_action"):
            incident.attributes = incident.attributes or {}
            incident.attributes["ai_triage"] = triage_result

    async def _triage(self, incident: Incident) -> dict:
        """Triage an incident using the best available method.

        Priority order:
          1. UC2 Supervisor (multi-agent orchestration) — if UC2_SUPERVISOR_ENDPOINT is set
          2. AI triage with UC1 knowledge context — if AZURE_OPENAI_ENDPOINT is set
          3. Rule-based fallback
        """
        # Try UC2 supervisor-mediated triage first (4.7)
        uc2_endpoint = os.environ.get("UC2_SUPERVISOR_ENDPOINT", "")
        if uc2_endpoint:
            try:
                result = await self._run_supervisor_triage(incident, uc2_endpoint)
                if result:
                    result["triage_method"] = "uc2_supervisor"
                    return result
            except Exception as e:
                logger.warning("UC2 supervisor triage failed, falling back: %s", e)

        # Try AI triage (optionally enriched with UC1 knowledge context)
        return await self._run_ai_triage(incident)

    async def _get_knowledge_context(self, incident: Incident) -> str:
        """Query UC1 RAG agent for engineering knowledge relevant to the incident (4.6)."""
        uc1_endpoint = os.environ.get("UC1_RAG_ENDPOINT", "")
        if not uc1_endpoint:
            return ""

        query = f"{incident.title}. {incident.description or ''}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{uc1_endpoint.rstrip('/')}/responses",
                    json={"input": query},
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    outputs = data.get("output", [])
                    messages = [o for o in outputs if o.get("type") == "message" and o.get("role") == "assistant"]
                    if messages:
                        content = messages[-1].get("content", [{}])
                        text = content[0].get("text", "") if content else ""
                        if text:
                            logger.info("UC1 knowledge context retrieved (%d chars)", len(text))
                            return text[:2000]  # Truncate to avoid token limits
                return ""
        except Exception as e:
            logger.warning("UC1 knowledge retrieval failed: %s", e)
            return ""

    async def _run_supervisor_triage(self, incident: Incident, uc2_endpoint: str) -> dict | None:
        """Route incident through UC2 multi-agent supervisor for comprehensive triage (4.7).

        The supervisor orchestrates Knowledge, Compliance, and Governance agents
        to produce a richer incident analysis than direct AI triage alone.
        """
        prompt = (
            f"Analyze this platform incident and classify it:\n"
            f"- Title: {incident.title}\n"
            f"- Description: {incident.description}\n"
            f"- Source: {incident.source}\n"
            f"- Tags: {incident.tags}\n\n"
            f"Provide: severity (p1-p4), category, recommended action, and reasoning. "
            f"Check Knowledge for any relevant engineering context, Compliance for "
            f"any regulatory implications, and Governance for recent platform health data."
        )

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{uc2_endpoint.rstrip('/')}/responses",
                    json={"input": prompt},
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    logger.warning("UC2 supervisor returned HTTP %s", resp.status_code)
                    return None

                data = resp.json()
                outputs = data.get("output", [])
                messages = [o for o in outputs if o.get("type") == "message" and o.get("role") == "assistant"]
                if not messages:
                    return None

                content = messages[-1].get("content", [{}])
                text = content[0].get("text", "") if content else ""
                if not text:
                    return None

                # Try to parse structured JSON from supervisor response
                import json as _json
                try:
                    # Look for JSON block in response
                    if "```" in text:
                        json_block = text.split("```")[1]
                        if json_block.startswith("json"):
                            json_block = json_block[4:]
                        return _json.loads(json_block.strip())
                    return _json.loads(text.strip())
                except (_json.JSONDecodeError, IndexError):
                    # Supervisor gave a natural language response — wrap it
                    return {
                        "severity": "medium",
                        "category": "infrastructure",
                        "recommended_action": text[:500],
                        "reasoning": "Multi-agent analysis via UC2 supervisor.",
                        "supervisor_response": text[:2000],
                    }
        except Exception as e:
            logger.warning("UC2 supervisor call failed: %s", e)
            return None

    async def _run_ai_triage(self, incident: Incident) -> dict:
        """Call Azure OpenAI for AI-driven incident classification and severity assessment.
        
        Enriches the triage prompt with UC1 knowledge context when available (4.6).
        """
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")

        if not endpoint or not api_key:
            logger.warning("Azure OpenAI not configured — using rule-based triage")
            return self._rule_based_triage(incident)

        # Retrieve engineering knowledge context from UC1 RAG (4.6)
        knowledge_context = await self._get_knowledge_context(incident)
        knowledge_section = ""
        if knowledge_context:
            knowledge_section = f"""

Relevant Engineering Knowledge (from UC1 Knowledge Base):
{knowledge_context}

Use this knowledge context to inform your severity assessment and recommended action."""

        prompt = f"""You are an AI incident triage agent for the Unified AI Platform.
Analyze the following incident and provide:
1. severity: one of [critical, high, medium, low]
2. category: one of [model_failure, latency_degradation, cost_anomaly, security_event, compliance_violation, infrastructure]
3. recommended_action: brief recommendation
4. reasoning: 1-2 sentence explanation

Incident:
- Title: {incident.title}
- Description: {incident.description}
- Source: {incident.source}
- Tags: {incident.tags}{knowledge_section}

Respond in JSON format only."""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{endpoint}openai/deployments/{model}/chat/completions?api-version=2024-10-21",
                    headers={"api-key": api_key, "Content-Type": "application/json"},
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 300,
                        "temperature": 0.1,
                    },
                )
                if resp.status_code == 200:
                    import json
                    content = resp.json()["choices"][0]["message"]["content"]
                    # Strip markdown code fences if present
                    content = content.strip()
                    if content.startswith("```"):
                        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
                    return json.loads(content)
                else:
                    logger.warning("AI triage failed (HTTP %s), falling back to rules", resp.status_code)
                    return self._rule_based_triage(incident)
        except Exception as e:
            logger.warning("AI triage error: %s, falling back to rules", e)
            return self._rule_based_triage(incident)

    def _rule_based_triage(self, incident: Incident) -> dict:
        """Fallback rule-based triage when AI is unavailable."""
        desc_lower = (incident.description or "").lower()
        title_lower = (incident.title or "").lower()
        combined = f"{title_lower} {desc_lower}"

        if any(w in combined for w in ["security", "unauthorized", "breach", "attack"]):
            return {"severity": "critical", "category": "security_event",
                    "recommended_action": "Escalate to security team immediately",
                    "reasoning": "Security-related keywords detected in incident description."}
        elif any(w in combined for w in ["cost", "token", "budget", "spend"]):
            return {"severity": "medium", "category": "cost_anomaly",
                    "recommended_action": "Review token consumption and set usage alerts",
                    "reasoning": "Cost/budget-related keywords detected."}
        elif any(w in combined for w in ["latency", "slow", "timeout", "degradation"]):
            return {"severity": "high", "category": "latency_degradation",
                    "recommended_action": "Check agent health and cross-cloud connectivity",
                    "reasoning": "Performance-related keywords detected."}
        elif any(w in combined for w in ["failure", "error", "crash", "500"]):
            return {"severity": "high", "category": "model_failure",
                    "recommended_action": "Check agent logs and model deployment status",
                    "reasoning": "Failure-related keywords detected."}
        else:
            return {"severity": "medium", "category": "infrastructure",
                    "recommended_action": "Investigate and assign to appropriate team",
                    "reasoning": "General incident — requires manual classification."}
