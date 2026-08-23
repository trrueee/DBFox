#!/usr/bin/env bash
# DBFox 开发环境一键启动脚本 (Unix / macOS / Git Bash)
# 用法: ./dev.sh [backend|frontend|both]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

TARGET="${1:-both}"

# 查找 Python：优先使用开发环境 .venv，否则回退到系统 Python。
# .build_venv 只属于 Frozen Sidecar 发布构建，开发脚本不使用。
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "[DBFox] ERROR: Python not found."
    exit 1
fi

echo "[DBFox] Python: $PYTHON"

start_backend() {
    initialize_system_dlcs
    echo "[DBFox] Starting backend engine on http://127.0.0.1:18625 ..."
    exec "$PYTHON" -m engine.main "$@"
}

initialize_system_dlcs() {
    local bundle
    bundle="$($PYTHON -m scripts.prepare_dev_system_dlcs)"
    export DBFOX_SYSTEM_DLC_DIR
    export DBFOX_SYSTEM_DLC_MANIFEST
    DBFOX_SYSTEM_DLC_DIR="$($PYTHON -c 'import json,sys; print(json.load(sys.stdin)["package_dir"])' <<<"$bundle")"
    DBFOX_SYSTEM_DLC_MANIFEST="$($PYTHON -c 'import json,sys; print(json.load(sys.stdin)["manifest"])' <<<"$bundle")"
}

start_frontend() {
    echo "[DBFox] Starting frontend (Vite) on http://localhost:5173 ..."
    cd "$SCRIPT_DIR/desktop"
    exec npm run dev
}

initialize_shared_dev_token() {
    local token
    token="$($PYTHON "$SCRIPT_DIR/scripts/dev_environment.py")"
    if [ -z "$token" ]; then
        echo "[DBFox] ERROR: failed to generate the local development token." >&2
        exit 1
    fi
    export DBFOX_ENGINE_TOKEN="$token"
}

wait_backend_ready() {
    for _ in $(seq 1 120); do
        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "[DBFox] ERROR: backend exited before becoming healthy." >&2
            return 1
        fi
        if "$PYTHON" -c 'import json, os, urllib.request; request = urllib.request.Request("http://127.0.0.1:18625/api/v1/health", headers={"X-Local-Token": os.environ["DBFOX_ENGINE_TOKEN"], "Origin": "http://127.0.0.1:5173"}); response = urllib.request.urlopen(request, timeout=1); raise SystemExit(0 if json.load(response).get("status") == "healthy" else 1)' 2>/dev/null; then
            return 0
        fi
        sleep 0.25
    done
    echo "[DBFox] ERROR: backend health check timed out." >&2
    return 1
}

case "$TARGET" in
    backend)
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    both)
        initialize_shared_dev_token
        initialize_system_dlcs
        echo "[DBFox] Starting backend in background..."
        "$PYTHON" -m engine.main &
        BACKEND_PID=$!
        trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM
        echo "[DBFox] Waiting for backend to be ready..."
        wait_backend_ready
        echo "[DBFox] Backend is healthy."
        echo "[DBFox] Starting frontend..."
        cd "$SCRIPT_DIR/desktop"
        npm run dev
        ;;
    *)
        echo "Usage: $0 [backend|frontend|both]"
        exit 1
        ;;
esac
