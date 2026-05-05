# -----------------------------------------------------------------------------
# Azure Monitor Workbook — UAIP FinOps Dashboard
# Provides token usage, cost tracking, and agent performance visibility.
# -----------------------------------------------------------------------------

resource "azurerm_application_insights_workbook" "finops" {
  name                = "c3f1a0b2-d4e5-6f78-9a0b-1c2d3e4f5678"
  display_name        = "UAIP FinOps & Governance Dashboard"
  resource_group_name = data.azurerm_resource_group.alz.name
  location            = data.azurerm_resource_group.alz.location
  tags                = var.tags

  data_json = jsonencode({
    version = "Notebook/1.0"
    items = [
      {
        type  = 1
        content = {
          json = "# FinOps & Governance Dashboard\nReal-time visibility into token consumption, agent performance, and cross-cloud costs."
        }
        name = "header"
      },
      {
        type = 9
        content = {
          version    = "KqlParameterItem/1.0"
          parameters = [
            {
              id          = "workspace-param"
              version     = "KqlParameterItem/1.0"
              name        = "Workspace"
              type        = 5
              isRequired  = true
              query       = "Resources | where type == 'microsoft.operationalinsights/workspaces' | project id"
              crossComponentResources = ["value::all"]
              typeSettings = {
                resourceTypeFilter = {
                  "microsoft.operationalinsights/workspaces" = true
                }
              }
              queryType    = 1
              resourceType = "microsoft.resourcegraph/resources"
            }
          ]
        }
        name = "parameters"
      },
      {
        type = 3
        content = {
          version    = "KqlItem/1.0"
          query      = <<-KQL
            AppDependencies
            | where TimeGenerated > ago(24h)
            | where Name startswith "invoke_agent" or Name startswith "chat"
            | extend agentName = tostring(Properties["gen_ai.agent.name"])
            | extend model = tostring(Properties["gen_ai.request.model"])
            | summarize
                calls = count(),
                avg_latency = round(avg(DurationMs), 0),
                p95_latency = round(percentile(DurationMs, 95), 0),
                errors = countif(Success == false)
              by Name, agentName, model
            | extend error_rate = round(100.0 * errors / calls, 1)
            | order by calls desc
          KQL
          size         = 0
          title        = "Agent Performance (Last 24h)"
          queryType    = 0
          resourceType = "microsoft.operationalinsights/workspaces"
          crossComponentResources = ["{Workspace}"]
        }
        name = "agent-performance"
      },
      {
        type = 3
        content = {
          version    = "KqlItem/1.0"
          query      = <<-KQL
            AppDependencies
            | where TimeGenerated > ago(24h)
            | where Name startswith "chat"
            | extend model = tostring(Properties["gen_ai.request.model"])
            | extend inTok = toint(Properties["gen_ai.usage.input_tokens"])
            | extend outTok = toint(Properties["gen_ai.usage.output_tokens"])
            | summarize
                calls = count(),
                total_input = sum(inTok),
                total_output = sum(outTok)
              by model
            | extend est_cost_usd = case(
                model == "gpt-4.1", round((total_input * 2.0 + total_output * 8.0) / 1000000, 4),
                model == "gpt-4.1-mini", round((total_input * 0.4 + total_output * 1.6) / 1000000, 4),
                model == "o4-mini", round((total_input * 1.1 + total_output * 4.4) / 1000000, 4),
                0.0)
            | order by total_input desc
          KQL
          size         = 0
          title        = "Token Consumption by Model (Last 24h)"
          queryType    = 0
          resourceType = "microsoft.operationalinsights/workspaces"
          crossComponentResources = ["{Workspace}"]
        }
        name = "token-consumption"
      },
      {
        type = 3
        content = {
          version    = "KqlItem/1.0"
          query      = <<-KQL
            AppDependencies
            | where TimeGenerated > ago(7d)
            | where Name startswith "chat"
            | extend inTok = toint(Properties["gen_ai.usage.input_tokens"])
            | extend outTok = toint(Properties["gen_ai.usage.output_tokens"])
            | summarize daily_tokens = sum(inTok) + sum(outTok) by bin(TimeGenerated, 1d)
            | order by TimeGenerated asc
          KQL
          size          = 0
          title         = "Daily Token Usage Trend (7 days)"
          queryType     = 0
          resourceType  = "microsoft.operationalinsights/workspaces"
          crossComponentResources = ["{Workspace}"]
          visualization = "timechart"
        }
        name = "token-trend"
      },
      {
        type = 3
        content = {
          version    = "KqlItem/1.0"
          query      = <<-KQL
            AppDependencies
            | where TimeGenerated > ago(24h)
            | where Name startswith "invoke_agent"
            | extend agent = tostring(Properties["gen_ai.agent.name"])
            | extend agentId = tostring(Properties["gen_ai.agent.id"])
            | extend inTok = toint(Properties["gen_ai.usage.input_tokens"])
            | extend outTok = toint(Properties["gen_ai.usage.output_tokens"])
            | summarize
                calls = count(),
                avgLatency = round(avg(DurationMs), 0),
                totalIn = sum(inTok),
                totalOut = sum(outTok),
                errors = countif(Success == false)
              by agent, agentId
            | extend error_rate = round(100.0 * errors / calls, 1)
            | order by calls desc
          KQL
          size         = 0
          title        = "Per-Agent Summary (Last 24h)"
          queryType    = 0
          resourceType = "microsoft.operationalinsights/workspaces"
          crossComponentResources = ["{Workspace}"]
        }
        name = "per-agent-summary"
      }
    ]
    isLocked = false
  })
}
