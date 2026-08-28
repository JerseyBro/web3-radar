#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/keychain.sh"
source "$DIR/lib/github.sh"

REPO="${1:-JerseyBro/web3-radar}"
export GH_REPO="$REPO"

gh_check || true
gh_auth_check || true

if [[ "$GH_AUTHENTICATED" != true ]]; then
  fail "GitHub Auth"
  log "  Run: gh auth login"
  exit 1
fi

printf '\nGitHub Secret Sync\n\n'

for i in "${!RADAR_SERVICES[@]}"; do
  local svc="${RADAR_SERVICES[$i]}"
  local env_name="${RADAR_ENV_NAMES[$i]}"

  if keychain_exists "$svc"; then
    gh_secret_set_from_keychain "$svc" "$env_name"
    synced "$env_name"
  else
    local is_required=false
    for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
      if [[ "$req" == "$svc" ]]; then is_required=true; break; fi
    done
    if [[ "$is_required" == true ]]; then
      missing "$env_name"
    else
      optional "$env_name"
    fi
  fi
done

printf '\nGitHub Secrets:\n\n'
gh_secret_list || true
printf '\n'
