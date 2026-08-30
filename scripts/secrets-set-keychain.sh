#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/keychain.sh"

LABELS=("OpenAI" "DeepSeek" "Anthropic" "Alibaba" "Tencent" "Volcengine" "OpenCode Go" "Google" "Custom OpenAI-Compatible" "Lark Industry Webhook" "Lark Competitor Webhook"
         "Industry Signing Secret" "Competitor Signing Secret" "Local HTTP Token")

set_menu() {
  for i in "${!LABELS[@]}"; do
    local num=$((i + 1))
    local svc="${RADAR_SERVICES[$i]}"
    local status="MISSING"
    if keychain_exists "$svc"; then status="CONFIGURED"; fi
    printf "  %d. %-35s [%s]\n" "$num" "${LABELS[$i]}" "$status"
  done
  printf "  %d. %-35s\n" $((${#LABELS[@]} + 1)) "Exit"
}

set_secret() {
  local idx="$1"
  local svc="${RADAR_SERVICES[$idx]}"
  local label="${LABELS[$idx]}"

  if keychain_exists "$svc"; then
    printf "Replace existing %s? [y/N] " "$label"
    read -r confirm
    confirm="${confirm:-N}"
    if [[ "$confirm" != [yY] ]]; then
      log "Skipped"
      return
    fi
  fi

  printf "Enter %s: " "$label"
  read -r -s value
  printf '\n'

  if [[ -z "$value" ]]; then
    log "Empty value, skipped"
    return
  fi

  keychain_set "$svc" "$value"
  unset value
  config "$label"
}

# ── Main ─────────────────────────────────────────────────────────
printf '\nJersey Secret Setup\n\n'
set_menu
printf '\nChoice: '
read -r choice
choice="${choice:-$((${#LABELS[@]} + 1))}"

if [[ "$choice" == $((${#LABELS[@]} + 1)) || "$choice" == "${#LABELS[@]}" ]]; then
  log "Exit"
  exit 0
fi

if [[ "$choice" -ge 1 && "$choice" -le "${#LABELS[@]}" ]]; then
  set_secret $((choice - 1))
else
  log "Invalid choice"
  exit 1
fi
