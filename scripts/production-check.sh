#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/keychain.sh"
source "$DIR/lib/github.sh"

REPO="${REPO:-JerseyBro/web3-radar}"
export GH_REPO="$REPO"

for arg in "$@"; do
  case "$arg" in
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

main() {
  printf '\nWeb3 Radar Production Check\n\n'

  section "GitHub"
  require_cmd "gh" && ok "gh CLI" || missing "gh CLI"
  gh_check
  gh_auth_check || true
  [[ "$GH_AUTHENTICATED" == true ]] && ok "Authenticated" || missing "Authenticated"
  gh_repo_access || true
  [[ "$GH_REPO_ACCESS" == true ]] && ok "Repository ($REPO)" || missing "Repository ($REPO)"
  gh_contents_write || true
  [[ "$GH_CONTENTS_WRITE" == true ]] && ok "Contents Write" || missing "Contents Write"
  gh_workflow_scope || true
  [[ "$GH_WORKFLOW_SCOPE" == true ]] && ok "Workflow Permission" || warn "Workflow Permission"

  if [[ "$GH_AUTHENTICATED" == true ]]; then
    if git ls-remote --heads "$REPO" 2>/dev/null | grep -q "refs/heads/radar-state"; then
      ok "radar-state"
    else
      warn "radar-state"
    fi
  fi

  section "Secrets"
  check_local_secrets

  section "Radar"
  log "Doctor                        (run with-secrets.sh python -m radar doctor)"
  log "Critical Push                 DISABLED"
  log "Weekly Industry               ENABLED"
  log "Weekly Competitor             ENABLED"

  section "Schedule"
  log "Industry                      Fri 08:20 Asia/Shanghai"
  log "Competitor                    Fri 08:35 Asia/Shanghai"

  section "Production Readiness"
  local blockers=()
  if [[ "$GH_AUTHENTICATED" != true ]]; then
    blockers+=("NOT_AUTHENTICATED")
  fi
  if [[ "$GH_AUTHENTICATED" == true && "$GH_WORKFLOW_SCOPE" != true ]]; then
    blockers+=("WORKFLOW_PERMISSION_MISSING")
  fi
  local req
  for req in "${RADAR_REQUIRED_SERVICES[@]}"; do
    if ! keychain_exists "$req"; then
      local env_name=""
      for i in "${!RADAR_SERVICES[@]}"; do
        if [[ "${RADAR_SERVICES[$i]}" == "$req" ]]; then
          env_name="${RADAR_ENV_NAMES[$i]}"
          break
        fi
      done
      blockers+=("${env_name}_MISSING")
    fi
  done
  # Dynamic LLM required keys (from roles.* in models.yaml)
  local llm_env
  for llm_env in $(python3 -c "
try:
    from pipeline.llm.registry import required_api_key_envs
    from radar.config import get_settings
    for e in sorted(required_api_key_envs(get_settings()['models'])):
        print(e)
except Exception:
    print('OPENAI_API_KEY')
" 2>/dev/null || echo "OPENAI_API_KEY"); do
    local found=false
    local idx
    for idx in "${!RADAR_ENV_NAMES[@]}"; do
      if [[ "${RADAR_ENV_NAMES[$idx]}" == "$llm_env" ]]; then
        if keychain_exists "${RADAR_SERVICES[$idx]}"; then found=true; fi
        break
      fi
    done
    if [[ "$found" == false ]]; then blockers+=("${llm_env}_MISSING"); fi
  done

  if [[ ${#blockers[@]} -eq 0 ]]; then
    log "READY_FOR_E2E"
  else
    log "BLOCKED_BY_CONFIGURATION"
    log ""
    log "Blockers:"
    local b
    for b in "${blockers[@]}"; do
      log "  - $b"
    done
  fi

  section "Next"
  log "  ./scripts/with-secrets.sh python -m radar ai-test"
  log "  ./scripts/with-secrets.sh python -m radar ai-test --model synthesis"
  log "  ./scripts/with-secrets.sh python -m radar output-test --target lark --radar industry --push"
  log "  ./scripts/with-secrets.sh python -m radar output-test --target lark --radar competitor --push"

  printf '\n'
}

main
