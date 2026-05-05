# -----------------------------------------------------------------------------
# Platform / ALZ references — these point to resources already deployed by the
# uaip-platform-alz Terraform.
# -----------------------------------------------------------------------------

variable "subscription_id" {
  description = "Azure subscription ID where the ALZ was deployed."
  type        = string
}

variable "resource_group_name" {
  description = "Name of the ALZ resource group (e.g. ai-lz-rg-standalone-yc9gj)."
  type        = string
}

variable "location" {
  description = "Azure region (must match ALZ deployment)."
  type        = string
  default     = "australiaeast"
}

variable "container_app_environment_name" {
  description = "Name of the Container App Environment deployed by the ALZ."
  type        = string
}

variable "container_registry_name" {
  description = "Name of the Azure Container Registry deployed by the ALZ."
  type        = string
}

variable "log_analytics_workspace_name" {
  description = "Name of the Log Analytics Workspace deployed by the ALZ."
  type        = string
}

variable "apim_name" {
  description = "Name of the API Management instance deployed by the ALZ."
  type        = string
}

variable "key_vault_name" {
  description = "Name of the GenAI Key Vault deployed by the ALZ."
  type        = string
}

variable "ai_services_name" {
  description = "Name of the AI Services (Cognitive Services) account deployed by the ALZ."
  type        = string
}

variable "azure_ai_deployment" {
  description = "Name of the AI Foundry model deployment to use for orchestration agents."
  type        = string
  default     = "gpt-4.1"
}

# -----------------------------------------------------------------------------
# UC3 workload configuration
# -----------------------------------------------------------------------------

variable "governance_image_tag" {
  description = "Container image tag for the governance-api (e.g. latest, v1.0.0)."
  type        = string
  default     = "latest"
}

variable "governance_min_replicas" {
  description = "Minimum number of Container App replicas."
  type        = number
  default     = 1
}

variable "governance_max_replicas" {
  description = "Maximum number of Container App replicas."
  type        = number
  default     = 3
}

variable "otel_collector_image" {
  description = "OTEL Collector container image."
  type        = string
  default     = "otel/opentelemetry-collector-contrib:0.100.0"
}

# -----------------------------------------------------------------------------
# Incident orchestration configuration (formerly UC4)
# -----------------------------------------------------------------------------

variable "service_bus_sku" {
  description = "Service Bus namespace SKU."
  type        = string
  default     = "Standard"

  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.service_bus_sku)
    error_message = "Must be Basic, Standard, or Premium."
  }
}

variable "cosmos_db_account_name" {
  description = "Name for the Cosmos DB account. Leave empty to auto-generate."
  type        = string
  default     = ""
}

variable "approval_timeout_minutes" {
  description = "Default timeout (minutes) before an unanswered approval request is auto-escalated."
  type        = number
  default     = 60
}

variable "auto_approve_confidence_threshold" {
  description = "Confidence score (0.0–1.0) above which the orchestrator auto-approves without human review."
  type        = number
  default     = 0.95
}

variable "uc1_rag_endpoint" {
  description = "HTTP endpoint for the UC1 RAG Agent API (via APIM)."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all workload resources."
  type        = map(string)
  default = {
    workload = "uc3-governance-hub"
    program  = "uaip"
  }
}
