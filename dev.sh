#!/usr/bin/env bash
# DBFox 开发环境一键启动脚本 (Unix / macOS / Git Bash)
# 用法: ./dev.sh [backend|frontend|both]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

TARGET="${1:-both}"

# 查找 Python
if [ -f "$SCRIPT_DIR/.build_venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.build_venv/bin/python"
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
    echo "[DBFox] Starting backend engine on http://127.0.0.1:18625 ..."
    exec "$PYTHON" -m engine.main "$@"
}

start_frontend() {
    echo "[DBFox] Starting frontend (Vite) on http://localhost:5173 ..."
    cd "$SCRIPT_DIR/desktop"
    exec npm run dev
}

case "$TARGET" in
    backend)
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    both)
        echo "[DBFox] Starting backend in background..."
        "$PYTHON" -m engine.main &
        BACKEND_PID=$!
        # Wait for backend to write .env.local
        echo "[DBFox] Waiting for backend to be ready..."
        for i in $(seq 1 30); do
            if [ -f "$SCRIPT_DIR/desktop/.env.local" ]; then
                sleep 1
                echo "[DBFox] Backend env file ready."
                break
            fi
            sleep 1
        done
        echo "[DBFox] Starting frontend..."
        start_frontend
        ;;
    *)
        echo "Usage: $0 [backend|frontend|both]"
        exit 1
        ;;
esac
