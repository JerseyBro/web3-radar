#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/github.sh"

REPO="${1:-JerseyBro/web3-radar}"
export GH_REPO="$REPO"

main() {
  printf '\nGitHub Authentication Check\n\n'

  section "Runtime"
  require_cmd "gh" && ok "gh CLI" || missing "gh CLI"
  gh_check

  section "GitHub"
  if [[ "$GH_AVAILABLE" != true ]]; then
    missing "Authenticated"
    missing "Repository Access"
    missing "Contents Write"
    missing "Workflow Permission"
    log ""
    log "ACTION REQUIRED: install gh CLI first"
    printf '\n'
    return
  fi

  gh_check
  gh_auth_check || true

  if [[ "$GH_AUTHENTICATED" != true ]]; then
    missing "Authenticated"
    log ""
    log "ACTION REQUIRED: gh auth login"
    printf '\n'
    return
  fi

  ok "Authenticated"

  gh_repo_access || true
  [[ "$GH_REPO_ACCESS" == true ]] && ok "Repository Access ($REPO)" || missing "Repository Access ($REPO)"

  gh_contents_write || true
  [[ "$?" -eq 0 ]] && ok "Contents Write" || missing "Contents Write"

  gh_workflow_scope || true
  if [[ "$GH_WORKFLOW_SCOPE" == true ]]; then
    ok "Workflow Permission"
  else
    warn "Workflow Permission"
    log ""
    log "ACTION REQUIRED: gh auth refresh -s repo,workflow"
  fi

  printf '\n'
}

main
