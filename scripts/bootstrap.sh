#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/keychain.sh"
source "$DIR/lib/github.sh"

REPO="${REPO:-JerseyBro/web3-radar}"
export GH_REPO="$REPO"
NON_INTERACTIVE=false

for arg in "$@"; do
  case "$arg" in
    --non-interactive) NON_INTERACTIVE=true ;;
    --repo) shift; REPO="${1:-$REPO}"; export GH_REPO="$REPO" ;;
  esac
done

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

check_all_local_ready() {
  local req
  for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
    if ! keychain_exists "$req"; then echo false; return; fi
  done
  echo true
}

main() {
  printf '\nJersey Secret Bootstrap\n\n'

  section "Environment"
  [[ "$(uname)" == "Darwin" ]] && ok "macOS" || fail "macOS"
  require_cmd "security" && ok "security CLI" || missing "security CLI"
  require_cmd "gh" && ok "gh CLI" || missing "gh CLI"

  section "GitHub Auth"
  if [[ "$GH_AVAILABLE" == true ]]; then
    gh_auth_check || true
    [[ "$GH_AUTHENTICATED" == true ]] && ok "Authenticated" || missing "Authenticated"
    gh_repo_access || true
    [[ "$GH_REPO_ACCESS" == true ]] && ok "Repository ($REPO)" || missing "Repository ($REPO)"
    gh_workflow_scope || true
    [[ "$GH_WORKFLOW_SCOPE" == true ]] && ok "Workflow Permission" || warn "Workflow Permission"
  else
    missing "gh CLI"
  fi

  section "Local Secrets"
  check_local_secrets

  section "GitHub Secrets"
  check_github_secrets

  local all_local
  all_local=$(check_all_local_ready)
  if [[ "$all_local" == "true" && "$GH_AUTHENTICATED" == true ]]; then
    section "Sync GitHub Secrets"
    if [[ "$NON_INTERACTIVE" == true ]]; then
      log "  (non-interactive — skipping sync)"
    else
      printf "Local secrets complete. Sync to GitHub? [y/N] "
      read -r choice
      choice="${choice:-N}"
      if [[ "$choice" == [yY] ]]; then
        "$DIR/secrets-sync-github.sh" "$REPO"
      fi
    fi
  fi

  section "Radar Doctor"
  if [[ -d "$REPO_ROOT/radar" ]] && [[ -f "$REPO_ROOT/radar/cli.py" ]]; then
    "$DIR/with-secrets.sh" python -m radar doctor 2>/dev/null || log "  (doctor not available)"
  else
    log "  (radar CLI not found)"
  fi

  section "Production Readiness"
  local ready=true
  [[ "$GH_AUTHENTICATED" == true ]] || ready=false
  [[ "$GH_REPO_ACCESS" == true ]] || ready=false
  for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
    if ! keychain_exists "$req"; then ready=false; break; fi
  done
  if [[ "$ready" == true ]]; then
    log "READY_FOR_E2E"
  else
    log "BLOCKED_BY_CONFIGURATION"
  fi

  section "Next"
  log "  ./scripts/production-check.sh"
  log "  ./scripts/with-secrets.sh python -m radar doctor"
  log "  ./scripts/with-secrets.sh python -m radar ai-test"

  printf '\n'
}

main
