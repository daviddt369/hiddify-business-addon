#!/usr/bin/env bash
set -euo pipefail

# Stage 3: install routing addon on top of business addon.
# Usage:
#   bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.4/scripts/install-routing-onecmd.sh)

REPO_REF="${REPO_REF:-v0.12.4}"
REPO_REF_KIND="${REPO_REF_KIND:-tag}" # tag recommended for releases
HIDDIFY_BASE_VERSION_REGEX="${HIDDIFY_BASE_VERSION_REGEX:-^12\\.0\\.}"
ALLOW_UNSUPPORTED_BASE_VERSION="${ALLOW_UNSUPPORTED_BASE_VERSION:-0}"
INSTALL_XRAY_ROUTER_TEST="${INSTALL_XRAY_ROUTER_TEST:-0}"
INSTALL_DB_ENUMS="${INSTALL_DB_ENUMS:-1}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo -i" >&2
  exit 1
fi

echo "[install-routing-onecmd] REPO_REF=${REPO_REF} (${REPO_REF_KIND})"

curl -fsSL "https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/${REPO_REF}/scripts/install-commercial-routing-addon.sh" \
| REPO_REF="${REPO_REF}" \
  REPO_REF_KIND="${REPO_REF_KIND}" \
  HIDDIFY_BASE_VERSION_REGEX="${HIDDIFY_BASE_VERSION_REGEX}" \
  ALLOW_UNSUPPORTED_BASE_VERSION="${ALLOW_UNSUPPORTED_BASE_VERSION}" \
  INSTALL_XRAY_ROUTER_TEST="${INSTALL_XRAY_ROUTER_TEST}" \
  INSTALL_DB_ENUMS="${INSTALL_DB_ENUMS}" \
  bash
