# -----------------------------------------------------------------------------
# Event Grid — system topic for monitoring/ticketing event subscriptions.
# Delivers events to the Service Bus incidents-inbound topic.
# -----------------------------------------------------------------------------

resource "azurerm_eventgrid_system_topic" "uc4" {
  name                   = "evgt-uc4-incident"
  location               = "global"
  resource_group_name    = data.azurerm_resource_group.alz.name
  source_resource_id     = data.azurerm_resource_group.alz.id
  topic_type             = "Microsoft.Resources.ResourceGroups"
  tags                   = var.tags
}

# Subscription: forward resource health events to Service Bus incidents-inbound
resource "azurerm_eventgrid_system_topic_event_subscription" "resource_health_to_sb" {
  name                = "resource-health-to-sb"
  system_topic        = azurerm_eventgrid_system_topic.uc4.name
  resource_group_name = data.azurerm_resource_group.alz.name

  service_bus_topic_endpoint_id = azurerm_servicebus_topic.incidents_inbound.id

  included_event_types = [
    "Microsoft.ResourceHealth.ResourceAnnotated",
  ]

  retry_policy {
    max_delivery_attempts = 5
    event_time_to_live    = 1440  # 24 hours
  }
}
