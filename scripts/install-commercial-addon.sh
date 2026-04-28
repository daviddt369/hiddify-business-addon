#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/opt/hiddify-manager"
TS="$(date +%F_%H-%M-%S)"
BACKUP_DIR="/root/hiddify-install-backups/$TS"
mkdir -p "$BACKUP_DIR"

echo "[commercial] backup => $BACKUP_DIR"
cp -a "$BASE_DIR/scripts/post-install-commercial.sh" "$BACKUP_DIR/post-install-commercial.sh.bak" 2>/dev/null || true
cp -a "$BASE_DIR/scripts/finalize-commercial.sh" "$BACKUP_DIR/finalize-commercial.sh.bak" 2>/dev/null || true

if [[ ! -x "$BASE_DIR/scripts/post-install-commercial.sh" ]]; then
  echo "[commercial] missing $BASE_DIR/scripts/post-install-commercial.sh" >&2
  exit 1
fi

bash "$BASE_DIR/scripts/post-install-commercial.sh"
echo "[commercial] done"
