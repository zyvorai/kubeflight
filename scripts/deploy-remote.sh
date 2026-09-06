#!/usr/bin/env bash
# Copyright 2026 Zyvor AI Labs · https://zyvor.dev
# SPDX-License-Identifier: Apache-2.0
# ============================================================================
# deploy-remote.sh — Deploy KubeFlight to a remote host as a systemd service
# KubeFlight is a Python app (FastAPI + uvicorn). Deployment:
#   1. Detect remote Python (>=3.11) over SSH
#   2. Ship source tarball (no local build required)
#   3. Create /opt/kubeflight venv, pip install -e .
#   4. Install systemd unit + env, open firewall port
#   5. Verify with scripts/smoke-remote.sh
#
# Usage:
#   ./scripts/deploy-remote.sh <host> [user] [password] [options]
#   ./scripts/deploy-remote.sh 212.8.248.187 sus
#   ./scripts/deploy-remote.sh 212.8.248.187 sus --port 27754
#   KUBEFLIGHT_PORT=27754 ./scripts/deploy-remote.sh 212.8.248.187 sus
#   ./scripts/deploy-remote.sh 212.8.248.187 sus --uninstall
#   ./scripts/deploy-remote.sh 212.8.248.187 sus --dry-run
#
# Options:
#   --port N      Listen/health-check TCP port (overrides env and .deploy-last)
#   --uninstall   Stop kubeflight.service and remove install from the host
#   --dry-run     Print what would happen; make no changes
#   --skip-smoke  Skip the smoke-remote.sh step at the end
#   --verbose     Show full remote command output
#
# Port resolution (first match wins):
#   1. --port N
#   2. KUBEFLIGHT_PORT env
#   3. PORT from .deploy-last (redeploy keeps the same port)
#   4. random in 18000–28999
#
# Environment variables:
#   DEPLOY_HOST, DEPLOY_USER, DEPLOY_PASS   — same as the positional args
#   KUBEFLIGHT_PORT                          — listen/health-check port

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/deploy-common.sh
source "$SCRIPT_DIR/lib/deploy-common.sh"

info()  { kubeflight_info "$@"; }
warn()  { kubeflight_warn "$@"; }
error() { kubeflight_error "$@"; }
step()  { LAST_ACTION="$*"; deploy_ui_step_start "$*"; }

REMOTE_ROOT=/opt/kubeflight
REMOTE_ENV=/etc/kubeflight/kubeflight.env
REMOTE_UNIT=/etc/systemd/system/kubeflight.service

# ── Parse args ──
UNINSTALL_MODE=false
DRY_RUN=false
SKIP_SMOKE=false
VERBOSE=false
PORT_FROM_CLI=""
POSITIONAL=()
while [ $# -gt 0 ]; do
    case "$1" in
        --port)
            [ $# -ge 2 ] || error "--port requires a value"
            PORT_FROM_CLI="$2"
            shift 2
            ;;
        --port=*)
            PORT_FROM_CLI="${1#*=}"
            shift
            ;;
        --uninstall)  UNINSTALL_MODE=true; shift ;;
        --dry-run)    DRY_RUN=true; shift ;;
        --skip-smoke) SKIP_SMOKE=true; shift ;;
        --verbose)    VERBOSE=true; shift ;;
        --help|-h)
            sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        --)
            shift
            POSITIONAL+=("$@")
            break
            ;;
        -*)
            error "Unknown option: $1 (see --help)"
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

HOST="${POSITIONAL[0]:-${DEPLOY_HOST:-}}"
USER="${POSITIONAL[1]:-${DEPLOY_USER:-root}}"
PASS="${POSITIONAL[2]:-${DEPLOY_PASS:-}}"

kubeflight_parse_target HOST USER
LAST_PORT=""
if [ -z "$HOST" ] && kubeflight_load_deploy_last "$REPO_DIR"; then
    info "Using .deploy-last → ${USER}@${HOST}"
    LAST_PORT="${PORT:-}"
elif [ -f "$REPO_DIR/.deploy-last" ]; then
    LAST_PORT="$(awk -F= '/^PORT=/ {print $2; exit}' "$REPO_DIR/.deploy-last")"
fi
[ -z "$HOST" ] && error "Usage: $0 <host> [user] [password] [options]  (see --help)"

# Resolve listen port: --port > env > .deploy-last > random
if [ -n "$PORT_FROM_CLI" ]; then
    KUBEFLIGHT_PORT="$PORT_FROM_CLI"
elif [ -n "${KUBEFLIGHT_PORT:-}" ]; then
    :
elif [ -n "$LAST_PORT" ]; then
    KUBEFLIGHT_PORT="$LAST_PORT"
    info "Reusing port ${KUBEFLIGHT_PORT} from .deploy-last"
else
    KUBEFLIGHT_PORT=$((18000 + RANDOM % 11000))
    info "Selected random port ${KUBEFLIGHT_PORT}"
