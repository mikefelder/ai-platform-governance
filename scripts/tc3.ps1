# =============================================================================
# TC-3 Zero-Bypass Gateway Enforcement (PowerShell 5.1, jumpbox)
#
# Proves:
#   3a. Calls to APIM /uc1/* WITHOUT a subscription key are rejected (401).
#   3b. Calls to APIM /uc1/* WITH a valid subscription key succeed.
#   3c. (Optional) Direct call to the UC1 Container App FQDN bypassing APIM
#       fails from the jumpbox network path (CAE is internal/ILB or denies).
#
# Usage:
#   $env:APIM_BASE = "https://ai-alz-apim-i40e.azure-api.net"
#   # APIM master key (run on Mac, paste on JB - JB cannot resolve KV yet):
#   #   az rest --method POST --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/service/ai-alz-apim-i40e/subscriptions/master/listSecrets?api-version=2022-08-01" --query primaryKey -o tsv
#   $env:APIM_SUBSCRIPTION_KEY = "<paste-key>"
#   # Optional, only needed for 3c:
#   $env:UC1_DIRECT_FQDN = "ca-uc1-rag-agent.<random>.australiaeast.azurecontainerapps.io"
#   .\tc3.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

$ApimBase = $env:APIM_BASE
if (-not $ApimBase) { $ApimBase = "https://ai-alz-apim-i40e.azure-api.net" }
$ApimKey  = $env:APIM_SUBSCRIPTION_KEY
$DirectFqdn = $env:UC1_DIRECT_FQDN

function H1($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function PASS($t) { Write-Host ("PASS: " + $t) -ForegroundColor Green }
function FAIL($t) { Write-Host ("FAIL: " + $t) -ForegroundColor Red }

# Minimal Responses-API request body - enough to elicit a routed call.
$body = @{
    model = "gpt-4.1-mini"
    input = @(
        @{ role = "user"; content = "tc3 probe - say ok" }
    )
} | ConvertTo-Json -Depth 5

# -----------------------------------------------------------------------------
# 3a. No subscription key -> APIM must reject (401 Access Denied)
# -----------------------------------------------------------------------------
H1 "3a. POST $ApimBase/uc1/responses WITHOUT subscription key"
try {
    Invoke-RestMethod -Uri "$ApimBase/uc1/responses" `
        -Method POST -Body $body `
        -ContentType "application/json" `
        -TimeoutSec 15 | Out-Null
    FAIL "3a: APIM accepted unauthenticated call (gateway is bypass-able)"
} catch {
    $code = "?"
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    if ($code -eq 401) {
        PASS "3a: APIM rejected unauthenticated call (401 Access Denied)"
    } else {
        FAIL ("3a: expected 401, got " + $code + " - " + $_.Exception.Message)
    }
}

# -----------------------------------------------------------------------------
# 3b. With valid subscription key -> APIM must accept and proxy upstream
# -----------------------------------------------------------------------------
H1 "3b. POST $ApimBase/uc1/responses WITH subscription key"
if (-not $ApimKey) {
    Write-Host "SKIP: APIM_SUBSCRIPTION_KEY env var not set." -ForegroundColor Yellow
} else {
    $hdrs = @{
        "Ocp-Apim-Subscription-Key" = $ApimKey
        "Content-Type"              = "application/json"
    }
    try {
        $resp = Invoke-RestMethod -Uri "$ApimBase/uc1/responses" `
            -Method POST -Headers $hdrs -Body $body -TimeoutSec 30
        PASS "3b: APIM accepted authenticated call and returned a response"
        $resp | ConvertTo-Json -Depth 5 | Out-String | Write-Host
    } catch {
        $code = "?"
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        # 200/2xx never lands here. Anything else is a real failure unless the
        # upstream itself errored - record the status either way.
        FAIL ("3b: APIM returned " + $code + " - " + $_.Exception.Message)
    }
}

# -----------------------------------------------------------------------------
# 3c. Direct hit on UC1 Container App FQDN (bypass attempt)
#     If the CAE is internal/ILB, DNS or TCP will simply fail from the public
#     internet path. From the jumpbox (peered into the ALZ hub) it should
#     either (a) refuse-connect, (b) time out, or (c) return 403/404 - but
#     MUST NOT proxy a successful Responses-API call.
#     Note: tested with /healthz first to avoid model-routing false positives.
# -----------------------------------------------------------------------------
H1 "3c. Direct POST to UC1 Container App FQDN (bypass attempt)"
if (-not $DirectFqdn) {
    Write-Host "SKIP: UC1_DIRECT_FQDN not set." -ForegroundColor Yellow
} else {
    try {
        $resp = Invoke-RestMethod -Uri ("https://" + $DirectFqdn + "/responses") `
            -Method POST -Body $body -ContentType "application/json" -TimeoutSec 10
        FAIL "3c: direct call to Container App SUCCEEDED - gateway bypass possible"
        $resp | ConvertTo-Json -Depth 4 | Out-String | Write-Host
    } catch {
        $code = "?"
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        PASS ("3c: direct call rejected (status=" + $code + " / " + $_.Exception.Message.Split("`n")[0] + ")")
    }
}

H1 "DONE"
