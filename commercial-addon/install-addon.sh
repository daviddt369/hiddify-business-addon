#!/usr/bin/env bash
set -euo pipefail

SCRIPT_VERSION="v0.1.5"
INSTALL_DIR="${INSTALL_DIR:-/opt/hiddify-manager}"
ADDON_REPO="${ADDON_REPO:-https://github.com/daviddt369/hiddify-business-addon.git}"
ADDON_REF="${ADDON_REF:-$SCRIPT_VERSION}"
ALLOW_UNPINNED="${ALLOW_UNPINNED:-0}"
TMP_ROOT="${TMP_ROOT:-/tmp/hiddify-business-addon}"
MANIFEST_PATH="${MANIFEST_PATH:-$INSTALL_DIR/business-addon.manifest}"

log() {
    echo "[commercial-addon] $*"
}

die() {
    echo "[commercial-addon][ERROR] $*" >&2
    exit 1
}

is_commit_sha() {
    [[ "$1" =~ ^[0-9a-f]{40}$ ]]
}

is_version_tag() {
    [[ "$1" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z._-]+)?$ ]]
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

validate_addon_ref() {
    if is_version_tag "$ADDON_REF" || is_commit_sha "$ADDON_REF"; then
        return 0
    fi

    if [[ "$ALLOW_UNPINNED" == "1" ]]; then
        log "ВНИМАНИЕ: используется неприбитый ref '$ADDON_REF' из-за ALLOW_UNPINNED=1"
        return 0
    fi

    die "ADDON_REF должен быть pinned tag (например v0.1.5) или полным commit SHA. Для неприбитого ref явно укажи ALLOW_UNPINNED=1"
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

resolve_commit_sha() {
    git -C "$TMP_ROOT/addon" rev-parse HEAD
}

write_manifest() {
    local stamp="$1"
    local commit_sha="$2"
    local tmp_manifest
    tmp_manifest="$(mktemp)"

    cat > "$tmp_manifest" <<EOF
INSTALL_TIMESTAMP=$stamp
SCRIPT_VERSION=$SCRIPT_VERSION
ADDON_REPO=$ADDON_REPO
ADDON_REF=$ADDON_REF
ADDON_COMMIT_SHA=$commit_sha
INSTALL_DIR=$INSTALL_DIR
EOF

    install -m 0644 "$tmp_manifest" "$MANIFEST_PATH"
    rm -f "$tmp_manifest"
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
    local commit_sha
    stamp="$(date +%F-%H%M%S)"

    require_root
    require_base_install
    check_supported_version
    validate_addon_ref
    print_intro
    prepare_temp
    clone_addon_repo
    commit_sha="$(resolve_commit_sha)"
    sync_manager_overlay "$stamp"
    sync_panel_overlay "$stamp"
    write_manifest "$stamp" "$commit_sha"

    echo
    log "Overlay установлен."
    log "Бэкапы созданы с суффиксом .bak.$stamp"
    log "Manifest записан в $MANIFEST_PATH"
    log "Установленный ref: $ADDON_REF"
    log "Commit SHA: $commit_sha"
    log "Запускаю interactive commercial finalize..."
    echo

    bash "$INSTALL_DIR/scripts/finalize-commercial.sh"
}

main "$@"
