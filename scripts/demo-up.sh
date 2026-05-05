#!/usr/bin/env bash
# demo-up.sh — Restore everything that demo-down.sh stopped.

set -euo pipefail

SUBSCRIPTION="${SUBSCRIPTION:-1784740a-1cf6-416b-b3db-bda6985970aa}"
RG="${RG:-ai-lz-rg-msdn-mb44x}"
APIM_NAME="${APIM_NAME:-ai-alz-apim-i40e}"
JUMPBOX_VM="${JUMPBOX_VM:-ai-alz-jumpvm}"

# Apps + their target min-replicas on resume.
# Keep ca-uc2-supervisor at 2 (HTTP concurrency rule), others at 1.
declare -A MIN_REPLICAS=(
  [ca-uaip-frontend]=1
  [ca-uc1-rag-agent]=1
  [ca-uc2-supervisor]=2
  [ca-uc3-governance]=1
  [ca-uc3-otel-collector]=1
)

log()  { printf '\033[1;36m[demo-up]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  ⚠\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m  ✗\033[0m %s\n' "$*" >&2; }

az account set --subscription "$SUBSCRIPTION" >/dev/null
log "Subscription: $SUBSCRIPTION"
log "Resource group: $RG"
echo

# --- 1. APIM first (slowest to come back) ---------------------------------
sku=$(az apim show -n "$APIM_NAME" -g "$RG" --query "sku.name" -o tsv 2>/dev/null || echo "")
if [[ -z "$sku" ]]; then
  warn "APIM $APIM_NAME not found"
elif [[ "$sku" == "Premium" ]]; then
  target_capacity=1
  if [[ -f /tmp/apim-capacity.txt ]]; then
    saved=$(cat /tmp/apim-capacity.txt)
    [[ "$saved" =~ ^[0-9]+$ && "$saved" -gt 0 ]] && target_capacity=$saved
  fi
  current=$(az apim show -n "$APIM_NAME" -g "$RG" --query "sku.capacity" -o tsv)
  if [[ "$current" -ge "$target_capacity" ]]; then
    ok "APIM already at capacity=$current"
  else
    log "Restoring APIM capacity -> $target_capacity (this can take 30-45 min)"
    az apim update -n "$APIM_NAME" -g "$RG" --sku-capacity "$target_capacity" --no-wait -o none \
      && ok "APIM scale requested" || err "APIM scale failed"
  fi
fi
echo

# --- 2. Jumpbox VM --------------------------------------------------------
state=$(az vm get-instance-view -n "$JUMPBOX_VM" -g "$RG" \
  --query "instanceView.statuses[?starts_with(code,'PowerState/')].code" -o tsv 2>/dev/null || echo "")
if [[ -z "$state" ]]; then
  warn "VM $JUMPBOX_VM not found"
elif [[ "$state" == "PowerState/running" ]]; then
  ok "$JUMPBOX_VM already running"
else
  log "Starting $JUMPBOX_VM"
  az vm start -n "$JUMPBOX_VM" -g "$RG" --no-wait \
    && ok "start requested (--no-wait)" || err "start failed"
fi
echo

# --- 3. Container Apps ----------------------------------------------------
log "Restoring Container App min-replicas"
for app in "${!MIN_REPLICAS[@]}"; do
  min=${MIN_REPLICAS[$app]}
  if az containerapp show -n "$app" -g "$RG" -o none 2>/dev/null; then
    az containerapp update -n "$app" -g "$RG" --min-replicas "$min" -o none \
      && ok "$app -> min=$min" \
      || err "$app failed to scale"
  else
    warn "$app not found"
  fi
done
echo

log "Done. APIM may still be warming; check with:"
log "  az apim show -n $APIM_NAME -g $RG --query '{state:provisioningState,cap:sku.capacity}'"
