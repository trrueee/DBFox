import os
import sys
import subprocess
import time
import socket

def is_port_open(port):
    """Check if local port is active"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def install_pywebview():
    """Ensure pywebview is installed"""
    try:
        import webview
    except ImportError:
        print(">>> 正在为桌面客户端安装 native 渲染引擎 (pywebview)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pywebview"])
        print("[+] pywebview 安装就绪。")

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root_dir)
    
    print("=================================================================")
    print("   DataBox 智能安全桌面客户端 - Native 窗口渲染启动器 V1.1")
    print("=================================================================")
    
    # 1. Check requirements
    install_pywebview()
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
        desktop_dir = os.path.join(root_dir, "desktop")
        
        # Check node_modules
        if not os.path.exists(os.path.join(desktop_dir, "node_modules")):
            print(">>> 正在为桌面包安装 npm 依赖...")
            subprocess.check_call("npm install", shell=True, cwd=desktop_dir)
            
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
