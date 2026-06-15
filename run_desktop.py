"""
⚠️ DEPRECATED — pywebview 原生窗口启动器已废弃。

DataBox 的主要桌面交付路径是 Tauri:
    cd desktop && npm run tauri dev

此脚本仅保留用于快速体验，不会自动安装依赖。
"""

import os
import sys
import subprocess
import time
import socket

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def is_port_open(port):
    """Check if local port is active"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def _ensure_pywebview():
    """Check pywebview is available; fail with instructions if not."""
    try:
        import webview  # noqa: F401
    except ImportError:
        print("[-] pywebview 未安装。请运行: pip install pywebview")
        sys.exit(1)

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root_dir)
    
    print("=================================================================")
    print("   DataBox — Native 窗口渲染启动器 (遗留)")
    print("   推荐使用: cd desktop && npm run tauri dev")
    print("=================================================================")

    # 1. Check pywebview
    _ensure_pywebview()
    import webview
    
    # 2. Check if backend & frontend services are already running
    # If not running, let's start them automatically in background
    backend_proc = None
    frontend_proc = None
    
    # Check if FastAPI backend (Port 18625) is running
    if not is_port_open(18625):
        print(">>> 检测到 DataBox 审计及 AI 引擎后台未启动，正在拉起 (热更新已开启)...")
        backend_proc = subprocess.Popen(
            [sys.executable, "-m", "engine.main", "--reload"],
            cwd=root_dir,
            env=os.environ.copy()
        )
        # Wait for port
        for _ in range(30):
            if is_port_open(18625):
                print("[+] Local Engine 就绪！")
                break
            time.sleep(0.5)
            
    # Check if Vite front-end (Port 5173 or 5174) is running
    front_port = None
    for p in [5173, 5174, 5175]:
        if is_port_open(p):
            front_port = p
            break
            
    if not front_port:
        print(">>> 检测到 React 前端服务未激活，正在拉起开发服务服务器...")
        desktop_dir = os.path.join(ROOT_DIR, "desktop")

        if not os.path.exists(os.path.join(desktop_dir, "node_modules")):
            print("[-] 前端依赖未安装。请运行: cd desktop && npm install")
            sys.exit(1)

        frontend_proc = subprocess.Popen(
            "npm run dev",
            shell=True,
            cwd=desktop_dir,
            env=os.environ.copy()
        )
        
        # Wait for port to open
        for _ in range(30):
            for p in [5173, 5174, 5175]:
                if is_port_open(p):
                    front_port = p
                    break
            if front_port:
                break
            time.sleep(0.5)
            
    if not front_port:
        print("[-] 无法加载前端服务。请手动运行 npm run dev 检查是否有编译错误。")
        sys.exit(1)
        
    url = f"http://localhost:{front_port}"
    print(f"\n[★] DataBox 桌面服务就绪，正在激活 native Windows WebView2 渲染框架...")
    print(f"  - 交互视图地址: {url}")
    print("=================================================================\n")
    
    try:
        # Create a premium, hardware-accelerated desktop client view frame
        webview.create_window(
            title="DataBox 智能安全数据探索桌面客户端",
            url=url,
            width=1440,
            height=900,
            min_size=(1024, 768),
            text_select=True
        )
        webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n>>> 正在安全退出 DataBox 桌面应用，回收底层服务进程...")
        if backend_proc:
            backend_proc.terminate()
        if frontend_proc:
            if sys.platform == "win32":
                subprocess.call(f"taskkill /F /T /PID {frontend_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                frontend_proc.terminate()
        print("[+] 感谢使用 DataBox 客户端！")

if __name__ == "__main__":
    main()
