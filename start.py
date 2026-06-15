"""
⚠️ DEPRECATED — 此启动器已废弃。

DataBox 推荐的启动方式:

  浏览器开发模式:
    pip install -r requirements.txt
    cd desktop && npm install
    python -m engine.main --reload     # 终端 1: 后端
    cd desktop && npm run dev          # 终端 2: 前端 → http://localhost:5173

  Tauri 桌面模式 (主要交付路径):
    pip install -r requirements.txt
    python -m engine.main --reload     # 终端 1: 后端
    cd desktop && npm run tauri dev    # 终端 2: 桌面窗口

此脚本仅保留作为快速体验入口，不会自动安装依赖。
"""

import os
import sys
import subprocess
import time
import socket
import webbrowser

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def is_port_open(port):
    """Check if local port is active"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def _check_backend_deps():
    """Verify Python dependencies are installed."""
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
    except ImportError:
        print("[-] Python 依赖未安装。请运行: pip install -r requirements.txt")
        sys.exit(1)


def _check_frontend_deps():
    """Verify npm dependencies are installed."""
    desktop_dir = os.path.join(ROOT_DIR, "desktop")
    if not os.path.exists(os.path.join(desktop_dir, "node_modules")):
        print("[-] 前端依赖未安装。请运行: cd desktop && npm install")
        sys.exit(1)

def run_backend():
    """Launch the FastAPI server engine with hot reload in dev."""
    print(">>> 正在启动 DataBox 安全审计及 AI 引擎后台 (热更新: engine/*.py)...")
    backend_path = os.path.dirname(os.path.abspath(__file__))
    return subprocess.Popen(
        [sys.executable, "-m", "engine.main", "--reload"],
        cwd=backend_path,
        env=os.environ.copy()
    )

def run_frontend():
    """Launch Vite development server"""
    print(">>> 正在启动 React + TypeScript 桌面极客端...")
    desktop_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop")
    # Run npm run dev in a background process
    return subprocess.Popen(
        "npm run dev",
        shell=True,
        cwd=desktop_dir,
        env=os.environ.copy()
    )

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root_dir)
    
    print("=================================================================")
    print("   DataBox — 浏览器开发模式启动器 (遗留)")
    print("   推荐使用: cd desktop && npm run tauri dev")
    print("=================================================================")

    # 1. Check dependencies (no auto-install)
    _check_backend_deps()
    _check_frontend_deps()

    # 2. Launch Backend
    backend_proc = None
    frontend_proc = None
    try:
        backend_proc = run_backend()
        
        # Wait until port 18625 opens up
        print(">>> 正在等待 Local Engine 安全套接字就绪 (Port: 18625)...")
        for _ in range(30):
            if is_port_open(18625):
                print("[+] Local Engine 就绪！安全令牌 (Token) 已写入 .local_token 文件。")
                break
            time.sleep(0.5)
        else:
            print("[-] Backend Engine 启动超时，请尝试运行 'python -m engine.main' 查看详细报错。")
            sys.exit(1)
            
        # 3. Launch Frontend
        frontend_proc = run_frontend()
        
        # Wait a moment for Vite server, then auto-open browser
        time.sleep(3.0)
        webbrowser.open("http://localhost:5173")
        
        print("\n=================================================================")
        print("[★] DataBox 服务集群已全数启动成功！")
        print("  - 安全后端核心: http://127.0.0.1:18625")
        print("  - 前端开发页面: http://localhost:5173 (浏览器已为您自动打开)")
        print("  - 退出程序: 请在此终端按下 Ctrl+C 键，系统将安全地回收全部进程。")
        print("=================================================================\n")
        
        # Keep waiting
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n>>> 正在安全回收和终止 DataBox 后端及前端进程...")
    finally:
        if backend_proc:
            backend_proc.terminate()
        if frontend_proc:
            # Under Windows npm subprocesses are wrapped in shell, make sure they are fully closed
            if sys.platform == "win32":
                subprocess.call(f"taskkill /F /T /PID {frontend_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                frontend_proc.terminate()
        print("[+] 所有服务进程已回收。谢谢使用 DataBox！")

if __name__ == "__main__":
    main()
