#!/usr/bin/env bash
set -euo pipefail
ROOT=/opt/hiddify-manager
FINALIZE_SCRIPT="$ROOT/scripts/finalize-commercial.sh"
if [[ $EUID -ne 0 ]]; then
  echo "Run as root"
  exit 1
fi
if [[ ! -f "$FINALIZE_SCRIPT" ]]; then
  echo "Commercial installer not found: $FINALIZE_SCRIPT"
  exit 1
fi

stop_apt_automation() {
  systemctl stop unattended-upgrades.service apt-daily.service apt-daily-upgrade.service apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
  pkill -f '/usr/bin/unattended-upgrade' >/dev/null 2>&1 || true
  pkill -f 'unattended-upgrade-shutdown' >/dev/null 2>&1 || true
}

wait_for_dpkg_lock() {
  local waited=0
  while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || fuser /var/lib/dpkg/lock >/dev/null 2>&1; do
    waited=$((waited + 2))
    echo "[stable_beta10.6] waiting for apt/dpkg lock (${waited}s)"
    sleep 2
    if [[ $waited -ge 120 ]]; then
      echo "[stable_beta10.6] apt/dpkg lock timeout" >&2
      return 1
    fi
  done
}

repair_dpkg_state() {
  dpkg --configure -a >/dev/null 2>&1 || true
  apt-get -f install -y >/dev/null 2>&1 || true
}

echo "[stable_beta10.6] Commercial install start"
echo "Prereq: base install done and panel first setup completed with real domain."
echo "[stable_beta10.6] preflight: stopping unattended apt automation"
stop_apt_automation
wait_for_dpkg_lock
repair_dpkg_state
bash "$FINALIZE_SCRIPT" "$@"
echo
echo "[stable_beta10.6] Commercial install completed."
