# -----------------------------------------------------------------------------
# Outputs — values needed for cross-workload integration
# -----------------------------------------------------------------------------

# --- Telemetry ---

output "appinsights_connection_string" {
  description = "Application Insights connection string — set as APPLICATIONINSIGHTS_CONNECTION_STRING."
  value       = azurerm_application_insights.uc3.connection_string
  sensitive   = true
}

output "appinsights_instrumentation_key" {
  description = "Application Insights instrumentation key."
  value       = azurerm_application_insights.uc3.instrumentation_key
  sensitive   = true
}

# --- OTEL Collector ---

output "otel_collector_fqdn" {
  description = "Internal FQDN of the OTEL Collector — set as OTEL_EXPORTER_OTLP_ENDPOINT for other UCs."
  value       = azurerm_container_app.otel_collector.ingress[0].fqdn
}

output "otel_collector_endpoint" {
  description = "Full gRPC endpoint for the OTEL Collector."
  value       = "https://${azurerm_container_app.otel_collector.ingress[0].fqdn}"
}

# --- Governance API ---

output "governance_fqdn" {
  description = "Internal FQDN of the Governance API Container App."
  value       = azurerm_container_app.governance.ingress[0].fqdn
}

output "governance_identity_principal_id" {
  description = "Principal ID of the governance managed identity."
  value       = azurerm_user_assigned_identity.governance.principal_id
}

output "governance_identity_client_id" {
  description = "Client ID of the governance managed identity."
  value       = azurerm_user_assigned_identity.governance.client_id
}

# --- APIM ---

output "apim_gateway_url" {
  description = "APIM gateway URL for the UC3 governance API."
  value       = "${data.azurerm_api_management.alz.gateway_url}/uc3"
}

# --- Incident orchestration (formerly UC4) ---

output "service_bus_namespace" {
  description = "Service Bus namespace hostname."
  value       = "${azurerm_servicebus_namespace.uc4.name}.servicebus.windows.net"
}

output "cosmos_endpoint" {
  description = "Cosmos DB account endpoint."
  value       = azurerm_cosmosdb_account.uc4.endpoint
}
