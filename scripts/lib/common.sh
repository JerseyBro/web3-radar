#!/usr/bin/env bash
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
  BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; BOLD=''; DIM=''; RESET=''
fi

log()  { printf '%s\n' "$*"; }
info() { printf "${DIM}%s${RESET}\n" "$*"; }
ok()   { printf "${GREEN}%-30s PASS${RESET}\n" "$*"; }
warn() { printf "${YELLOW}%-30s MISSING${RESET}\n" "$*"; }
fail() { printf "${RED}%-30s FAIL${RESET}\n" "$*"; }
config() { printf "${GREEN}%-30s CONFIGURED${RESET}\n" "$*"; }
missing() { printf "${RED}%-30s MISSING${RESET}\n" "$*"; }
optional() { printf "${DIM}%-30s OPTIONAL${RESET}\n" "$*"; }
synced() { printf "${GREEN}%-30s SYNCED${RESET}\n" "$*"; }
blocked() { printf "${RED}%-30s BLOCKED${RESET}\n" "$*"; }
skipped() { printf "${DIM}%-30s SKIPPED${RESET}\n" "$*"; }
section() { printf '\n%s\n%s\n' "$*" "$(printf '%*s' ${#1} '' | tr ' ' '-')"; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "$1"
    return 1
  fi
  return 0
}

# ── Path ─────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
