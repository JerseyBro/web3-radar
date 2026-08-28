#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/keychain.sh"
source "$DIR/lib/github.sh"

REPO="${1:-JerseyBro/web3-radar}"
export GH_REPO="$REPO"

check_local_secrets() {
  local i svc label is_required req
  for i in "${!RADAR_SERVICES[@]}"; do
    svc="${RADAR_SERVICES[$i]}"
    label="${RADAR_ENV_NAMES[$i]}"
    if keychain_exists "$svc"; then
      config "$label"
    else
      is_required=false
      for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
        if [[ "$req" == "$svc" ]]; then is_required=true; break; fi
      done
      if [[ "$is_required" == true ]]; then
        missing "$label"
      else
        optional "$label"
      fi
    fi
  done
}

check_github_secrets() {
  local i env_name is_required req
  if [[ "$GH_AUTHENTICATED" == true ]]; then
    local gh_secret_output
    gh_secret_output=$(gh_secret_list 2>/dev/null || echo "")
    for i in "${!RADAR_SERVICES[@]}"; do
      env_name="${RADAR_ENV_NAMES[$i]}"
      if echo "$gh_secret_output" | grep -q "$env_name"; then
        config "$env_name"
      else
        is_required=false
        for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
          if [[ "$req" == "${RADAR_SERVICES[$i]}" ]]; then is_required=true; break; fi
        done
        if [[ "$is_required" == true ]]; then
          missing "$env_name"
        else
          optional "$env_name"
        fi
      fi
    done
  else
    log "  (GitHub not authenticated — skipping)"
  fi
}

main() {
  printf '\nJersey Secret Doctor\n\n'

  section "Runtime"
  [[ "$(uname)" == "Darwin" ]] && ok "macOS" || fail "macOS"
  require_cmd "security" && ok "security CLI" || missing "security CLI"
  require_cmd "gh" && ok "gh CLI" || missing "gh CLI"

  section "GitHub"
  if command -v gh >/dev/null 2>&1; then
    gh_check
    gh_auth_check || true
    [[ "$GH_AUTHENTICATED" == true ]] && ok "Authenticated" || missing "Authenticated"
    gh_repo_access || true
    [[ "$GH_REPO_ACCESS" == true ]] && ok "Repository" || missing "Repository"
    gh_workflow_scope || true
    [[ "$GH_WORKFLOW_SCOPE" == true ]] && ok "Workflow Permission" || warn "Workflow Permission"
  else
    missing "gh CLI"
    missing "Authenticated"
    missing "Repository"
    missing "Workflow Permission"
  fi

  section "Local Secret Store"
  check_local_secrets

  section "GitHub Secrets"
  check_github_secrets

  section "Overall"
  local all_ok=true req
  for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
    if ! keychain_exists "$req"; then all_ok=false; break; fi
  done
  if [[ "$all_ok" == true ]]; then
    log "READY"
  else
    log "BLOCKED_BY_CONFIGURATION"
  fi

  printf '\n'
}

main
