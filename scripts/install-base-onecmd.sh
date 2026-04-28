#!/usr/bin/env bash
set -euo pipefail

# Stage 1: install official Hiddify 12.0.x base.
# Usage:
#   bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.1/scripts/install-base-onecmd.sh)

BASE_INSTALL_URL="${BASE_INSTALL_URL:-https://raw.githubusercontent.com/hiddify/hiddify-manager/v12.0.0/install.sh}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo -i" >&2
  exit 1
fi

echo "[install-base-onecmd] Running official base installer: ${BASE_INSTALL_URL}"
bash <(curl -fsSL "${BASE_INSTALL_URL}")
