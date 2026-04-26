#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/daviddt369/hiddify-business-addon}"
BRANCH="${BRANCH:-routing_hiddify_addons}"
HIDDIFY_DIR="${HIDDIFY_DIR:-/opt/hiddify-manager}"

INSTALL_XRAY_ROUTER_TEST="${INSTALL_XRAY_ROUTER_TEST:-0}"
INSTALL_DB_ENUMS="${INSTALL_DB_ENUMS:-1}"

TS="$(date +%F_%H-%M-%S)"
TMP_DIR="/tmp/hiddify-commercial-routing-$TS"
BACKUP_DIR="/root/commercial-routing-install-backups/$TS"

BOOL_KEYS=(
  commercial_routing_enable
  commercial_apply_to_xray
  commercial_apply_to_singbox
  commercial_ru_geoip_enabled
)

STR_KEYS=(
  commercial_router_host
  commercial_router_port
  commercial_router_protocol
  commercial_domestic_policy
  commercial_udp443_policy
  commercial_ru_domain_suffixes
  commercial_default_global_policy
  commercial_router_core_type
  commercial_de_tunnel_type
  commercial_de_endpoint
  commercial_de_public_key
  commercial_de_private_key_ref
  commercial_de_vless_uri
  commercial_de_trojan_uri
)

log() {
  echo "[commercial-routing-install] $*" >&2
}

fail() {
  echo "[commercial-routing-install][ERROR] $*" >&2
  exit 1
}

need_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    fail "Run as root"
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"
}

backup_file() {
  local path="$1"
  if [[ -e "$path" ]]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$path")"
    cp -a "$path" "$BACKUP_DIR/$path"
  fi
}

copy_overlay_file() {
  local src="$1"
  local dst="$2"

  if [[ ! -f "$src" ]]; then
    fail "Source file not found: $src"
  fi

  backup_file "$dst"
  mkdir -p "$(dirname "$dst")"
  cp -a "$src" "$dst"
}

download_branch() {
  mkdir -p "$TMP_DIR"
  cd "$TMP_DIR"

  log "Downloading ${REPO_URL} branch ${BRANCH}"

  curl -fsSL "${REPO_URL}/archive/refs/heads/${BRANCH}.tar.gz" -o addon.tar.gz
  tar -xzf addon.tar.gz

  local extracted
  extracted="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"

  if [[ -z "$extracted" ]]; then
    fail "Cannot find extracted addon directory"
  fi

  echo "$extracted"
}

detect_mysql_db() {
  local db=""

  if [[ -n "${MYSQL_DB:-}" ]]; then
    echo "$MYSQL_DB"
    return 0
  fi

  db="$(mysql -NBe "SHOW DATABASES" 2>/dev/null | grep -E '^hiddifypanel$|hiddify|panel' | head -n 1 || true)"

  if [[ -z "$db" ]]; then
    fail "Cannot detect MySQL database. Run with MYSQL_DB=your_db_name"
  fi

  echo "$db"
}

kill_old_enum_queries() {
  log "Killing old hanging ENUM ALTER queries if any"

  mysql -NBe "SHOW FULL PROCESSLIST" | awk '/ALTER TABLE.*(bool_config|str_config).*MODIFY COLUMN.*key/ {print $1}' | while read -r id; do
    if [[ -n "$id" ]]; then
      log "KILL MySQL query id $id"
      mysql -e "KILL $id;" || true
    fi
  done
}

