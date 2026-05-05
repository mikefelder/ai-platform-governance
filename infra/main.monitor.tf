# -----------------------------------------------------------------------------
# Azure Monitor — Alert Rules and Action Groups
# Operational alerting for the UC3 governance infrastructure.
# -----------------------------------------------------------------------------

resource "azurerm_monitor_action_group" "uc3_ops" {
  name                = "ag-uc3-governance-ops"
  resource_group_name = data.azurerm_resource_group.alz.name
  short_name          = "uc3-ops"
  tags                = var.tags

  # Add email/webhook receivers as needed:
  # email_receiver {
  #   name          = "platform-team"
  #   email_address = "platform-team@example.com"
  # }
}

# --- APIM error rate alert ---

resource "azurerm_monitor_metric_alert" "apim_errors" {
  name                = "alert-uc3-apim-errors"
  resource_group_name = data.azurerm_resource_group.alz.name
  scopes              = [data.azurerm_api_management.alz.id]
  description         = "Fires when APIM 4xx/5xx error rate exceeds threshold."
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"
  tags                = var.tags

  criteria {
    metric_namespace = "Microsoft.ApiManagement/service"
    metric_name      = "UnauthorizedRequests"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 50
  }

  action {
    action_group_id = azurerm_monitor_action_group.uc3_ops.id
  }
}

# --- APIM Diagnostic Settings ---
# NOTE: APIM GatewayLogs already configured by ALZ (sendToLogAnalytics-apim-i40e)
# No additional diagnostic setting needed — data already flows to Log Analytics → Sentinel
# Container App console/system logs flow through the CAE's built-in Log Analytics integration
