# -----------------------------------------------------------------------------
# APIM — UC3 Governance API
# Adds the governance API as an internal APIM API.
# -----------------------------------------------------------------------------

resource "azurerm_api_management_api" "governance" {
  name                = "uc3-governance-api"
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  revision            = "1"
  display_name        = "UC3 Governance Hub API"
  path                = "uc3"
  protocols           = ["https"]

  subscription_required = true
  subscription_key_parameter_names {
    header = "Ocp-Apim-Subscription-Key"
    query  = "subscription-key"
  }
}

# --- Operations ---

resource "azurerm_api_management_api_operation" "costs_summary" {
  operation_id        = "costs-summary"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Cost Summary"
  method              = "GET"
  url_template        = "/api/costs/summary"
}

resource "azurerm_api_management_api_operation" "costs_by_agent" {
  operation_id        = "costs-by-agent"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Cost By Agent"
  method              = "GET"
  url_template        = "/api/costs/by-agent"
}

resource "azurerm_api_management_api_operation" "costs_trends" {
  operation_id        = "costs-trends"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Cost Trends"
  method              = "GET"
  url_template        = "/api/costs/trends"
}

resource "azurerm_api_management_api_operation" "agents_traces" {
  operation_id        = "agents-traces"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Agent Traces"
  method              = "GET"
  url_template        = "/api/agents/traces"
}

resource "azurerm_api_management_api_operation" "agents_trace_detail" {
  operation_id        = "agents-trace-detail"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Agent Trace Detail"
  method              = "GET"
  url_template        = "/api/agents/{trace_id}"

  template_parameter {
    name     = "trace_id"
    required = true
    type     = "string"
  }
}

resource "azurerm_api_management_api_operation" "agents_health" {
  operation_id        = "agents-health"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Agent Health"
  method              = "GET"
  url_template        = "/api/agents/health"
}

resource "azurerm_api_management_api_operation" "policies_list" {
  operation_id        = "policies-list"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "List Policies"
  method              = "GET"
  url_template        = "/api/policies"
}

resource "azurerm_api_management_api_operation" "policies_create" {
  operation_id        = "policies-create"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Create Policy"
  method              = "POST"
  url_template        = "/api/policies"
}

resource "azurerm_api_management_api_operation" "policies_update" {
  operation_id        = "policies-update"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Update Policy"
  method              = "PUT"
  url_template        = "/api/policies/{policy_id}"

  template_parameter {
    name     = "policy_id"
    required = true
    type     = "string"
  }
}

resource "azurerm_api_management_api_operation" "policies_delete" {
  operation_id        = "policies-delete"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Delete Policy"
  method              = "DELETE"
  url_template        = "/api/policies/{policy_id}"

  template_parameter {
    name     = "policy_id"
    required = true
    type     = "string"
  }
}

resource "azurerm_api_management_api_operation" "compliance_report" {
  operation_id        = "compliance-report"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Compliance Report"
  method              = "GET"
  url_template        = "/api/compliance/report"
}

resource "azurerm_api_management_api_operation" "compliance_violations" {
  operation_id        = "compliance-violations"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Compliance Violations"
  method              = "GET"
  url_template        = "/api/compliance/violations"
}

resource "azurerm_api_management_api_operation" "health" {
  operation_id        = "health"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Health Check"
  method              = "GET"
  url_template        = "/health"
}

# --- Incident orchestration operations (formerly UC4) ---

resource "azurerm_api_management_api_operation" "incidents_create" {
  operation_id        = "incidents-create"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Create Incident"
  method              = "POST"
  url_template        = "/api/incidents"
}

resource "azurerm_api_management_api_operation" "incidents_list" {
  operation_id        = "incidents-list"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "List Incidents"
  method              = "GET"
  url_template        = "/api/incidents"
}

resource "azurerm_api_management_api_operation" "incidents_get" {
  operation_id        = "incidents-get"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Get Incident"
  method              = "GET"
  url_template        = "/api/incidents/{incident_id}"

  template_parameter {
    name     = "incident_id"
    required = true
    type     = "string"
  }
}

resource "azurerm_api_management_api_operation" "approvals_list" {
  operation_id        = "approvals-list"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "List Approvals"
  method              = "GET"
  url_template        = "/api/approvals"
}