fi
case "$KUBEFLIGHT_PORT" in
    ''|*[!0-9]*) error "Invalid port: ${KUBEFLIGHT_PORT} (need integer 1–65535)" ;;
esac
if [ "$KUBEFLIGHT_PORT" -lt 1 ] || [ "$KUBEFLIGHT_PORT" -gt 65535 ]; then
    error "Port out of range: ${KUBEFLIGHT_PORT} (need 1–65535)"
fi

[ -f "$REPO_DIR/pyproject.toml" ] || error "Not in the kubeflight repo: $REPO_DIR"
[ -d "$REPO_DIR/kubeflight" ] || error "kubeflight/ package missing in $REPO_DIR"
kubeflight_build_metadata "$REPO_DIR"
DEPLOY_UI_PORT="$KUBEFLIGHT_PORT"

SUDO=""
[ "$USER" != "root" ] && SUDO="sudo"

DEPLOY_SSH_OPTS=(
    -o StrictHostKeyChecking=no
    -o ConnectTimeout=15
    -o ServerAliveInterval=15
    -o ServerAliveCountMax=8
)
DEPLOY_SSH_TTY_OPTS=()
[ "$USER" != "root" ] && DEPLOY_SSH_TTY_OPTS=(-tt)

if [ -n "$PASS" ] && ! command -v sshpass &>/dev/null; then
    error "sshpass required for password auth (brew install sshpass / dnf install sshpass)"
fi

_ssh() {
    local -a ssh_args=("${DEPLOY_SSH_OPTS[@]}" "${DEPLOY_SSH_TTY_OPTS[@]}")
    if [ -n "$PASS" ]; then
        SSHPASS="$PASS" sshpass -e ssh "${ssh_args[@]}" "${USER}@${HOST}" "$@"
    else
        ssh "${ssh_args[@]}" "${USER}@${HOST}" "$@"
    fi
}

_ssh_batch() {
    local -a ssh_args=("${DEPLOY_SSH_OPTS[@]}")
    if [ -n "$PASS" ]; then
        SSHPASS="$PASS" sshpass -e ssh "${ssh_args[@]}" "${USER}@${HOST}" "$@"
    else
        ssh "${ssh_args[@]}" "${USER}@${HOST}" "$@"
    fi
}

_scp() {
    local -a scp_args=("${DEPLOY_SSH_OPTS[@]}")
    if [ -n "$PASS" ]; then
        SSHPASS="$PASS" sshpass -e scp "${scp_args[@]}" "$@"
    else
        scp "${scp_args[@]}" "$@"
    fi
}

if $DRY_RUN; then
    deploy_ui_banner "${DEPLOY_UI_ICON_MAGIC} Dry run" "no changes will be made"
    deploy_ui_kv "🎯" "Target" "${USER}@${HOST}"
    deploy_ui_kv "📦" "Install root" "$REMOTE_ROOT"
    deploy_ui_kv "📄" "Env file" "$REMOTE_ENV (refreshed each deploy)"
    deploy_ui_kv "⚙️" "Unit" "$REMOTE_UNIT"
    echo ""
    deploy_ui_note "Would: detect Python → ship source → venv + pip install → enable/start → smoke-remote.sh"
    echo ""
    exit 0
fi

deploy_ui_banner "Remote Deploy" "${KUBEFLIGHT_GIT_VERSION} (${KUBEFLIGHT_GIT_COMMIT}) → ${USER}@${HOST}"
deploy_ui_kv "🎯" "Target" "${USER}@${HOST}"
deploy_ui_kv "🔐" "Auth" "$([ -n "$PASS" ] && echo 'password' || echo 'SSH key')"
deploy_ui_kv "🌐" "Port" "$KUBEFLIGHT_PORT"
echo ""

# ── Uninstall mode ──
if $UNINSTALL_MODE; then
    deploy_ui_uninstall_banner
    step "Uninstalling kubeflight from ${HOST}"
    _ssh "
        $SUDO systemctl disable --now kubeflight.service 2>/dev/null || true
        $SUDO rm -f $REMOTE_UNIT
        $SUDO rm -rf $REMOTE_ROOT /etc/kubeflight
        $SUDO userdel kubeflight 2>/dev/null || true
        $SUDO systemctl daemon-reload 2>/dev/null || true
    "
    info "kubeflight removed from ${HOST}"
    exit 0
fi

# ── Step 1: detect remote Python ──
step "Detecting remote Python"
REMOTE_PY=$(_ssh_batch "command -v python3" | tr -d '\r')
[ -n "$REMOTE_PY" ] || error "python3 not found on remote"
REMOTE_PY_VER=$(_ssh_batch "$REMOTE_PY -c 'import sys; print(\"%d.%d\" % sys.version_info[:2])'" | tr -d '\r')
case "$REMOTE_PY_VER" in
    3.11|3.12|3.13|3.14) ;;
    *) error "Remote Python ${REMOTE_PY_VER} is too old (need >=3.11)" ;;
esac
info "Remote: ${REMOTE_PY} (${REMOTE_PY_VER})"

