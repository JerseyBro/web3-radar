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
# LLM provider keys (provider agnostic — add new provider by extending mapping)
RADAR_SERVICES=(
  "web3-radar-openai"
  "web3-radar-deepseek"
  "web3-radar-anthropic"
  "web3-radar-alibaba"
  "web3-radar-tencent"
  "web3-radar-volcengine"
  "web3-radar-opencode-go"
  "web3-radar-generic-llm"
  "web3-radar-lark-industry"
  "web3-radar-lark-competitor"
  "web3-radar-lark-signing-industry"
  "web3-radar-lark-signing-competitor"
  "web3-radar-local-http-token"
)

RADAR_ENV_NAMES=(
  "OPENAI_API_KEY"
  "DEEPSEEK_API_KEY"
  "ANTHROPIC_API_KEY"
  "DASHSCOPE_API_KEY"
  "TENCENT_LLM_API_KEY"
  "VOLCENGINE_API_KEY"
  "OPENCODE_GO_API_KEY"
  "CUSTOM_LLM_API_KEY"
  "LARK_WEBHOOK_INDUSTRY"
  "LARK_WEBHOOK_COMPETITOR"
  "LARK_SIGNING_SECRET_INDUSTRY"
  "LARK_SIGNING_SECRET_COMPETITOR"
  "LOCAL_WEBHOOK_TOKEN"
)

# Required vs optional (LLM keys are dynamic — determined by config/models.yaml roles)
# Static required: only Lark webhooks. LLM key requirement is resolved at runtime
# by doctor/production-check reading roles.* from models.yaml.
RADAR_REQUIRED_SERVICES=(
  "web3-radar-lark-industry"
  "web3-radar-lark-competitor"
)

RADAR_LLM_SERVICES=(
  "web3-radar-openai"
  "web3-radar-deepseek"
  "web3-radar-anthropic"
  "web3-radar-alibaba"
  "web3-radar-tencent"
  "web3-radar-volcengine"
  "web3-radar-opencode-go"
  "web3-radar-generic-llm"
)
