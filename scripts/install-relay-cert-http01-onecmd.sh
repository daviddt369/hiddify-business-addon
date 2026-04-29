#!/usr/bin/env bash
set -euo pipefail

# Optional cert stage: relay HTTP-01 flow.
# Usage:
#   bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.4/scripts/install-relay-cert-http01-onecmd.sh)

ADDON_REF="${ADDON_REF:-v0.12.4}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo -i" >&2
  exit 1
fi

curl -fsSL "https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/${ADDON_REF}/relay-cert/install-http01.sh" | bash
