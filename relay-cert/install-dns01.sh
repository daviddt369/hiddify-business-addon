#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/opt/hiddify-manager"
RELAY_DOMAIN="${RELAY_DOMAIN:-}"
DNS_PROVIDER="${DNS_PROVIDER:-manual-txt}"

die() {
    echo "[relay-dns01][ERROR] $*" >&2
    exit 1
}

require_root() {
    [[ "$(id -u)" -eq 0 ]] || die "Запусти script от root."
}

require_hiddify() {
    [[ -d "$WORKDIR" ]] || die "$WORKDIR не найден."
}

main() {
    require_root
    require_hiddify

    cat <<EOF
[relay-dns01] Для dns-01 server-side patch не нужен.

Рекомендуемый режим relay SSL:
  relay_ssl_mode=dns01

Текущие переменные:
  RELAY_DOMAIN=${RELAY_DOMAIN:-<задай RELAY_DOMAIN>}
  DNS_PROVIDER=${DNS_PROVIDER}

Стандартный сценарий:
1. Открой гайд по relay SSL:
   https://github.com/daviddt369/hiddify-business-addon/blob/main/docs/relay-ssl-ru.md
2. Для relay-доменов используй dns-01, если не хочешь править relay ingress.
3. Выпусти сертификат одним из двух способов:
   - вручную через TXT-запись (_acme-challenge.<subdomain>)
   - через DNS provider API в acme.sh
4. После завершения TXT/API шага нажми "Apply Configs" в панели Hiddify.

Этот режим рекомендован для обычного пользователя, потому что не зависит от relay nginx/http routing.
EOF
}

main "$@"
