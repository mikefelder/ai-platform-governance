# Cross-Cloud Governance & Monitoring Hub

> Centralized governance, observability, cost tracking, and SIEM integration across all platform workloads and cloud providers. Also incorporates incident resolution capabilities.

## Complete Solution Architecture
For the **end-to-end solution architecture** spanning all platform services, networking, identity, and cross-cloud telemetry flows, see:

**[docs/uaip_solution_architecture.md](docs/uaip_solution_architecture.md)** — full solution architecture reference.

## Introduction
Start there for the big-picture view before diving into governance-specific details below.

This repository contains the **Governance Hub**, the horizontal governance, observability, and incident-resolution layer that ties together the agent workloads (RAG Agent, Supervisor Agent, Incident Resolution) and cross-cloud workloads (Azure + AWS).

---

## Overview

The Governance Hub is the **horizontal platform layer** of the UAIP. It provides unified observability across Azure and AWS, centralizes cost and token usage tracking, enforces governance policies, integrates with Microsoft Sentinel for security monitoring, and manages incident resolution workflows.

All UAIP agents — whether running on Azure Container Apps or AWS Lambda — emit OpenTelemetry telemetry that is collected, normalized, and aggregated by UC3 for enterprise-wide visibility.

### Key Capabilities

- **Unified telemetry** — OTEL Collector ingests traces, metrics, and logs from all agents
- **Cross-cloud observability** — Azure + AWS spans correlated via W3C traceparent
- **Cost & token tracking** — Token consumption by model, agent, and provider
- **Policy enforcement** — Append-only versioned `EnterprisePolicy` registry with SHA-256 canonical hashing; per-incident snapshot binding; approver-role enforcement (TC-2)
- **Caller identity** — Entra JWT validation on incidents and approvals; 4 Entra app roles on `uaip-governance` (TC-1 / TC-9)
- **SIEM integration** — Microsoft Sentinel with 6 analytics rules (incl. Agent SLA Breach for TC-5)
- **Incident management** — AI-driven incident analysis with human-in-the-loop approvals (UC4)
- **Event-driven workflows** — Service Bus + Event Grid for incident orchestration

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                         Azure AI Landing Zone                         │
│                                                                       │
│  UC1 RAG Agent ──┐                                                    │
│  UC2 Supervisor ─┤   ┌──────────┐    ┌──────────────────────────────┐ │
│  AWS Bedrock   ──┼──▶│   APIM   │───▶│  OTEL Collector (ca-uc3-     │ │
│  Frontend      ──┘   │  /otel/* │    │  otel-collector, port 4318)  │ │
│                      │  /uc3/*  │    │  OTLP/HTTP receivers         │ │
│                      └──────────┘    │  → Batch → Transform         │ │
│                           │          │  → Azure Monitor Exporter    │ │
│                           │          └──────────────────────────────┘ │
│                           │                    │                      │
│                           ▼                    ▼                      │
│  ┌────────────────────────────────┐  ┌──────────────────────────────┐ │
│  │  Governance API (ca-uc3-       │  │  Log Analytics Workspace     │ │
│  │  governance, FastAPI, 8000)    │  │                              │ │
│  │                                │  │  ┌────────────────────────┐  │ │
│  │  /api/costs     → Token costs  │  │  │  Microsoft Sentinel    │  │ │
│  │  /api/agents/*  → Traces/health│  │  │  • Analytics rules     │  │ │
│  │  /api/policies  → Policy CRUD  │◀─┤  │  • Anomaly detection   │  │ │
│  │  /api/compliance → Reports     │  │  │  • Alerting            │  │ │
│  │  /api/incidents → Incidents    │  │  └────────────────────────┘  │ │
│  │  /api/approvals → HITL         │  │                              │ │
│  │  /api/workflows → State mgmt   │  │  ┌────────────────────────┐  │ │
│  │  /api/events    → Routing      │  │  │  Application Insights  │  │ │
│  │  /readiness     → Health       │  │  │  OTEL telemetry        │  │ │
│  └────────────────────────────────┘  │  └────────────────────────┘  │ │
│                                      └──────────────────────────────┘ │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐   │
│  │  Cosmos DB   │  │ Service Bus  │  │  Event Grid                │   │
│  │  Incident    │  │ Event-driven │  │  Incident triggers         │   │
│  │  workflow    │  │ orchestration│  │                            │   │
│  │  state       │  │              │  │                            │   │
│  └──────────────┘  └──────────────┘  └────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘
```

### Azure Services

| Service | Resource | Purpose |
|---------|----------|---------|
| Azure Container Apps | `ca-uc3-governance` | Governance API (FastAPI) |
| Azure Container Apps | `ca-uc3-otel-collector` | OpenTelemetry Collector |
| Azure API Management | `ai-alz-apim-i40e` | AI Gateway — `/uc3/*`, `/otel/v1/*` routes |
| Azure Cosmos DB | `cosmos-uc4-incident-mb44x` | Incident and workflow state storage |
| Azure Service Bus | `sb-uc4-incident-mb44x` | Event-driven incident orchestration |
| Azure Event Grid | Event topic | Incident event routing and triggers |
| Microsoft Sentinel | Sentinel workspace | SIEM — analytics rules, anomaly detection |
| Application Insights | UC3 workspace | Observability telemetry |
| Log Analytics | Shared workspace | Centralized log aggregation |

---

## API Endpoints

### Governance API (`/uc3/*` via APIM)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/costs` | Token & cost analytics from Log Analytics |
| `GET` | `/api/agents/traces` | Agent trace queries |
| `GET` | `/api/agents/health` | Agent health status across all UCs |
| `GET` | `/api/agents/suspensions` | List all current agent suspension states (TC-10) |
| `GET` | `/api/agents/{name}/suspension` | Current suspension state for a single agent (TC-10) |
| `POST` | `/api/agents/{name}/suspend` | Suspend an agent (audited; Sentinel `agent.sla_breach` webhook target) (TC-10) |
| `POST` | `/api/agents/{name}/resume` | Resume a suspended agent (409 if already active) (TC-10) |
| `GET/POST` | `/api/policies` | Governance policy CRUD (legacy single-version) |
| `GET/POST` | `/api/policies/registry` | Append-only versioned `EnterprisePolicy` registry (TC-2) |
| `GET` | `/api/policies/registry/{id}/active` | Currently active version of a policy |
| `GET` | `/api/policies/registry/{id}/versions` | Full version history (immutable, SHA-256 hashed) |
| `GET` | `/api/policies/gateway/digest` | SHA-256 over `infra/main.apim*.tf` + APIM policy XML (TC-2f) |
| `GET` | `/api/incidents/{id}/approvals` | List approval requests for an incident (with snapshot + caller identity) |
| `GET` | `/api/compliance` | Compliance report generation |
| `POST` | `/api/incidents` | Create AI-driven incident |
| `GET` | `/api/incidents` | List incidents with status |
| `POST` | `/api/incidents/{id}/votes` | Submit agent vote (recommendation + confidence) |
| `GET` | `/api/incidents/{id}/votes` | List all votes for an incident |
| `POST` | `/api/incidents/{id}/decide` | Run decision engine (strategy: weighted_majority/unanimous/quorum) |
| `GET` | `/api/incidents/{id}/decision` | Get decision outcome |
| `POST` | `/api/incidents/{id}/resolve` | Resolve incident with notes |
| `POST` | `/api/approvals/{id}/respond` | Human-in-the-loop approval |
| `GET` | `/api/workflows` | Long-running workflow state |
| `POST` | `/api/events` | Event routing |
| `GET` | `/readiness` | Health check |

### OTEL Collector (`/otel/*` via APIM)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/otel/v1/traces` | OTLP/HTTP trace ingestion |
| `POST` | `/otel/v1/metrics` | OTLP/HTTP metric ingestion |
| `POST` | `/otel/v1/logs` | OTLP/HTTP log ingestion |

---

## How It Works

### Telemetry Flow

```
1. Agent emits OTEL spans (Agent Framework SDK ObservabilitySettings)
2. Spans exported via Azure Monitor exporter OR OTLP/HTTP to collector
3. OTEL Collector receives, batches, transforms (adds service.namespace=uaip)
4. Collector exports to Azure Monitor / Log Analytics
5. Sentinel ingests from Log Analytics for security analytics
6. Governance API queries Log Analytics for cost/trace/health data
```

### Cross-Cloud Telemetry

AWS Bedrock agents export OTEL spans to either:
- **Direct**: Azure Monitor via `APPLICATIONINSIGHTS_CONNECTION_STRING`
- **Via APIM**: `POST /otel/v1/traces` to the OTEL Collector through APIM

Both paths preserve the W3C `traceparent` from the Azure supervisor, enabling end-to-end trace correlation across clouds.

### Incident Resolution

Incident resolution workflows are integrated into the Governance Hub with AI-driven triage, multi-agent voting, and cross-service integration:

1. Events trigger incidents via Event Grid → Service Bus (`POST /api/incidents`)
2. **Triage cascade** (tries each in order, falls back on failure):
   - **Supervisor Agent** — routes incident through multi-agent orchestration (Knowledge + Compliance + Governance agents concurrently) when `SUPERVISOR_ENDPOINT` is set
   - **AI triage with knowledge context** — calls Azure OpenAI gpt-4.1-mini, enriched with context from the RAG Agent when `RAG_ENDPOINT` is set
   - **Rule-based fallback** — keyword matching for severity/category classification
3. Triage results stored on the incident as `attributes.ai_triage`
4. **Multi-agent voting** — agents submit votes via `POST /api/incidents/{id}/votes` with recommendations and confidence scores
5. **Decision engine** — `POST /api/incidents/{id}/decide` runs voting strategy (weighted_majority, unanimous, or quorum)
   - P1/P2 incidents always require human approval
   - P3/P4 with >95% confidence can be auto-approved
6. Human-in-the-loop approvals via `POST /api/approvals/{id}/respond`
7. Incidents resolved via `POST /api/incidents/{id}/resolve` with resolution notes
8. **Cosmos DB persistence** — incidents persisted with in-memory cache and read-through fallback
9. All actions logged to Sentinel for audit

**AI Triage Categories:** `model_failure`, `latency_degradation`, `cost_anomaly`, `security_event`, `compliance_violation`, `infrastructure`

**Voting Strategies:**
- **Weighted majority** — each vote weighted by confidence score; highest-weight recommendation wins
- **Unanimous** — all agents must agree or escalate
- **Quorum** — >50% of agents must agree on a recommendation

---

## Project Structure

```
services/
  governance-api/            # FastAPI governance service
    Dockerfile               # python:3.11-slim, uvicorn on port 8000
    src/governance_api/
      main.py                # FastAPI app with 9 routers
      routers/
        costs.py             # Token & cost analytics
        agents.py            # Agent trace and health queries
        policies.py          # Policy CRUD
        compliance.py        # Compliance report generation
        incidents.py         # AI-driven incident management + voting endpoints
        approvals.py         # Human-in-the-loop approvals
        workflows.py         # Long-running workflow state
        events.py            # Event routing
        health.py            # Health check
      services/
        orchestration_service.py  # Incident workflow + AI triage + Cosmos persistence
        decision_engine.py        # Multi-agent voting (weighted majority, unanimous, quorum)
        cost_aggregator.py        # Token & cost analytics from Log Analytics
        policy_engine.py          # Governance policy evaluation
        approval_service.py       # Approval workflow management
        telemetry_query.py        # Log Analytics / App Insights queries
      models/
        incident.py          # Incident, severity, category, status enums
        decision.py          # AgentVote, Decision, VotingStrategy
        workflow.py          # WorkflowState, WorkflowEvent
        approval.py          # Approval models
        cost.py              # Cost summary and trend models
        policy.py            # Governance policy models
    tests/                   # 12 test files covering all routers

  otel-collector/            # OTEL Collector configuration
    otel-collector-config.yaml   # OTLP receivers, batch, transform, Azure Monitor export

  mock-telemetry/            # Mock telemetry generator for testing

infra/                       # Terraform deployment
  main.container_app.tf      # Governance API Container App
  main.otel_collector.tf     # OTEL Collector Container App
  main.apim.tf               # APIM routes (governance + OTEL)
  main.identity.tf           # UAMI + RBAC
  main.cosmos.tf             # Cosmos DB for incident state
  main.service_bus.tf        # Service Bus for event-driven workflows
  main.event_grid.tf         # Event Grid for incident triggers
  main.sentinel.tf           # Sentinel workspace + analytics rules
  main.monitor.tf            # Application Insights
  data.tf                    # Data sources for ALZ resources
  terraform.tfvars.msdn      # MSDN PoC configuration
```

---

## Getting Started

### Prerequisites

- Azure subscription with AI Landing Zone deployed
- Azure CLI (`az`) authenticated
- Terraform >= 1.9
- Python 3.11+

### 1. Build and Push Container Image

```bash
az acr update -n genaicri40e --default-action Allow

az acr build --registry genaicri40e \
  --image uc3-governance-api:v0.2.0 \
  --file services/governance-api/Dockerfile services/governance-api

az acr update -n genaicri40e --default-action Deny
```

### 2. Deploy Infrastructure

```bash
cd infra
terraform init
terraform workspace select msdn
terraform plan -var-file=terraform.tfvars.msdn -out=tfplan
terraform apply tfplan
```

### 3. Deploy New Image

```bash
az containerapp update -n ca-uc3-governance -g ai-lz-rg-msdn-mb44x \
  --image genaicri40e.azurecr.io/uc3-governance-api:v0.2.0
```

### 4. Verify Deployment

```bash
# Check container apps
az containerapp revision list -n ca-uc3-governance \
  -g ai-lz-rg-msdn-mb44x \
  --query "[?properties.active].{name:name,health:properties.healthState}" -o table

az containerapp revision list -n ca-uc3-otel-collector \
  -g ai-lz-rg-msdn-mb44x \
  --query "[?properties.active].{name:name,health:properties.healthState}" -o table
```

### 4. Run Tests

```bash
cd services/governance-api
pip install -r requirements.txt
pytest tests/ -v
```

### 5. Demo Lifecycle (Spin-Down / Spin-Up)

Two helper scripts in `scripts/` let you cheaply hibernate the entire UAIP estate between demo runs and bring it back without losing any configuration. Both are idempotent and safe to re-run.

```bash
# Cheapest overnight state — Container Apps to 0 replicas, jumpbox VM deallocated.
# APIM (Developer SKU) is intentionally left running: stop/start is Premium-only.
./scripts/demo-down.sh

# Restore: APIM first (no-op on Developer), then VM, then per-app min replicas.
./scripts/demo-up.sh
```

| Variable | Default | Notes |
|----------|---------|-------|
| `SUBSCRIPTION` | `1784740a-1cf6-416b-b3db-bda6985970aa` | MSDN PoC subscription |
| `RG` | `ai-lz-rg-msdn-mb44x` | Resource group |
| `APIM_NAME` | `ai-alz-apim-i40e` | Skipped automatically when SKU != Premium |
| `JUMPBOX_VM` | `ai-alz-jumpvm` | Deallocated (compute stops, disk persists) |

What each script touches:

| Resource | `demo-down.sh` | `demo-up.sh` |
|----------|---------------|--------------|
| `ca-uaip-frontend`, `ca-uc1-rag-agent`, `ca-uc3-governance`, `ca-uc3-otel-collector` | `--min-replicas 0` | restore `min=1` |
| `ca-uc2-supervisor` | `--min-replicas 0` | restore `min=2` (warm pool for demos / TC scripts) |
| `ai-alz-jumpvm` | `az vm deallocate --no-wait` | `az vm start --no-wait` |
| `ai-alz-apim-i40e` | **skipped** (Developer SKU has no scale-to-0 / stop API) | **skipped** |
| Managed Grafana, Sentinel, Cosmos, Service Bus, Event Grid | untouched (no idle cost or already minimal) | untouched |

**State caveat:** `demo-down.sh` writes the previous APIM capacity to `/tmp/apim-capacity.txt` so a future Premium tier can round-trip cleanly. On macOS/Linux `/tmp` is wiped on reboot, so move the file to `~/.uaip-demo/` if you need it to survive a host restart \u2014 not required while APIM stays on Developer.

**APIM SKU note:** the live APIM is **Developer (Internal VNet, IP `192.168.4.4`)**, ~$50/mo fixed. The only scale-to-0 path is `terraform destroy` (loses the VIP and all subscription keys) or migrating to Consumption SKU. The scripts gate on `sku.name` so they will not attempt unsupported operations.

---

## Integration Points

| Source | Integration | How |
|--------|------------|-----|
| **UC2 → UC3** | Supervisor queries governance data | `query_governance_*` tools call `/uc3/*` via APIM |
| **AWS → UC3** | Bedrock agents push telemetry | OTEL export to `/otel/v1/traces` via APIM |
| **UC1 → UC3** | RAG agent telemetry | App Insights → Log Analytics |
| **APIM → UC3** | All API traffic logged | APIM diagnostic settings → Log Analytics |
| **Sentinel** | Security monitoring | Log Analytics → Sentinel analytics rules |

---

## Observability

- **OTEL Collector** — receives OTLP/HTTP, normalizes with `service.namespace=uaip`, exports to Azure Monitor
- **Schema normalization** — Cross-platform telemetry enriched with consistent attributes
- **W3C traceparent** — End-to-end trace correlation across Azure and AWS
- **APIM diagnostic settings** — `GatewayLogs` + `AllMetrics` streamed to Log Analytics
- **Container App diagnostics** — Console + System logs streamed to Log Analytics

---

## Sentinel SIEM Integration

Microsoft Sentinel is onboarded on the shared Log Analytics workspace with 6 analytics rules:

| Rule | Severity | Trigger |
|------|----------|--------|
| Anomalous Token Consumption | Medium | Token spike > 3x rolling average |
| High Agent Failure Rate | High | Any agent > 20% failure rate in 15min |
| Content Safety Violations | High | Requests blocked by content safety |
| Repeated Rate Limit Breaches | Medium | > 10 429s per subscription in 5min |
| Cross-Cloud Latency Degradation | Medium | P95 latency on Bedrock/OCI calls > 5s |
| **Agent SLA Breach (TC-5)** | High | OTEL `agent.sla_breach` event emitted by UC2 supervisor when a per-agent `sla_timeout_seconds` is exceeded |

Data flows: APIM GatewayLogs → Log Analytics → Sentinel analytics rules → alerts.

---

## FinOps Dashboard

An Azure Monitor Workbook (`main.workbook.tf`) provides 6 governance panels:

| Panel | Data Source | Shows |
|-------|-------------|-------|
| Agent Performance | `AppDependencies` | Request count, avg/P95 latency, failure rate per agent |
| Token Consumption by Model | `AppTraces` | Input/output tokens, estimated cost by model |
| Daily Token Trend | `AppTraces` | 7-day daily token usage chart |
| API Gateway Traffic | `ApiManagementGatewayLogs` | Requests, success rate, avg latency per API |
| Cross-Cloud Performance | `AppDependencies` | Bedrock/OCI call metrics |
| Content Safety Summary | `AppTraces` | Blocked/flagged/passed counts |

---

## Security

| Control | Implementation |
|---------|---------------|
| Service authentication | User-Assigned Managed Identity |
| API access control | APIM subscription key required |
| Caller identity (TC-1 / TC-9) | `CallerIdentity` model + Entra JWT validation (PyJWT + JWKS cache). `AUTH_MODE` env: `required` / `optional` / `disabled`. `Incident.reported_by` and `ApprovalRequest.approver_oid` / `_tenant_id` / `_auth_mode` populated from validated tokens. |
| Approver authorisation (TC-2) | `approval_service.respond()` reads the per-incident `policy_applied` snapshot and enforces `approver_role` via Entra app role membership. Mismatched roles raise `ApprovalRoleError` \u2192 HTTP 403. Distinct-approver tally + single-veto short-circuit. Idempotent `policy_decision` writes. |
| Versioned policy registry (TC-2) | Append-only `EnterprisePolicy` registry with SHA-256 canonical hashing. `Incident.create` embeds a `policy_applied` snapshot (policy_id, version, hash, threshold rule, approver_role). Emits `WorkflowEvent`s `policy.threshold_met` and `policy.rejected`. |
| APIM gateway digest (TC-2f) | `GET /api/policies/gateway/digest` returns SHA-256 over `infra/main.apim*.tf` + APIM policy XML \u2014 governance plane can prove which policy bundle is live. |
| Agent suspension (TC-10) | `agent_suspension` service + 4 endpoints under `/api/agents/{name}/{suspend,resume}` and `/api/agents/suspensions`. State machine `active`\u2194`suspended` with full history audit (reason, requested_by, source, correlation_id, suspended_at, resumed_at). Sentinel **Agent SLA Breach** analytics rule fires a webhook into `/suspend` to enforce automatic isolation when SLA budgets are exceeded; resumed via human-in-the-loop. |
| Entra app roles | 4 app roles defined on `uaip-governance` (appId `06bf98a1-d997-4a60-a616-3c384828f408`): `workflow-orchestrator`, `incident-commanders`, `senior-engineers`, `on-call`. Codified in [`infra/main.entra.tf`](infra/main.entra.tf) (azuread `~> 3.0`). |
| Network isolation | VNet-integrated CAE (internal LB) |
| Audit logging | All actions logged to Sentinel via Log Analytics |
| Data storage | Cosmos DB with managed encryption |
| Content safety | APIM policies on UC1+UC2 block prompt injection |
| Rate limiting | APIM enforces per-subscription request quotas |
