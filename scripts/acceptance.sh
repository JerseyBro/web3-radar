#!/usr/bin/env bash
set -u -o pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON_BIN:-python3}" -m radar.acceptance "$@"
