# -----------------------------------------------------------------------------
# Governance API — Container App
# Runs the FastAPI governance API that queries telemetry and enforces policies.
# -----------------------------------------------------------------------------

resource "azurerm_container_app" "governance" {
  name                         = "ca-uc3-governance"
  container_app_environment_id = data.azurerm_container_app_environment.alz.id
  resource_group_name          = data.azurerm_resource_group.alz.name
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.governance.id]
  }

  registry {
    server   = data.azurerm_container_registry.alz.login_server
    identity = azurerm_user_assigned_identity.governance.id
  }

  template {
    min_replicas = 1
    max_replicas = var.governance_max_replicas

    container {
      name   = "governance-api"
      image  = "${data.azurerm_container_registry.alz.login_server}/uc3-governance-api:latest"
      cpu    = 0.5
      memory = "1Gi"

      # --- Log Analytics query configuration ---
      env {
        name  = "LOG_ANALYTICS_WORKSPACE_ID"
        value = data.azurerm_log_analytics_workspace.alz.workspace_id
      }

      # --- Managed identity ---
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.governance.client_id
      }

      # --- Telemetry ---
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.uc3.connection_string
      }
      env {
        name  = "OTEL_SERVICE_NAME"
        value = "uc3-governance-api"
      }
      env {
        name  = "OTEL_RESOURCE_ATTRIBUTES"
        value = "service.namespace=uaip,deployment.environment=poc"
      }

      # --- Incident orchestration (formerly UC4) ---
      env {
        name  = "AZURE_AI_ENDPOINT"
        value = data.azurerm_cognitive_account.ai_services.endpoint
      }
      env {
        name  = "AZURE_AI_DEPLOYMENT"
        value = var.azure_ai_deployment
      }
      env {
        name  = "SERVICE_BUS_NAMESPACE"
        value = "${azurerm_servicebus_namespace.uc4.name}.servicebus.windows.net"
      }
      env {
        name  = "COSMOS_ENDPOINT"
        value = azurerm_cosmosdb_account.uc4.endpoint
      }
      env {
        name  = "COSMOS_DATABASE"
        value = azurerm_cosmosdb_sql_database.incidents.name
      }
      env {
        name  = "UC1_RAG_ENDPOINT"
        value = var.uc1_rag_endpoint
      }
      env {
        name  = "APPROVAL_TIMEOUT_MINUTES"
        value = tostring(var.approval_timeout_minutes)
      }
      env {
        name  = "AUTO_APPROVE_CONFIDENCE_THRESHOLD"
        value = tostring(var.auto_approve_confidence_threshold)
      }

      # --- Policy gateway digest (TC-2f) ---
      # Source files are staged into the image at /app/policy_sources/*.tf
      # by `make stage-policy-sources` (Makefile target).
      env {
        name  = "APIM_POLICY_PATHS"
        value = "/app/policy_sources/*.tf"
      }

      # --- Health probes ---
      liveness_probe {
        transport        = "HTTP"
        path             = "/health"
        port             = 8000
        timeout          = 5
        interval_seconds = 10
      }

      readiness_probe {
        transport        = "HTTP"
        path             = "/health"
        port             = 8000
        timeout          = 5
        interval_seconds = 10
      }

      startup_probe {
        transport               = "HTTP"
        path                    = "/health"
        port                    = 8000
        timeout                 = 5
        interval_seconds        = 3
        failure_count_threshold = 10
      }
    }

    # Scale on HTTP concurrency — read-heavy, lower threshold than UC2
    http_scale_rule {
      name                = "http-concurrency"
      concurrent_requests = "10"
    }
  }

  ingress {
    external_enabled = true # CAE is already internal (ILB) — "external" here means VNet-accessible
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  depends_on = [
    azurerm_role_assignment.governance_acr_pull
  ]
}
