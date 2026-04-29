#!/usr/bin/env bash
set -euo pipefail

# Stage 2: install business addon on top of base 12.0.x.
# Usage:
#   bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.4/scripts/install-commercial-onecmd.sh)

ADDON_REF="${ADDON_REF:-v0.12.4}"
ADDON_REPO="${ADDON_REPO:-https://github.com/daviddt369/hiddify-business-addon.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/hiddify-manager}"
HIDDIFY_BASE_VERSION_REGEX="${HIDDIFY_BASE_VERSION_REGEX:-^12\\.0\\.}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo -i" >&2
  exit 1
fi

echo "[install-commercial-onecmd] INSTALL_DIR=${INSTALL_DIR}"
echo "[install-commercial-onecmd] ADDON_REF=${ADDON_REF}"

TMP_SCRIPT="$(mktemp /tmp/install-addon.XXXXXX.sh)"
trap 'rm -f "$TMP_SCRIPT"' EXIT

curl -fsSL "https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/${ADDON_REF}/commercial-addon/install-addon.sh" -o "$TMP_SCRIPT"
chmod +x "$TMP_SCRIPT"

INSTALL_DIR="${INSTALL_DIR}" \
ADDON_REPO="${ADDON_REPO}" \
ADDON_REF="${ADDON_REF}" \
HIDDIFY_BASE_VERSION_REGEX="${HIDDIFY_BASE_VERSION_REGEX}" \
bash "$TMP_SCRIPT"