alter_enum_add_values() {
  local db="$1"
  local table="$2"
  shift 2
  local new_values=("$@")

  log "Checking ENUM ${db}.${table}.key"

  local type
  type="$(mysql "$db" -NBe "SHOW COLUMNS FROM \`${table}\` LIKE 'key';" | awk '{print $2}')"

  if [[ -z "$type" ]]; then
    fail "Cannot read ${db}.${table}.key column"
  fi

  local enum_sql
  enum_sql="$(python3 - "$type" "${new_values[@]}" <<'PY'
import csv
import sys

current_type = sys.argv[1]
to_add = sys.argv[2:]

if not current_type.startswith("enum("):
    raise SystemExit(f"column is not enum: {current_type}")

inner = current_type[len("enum("):-1]
reader = csv.reader([inner], quotechar="'", escapechar="\\")
values = next(reader)

changed = False
for value in to_add:
    if value not in values:
        values.append(value)
        changed = True

def q(v):
    return "'" + v.replace("\\", "\\\\").replace("'", "''") + "'"

if changed:
    print("enum(" + ",".join(q(v) for v in values) + ")")
else:
    print("")
PY
)"

  if [[ -z "$enum_sql" ]]; then
    log "No ENUM changes needed for ${table}"
    return 0
  fi

  log "Altering ${db}.${table}.key ENUM"

  local sql_file
  sql_file="$(mktemp)"

  cat > "$sql_file" <<SQL
SET SESSION lock_wait_timeout=30;
ALTER TABLE \`${table}\` MODIFY COLUMN \`key\` ${enum_sql} NOT NULL;
SQL

  timeout 120 mysql "$db" < "$sql_file"
  rm -f "$sql_file"
}

stop_panel_for_db_migration() {
  log "Stopping panel services before DB enum migration"

  systemctl stop hiddify-panel-background-tasks 2>/dev/null || true
  systemctl stop hiddify-panel 2>/dev/null || true

  sleep 2
}

start_panel_services() {
  log "Starting panel services"

  systemctl restart hiddify-panel || true
  systemctl restart hiddify-panel-background-tasks || true

  systemctl status hiddify-panel --no-pager || true
  systemctl status hiddify-panel-background-tasks --no-pager || true
}

update_mysql_enums() {
  if [[ "$INSTALL_DB_ENUMS" != "1" ]]; then
    log "Skipping MySQL ENUM update because INSTALL_DB_ENUMS=$INSTALL_DB_ENUMS"
    return 0
  fi

  if ! command -v mysql >/dev/null 2>&1; then
    log "mysql command not found, skipping ENUM update"
    return 0
  fi

  local db
  db="$(detect_mysql_db)"

  log "Detected MySQL database: $db"

  stop_panel_for_db_migration
  kill_old_enum_queries

  alter_enum_add_values "$db" "bool_config" "${BOOL_KEYS[@]}"
  alter_enum_add_values "$db" "str_config" "${STR_KEYS[@]}"
}

copy_overlays() {
  local src_root="$1"

  log "Creating backup dir: $BACKUP_DIR"
  mkdir -p "$BACKUP_DIR"

  log "Copying panel overlay"

  copy_overlay_file "$src_root/panel-overlay/hiddifypanel/models/config_enum.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/models/config_enum.py"

  copy_overlay_file "$src_root/panel-overlay/hiddifypanel/panel/init_db.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/panel/init_db.py"

  copy_overlay_file "$src_root/panel-overlay/hiddifypanel/panel/admin/BusinessAdmin.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/panel/admin/BusinessAdmin.py"

  copy_overlay_file "$src_root/panel-overlay/hiddifypanel/panel/cli.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/panel/cli.py"

  copy_overlay_file "$src_root/panel-overlay/hiddifypanel/templates/business-settings.html" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/templates/business-settings.html"

  copy_overlay_file "$src_root/panel-overlay/hiddifypanel/models/commercial_routing_custom_rule.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/models/commercial_routing_custom_rule.py"

  copy_overlay_file "$src_root/panel-overlay/hiddifypanel/hutils/commercial_routing.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/hutils/commercial_routing.py"

  copy_overlay_file "$src_root/panel-overlay/hiddifypanel/hutils/proxy/router_core.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/hutils/proxy/router_core.py"

  log "Copying manager overlay"

  copy_overlay_file "$src_root/manager-overlay/xray/configs/03_routing.json.j2" \
    "$HIDDIFY_DIR/xray/configs/03_routing.json.j2"

  copy_overlay_file "$src_root/manager-overlay/xray/configs/06_outbounds.json.j2" \
    "$HIDDIFY_DIR/xray/configs/06_outbounds.json.j2"

  copy_overlay_file "$src_root/manager-overlay/singbox/configs/03_routing.json.j2" \
    "$HIDDIFY_DIR/singbox/configs/03_routing.json.j2"

  copy_overlay_file "$src_root/manager-overlay/singbox/configs/06_outbounds.json.j2" \
    "$HIDDIFY_DIR/singbox/configs/06_outbounds.json.j2"
}

copy_runtime_site_packages() {
  log "Checking runtime site-packages copies"

  local src_panel="$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel"

  if [[ ! -d "$src_panel" ]]; then
    log "Source panel package not found, skipping runtime copy"
    return 0
  fi

  mapfile -t targets < <(find "$HIDDIFY_DIR" -type d -path "*/site-packages/hiddifypanel" 2>/dev/null || true)

  if [[ "${#targets[@]}" -eq 0 ]]; then
    log "No runtime site-packages hiddifypanel found, skipping"
    return 0
  fi

  for dst in "${targets[@]}"; do
    log "Copying runtime package to $dst"
    rsync -a "$src_panel/" "$dst/"
  done
}

compile_python() {
  log "Compiling changed Python files"

  local py="python3"

  if [[ -x "$HIDDIFY_DIR/.venv313/bin/python" ]]; then
    py="$HIDDIFY_DIR/.venv313/bin/python"
  elif [[ -x "$HIDDIFY_DIR/.venv/bin/python" ]]; then
    py="$HIDDIFY_DIR/.venv/bin/python"
  fi

  "$py" -m py_compile \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/models/config_enum.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/panel/init_db.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/panel/admin/BusinessAdmin.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/panel/cli.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/models/commercial_routing_custom_rule.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/hutils/commercial_routing.py" \
    "$HIDDIFY_DIR/hiddify-panel/src/hiddifypanel/hutils/proxy/router_core.py"
}

write_xray_router_test_blackhole() {
  log "Writing xray-router test_blackhole config"

  mkdir -p /etc/xray-router

  if [[ -f /etc/xray-router/config.json ]]; then
    backup_file /etc/xray-router/config.json
  fi

  cat > /etc/xray-router/config.json <<'JSON'
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "tag": "from-hiddify",
      "listen": "127.0.0.1",
      "port": 20808,
      "protocol": "socks",
      "settings": {
        "auth": "noauth",
        "udp": true,
        "ip": "127.0.0.1"
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls", "quic"],
        "routeOnly": true
      }
    }
  ],
  "outbounds": [
    {
      "tag": "to-de",
      "protocol": "blackhole"
    },
    {
      "tag": "direct-ru",
      "protocol": "freedom"
    },
    {
      "tag": "block",
      "protocol": "blackhole"
    }
  ],
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "rules": [
      {
        "type": "field",
        "domain": [
          "regexp:.*\\.ru$",
          "regexp:.*\\.su$",
          "regexp:.*\\.xn--p1ai$"
        ],
        "outboundTag": "direct-ru"
      },
      {
        "type": "field",
        "ip": ["geoip:ru"],
        "outboundTag": "direct-ru"
      },
      {
        "type": "field",
        "network": "tcp,udp",
        "outboundTag": "to-de"
      }
    ]
  }
}
JSON

  xray run -test -config /etc/xray-router/config.json

  if [[ -f /etc/systemd/system/xray-router.service ]]; then
    backup_file /etc/systemd/system/xray-router.service
  fi

  cat > /etc/systemd/system/xray-router.service <<'EOF'
[Unit]
Description=Xray Router Core for Commercial Routing
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
ExecStart=/usr/local/bin/xray run -config /etc/xray-router/config.json
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now xray-router
  systemctl status xray-router --no-pager || true
}

main() {
  need_root
  need_cmd curl
  need_cmd tar
  need_cmd rsync
  need_cmd python3
  need_cmd timeout

  [[ -d "$HIDDIFY_DIR" ]] || fail "Hiddify dir not found: $HIDDIFY_DIR"

  local src_root
  src_root="$(download_branch)"

  copy_overlays "$src_root"
  update_mysql_enums
  compile_python
  copy_runtime_site_packages

  if [[ "$INSTALL_XRAY_ROUTER_TEST" == "1" ]]; then
    write_xray_router_test_blackhole
  else
    log "Skipping xray-router system install. To enable test router, rerun with INSTALL_XRAY_ROUTER_TEST=1"
  fi

  start_panel_services

  log "Done"
  log "Backup dir: $BACKUP_DIR"
  log "Routing is not automatically enabled in Hiddify settings."
}

main "$@"