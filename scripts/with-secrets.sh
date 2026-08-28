#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/keychain.sh"

show_keychain() {
  local i svc env_name
  for i in "${!RADAR_SERVICES[@]}"; do
    svc="${RADAR_SERVICES[$i]}"
    env_name="${RADAR_ENV_NAMES[$i]}"
    if keychain_exists "$svc"; then
      printf "  KEYCHAIN: %-35s -> %s\n" "$svc" "$env_name"
    fi
  done
}

export_deg() {
  local svc="$1"
  local env_name="$2"
  local val
  if keychain_exists "$svc"; then
    val=$(keychain_get "$svc")
    export "$env_name=$val"
    unset val
  fi
}

main() {
  if [[ $# -eq 0 ]]; then
    echo "Usage: with-secrets.sh <command> [args...]"
    echo ""
    echo "Reads secrets from macOS Keychain and executes the command with"
    echo "secrets injected into the environment."
    show_keychain
    exit 0
  fi

  local i
  for i in "${!RADAR_SERVICES[@]}"; do
    export_deg "${RADAR_SERVICES[$i]}" "${RADAR_ENV_NAMES[$i]}"
  done

  exec "$@"
}

main "$@"
