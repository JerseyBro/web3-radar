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
    for i in "${!RADAR_SERVICES[@]}"; do
      env_name="${RADAR_ENV_NAMES[$i]}"
      missing "$env_name"
    done
  fi
}

main() {
  printf '\nJersey Secret Doctor\n\n'

  section "Runtime"
  [[ "$(uname)" == "Darwin" ]] && ok "macOS" || fail "macOS"
  require_cmd "security" && ok "security CLI" || missing "security CLI"
  require_cmd "gh" && ok "gh CLI" || missing "gh CLI"

  section "GitHub"
  gh_check
  if [[ "$GH_AVAILABLE" == true ]]; then
    gh_auth_check || true
    [[ "$GH_AUTHENTICATED" == true ]] && ok "Authenticated" || missing "Authenticated"
    gh_repo_access || true
    [[ "$GH_REPO_ACCESS" == true ]] && ok "Repository ($REPO)" || missing "Repository ($REPO)"
    gh_contents_write || true
    [[ "$GH_CONTENTS_WRITE" == true ]] && ok "Contents Write" || missing "Contents Write"
    gh_workflow_scope || true
    [[ "$GH_WORKFLOW_SCOPE" == true ]] && ok "Workflow Permission" || warn "Workflow Permission"
  else
    missing "Authenticated"
    missing "Repository ($REPO)"
    missing "Contents Write"
    missing "Workflow Permission"
  fi

  section "Local Secret Store"
  check_local_secrets

  section "Optional"
  optional "Industry Signing"
  optional "Competitor Signing"
  optional "Local HTTP Token"

  section "GitHub Secrets"
  check_github_secrets

  section "OpenAI Secure Provisioning"
  # Runtime detection is informational only — scripts stay agent-independent.
  local runtime="Local Shell"
  if [[ -n "${CODEX_HOME:-}" || -n "${CODEX_SANDBOX:-}" || -n "${CODEX:-}" ]]; then
    runtime="Codex"
  elif [[ -n "${OPENCODE:-}" || -n "${OPENCODE_SERVER:-}" ]]; then
    runtime="OpenCode"
  fi
  log "$(printf '%-30s %s' "Current Runtime" "$runtime")"
  if [[ "$runtime" == "Codex" ]]; then
    log "$(printf '%-30s %s' "Secure Provisioning" "AVAILABLE")"
    log "  (Codex may provision the key securely; do not paste keys into chat)"
  else
    log "$(printf '%-30s %s' "Secure Provisioning" "UNAVAILABLE_IN_CURRENT_RUNTIME")"
  fi
  log "$(printf '%-30s %s' "Shared Keychain Support" "PASS")"

  section "Overall"
  local blocked_credential=false blocked_config=false
  if [[ "$GH_AUTHENTICATED" == true && "$GH_WORKFLOW_SCOPE" != true ]]; then
    blocked_credential=true
  fi
  local req
  for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
    if ! keychain_exists "$req"; then blocked_config=true; break; fi
  done

  if [[ "$blocked_credential" == true ]]; then
    log "BLOCKED_BY_CREDENTIAL_SCOPE"
  elif [[ "$blocked_config" == true ]]; then
    log "BLOCKED_BY_CONFIGURATION"
  else
    log "READY"
  fi

  if [[ "$blocked_credential" == true || "$blocked_config" == true ]]; then
    if [[ "$blocked_credential" == true ]]; then
      log ""
      log "Additional Blocker:"
      log "WORKFLOW_PERMISSION_MISSING"
    fi
    log ""
    log "Next Actions:"
    local n=1
    if [[ "$blocked_credential" == true ]]; then
      log "  $((n++)). gh auth refresh -s repo,workflow"
    fi
    if [[ "$blocked_config" == true ]]; then
      log "  $((n++)). ./scripts/secrets-set-keychain.sh"
      log "  $((n++)). ./scripts/bootstrap.sh"
    fi
  fi

  printf '\n'
}

main
