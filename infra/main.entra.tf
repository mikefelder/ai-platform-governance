# =============================================================================
# UC3 Governance Hub - Entra ID app registration
#
# Defines the "uaip-governance" app registration that fronts the governance API.
# App roles are the canonical authority for who can:
#   - request approvals (workflow-orchestrator, incident-commanders)
#   - respond to approvals as approver (senior-engineers for P2, on-call for P1/P0)
#
# These role values MUST match POL-INCIDENT-RESPONSE.severity_rules[*].approver_role
# in services/governance-api/policy_seed/.
#
# IMPORTANT - migration note for the MSDN subscription (existing app):
#   The app already exists out-of-band as appId 06bf98a1-d997-4a60-a616-3c384828f408.
#   Use `terraform import` to adopt it before the first apply:
#
#     terraform import azuread_application.uaip_governance \
#       /applications/<object-id>
#
#   Get the object-id with:
#     az ad app show --id 06bf98a1-d997-4a60-a616-3c384828f408 --query id -o tsv
#
#   For new subscriptions, terraform apply will create it fresh and the role IDs
#   below will be assigned (they are stable across environments).
# =============================================================================

resource "azuread_application" "uaip_governance" {
  display_name     = "uaip-governance"
  sign_in_audience = "AzureADMyOrg"

  api {
    requested_access_token_version = 2
  }

  app_role {
    id                   = "fb87977e-5136-4a9a-9795-425db58b0d41"
    allowed_member_types = ["User", "Application"]
    description          = "Incident commander - can request and respond to approvals."
    display_name         = "Incident Commanders"
    enabled              = true
    value                = "incident-commanders"
  }

  app_role {
    id                   = "f32170ba-cc6b-46a6-b359-19d80841dc1b"
    allowed_member_types = ["User", "Application"]
    description          = "Can request approvals on incidents and orchestrate workflow steps."
    display_name         = "Workflow Orchestrator"
    enabled              = true
    value                = "workflow-orchestrator"
  }

  app_role {
    id                   = "34f76a2e-2219-451a-a023-568c2a8f2815"
    allowed_member_types = ["User", "Application"]
    description          = "Senior engineer - approver role for P2 incident remediation actions."
    display_name         = "Senior Engineers"
    enabled              = true
    value                = "senior-engineers"
  }

  app_role {
    id                   = "13a86c95-7681-47ad-8c90-6b3315b408df"
    allowed_member_types = ["User", "Application"]
    description          = "On-call engineer - approver role for P1/P0 incident remediation actions."
    display_name         = "On-Call"
    enabled              = true
    value                = "on-call"
  }
}

resource "azuread_service_principal" "uaip_governance" {
  client_id = azuread_application.uaip_governance.client_id
}

output "uaip_governance_app_id" {
  description = "Client/Application ID of the uaip-governance Entra app."
  value       = azuread_application.uaip_governance.client_id
}

output "uaip_governance_app_role_ids" {
  description = "Map of role value -> role ID for uaip-governance app roles."
  value = {
    "incident-commanders"    = "fb87977e-5136-4a9a-9795-425db58b0d41"
    "workflow-orchestrator"  = "f32170ba-cc6b-46a6-b359-19d80841dc1b"
    "senior-engineers"       = "34f76a2e-2219-451a-a023-568c2a8f2815"
    "on-call"                = "13a86c95-7681-47ad-8c90-6b3315b408df"
  }
}
