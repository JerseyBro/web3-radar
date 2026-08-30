#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/keychain.sh"
source "$DIR/lib/github.sh"

REPO="${1:-JerseyBro/web3-radar}"
export GH_REPO="$REPO"

_required_envs() {
  # Dynamic: ask Python registry which LLM keys are actually needed by roles.*.
  # Falls back to OPENAI_API_KEY if Python unavailable (backward compat).
  python3 -c "
try:
    from pipeline.llm.registry import required_api_key_envs
    from radar.config import get_settings
    for e in sorted(required_api_key_envs(get_settings()['models'])):
        print(e)
except Exception:
    print('OPENAI_API_KEY')
" 2>/dev/null || echo "OPENAI_API_KEY"
}

_is_required_env() {
  local env_name="$1"
  local req
  # Check static required (Lark)
  for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
    if [[ "$req" == "$env_name" ]]; then echo true; return; fi
    # RADAR_REQUIRED_SERVICES holds service names, check via index
    local idx
    for idx in "${!RADAR_SERVICES[@]}"; do
      if [[ "${RADAR_SERVICES[$idx]}" == "$req" && "${RADAR_ENV_NAMES[$idx]}" == "$env_name" ]]; then
        echo true; return
      fi
    done
  done
  # Check dynamic LLM required
  local dyn
  dyn=$(_required_envs)
  if echo "$dyn" | grep -qx "$env_name"; then
    echo true; return
  fi
  echo false
}

_is_llm_env() {
  local env_name="$1"
  local svc
  for svc in "${RADAR_LLM_SERVICES[@]}"; do
    local idx
    for idx in "${!RADAR_SERVICES[@]}"; do
      if [[ "${RADAR_SERVICES[$idx]}" == "$svc" && "${RADAR_ENV_NAMES[$idx]}" == "$env_name" ]]; then
        echo true; return
      fi
    done
  done
  echo false
}

check_local_secrets() {
  local i svc label is_required
  # Determine dynamic LLM required set once
  local required_llm
  required_llm=$(_required_envs)
  for i in "${!RADAR_SERVICES[@]}"; do
    svc="${RADAR_SERVICES[$i]}"
    label="${RADAR_ENV_NAMES[$i]}"
    if keychain_exists "$svc"; then
      config "$label"
    else
      # LLM keys: REQUIRED only if in required_llm, else OPTIONAL/UNUSED
      if [[ "$(_is_llm_env "$label")" == "true" ]]; then
        if echo "$required_llm" | grep -qx "$label"; then
          missing "$label"
        else
          optional "$label"
        fi
      else
        is_required=false
        local req
        for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
          # RADAR_REQUIRED_SERVICES are service names, need to map
          local ridx
          for ridx in "${!RADAR_SERVICES[@]}"; do
            if [[ "${RADAR_SERVICES[$ridx]}" == "$req" && "${RADAR_ENV_NAMES[$ridx]}" == "$label" ]]; then
              is_required=true; break
            fi
          done
          if [[ "$is_required" == true ]]; then break; fi
        done
        if [[ "$is_required" == true ]]; then
          missing "$label"
        else
          optional "$label"
        fi
      fi
    fi
  done
}

check_github_secrets() {
  local i env_name
  if [[ "$GH_AUTHENTICATED" == true ]]; then
    local gh_secret_output
    gh_secret_output=$(gh_secret_list 2>/dev/null || echo "")
    local required_llm
    required_llm=$(_required_envs)
    for i in "${!RADAR_SERVICES[@]}"; do
      env_name="${RADAR_ENV_NAMES[$i]}"
      if echo "$gh_secret_output" | grep -q "$env_name"; then
        config "$env_name"
      else
        if [[ "$(_is_llm_env "$env_name")" == "true" ]]; then
          if echo "$required_llm" | grep -qx "$env_name"; then
            missing "$env_name"
          else
            optional "$env_name"
          fi
        else
          local is_required=false
          local req
          for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
            local ridx
            for ridx in "${!RADAR_SERVICES[@]}"; do
              if [[ "${RADAR_SERVICES[$ridx]}" == "$req" && "${RADAR_ENV_NAMES[$ridx]}" == "$env_name" ]]; then
                is_required=true; break
              fi
            done
            if [[ "$is_required" == true ]]; then break; fi
          done
          if [[ "$is_required" == true ]]; then
            missing "$env_name"
          else
            optional "$env_name"
          fi
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
  # Also check required LLM keys (dynamic)
  if [[ "$blocked_config" == false ]]; then
    local llm_env
    for llm_env in $(_required_envs); do
      local found=false
      local idx
      for idx in "${!RADAR_ENV_NAMES[@]}"; do
        if [[ "${RADAR_ENV_NAMES[$idx]}" == "$llm_env" ]]; then
          if keychain_exists "${RADAR_SERVICES[$idx]}"; then found=true; fi
          break
        fi
      done
      if [[ "$found" == false ]]; then blocked_config=true; break; fi
    done
  fi

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
