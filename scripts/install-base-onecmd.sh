#!/usr/bin/env bash
set -euo pipefail

# Stage 1: install official Hiddify 12.0.x base.
# Usage:
#   bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.5/scripts/install-base-onecmd.sh)

BASE_VERSION="${BASE_VERSION:-v12.0.0}"
BASE_BOOTSTRAP_URL="${BASE_BOOTSTRAP_URL:-https://raw.githubusercontent.com/hiddify/Hiddify-Manager/refs/tags/${BASE_VERSION}/common/download.sh}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo -i" >&2
  exit 1
fi

echo "[install-base-onecmd] Running official base bootstrap: ${BASE_BOOTSTRAP_URL}"
bash <(curl -fsSL "${BASE_BOOTSTRAP_URL}") "${BASE_VERSION}" --no-gui
