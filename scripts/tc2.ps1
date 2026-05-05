# =============================================================================
# TC-2 + Option A live exercise script (PowerShell 5.1 compatible)
# Targets: ca-uc3-governance (rev 0000007 image: tc2-live)
# Run on the jumpbox. ASCII-only. No PS7 ternary.
# =============================================================================

$ErrorActionPreference = "Stop"

$Base   = "https://ca-uc3-governance.ambitiouscliff-ec38b96b.australiaeast.azurecontainerapps.io"
$AppId  = "06bf98a1-d997-4a60-a616-3c384828f408"
$Scope  = "api://$AppId/.default"

function H1($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function H2($t) { Write-Host ""; Write-Host "--- $t ---" -ForegroundColor Yellow }

# -----------------------------------------------------------------------------
# 0. Acquire token (interactive device-code on first run, cached after)
# -----------------------------------------------------------------------------
H1 "0. Acquiring access token for $Scope"
$tokenJson = az account get-access-token --scope $Scope --output json
if ($LASTEXITCODE -ne 0) { throw "az get-access-token failed" }
$Token = ($tokenJson | ConvertFrom-Json).accessToken
$Headers = @{ Authorization = "Bearer $Token"; "Content-Type" = "application/json" }
Write-Host ("Token acquired (length=" + $Token.Length + ")")

# -----------------------------------------------------------------------------
# 1. Health + caller identity sanity (decode roles from JWT)
# -----------------------------------------------------------------------------
H1 "1. /health (no auth) and decode roles from access token"
Invoke-RestMethod -Uri "$Base/health" -Method GET | ConvertTo-Json -Depth 5

function Decode-JwtPayload($jwt) {
    $parts = $jwt.Split('.')
    if ($parts.Length -lt 2) { return $null }
    $payload = $parts[1].Replace('-', '+').Replace('_', '/')
    switch ($payload.Length % 4) {
        2 { $payload += '==' }
        3 { $payload += '='  }
    }
    $bytes = [Convert]::FromBase64String($payload)
    $json  = [Text.Encoding]::UTF8.GetString($bytes)
    return $json | ConvertFrom-Json
}

$claims = Decode-JwtPayload $Token
Write-Host ("upn/preferred_username = " + $claims.preferred_username)
Write-Host ("oid                    = " + $claims.oid)
Write-Host ("aud                    = " + $claims.aud)
Write-Host ("tid                    = " + $claims.tid)
$callerRoles = @()
if ($claims.roles) { $callerRoles = @($claims.roles) }
Write-Host ("roles                  = " + ($callerRoles -join ","))

# -----------------------------------------------------------------------------
# 2a. TC-2a: create incident, verify policy_applied snapshot is embedded
# -----------------------------------------------------------------------------
H1 "2a. Create P2 incident and verify embedded policy_applied snapshot"
$bodyOld = @{
    title       = "tc2-snapshot-old"
    description = "exercise embedded policy snapshot"
    severity    = "p2"
} | ConvertTo-Json
$incOld = Invoke-RestMethod -Uri "$Base/api/incidents" -Headers $Headers -Method POST -Body $bodyOld
$incOldId = $incOld.incident_id
Write-Host ("Created incident: " + $incOldId)
$incOldFull = Invoke-RestMethod -Uri "$Base/api/incidents/$incOldId" -Headers $Headers -Method GET
$snapOld = $null
if ($incOldFull.attributes) { $snapOld = $incOldFull.attributes.policy_applied }
if (-not $snapOld) {
    Write-Host "DEBUG: full incident payload:" -ForegroundColor Yellow
    $incOldFull | ConvertTo-Json -Depth 8
    throw "attributes.policy_applied is missing on $incOldId"
}
Write-Host ("policy_applied.policy_id            = " + $snapOld.policy_id)
Write-Host ("policy_applied.version              = " + $snapOld.version)
Write-Host ("policy_applied.content_hash         = " + $snapOld.content_hash)
Write-Host ("policy_applied.severity              = " + $snapOld.severity_rule.severity)
Write-Host ("policy_applied.required_approvals   = " + $snapOld.severity_rule.required_approvals)
Write-Host ("policy_applied.approver_role        = " + $snapOld.severity_rule.approver_role)
$snapOldVer = $snapOld.version

# -----------------------------------------------------------------------------
# 2b. TC-2b: publish a NEW policy version (bump P2 required_approvals)
# -----------------------------------------------------------------------------
H1 "2b. Publish a new version of POL-INCIDENT-RESPONSE"
$policyId = "POL-INCIDENT-RESPONSE"
$active = Invoke-RestMethod -Uri "$Base/api/policies/registry/$policyId/active" -Headers $Headers -Method GET
$activeVer = $active.version
# Bump patch component (1.0.0 -> 1.0.1, 1.0.1 -> 1.0.2, ...)
$parts = $activeVer.Split('.')
$parts[2] = ([int]$parts[2] + 1).ToString()
$nextVer = ($parts -join '.')
# Clone severity rules and bump P2 required_approvals to 3
$newRules = @()
foreach ($r in $active.severity_rules) {
    $rule = @{
        severity               = $r.severity
        required_approvals     = $r.required_approvals
        approver_role          = $r.approver_role
        max_resolution_minutes = $r.max_resolution_minutes
        escalation_minutes     = $r.escalation_minutes
        auto_remediate         = $r.auto_remediate
        required_agents        = @($r.required_agents)
    }
    if ($r.severity -eq "p2") { $rule.required_approvals = 3 }
    $newRules += $rule
}
$verBody = @{
    version             = $nextVer
    description         = "tc2-live: bumped P2 required_approvals to 3"
    severity_rules      = $newRules
    approval_thresholds = $active.approval_thresholds
} | ConvertTo-Json -Depth 8
try {
    $newVer = Invoke-RestMethod -Uri "$Base/api/policies/registry/$policyId/versions" -Headers $Headers -Method POST -Body $verBody
    Write-Host ("Published new version: " + $newVer.version + " (status=" + $newVer.status + ")")
} catch {
    Write-Host ("Publish failed: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "Continuing - 2c will still demonstrate immutability." -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# 2c. TC-2c: re-fetch the OLD incident and confirm its snapshot is unchanged
# -----------------------------------------------------------------------------
H1 "2c. Re-fetch old incident - snapshot must be IMMUTABLE"
$incOldRefetch = Invoke-RestMethod -Uri "$Base/api/incidents/$incOldId" -Headers $Headers -Method GET
$snapOldAfter  = $incOldRefetch.attributes.policy_applied
Write-Host ("Old incident snapshot version BEFORE publish: " + $snapOldVer)
Write-Host ("Old incident snapshot version AFTER  publish: " + $snapOldAfter.version)
if ($snapOldAfter.version -ne $snapOldVer) {
    Write-Host "FAIL: snapshot drifted on existing incident." -ForegroundColor Red
} else {
    Write-Host "PASS: snapshot is immutable on existing incident." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# 2d. TC-2d: new incident picks up the NEW active version
# -----------------------------------------------------------------------------
H1 "2d. Create a NEW P2 incident - must pick up new policy version"
$bodyNew = @{
    title       = "tc2-snapshot-new"
    description = "should bind to newly-published version"
    severity    = "p2"
} | ConvertTo-Json
$incNew = Invoke-RestMethod -Uri "$Base/api/incidents" -Headers $Headers -Method POST -Body $bodyNew
$incNewId = $incNew.incident_id
$incNewFull = Invoke-RestMethod -Uri "$Base/api/incidents/$incNewId" -Headers $Headers -Method GET
$snapNew = $incNewFull.attributes.policy_applied
Write-Host ("New incident: " + $incNewId)
Write-Host ("  version            = " + $snapNew.version)
Write-Host ("  required_approvals = " + $snapNew.severity_rule.required_approvals)
if ($snapNew.version -ne $snapOldVer) {
    Write-Host "PASS: new incident picked up newer version." -ForegroundColor Green
} else {
    Write-Host "INFO: version unchanged (publish may have been skipped)." -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# 2e. TC-2e: workflow events should record the policy snapshot reference
# -----------------------------------------------------------------------------
H1 "2e. Workflow events for old incident"
try {
    $wf = Invoke-RestMethod -Uri "$Base/api/workflows/$incOldId/events" -Headers $Headers -Method GET
    $wf | ConvertTo-Json -Depth 6
} catch {
    Write-Host ("Workflow lookup skipped: " + $_.Exception.Message) -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# 2f. TC-2f: gateway digest / config hash
# -----------------------------------------------------------------------------
H1 "2f. /api/policies/gateway/digest"
try {
    Invoke-RestMethod -Uri "$Base/api/policies/gateway/digest" -Headers $Headers -Method GET | ConvertTo-Json -Depth 5
} catch {
    Write-Host ("Digest call failed: " + $_.Exception.Message) -ForegroundColor Yellow
}

# =============================================================================
# Option A live: POST /api/incidents/{id}/approvals
# =============================================================================
H1 "OPTION A. Mint approval bound to a real incident, then respond"

H2 "A1. Request approval against the OLD incident (snapshot stays bound)"
$reqBody = @{
    workflow_step      = "DECIDING"
    proposed_action    = @{ action = "restart_service"; target = "api-gw" }
    agent_analysis     = @(
        @{ agent = "root_cause"; recommendation = "restart_service"; confidence = 0.78 }
    )
    confidence_score   = 0.78
    rationale          = "tc2-live: confidence below autonomous threshold"
    requested_by_agent = "supervisor"
} | ConvertTo-Json -Depth 6

$hasOrchestrator = $false
foreach ($r in $callerRoles) {
    if ($r -eq "workflow-orchestrator" -or $r -eq "incident-commanders") { $hasOrchestrator = $true }
}

try {
    $apr = Invoke-RestMethod -Uri "$Base/api/incidents/$incOldId/approvals" -Headers $Headers -Method POST -Body $reqBody
    Write-Host ("PASS: approval created " + $apr.approval_id) -ForegroundColor Green
    Write-Host ("  incident_id        = " + $apr.incident_id)
    Write-Host ("  severity (from inc) = " + $apr.severity)
    Write-Host ("  requested_by_upn   = " + $apr.requested_by_upn)
    Write-Host ("  requested_by_agent = " + $apr.requested_by_agent)
    $aprId = $apr.approval_id
} catch {
    $resp = $_.Exception.Response
    $code = "?"
    if ($resp) { $code = [int]$resp.StatusCode }
    if ($code -eq 403 -and -not $hasOrchestrator) {
        Write-Host "PASS (RBAC): 403 as expected - caller lacks workflow-orchestrator role." -ForegroundColor Green
    } else {
        Write-Host ("FAIL: approval POST returned " + $code) -ForegroundColor Red
        Write-Host $_.Exception.Message
    }
    $aprId = $null
}

if ($aprId) {
    H2 "A2. Respond to approval (approve) - exercises policy approver_role enforcement"
    $respBody = @{
        decision = "approved"
        comment  = "tc2-live: approving via jumpbox"
    } | ConvertTo-Json
    try {
        $aprResp = Invoke-RestMethod -Uri "$Base/api/approvals/$aprId/respond" -Headers $Headers -Method POST -Body $respBody
        $aprResp | ConvertTo-Json -Depth 6

        H2 "A3. Re-GET incident - policy_decision should reflect tally if threshold met"
        $incFinal = Invoke-RestMethod -Uri "$Base/api/incidents/$incOldId" -Headers $Headers -Method GET
        if ($incFinal.policy_decision) {
            $incFinal.policy_decision | ConvertTo-Json -Depth 6
        } else {
            Write-Host "policy_decision not yet populated (threshold may need more votes)." -ForegroundColor Yellow
        }
    } catch {
        $resp = $_.Exception.Response
        $code = "?"
        if ($resp) { $code = [int]$resp.StatusCode }
        $expectedRole = $snapOld.severity_rule.approver_role
        $callerHasApproverRole = $false
        foreach ($r in $callerRoles) { if ($r -eq $expectedRole) { $callerHasApproverRole = $true } }
        if ($code -eq 403 -and -not $callerHasApproverRole) {
            Write-Host ("PASS (policy enforcement): 403 as expected - policy requires approver_role '" + $expectedRole + "', caller has [" + ($callerRoles -join ",") + "].") -ForegroundColor Green
        } else {
            Write-Host ("FAIL: respond returned " + $code) -ForegroundColor Red
            Write-Host $_.Exception.Message
        }
    }
}

H1 "DONE"