# ── Step 2: package source ──
step "Packaging source"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
COPYFILE_DISABLE=1 tar -C "$REPO_DIR" \
    --exclude='.git' --exclude='.venv' --exclude='venv' --exclude='dist' \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    --exclude='*.egg-info' --exclude='.DS_Store' --exclude='.deploy-last' \
    -czf "$BUILD_DIR/kubeflight.tgz" \
    pyproject.toml requirements.txt README.md LICENSE \
    kubeflight examples
info "Built $BUILD_DIR/kubeflight.tgz"

# ── Step 3: install on remote ──
step "Installing kubeflight on ${HOST}"
_scp "$BUILD_DIR/kubeflight.tgz" "${USER}@${HOST}:/tmp/kubeflight.tgz"
_scp "$REPO_DIR/systemd/kubeflight.service" "${USER}@${HOST}:/tmp/kubeflight.service.new"

cat > "$BUILD_DIR/kubeflight.env" <<ENVEOF
KUBEFLIGHT_PORT=${KUBEFLIGHT_PORT}
ENVEOF
_scp "$BUILD_DIR/kubeflight.env" "${USER}@${HOST}:/tmp/kubeflight.env.new"

_ssh "
    set -euo pipefail
    $SUDO id -u kubeflight >/dev/null 2>&1 || $SUDO useradd --system --home $REMOTE_ROOT --shell /usr/sbin/nologin kubeflight
    $SUDO mkdir -p $REMOTE_ROOT /etc/kubeflight
    $SUDO tar -C $REMOTE_ROOT -xzf /tmp/kubeflight.tgz
    rm -f /tmp/kubeflight.tgz
    if [ ! -d $REMOTE_ROOT/.venv ]; then
        $SUDO $REMOTE_PY -m venv $REMOTE_ROOT/.venv
    fi
    $SUDO $REMOTE_ROOT/.venv/bin/pip install -q --upgrade pip
    $SUDO $REMOTE_ROOT/.venv/bin/pip install -q -e $REMOTE_ROOT
    $SUDO chown -R kubeflight:kubeflight $REMOTE_ROOT
    $SUDO install -m 640 /tmp/kubeflight.env.new $REMOTE_ENV
    $SUDO chown root:kubeflight $REMOTE_ENV 2>/dev/null || $SUDO chown root:root $REMOTE_ENV
    rm -f /tmp/kubeflight.env.new
    $SUDO install -m 644 /tmp/kubeflight.service.new $REMOTE_UNIT
    rm -f /tmp/kubeflight.service.new
    $REMOTE_ROOT/.venv/bin/kubeflight --help >/dev/null
    echo 'kubeflight CLI OK'
"
info "Source + venv + config + systemd unit installed"

# ── Step 4: enable/start service, open firewall ──
step "Starting kubeflight.service"
_ssh "
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now kubeflight.service
    $SUDO systemctl restart kubeflight.service
    if command -v firewall-cmd &>/dev/null; then
        $SUDO firewall-cmd --permanent --add-port=${KUBEFLIGHT_PORT}/tcp 2>/dev/null || true
        $SUDO firewall-cmd --reload 2>/dev/null || true
    elif command -v ufw &>/dev/null; then
        $SUDO ufw allow ${KUBEFLIGHT_PORT}/tcp 2>/dev/null || true
    fi
    sleep 2
    if $SUDO systemctl is-active kubeflight.service &>/dev/null; then
        echo 'kubeflight.service: running'
    else
        echo 'kubeflight.service: FAILED TO START'
        $SUDO journalctl -u kubeflight.service --no-pager -n 30
        exit 1
    fi
"
info "kubeflight.service active"

# ── Step 5: verify ──
step "Verifying deployment"
BASE_URL="http://${HOST}:${KUBEFLIGHT_PORT}"
DEPLOY_UI_SCHEME="http"
_ssh "curl -fsS http://127.0.0.1:${KUBEFLIGHT_PORT}/api/healthz >/dev/null" \
    && info "Health check OK (http://127.0.0.1:${KUBEFLIGHT_PORT}/api/healthz, on-host)"

kubeflight_save_deploy_last "$REPO_DIR" "$HOST" "$USER" "full"

deploy_ui_highlight "📋 Final checklist"
deploy_ui_checklist "service" "$(_ssh_batch "$SUDO systemctl is-active kubeflight.service" | tr -d '\r')"
deploy_ui_checklist "health"  "$(_ssh_batch "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:${KUBEFLIGHT_PORT}/api/healthz" | tr -d '\r')"

kubeflight_print_success "$HOST" 0

# ── Step 6: smoke from the workstation against the remote URL ──
if $SKIP_SMOKE; then
    info "Skipped smoke-remote.sh (--skip-smoke)"
else
    step "Running scripts/smoke-remote.sh against ${BASE_URL}"
    ( cd "$REPO_DIR" && KUBEFLIGHT_URL="$BASE_URL" ./scripts/smoke-remote.sh )
fi
