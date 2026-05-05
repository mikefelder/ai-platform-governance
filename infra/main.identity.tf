# -----------------------------------------------------------------------------
# Application Insights — linked to the ALZ Log Analytics Workspace
# Provides the OTEL endpoint for the Governance API telemetry.
# -----------------------------------------------------------------------------

resource "azurerm_application_insights" "uc3" {
  name                = "ai-uc3-governance-appinsights"
  location            = data.azurerm_resource_group.alz.location
  resource_group_name = data.azurerm_resource_group.alz.name
  workspace_id        = data.azurerm_log_analytics_workspace.alz.id
  application_type    = "web"
  tags                = var.tags
}

# -----------------------------------------------------------------------------
# User-Assigned Managed Identity for the Governance Container App.
# Used for ACR pull, Key Vault access, and Log Analytics queries.
# -----------------------------------------------------------------------------

resource "azurerm_user_assigned_identity" "governance" {
  name                = "id-uc3-governance"
  location            = data.azurerm_resource_group.alz.location
  resource_group_name = data.azurerm_resource_group.alz.name
  tags                = var.tags
}

# ACR pull role — lets the Container App pull images
resource "azurerm_role_assignment" "governance_acr_pull" {
  scope                = data.azurerm_container_registry.alz.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.governance.principal_id
}

# Key Vault Secrets User — lets the app read secrets at runtime
resource "azurerm_role_assignment" "governance_kv_reader" {
  scope                = data.azurerm_key_vault.alz.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.governance.principal_id
}

# Log Analytics Reader — lets the app query telemetry data
resource "azurerm_role_assignment" "governance_law_reader" {
  scope                = data.azurerm_log_analytics_workspace.alz.id
  role_definition_name = "Log Analytics Reader"
  principal_id         = azurerm_user_assigned_identity.governance.principal_id
}

# Monitoring Reader — lets the app query Azure Monitor metrics
resource "azurerm_role_assignment" "governance_monitoring_reader" {
  scope                = data.azurerm_resource_group.alz.id
  role_definition_name = "Monitoring Reader"
  principal_id         = azurerm_user_assigned_identity.governance.principal_id
}

# -----------------------------------------------------------------------------
# Incident orchestration roles (formerly UC4) — granted to the same identity
# now that UC4 capabilities are absorbed into UC3.
# -----------------------------------------------------------------------------

# Cognitive Services OpenAI User — LLM inference via AI Foundry for orchestration agents
resource "azurerm_role_assignment" "governance_openai_user" {
  scope                = data.azurerm_cognitive_account.ai_services.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.governance.principal_id
}

# Service Bus Data Owner — send/receive on incident topics/queues
resource "azurerm_role_assignment" "governance_sb_owner" {
  scope                = azurerm_servicebus_namespace.uc4.id
  role_definition_name = "Azure Service Bus Data Owner"
  principal_id         = azurerm_user_assigned_identity.governance.principal_id
}

# Cosmos DB Built-in Data Contributor — read/write workflow state
resource "azurerm_cosmosdb_sql_role_assignment" "governance_cosmos" {
  resource_group_name = data.azurerm_resource_group.alz.name
  account_name        = azurerm_cosmosdb_account.uc4.name
  role_definition_id  = "${azurerm_cosmosdb_account.uc4.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azurerm_user_assigned_identity.governance.principal_id
  scope               = azurerm_cosmosdb_account.uc4.id
}
