#!/usr/bin/env bash
set -euo pipefail

# ── macOS Keychain Helpers ───────────────────────────────────────
# Service names for web3-radar secrets.
# Account is always $USER.

keychain_exists() {
  local svc="$1"
  security find-generic-password -a "$USER" -s "$svc" >/dev/null 2>&1
}

keychain_get() {
  local svc="$1"
  security find-generic-password -a "$USER" -s "$svc" -w 2>/dev/null
}

keychain_set() {
  local svc="$1"
  local value="$2"
  if keychain_exists "$svc"; then
    security delete-generic-password -a "$USER" -s "$svc" >/dev/null 2>&1
  fi
  security add-generic-password -a "$USER" -s "$svc" -w "$value" >/dev/null 2>&1
}

keychain_delete() {
  local svc="$1"
  security delete-generic-password -a "$USER" -s "$svc" >/dev/null 2>&1
}

keychain_pipe() {
  local svc="$1"
  security find-generic-password -a "$USER" -s "$svc" -w 2>/dev/null
}

# ── Web3 Radar Secret Service Names ─────────────────────────────
RADAR_SERVICES=(
  "web3-radar-openai"
  "web3-radar-lark-industry"
  "web3-radar-lark-competitor"
  "web3-radar-lark-signing-industry"
  "web3-radar-lark-signing-competitor"
  "web3-radar-local-http-token"
)

RADAR_ENV_NAMES=(
  "OPENAI_API_KEY"
  "LARK_WEBHOOK_INDUSTRY"
  "LARK_WEBHOOK_COMPETITOR"
  "LARK_SIGNING_SECRET_INDUSTRY"
  "LARK_SIGNING_SECRET_COMPETITOR"
  "LOCAL_WEBHOOK_TOKEN"
)

# Required vs optional
RADAR_REQUIRED_SERVICES=(
  "web3-radar-openai"
  "web3-radar-lark-industry"
  "web3-radar-lark-competitor"
)
