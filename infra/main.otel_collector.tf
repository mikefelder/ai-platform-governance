# -----------------------------------------------------------------------------
# OpenTelemetry Collector — Container App
# Centralized OTEL Collector that receives telemetry from all UCs,
# normalizes schemas, and exports to Log Analytics / Sentinel.
# -----------------------------------------------------------------------------

# The OTEL Collector config is baked into the image or mounted via volume.
# For Container Apps, we use environment variables to configure the collector
# since volume mounts from host are not supported. The config is embedded
# in the image at build time.

resource "azurerm_container_app" "otel_collector" {
  name                         = "ca-uc3-otel-collector"
  container_app_environment_id = data.azurerm_container_app_environment.alz.id
  resource_group_name          = data.azurerm_resource_group.alz.name
  revision_mode                = "Single"
  tags                         = var.tags

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "otel-collector"
      image  = var.otel_collector_image
      cpu    = 0.5
      memory = "1Gi"

      # Azure Monitor exporter needs the connection string
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.uc3.connection_string
      }

      liveness_probe {
        transport        = "HTTP"
        path             = "/"
        port             = 13133 # OTEL Collector health check extension
        timeout          = 5
        interval_seconds = 10
      }

      readiness_probe {
        transport        = "HTTP"
        path             = "/"
        port             = 13133
        timeout          = 5
        interval_seconds = 10
      }
    }
  }

  ingress {
    external_enabled = true # VNet-accessible — AWS agents send OTLP via APIM
    target_port      = 4318  # OTLP/HTTP (APIM can't proxy gRPC; 4317 is gRPC)
    transport        = "http"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}
