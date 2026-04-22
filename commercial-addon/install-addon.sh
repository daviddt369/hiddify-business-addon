#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/hiddify-manager}"
ADDON_REPO="${ADDON_REPO:-https://github.com/daviddt369/hiddify-business-addon.git}"
ADDON_REF="${ADDON_REF:-main}"
TMP_ROOT="${TMP_ROOT:-/tmp/hiddify-business-addon}"

log() {
    echo "[commercial-addon] $*"
}

die() {
    echo "[commercial-addon][ERROR] $*" >&2
    exit 1
}

require_root() {
    [[ "$(id -u)" -eq 0 ]] || die "Запусти installer от root."
}

require_base_install() {
    [[ -d "$INSTALL_DIR" ]] || die "Базовая установка Hiddify не найдена: $INSTALL_DIR"
    [[ -d "$INSTALL_DIR/hiddify-panel" ]] || die "Не найдена панель в $INSTALL_DIR"
    [[ -f "$INSTALL_DIR/VERSION" ]] || die "Не найден VERSION в $INSTALL_DIR"
}

check_supported_version() {
    local version
    version="$(tr -d '\r\n' < "$INSTALL_DIR/VERSION")"
    case "$version" in
        12.*)
            log "Найдена поддерживаемая версия Hiddify: $version"
            ;;
        *)
            die "Неподдерживаемая версия Hiddify: $version. Поддерживается только ветка 12.x"
            ;;
    esac
}

prepare_temp() {
    rm -rf "$TMP_ROOT"
    mkdir -p "$TMP_ROOT"
}

clone_addon_repo() {
    git clone --depth 1 --branch "$ADDON_REF" "$ADDON_REPO" "$TMP_ROOT/addon" >/dev/null 2>&1 \
        || die "Не удалось скачать addon repo: $ADDON_REPO ($ADDON_REF)"
}

backup_target() {
    local path="$1"
    local stamp="$2"
    if [[ -e "$path" ]]; then
        cp -a "$path" "${path}.bak.${stamp}"
    fi
}

sync_manager_overlay() {
    local stamp="$1"
    local repo_root="$TMP_ROOT/addon"

    mkdir -p "$INSTALL_DIR/scripts"
    mkdir -p "$INSTALL_DIR/stable_beta10"

    backup_target "$INSTALL_DIR/scripts/finalize-commercial.sh" "$stamp"
    backup_target "$INSTALL_DIR/scripts/post-install-commercial.sh" "$stamp"
    backup_target "$INSTALL_DIR/stable_beta10/install-commercial.sh" "$stamp"

    install -m 0755 "$repo_root/manager-overlay/scripts/finalize-commercial.sh" \
        "$INSTALL_DIR/scripts/finalize-commercial.sh"
    install -m 0755 "$repo_root/manager-overlay/scripts/post-install-commercial.sh" \
        "$INSTALL_DIR/scripts/post-install-commercial.sh"
    install -m 0755 "$repo_root/manager-overlay/stable_beta10/install-commercial.sh" \
        "$INSTALL_DIR/stable_beta10/install-commercial.sh"
}

sync_panel_overlay() {
    local stamp="$1"
    local repo_root="$TMP_ROOT/addon"
    local panel_src="$INSTALL_DIR/hiddify-panel/src/hiddifypanel"
    local runtime_pkg=""

    runtime_pkg="$("$INSTALL_DIR/.venv313/bin/python" - <<'PY'
import os
import hiddifypanel
print(os.path.dirname(hiddifypanel.__file__))
PY
)"

    [[ -d "$runtime_pkg" ]] || die "Не найден runtime package панели: $runtime_pkg"

    mkdir -p "$panel_src"
    backup_target "$panel_src" "$stamp"
    backup_target "$runtime_pkg" "$stamp"

    rsync -a --delete --exclude '.git' "$repo_root/panel-overlay/hiddifypanel/" "$panel_src/"
    rsync -a --delete --exclude '.git' "$repo_root/panel-overlay/hiddifypanel/" "$runtime_pkg/"
}

print_intro() {
    cat <<'EOF'
Business addon installer

Этот режим ожидает:
1. official Hiddify Manager уже установлен в /opt/hiddify-manager
2. first setup уже завершён
3. реальный домен панели уже сохранён

Что делает installer:
- накатывает manager overlay
- накатывает panel overlay
- запускает интерактивный шаг commercial finalize
EOF
}

main() {
    local stamp
    stamp="$(date +%F-%H%M%S)"

    require_root
    require_base_install
    check_supported_version
    print_intro
    prepare_temp
    clone_addon_repo
    sync_manager_overlay "$stamp"
    sync_panel_overlay "$stamp"

    echo
    log "Overlay установлен."
    log "Бэкапы созданы с суффиксом .bak.$stamp"
    log "Запускаю interactive commercial finalize..."
    echo

    bash "$INSTALL_DIR/scripts/finalize-commercial.sh"
}

main "$@"
