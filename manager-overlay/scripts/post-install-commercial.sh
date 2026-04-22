#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/hiddify-manager}"
SECRETS_DIR="/etc/hiddify-panel"
SECRETS_FILE="$SECRETS_DIR/panel-secrets.env"

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-${HIDDIFY_TELEGRAM_BOT_TOKEN:-}}"
ENABLE_TELEGRAM_PAYMENTS="${ENABLE_TELEGRAM_PAYMENTS:-0}"
TELEGRAM_PAYMENT_PROVIDER_TOKEN="${TELEGRAM_PAYMENT_PROVIDER_TOKEN:-${HIDDIFY_TELEGRAM_PAYMENT_PROVIDER_TOKEN:-}}"
HIDDIFY_TELEGRAM_WEBHOOK_SECRET="${HIDDIFY_TELEGRAM_WEBHOOK_SECRET:-}"
HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN="${HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN:-}"
HIDDIFY_SUPPORT_URL="${HIDDIFY_SUPPORT_URL:-${SUPPORT_URL:-}}"
HIDDIFY_TELEGRAM_REGISTRATION_MODE="${HIDDIFY_TELEGRAM_REGISTRATION_MODE:-${TELEGRAM_REGISTRATION_MODE:-admin_only}}"

require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        echo "This script must be run as root." >&2
        exit 1
    fi
}

mysql_escape() {
    local value="${1:-}"
    value="${value//\\/\\\\}"
    value="${value//\'/\\\'}"
    printf '%s' "$value"
}

ensure_config_schema() {
    python3 - <<'PY'
import re
import subprocess
import sys


def mysql_query(db, query):
    return subprocess.check_output(
        ["mysql", "-N", "-B", db, "-e", query],
        text=True,
    ).strip()


def parse_enum(column_type: str):
    return re.findall(r"'((?:[^'\\\\]|\\\\.)*)'", column_type)


def ensure_enum(table: str, required: list[str], value_type: str):
    column_type = mysql_query(
        "information_schema",
        f"select COLUMN_TYPE from COLUMNS where TABLE_SCHEMA='hiddifypanel' and TABLE_NAME='{table}' and COLUMN_NAME='key'",
    )
    if not column_type:
        raise SystemExit(f"missing COLUMN_TYPE for {table}.key")

    values = parse_enum(column_type)
    changed = False
    for item in required:
        if item not in values:
            values.append(item)
            changed = True

    if not changed:
        return

    enum_sql = ",".join("'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'" for value in values)
    alter = f"ALTER TABLE {table} MODIFY COLUMN `key` enum({enum_sql}) NOT NULL"
    if value_type == "varchar":
        alter += ", MODIFY COLUMN `value` varchar(3072) NULL"
    elif value_type == "bool":
        alter += ", MODIFY COLUMN `value` tinyint(1) NULL"
    subprocess.check_call(["mysql", "hiddifypanel", "-e", alter])


ensure_enum(
    "str_config",
    ["telegram_webhook_domain", "telegram_payment_provider_token", "support_url"],
    "varchar",
)
ensure_enum(
    "bool_config",
    ["business_enabled"],
    "bool",
)
PY
}

panel_cli() {
    # The supported CLI entrypoint is a shell helper from common/utils.sh.
    # Using it keeps us aligned with the current install layout and venv path.
    local quoted_args=()
    local arg
    for arg in "$@"; do
        quoted_args+=("$(printf '%q' "$arg")")
    done
    bash -lc "source '$INSTALL_DIR/common/utils.sh'; hiddify-panel-cli ${quoted_args[*]}"
}

