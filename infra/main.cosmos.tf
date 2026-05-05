# -----------------------------------------------------------------------------
# Cosmos DB — workflow state store for UC4 incident orchestrator.
# NoSQL API, partition key per incident_id for event-sourcing pattern.
# -----------------------------------------------------------------------------

locals {
  cosmos_name = coalesce(
    var.cosmos_db_account_name,
    "cosmos-uc4-incident-${lower(substr(data.azurerm_resource_group.alz.name, -5, -1))}"
  )
}

resource "azurerm_cosmosdb_account" "uc4" {
  name                = local.cosmos_name
  location            = data.azurerm_resource_group.alz.location
  resource_group_name = data.azurerm_resource_group.alz.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  # Disable key-based auth — managed identity only
  local_authentication_disabled = true

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = data.azurerm_resource_group.alz.location
    failover_priority = 0
  }

  tags = var.tags
}

resource "azurerm_cosmosdb_sql_database" "incidents" {
  name                = "incidents"
  resource_group_name = data.azurerm_resource_group.alz.name
  account_name        = azurerm_cosmosdb_account.uc4.name
}

# Workflow state documents (current state per incident)
resource "azurerm_cosmosdb_sql_container" "workflow_state" {
  name                = "workflow-state"
  resource_group_name = data.azurerm_resource_group.alz.name
  account_name        = azurerm_cosmosdb_account.uc4.name
  database_name       = azurerm_cosmosdb_sql_database.incidents.name
  partition_key_paths = ["/incident_id"]

  default_ttl = -1  # No TTL — retain for audit

  indexing_policy {
    indexing_mode = "consistent"
    included_path { path = "/*" }
    excluded_path { path = "/_etag/?" }
  }
}

# Immutable event log (event-sourcing — one doc per state transition)
resource "azurerm_cosmosdb_sql_container" "events" {
  name                = "events"
  resource_group_name = data.azurerm_resource_group.alz.name
  account_name        = azurerm_cosmosdb_account.uc4.name
  database_name       = azurerm_cosmosdb_sql_database.incidents.name
  partition_key_paths = ["/incident_id"]

  default_ttl = -1

  indexing_policy {
    indexing_mode = "consistent"
    included_path { path = "/*" }
    excluded_path { path = "/_etag/?" }
  }
}

# Pending approval requests
resource "azurerm_cosmosdb_sql_container" "approvals" {
  name                = "approvals"
  resource_group_name = data.azurerm_resource_group.alz.name
  account_name        = azurerm_cosmosdb_account.uc4.name
  database_name       = azurerm_cosmosdb_sql_database.incidents.name
  partition_key_paths = ["/incident_id"]

  # TTL 7 days for approval requests (resolved ones expire automatically)
  default_ttl = 604800

  indexing_policy {
    indexing_mode = "consistent"
    included_path { path = "/*" }
    excluded_path { path = "/_etag/?" }
  }
}
