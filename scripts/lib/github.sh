#!/usr/bin/env bash
set -euo pipefail

# ── GitHub CLI Helpers ───────────────────────────────────────────

GH_CHECKED=false
GH_AVAILABLE=false
GH_AUTHENTICATED=false
GH_REPO="JerseyBro/web3-radar"
GH_WORKFLOW_SCOPE=false
GH_REPO_ACCESS=false
GH_CONTENTS_WRITE=false

gh_check() {
  if command -v gh >/dev/null 2>&1; then
    GH_CHECKED=true
    GH_AVAILABLE=true
  else
    GH_CHECKED=true
    GH_AVAILABLE=false
  fi
}

gh_auth_check() {
  if [[ "$GH_AVAILABLE" != true ]]; then return 1; fi
  if gh auth status >/dev/null 2>&1; then
    GH_AUTHENTICATED=true
    return 0
  fi
  GH_AUTHENTICATED=false
  return 1
}

gh_repo_access() {
  if [[ "$GH_AUTHENTICATED" != true ]]; then return 1; fi
  if gh repo view "$GH_REPO" --json name >/dev/null 2>&1; then
    GH_REPO_ACCESS=true
    return 0
  fi
  GH_REPO_ACCESS=false
  return 1
}

gh_workflow_scope() {
  if [[ "$GH_AUTHENTICATED" != true ]]; then return 1; fi
  # Attempt to list workflows — succeeds only with workflow scope
  if gh api repos/"$GH_REPO"/workflows --jq '.id' >/dev/null 2>&1; then
    GH_WORKFLOW_SCOPE=true
    return 0
  fi
  GH_WORKFLOW_SCOPE=false
  return 1
}

gh_contents_write() {
  if [[ "$GH_AUTHENTICATED" != true ]]; then
    GH_CONTENTS_WRITE=false
    return 1
  fi
  # Attempt to read content (write permission implies read)
  if gh api repos/"$GH_REPO"/contents/.github >/dev/null 2>&1; then
    GH_CONTENTS_WRITE=true
    return 0
  fi
  GH_CONTENTS_WRITE=false
  return 1
}

gh_secret_list() {
  if [[ "$GH_AUTHENTICATED" != true ]]; then return 1; fi
  gh secret list --repo "$GH_REPO" 2>/dev/null
}

gh_secret_set_from_keychain() {
  local service="$1"
  local env_name="$2"
  if [[ "$GH_AUTHENTICATED" != true ]]; then return 1; fi
  keychain_pipe "$service" | gh secret set "$env_name" --repo "$GH_REPO"
}
