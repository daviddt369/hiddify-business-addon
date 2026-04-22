#!/usr/bin/env bash
set -euo pipefail

MAIN_SERVER_IP="${MAIN_SERVER_IP:-$(hostname -I | awk '{print $1}')}"
RELAY_DOMAIN="${RELAY_DOMAIN:-}"
RELAY_SERVER_IP="${RELAY_SERVER_IP:-}"
WORKDIR="/opt/hiddify-manager"
PREPARE_ACME="$WORKDIR/acme.sh/prepare_acme.sh"
CERT_UTILS="$WORKDIR/acme.sh/cert_utils.sh"

log() {
    echo "[relay-http01] $*"
}

die() {
    echo "[relay-http01][ERROR] $*" >&2
    exit 1
}

require_root() {
    [[ "$(id -u)" -eq 0 ]] || die "Запусти script от root."
}

require_files() {
    [[ -d "$WORKDIR" ]] || die "$WORKDIR не найден."
    [[ -f "$PREPARE_ACME" ]] || die "Не найден $PREPARE_ACME"
    [[ -f "$CERT_UTILS" ]] || die "Не найден $CERT_UTILS"
}

backup_file() {
    local file="$1"
    cp "$file" "$file.bak.$(date +%F-%H%M%S)"
}

patch_prepare_acme() {
    python3 - "$PREPARE_ACME" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

marker = "location ^~ /.well-known/acme-challenge/"
if marker in text:
    print("prepare_acme.sh уже пропатчен")
    raise SystemExit(0)

old = """mkdir -p /opt/hiddify-manager/acme.sh/www/\necho \"location /.well-known/acme-challenge {root /opt/hiddify-manager/acme.sh/www/;}\" >/opt/hiddify-manager/nginx/parts/acme.conf\nchown -R nginx /opt/hiddify-manager/acme.sh/www/\nsystemctl reload hiddify-nginx\n"""
new = """mkdir -p /opt/hiddify-manager/acme.sh/www/.well-known/acme-challenge\ncat > /opt/hiddify-manager/nginx/parts/acme.conf <<'EOF'\nlocation ^~ /.well-known/acme-challenge/ {\n    root /opt/hiddify-manager/acme.sh/www;\n    default_type \"text/plain\";\n    try_files $uri =404;\n}\nEOF\nchown -R nginx /opt/hiddify-manager/acme.sh/www/\nsystemctl reload hiddify-nginx\nsystemctl reload hiddify-haproxy 2>/dev/null || true\n"""

if old not in text:
    raise SystemExit("Не найден целевой блок для patch в prepare_acme.sh")

path.write_text(text.replace(old, new, 1))
print("prepare_acme.sh пропатчен")
PY
}

patch_cert_utils() {
    python3 - "$CERT_UTILS" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

replacement = """stop_nginx_acme(){\n    bash /opt/hiddify-manager/acme.sh/prepare_acme.sh\n}\n"""

if replacement in text:
    print("cert_utils.sh уже пропатчен")
    raise SystemExit(0)

start = text.find("stop_nginx_acme(){")
if start == -1:
    raise SystemExit("stop_nginx_acme() не найден")
end = text.find("\n}\n", start)
if end == -1:
    raise SystemExit("Не найден конец stop_nginx_acme()")
end += len("\n}\n")

path.write_text(text[:start] + replacement + text[end:])
print("cert_utils.sh пропатчен")
PY
}

check_services() {
    nginx -t
    systemctl reload hiddify-nginx
    systemctl reload hiddify-haproxy
}

print_next_steps() {
    cat <<EOF

[relay-http01] Патч main server применён.

Следующий шаг на relay server:

Добавь в nginx для relay-домена такой location:

location ^~ /.well-known/acme-challenge/ {
    proxy_pass http://${MAIN_SERVER_IP}:80;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
}

Текущие переменные:
  MAIN_SERVER_IP=${MAIN_SERVER_IP}
  RELAY_DOMAIN=${RELAY_DOMAIN:-<задай RELAY_DOMAIN>}
  RELAY_SERVER_IP=${RELAY_SERVER_IP:-<задай RELAY_SERVER_IP>}

После обновления relay nginx:
1. Проверь challenge path:
   curl http://\${RELAY_DOMAIN}/.well-known/acme-challenge/test-ok
2. Нажми "Apply Configs" в панели Hiddify
3. Проверь live-сертификат на relay-домене
EOF
}

main() {
    require_root
    require_files
    backup_file "$PREPARE_ACME"
    backup_file "$CERT_UTILS"
    patch_prepare_acme
    patch_cert_utils
    check_services
    print_next_steps
}

main "$@"