refresh_telegram_webhook() {
    if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
        return 0
    fi
    local refresh_script=""
    local rc=0
    umask 077
    refresh_script="$(mktemp /tmp/hiddify_refresh_tg_webhook.XXXXXX.py)"
    cat >"$refresh_script" <<'PY'
from hiddifypanel import create_app

app = create_app(app_mode="cli")
with app.app_context():
    from hiddifypanel.panel.commercial.restapi.v2.telegram.tgbot import register_bot
    register_bot(set_hook=True)
    print("webhook_refresh_ok")
PY
    chmod 600 "$refresh_script"
    if su hiddify-panel -s /bin/bash -c "set -a; [ -f '$SECRETS_FILE' ] && . '$SECRETS_FILE'; set +a; cd '$INSTALL_DIR/hiddify-panel' && source '$INSTALL_DIR/.venv313/bin/activate' && python3 '$refresh_script'"; then
        :
    else
        rc=$?
        echo "WARNING: telegram webhook refresh failed with exit code $rc" >&2
    fi
    rm -f "$refresh_script"
    return 0
}

set_panel_setting() {
    local key="$1"
    local value="$2"
    panel_cli set-setting -k "$key" -v "$value"
}

upsert_str_config() {
    local key="$1"
    local value="$2"
    local esc
    esc="$(mysql_escape "$value")"
    mysql hiddifypanel -e "INSERT INTO str_config (child_id, \`key\`, value) VALUES (0, '$key', '$esc') ON DUPLICATE KEY UPDATE value=VALUES(value);"
}

upsert_bool_config() {
    local key="$1"
    local value="$2"
    mysql hiddifypanel -e "INSERT INTO bool_config (child_id, \`key\`, value) VALUES (0, '$key', $value) ON DUPLICATE KEY UPDATE value=VALUES(value);"
}

write_secrets_env() {
    local tmp_secrets=""
    mkdir -p "$SECRETS_DIR"
    chmod 700 "$SECRETS_DIR"
    umask 077
    tmp_secrets="$(mktemp "$SECRETS_DIR/panel-secrets.env.XXXXXX")"
    chmod 600 "$tmp_secrets"

    if [[ -n "$HIDDIFY_TELEGRAM_WEBHOOK_SECRET" ]]; then
        printf 'HIDDIFY_TELEGRAM_WEBHOOK_SECRET=%s\n' "$HIDDIFY_TELEGRAM_WEBHOOK_SECRET" >>"$tmp_secrets"
    fi
    if [[ -n "$HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN" ]]; then
        printf 'HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN=%s\n' "$HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN" >>"$tmp_secrets"
    fi
    if [[ -n "$HIDDIFY_SUPPORT_URL" ]]; then
        printf 'HIDDIFY_SUPPORT_URL=%s\n' "$HIDDIFY_SUPPORT_URL" >>"$tmp_secrets"
    fi
    printf 'HIDDIFY_TELEGRAM_REGISTRATION_MODE=%s\n' "$HIDDIFY_TELEGRAM_REGISTRATION_MODE" >>"$tmp_secrets"
    if [[ "$ENABLE_TELEGRAM_PAYMENTS" == "1" && -n "$TELEGRAM_PAYMENT_PROVIDER_TOKEN" ]]; then
        printf 'HIDDIFY_TELEGRAM_PAYMENT_PROVIDER_TOKEN=%s\n' "$TELEGRAM_PAYMENT_PROVIDER_TOKEN" >>"$tmp_secrets"
    fi
    mv -f "$tmp_secrets" "$SECRETS_FILE"
}

write_systemd_overrides() {
    mkdir -p /etc/systemd/system/hiddify-panel.service.d
    mkdir -p /etc/systemd/system/hiddify-panel-background-tasks.service.d

    cat >/etc/systemd/system/hiddify-panel.service.d/override.conf <<EOF
[Service]
EnvironmentFile=$SECRETS_FILE
EOF

    cat >/etc/systemd/system/hiddify-panel-background-tasks.service.d/override.conf <<EOF
[Service]
EnvironmentFile=$SECRETS_FILE
EOF
}

