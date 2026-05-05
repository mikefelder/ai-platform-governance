# -----------------------------------------------------------------------------
# Service Bus namespace — event ingestion, approval request/response,
# and workflow message queues for the UC4 incident orchestrator.
# -----------------------------------------------------------------------------

locals {
  sb_name = "sb-uc4-incident-${lower(substr(data.azurerm_resource_group.alz.name, -5, -1))}"
}

resource "azurerm_servicebus_namespace" "uc4" {
  name                = local.sb_name
  location            = data.azurerm_resource_group.alz.location
  resource_group_name = data.azurerm_resource_group.alz.name
  sku                 = var.service_bus_sku
  tags                = var.tags
}

# --- Topics ---

# Incoming incidents from Event Grid and external systems
resource "azurerm_servicebus_topic" "incidents_inbound" {
  name         = "incidents-inbound"
  namespace_id = azurerm_servicebus_namespace.uc4.id
}

# Human approval requests (published by orchestrator, consumed by approval portal)
resource "azurerm_servicebus_topic" "approval_requests" {
  name         = "approval-requests"
  namespace_id = azurerm_servicebus_namespace.uc4.id
}

# Human approval responses (published by approvers, consumed by orchestrator)
resource "azurerm_servicebus_topic" "approval_responses" {
  name         = "approval-responses"
  namespace_id = azurerm_servicebus_namespace.uc4.id
}

# Resolved/closed incident events (for UC3 SIEM forwarding)
resource "azurerm_servicebus_topic" "incidents_resolved" {
  name         = "incidents-resolved"
  namespace_id = azurerm_servicebus_namespace.uc4.id
}

# --- Subscriptions ---

resource "azurerm_servicebus_subscription" "orchestrator_incidents" {
  name               = "orchestrator"
  topic_id           = azurerm_servicebus_topic.incidents_inbound.id
  max_delivery_count = 5
}

resource "azurerm_servicebus_subscription" "orchestrator_approvals" {
  name               = "orchestrator"
  topic_id           = azurerm_servicebus_topic.approval_responses.id
  max_delivery_count = 5
}

resource "azurerm_servicebus_subscription" "governance_resolved" {
  name               = "governance-hub"
  topic_id           = azurerm_servicebus_topic.incidents_resolved.id
  max_delivery_count = 3
}
