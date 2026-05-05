# -----------------------------------------------------------------------------
# Microsoft Sentinel — SIEM Integration
# Enables Sentinel on the ALZ Log Analytics Workspace and creates
# analytics rules for AI platform governance alerting.
# -----------------------------------------------------------------------------

resource "azurerm_sentinel_log_analytics_workspace_onboarding" "uc3" {
  workspace_id = data.azurerm_log_analytics_workspace.alz.id
}

# --- Analytics Rules ---

resource "azurerm_sentinel_alert_rule_scheduled" "anomalous_token_consumption" {
  name                       = "uc3-anomalous-token-consumption"
  display_name               = "Anomalous AI Token Consumption"
  description                = "Detects spike in token consumption across AI model providers that exceeds 3x the rolling 1-hour average."
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.alz.id
  severity                   = "Medium"
  query_frequency            = "PT1H"
  query_period               = "PT1H"
  query                      = <<-KQL
    AppTraces
    | where Properties has "tokens_total"
    | extend tokens = toint(Properties.tokens_total)
    | summarize total_tokens = sum(tokens), avg_tokens = avg(tokens) by bin(TimeGenerated, 15m)
    | where total_tokens > avg_tokens * 3
  KQL
  trigger_operator           = "GreaterThan"
  trigger_threshold          = 0
  enabled                    = true

  depends_on = [azurerm_sentinel_log_analytics_workspace_onboarding.uc3]
}

resource "azurerm_sentinel_alert_rule_scheduled" "agent_failure_rate" {
  name                       = "uc3-agent-failure-rate"
  display_name               = "High AI Agent Failure Rate"
  description                = "Fires when any agent has a failure rate exceeding 20% over a 15-minute window."
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.alz.id
  severity                   = "High"
  query_frequency            = "PT15M"
  query_period               = "PT15M"
  query                      = <<-KQL
    AppDependencies
    | where Name startswith "agent."
    | summarize total = count(), failures = countif(Success == false) by Name
    | extend failure_rate = round(todouble(failures) / todouble(total) * 100, 2)
    | where failure_rate > 20
  KQL
  trigger_operator           = "GreaterThan"
  trigger_threshold          = 0
  enabled                    = true

  depends_on = [azurerm_sentinel_log_analytics_workspace_onboarding.uc3]
}

resource "azurerm_sentinel_alert_rule_scheduled" "content_safety_violations" {
  name                       = "uc3-content-safety-violations"
  display_name               = "Content Safety Policy Violation"
  description                = "Detects requests blocked by Azure Content Safety filters."
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.alz.id
  severity                   = "High"
  query_frequency            = "PT5M"
  query_period               = "PT5M"
  query                      = <<-KQL
    AppTraces
    | where Properties has "content_safety_result"
    | extend safety_result = tostring(Properties.content_safety_result)
    | where safety_result == "blocked"
  KQL
  trigger_operator           = "GreaterThan"
  trigger_threshold          = 0
  enabled                    = true

  depends_on = [azurerm_sentinel_log_analytics_workspace_onboarding.uc3]
}

resource "azurerm_sentinel_alert_rule_scheduled" "rate_limit_breach" {
  name                       = "uc3-rate-limit-breach"
  display_name               = "Repeated Rate Limit Breaches"
  description                = "Detects repeated 429 responses from the AI Gateway indicating sustained rate limit pressure."
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.alz.id
  severity                   = "Medium"
  query_frequency            = "PT15M"
  query_period               = "PT15M"
  query                      = <<-KQL
    ApiManagementGatewayLogs
    | where ResponseCode == 429
    | summarize breach_count = count() by ApimSubscriptionId, ApiId, bin(TimeGenerated, 5m)
    | where breach_count > 10
  KQL
  trigger_operator           = "GreaterThan"
  trigger_threshold          = 0
  enabled                    = true

  depends_on = [azurerm_sentinel_log_analytics_workspace_onboarding.uc3]
}

resource "azurerm_sentinel_alert_rule_scheduled" "cross_cloud_latency" {
  name                       = "uc3-cross-cloud-latency-degradation"
  display_name               = "Cross-Cloud AI Latency Degradation"
  description                = "Fires when P95 latency on cross-cloud agent calls exceeds 5 seconds."
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.alz.id
  severity                   = "Medium"
  query_frequency            = "PT30M"
  query_period               = "PT30M"
  query                      = <<-KQL
    AppDependencies
    | where Name has "bedrock" or Name has "oci"
    | summarize p95_duration = percentile(DurationMs, 95) by Name, bin(TimeGenerated, 15m)
    | where p95_duration > 5000
  KQL
  trigger_operator           = "GreaterThan"
  trigger_threshold          = 0
  enabled                    = true

  depends_on = [azurerm_sentinel_log_analytics_workspace_onboarding.uc3]
}

# TC-5: Per-agent SLA breach (emitted by UC2 supervisor as OTEL span event
# `agent.sla_breach`). Surface as a Sentinel incident so an on-call engineer
# can ack/investigate. Span events land in App Insights `customEvents`.
resource "azurerm_sentinel_alert_rule_scheduled" "agent_sla_breach" {
  name                       = "uc3-agent-sla-breach"
  display_name               = "Agent SLA Breach"
  description                = "Per-agent SLA breach event emitted by UC2 supervisor when an agent invocation exceeds its configured sla_timeout_seconds."
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.alz.id
  severity                   = "Medium"
  query_frequency            = "PT5M"
  query_period               = "PT5M"
  query                      = <<-KQL
    AppEvents
    | where Name == "agent.sla_breach"
    | extend agent     = tostring(Properties["agent.name"])
    | extend threshold = todouble(Properties["sla.threshold_seconds"])
    | extend elapsed   = todouble(Properties["sla.elapsed_seconds"])
    | extend cause     = tostring(Properties["sla.cause"])
    | project TimeGenerated, agent, threshold, elapsed, cause, OperationId, AppRoleName
  KQL
  trigger_operator           = "GreaterThan"
  trigger_threshold          = 0
  enabled                    = true

  event_grouping {
    aggregation_method = "AlertPerResult"
  }

  incident {
    create_incident_enabled = true
    grouping {
      enabled                 = true
      lookback_duration       = "PT15M"
      reopen_closed_incidents = false
      entity_matching_method  = "AnyAlert"
    }
  }

  depends_on = [azurerm_sentinel_log_analytics_workspace_onboarding.uc3]
}