configure_panel() {
    ensure_config_schema
    upsert_bool_config "business_enabled" 1
    if [[ -n "$TELEGRAM_BOT_TOKEN" ]]; then
        upsert_str_config "telegram_bot_token" "$TELEGRAM_BOT_TOKEN"
    fi
    if [[ -n "$HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN" ]]; then
        upsert_str_config "telegram_webhook_domain" "$HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN"
    fi
    if [[ "$ENABLE_TELEGRAM_PAYMENTS" == "1" && -n "$TELEGRAM_PAYMENT_PROVIDER_TOKEN" ]]; then
        upsert_str_config "telegram_payment_provider_token" "$TELEGRAM_PAYMENT_PROVIDER_TOKEN"
    fi
    if [[ -n "$HIDDIFY_SUPPORT_URL" ]]; then
        upsert_str_config "support_url" "$HIDDIFY_SUPPORT_URL"
    fi

    # Keep official CLI in sync for keys it already understands.
    set_panel_setting "business_enabled" "true" || true
    if [[ -n "$TELEGRAM_BOT_TOKEN" ]]; then
        set_panel_setting "telegram_bot_token" "$TELEGRAM_BOT_TOKEN" || true
    fi
    if [[ -n "$HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN" ]]; then
        set_panel_setting "telegram_webhook_domain" "$HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN" || true
    fi
    if [[ "$ENABLE_TELEGRAM_PAYMENTS" == "1" && -n "$TELEGRAM_PAYMENT_PROVIDER_TOKEN" ]]; then
        set_panel_setting "telegram_payment_provider_token" "$TELEGRAM_PAYMENT_PROVIDER_TOKEN" || true
    fi
    if [[ -n "$HIDDIFY_SUPPORT_URL" ]]; then
        set_panel_setting "support_url" "$HIDDIFY_SUPPORT_URL" || true
    fi
}

ensure_haproxy_runtime() {
    if systemctl is-active --quiet hiddify-haproxy; then
        return 0
    fi

    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y haproxy
    systemctl restart hiddify-haproxy
}

restart_services() {
    systemctl daemon-reload
    systemctl restart hiddify-panel hiddify-panel-background-tasks
}

get_owner_uuid() {
    mysql -N -B hiddifypanel -e "select uuid from admin_user order by id limit 1" 2>/dev/null | head -n 1 || true
}

print_summary() {
    local owner_uuid=""
    owner_uuid="$(get_owner_uuid)"

    echo "Commercial post-install completed."
    echo "Install dir: $INSTALL_DIR"
    echo "Business menu: enabled"
    echo "Panel domain: set it in Hiddify first setup."
    if [[ -n "$TELEGRAM_BOT_TOKEN" ]]; then
        echo "Telegram bot token configured in panel settings."
    else
        echo "Telegram bot token not configured."
    fi
    if [[ "$ENABLE_TELEGRAM_PAYMENTS" == "1" && -n "$TELEGRAM_PAYMENT_PROVIDER_TOKEN" ]]; then
        echo "Telegram payments (YooKassa provider token) enabled via server-only env file."
    else
    echo "Telegram payments not enabled."
    fi
    if [[ -n "$HIDDIFY_TELEGRAM_WEBHOOK_SECRET" ]]; then
        echo "Telegram webhook secret configured in server-only env file."
        echo "Webhook will be refreshed automatically after first setup saves the real panel domain."
    fi
    if [[ -n "$HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN" ]]; then
        echo "Telegram webhook domain fixed to: $HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN"
    fi
    if [[ -n "$HIDDIFY_SUPPORT_URL" ]]; then
        echo "Support URL configured: $HIDDIFY_SUPPORT_URL"
    fi
    echo "Telegram bot registration mode: ${HIDDIFY_TELEGRAM_REGISTRATION_MODE}"
    if [[ -n "$TELEGRAM_BOT_TOKEN" && -n "$owner_uuid" ]]; then
        echo "Bind admin notifications in Telegram with:"
        echo "/start admin_$owner_uuid"
    fi
    echo "Note: current commercial build includes the tested trial onboarding profile by code."
}

main() {
    require_root
    write_secrets_env
    write_systemd_overrides
    ensure_haproxy_runtime
    configure_panel
    restart_services
    refresh_telegram_webhook
    print_summary
}

main "$@"