resource "azurerm_api_management_api_operation" "approvals_respond" {
  operation_id        = "approvals-respond"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Respond to Approval"
  method              = "POST"
  url_template        = "/api/approvals/{approval_id}/respond"

  template_parameter {
    name     = "approval_id"
    required = true
    type     = "string"
  }
}

resource "azurerm_api_management_api_operation" "workflows_list" {
  operation_id        = "workflows-list"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "List Workflows"
  method              = "GET"
  url_template        = "/api/workflows"
}

resource "azurerm_api_management_api_operation" "events_ingest" {
  operation_id        = "events-ingest"
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Ingest Event"
  method              = "POST"
  url_template        = "/api/events"
}

# --- Backend ---

resource "azurerm_api_management_backend" "governance" {
  name                = "uc3-governance-backend"
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  protocol            = "http"
  url                 = "https://${azurerm_container_app.governance.ingress[0].fqdn}"
}

# --- Policy: route to governance backend + propagate traceparent ---

resource "azurerm_api_management_api_policy" "governance" {
  api_name            = azurerm_api_management_api.governance.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name

  xml_content = <<-XML
    <policies>
      <inbound>
        <base />
        <set-backend-service backend-id="${azurerm_api_management_backend.governance.name}" />
        <set-header name="traceparent" exists-action="skip">
          <value>@{
            var traceId = Guid.NewGuid().ToString("N");
            var spanId  = Guid.NewGuid().ToString("N").Substring(0, 16);
            return $"00-{traceId}-{spanId}-01";
          }</value>
        </set-header>
      </inbound>
      <backend>
        <base />
      </backend>
      <outbound>
        <base />
      </outbound>
      <on-error>
        <base />
      </on-error>
    </policies>
  XML
}

# -----------------------------------------------------------------------------
# APIM — OTEL Collector (telemetry ingestion from cross-cloud agents)
# Exposes the OTLP/HTTP endpoint through the AI Gateway so AWS Bedrock
# agents can push telemetry via APIM.
# -----------------------------------------------------------------------------

resource "azurerm_api_management_api" "otel_collector" {
  name                = "uc3-otel-collector"
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  revision            = "1"
  display_name        = "UC3 OTEL Collector"
  path                = "otel"
  protocols           = ["https"]

  subscription_required = true
  subscription_key_parameter_names {
    header = "Ocp-Apim-Subscription-Key"
    query  = "subscription-key"
  }
}

resource "azurerm_api_management_api_operation" "otel_traces" {
  operation_id        = "otel-traces"
  api_name            = azurerm_api_management_api.otel_collector.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Push Traces (OTLP/HTTP)"
  method              = "POST"
  url_template        = "/v1/traces"
}

resource "azurerm_api_management_api_operation" "otel_metrics" {
  operation_id        = "otel-metrics"
  api_name            = azurerm_api_management_api.otel_collector.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Push Metrics (OTLP/HTTP)"
  method              = "POST"
  url_template        = "/v1/metrics"
}

resource "azurerm_api_management_api_operation" "otel_logs" {
  operation_id        = "otel-logs"
  api_name            = azurerm_api_management_api.otel_collector.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  display_name        = "Push Logs (OTLP/HTTP)"
  method              = "POST"
  url_template        = "/v1/logs"
}

resource "azurerm_api_management_backend" "otel_collector" {
  name                = "uc3-otel-collector-backend"
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name
  protocol            = "http"
  url                 = "https://${azurerm_container_app.otel_collector.ingress[0].fqdn}"
}

resource "azurerm_api_management_api_policy" "otel_collector" {
  api_name            = azurerm_api_management_api.otel_collector.name
  api_management_name = data.azurerm_api_management.alz.name
  resource_group_name = data.azurerm_resource_group.alz.name

  xml_content = <<-XML
    <policies>
      <inbound>
        <base />
        <set-backend-service backend-id="${azurerm_api_management_backend.otel_collector.name}" />
      </inbound>
      <backend>
        <base />
      </backend>
      <outbound>
        <base />
      </outbound>
      <on-error>
        <base />
      </on-error>
    </policies>
  XML
}
