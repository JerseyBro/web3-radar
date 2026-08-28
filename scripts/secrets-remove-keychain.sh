#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/keychain.sh"

LABELS=("OpenAI" "Lark Industry Webhook" "Lark Competitor Webhook"
         "Industry Signing Secret" "Competitor Signing Secret" "Local HTTP Token")

set_menu() {
  for i in "${!LABELS[@]}"; do
    local num=$((i + 1))
    local svc="${RADAR_SERVICES[$i]}"
    local status="NOT SET"
    if keychain_exists "$svc"; then status="CONFIGURED"; fi
    printf "  %d. %-35s [%s]\n" "$num" "${LABELS[$i]}" "$status"
  done
  printf "  %d. %-35s\n" $((${#LABELS[@]} + 1)) "Exit"
}

remove_secret() {
  local idx="$1"
  local svc="${RADAR_SERVICES[$idx]}"
  local label="${LABELS[$idx]}"

  if ! keychain_exists "$svc"; then
    log "$label is not set"
    return
  fi

  printf "Delete %s? [y/N] " "$label"
  read -r confirm
  confirm="${confirm:-N}"
  if [[ "$confirm" != [yY] ]]; then
    log "Skipped"
    return
  fi

  keychain_delete "$svc"
  log "DELETED"
}

# ── Main ─────────────────────────────────────────────────────────
printf '\nJersey Secret Remove\n\n'
set_menu
printf '\nChoice: '
read -r choice
choice="${choice:-$((${#LABELS[@]} + 1))}"

if [[ "$choice" == $((${#LABELS[@]} + 1)) ]]; then
  log "Exit"
  exit 0
fi

if [[ "$choice" -ge 1 && "$choice" -le "${#LABELS[@]}" ]]; then
  remove_secret $((choice - 1))
else
  log "Invalid choice"
  exit 1
fi
