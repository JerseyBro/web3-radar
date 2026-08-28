#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/lib/common.sh"
source "$DIR/lib/github.sh"

REPO="${1:-JerseyBro/web3-radar}"
export GH_REPO="$REPO"

check_runtime() {
  section "Runtime"
  require_cmd "gh" && ok "gh CLI" || missing "gh CLI"
}

check_auth() {
  section "GitHub"
  if [[ "$GH_AVAILABLE" != true ]]; then
    fail "gh not installed"
    return
  fi
  gh_check
  gh_auth_check || true
  if [[ "$GH_AUTHENTICATED" == true ]]; then
    ok "Authenticated"
  else
    missing "Authenticated"
    log "  Run: gh auth login"
    return
  fi
  gh_repo_access || true
  if [[ "$GH_REPO_ACCESS" == true ]]; then
    ok "Repository Access ($REPO)"
  else
    missing "Repository Access ($REPO)"
  fi
  gh_contents_write || true
  if [[ "$?" -eq 0 ]]; then
    ok "Contents Write Permission"
  else
    missing "Contents Write Permission"
  fi
  gh_workflow_scope || true
  if [[ "$GH_WORKFLOW_SCOPE" == true ]]; then
    ok "Workflow Permission"
  else
    warn "Workflow Permission"
    log "  Action Required: gh auth refresh -s repo,workflow"
  fi
}

main() {
  printf '\nGitHub Authentication Check\n'
  check_runtime
  if [[ "$GH_AVAILABLE" == true ]]; then
    check_auth
  fi
  printf '\n'
}

main
