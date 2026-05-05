#!/usr/bin/env bash
# demo-down.sh — Stop everything resumable to reduce idle Azure spend.
# Mirror: demo-up.sh restores all of these.
#
# Stops only RESUMABLE resources (no destruction, no data loss):
#   - Container Apps        -> min-replicas 0 (scale to zero)
#   - Jumpbox VM            -> deallocate (stops compute billing)
#   - APIM (Premium only)   -> stop via ARM REST (preserves config & VIP)
#
# Skips (NOT resumable / requires recreate):
#   - Foundry / AOAI deployments (delete & redeploy if needed)
#   - ACR (no stop; just stops pulls — premium price continues)
#   - Managed Grafana (no stop API)
#   - Log Analytics, Sentinel, Cosmos, KV, Storage, VNet, PEs, DNS

set -euo pipefail

SUBSCRIPTION="${SUBSCRIPTION:-1784740a-1cf6-416b-b3db-bda6985970aa}"
RG="${RG:-ai-lz-rg-msdn-mb44x}"
APIM_NAME="${APIM_NAME:-ai-alz-apim-i40e}"
JUMPBOX_VM="${JUMPBOX_VM:-ai-alz-jumpvm}"

# Container apps to scale-to-zero. Edit the list to keep one hot if desired.
CONTAINER_APPS=(
  ca-uaip-frontend
  ca-uc1-rag-agent
  ca-uc2-supervisor
  ca-uc3-governance
  ca-uc3-otel-collector
)

# --- pretty helpers --------------------------------------------------------
log()  { printf '\033[1;36m[demo-down]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  ⚠\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m  ✗\033[0m %s\n' "$*" >&2; }

az account set --subscription "$SUBSCRIPTION" >/dev/null
log "Subscription: $SUBSCRIPTION"
log "Resource group: $RG"
echo

# --- 1. Container Apps -> min 0 -------------------------------------------
log "Scaling Container Apps to min-replicas=0"
for app in "${CONTAINER_APPS[@]}"; do
  if az containerapp show -n "$app" -g "$RG" -o none 2>/dev/null; then
    az containerapp update -n "$app" -g "$RG" --min-replicas 0 -o none \
      && ok "$app -> min=0" \
      || err "$app failed to scale"
  else
    warn "$app not found, skipping"
  fi
done
echo

# --- 2. Jumpbox VM -> deallocate ------------------------------------------
log "Deallocating jumpbox VM ($JUMPBOX_VM)"
state=$(az vm get-instance-view -n "$JUMPBOX_VM" -g "$RG" \
  --query "instanceView.statuses[?starts_with(code,'PowerState/')].code" -o tsv 2>/dev/null || echo "")
if [[ -z "$state" ]]; then
  warn "VM $JUMPBOX_VM not found, skipping"
elif [[ "$state" == "PowerState/deallocated" ]]; then
  ok "$JUMPBOX_VM already deallocated"
else
  az vm deallocate -n "$JUMPBOX_VM" -g "$RG" --no-wait \
    && ok "$JUMPBOX_VM deallocate requested (--no-wait)" \
    || err "deallocate failed"
fi
echo

# --- 3. APIM -> stop (Premium tier only) ----------------------------------
log "Checking APIM ($APIM_NAME) tier"
sku=$(az apim show -n "$APIM_NAME" -g "$RG" --query "sku.name" -o tsv 2>/dev/null || echo "")
if [[ -z "$sku" ]]; then
  warn "APIM $APIM_NAME not found, skipping"
elif [[ "$sku" != "Premium" ]]; then
  warn "APIM SKU=$sku — stop/start only supported on Premium. Skipping."
  warn "  (If you don't need the demo for >24h, consider tearing it down via terraform.)"
else
  log "Stopping APIM via ARM REST (units -> 0)"
  # Stop is not yet in az CLI; use ARM REST to set capacity=0 (idle billing).
  # NOTE: True 'stop' via /applynetworkconfigurationupdates is preview;
  # the supported pattern is to scale capacity to 0.
  current_capacity=$(az apim show -n "$APIM_NAME" -g "$RG" --query "sku.capacity" -o tsv)
  log "  current capacity: $current_capacity (saving to /tmp/apim-capacity.txt for spin-up)"
  echo "$current_capacity" > /tmp/apim-capacity.txt
  if [[ "$current_capacity" == "0" ]]; then
    ok "APIM already at capacity=0"
  else
    az apim update -n "$APIM_NAME" -g "$RG" --sku-capacity 0 --no-wait -o none \
      && ok "APIM scale-to-0 requested (--no-wait, may take 30-45 min)" \
      || err "APIM scale failed"
  fi
fi
echo

log "Done. Run scripts/demo-up.sh to restore."
