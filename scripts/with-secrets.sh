#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/keychain.sh"

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
    echo "Reads secrets from macOS Keychain and injects them into the child"
    echo "process environment. Only configured secrets are injected."
    exit 0
  fi

  log "Injecting configured secrets into child process..."

  local i
  for i in "${!RADAR_SERVICES[@]}"; do
    export_deg "${RADAR_SERVICES[$i]}" "${RADAR_ENV_NAMES[$i]}"
  done

  exec "$@"
}

main "$@"
