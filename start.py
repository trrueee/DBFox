import os
import sys
import subprocess
import time
import socket
import webbrowser
import threading

def is_port_open(port):
    """Check if local port is active"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def install_python_dependencies():
    """Ensure all core backend libraries are installed in the environment"""
    print(">>> 正在核对并安装 Python 后端依赖库...")
    reqs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", reqs_file])
    print(">>> Python 后端依赖库配置完毕。")

def install_node_dependencies():
    """Ensure npm dependencies are loaded in the desktop client folder"""
    print(">>> 正在检测 React 前端 npm 依赖库...")
    desktop_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop")
    if not os.path.exists(os.path.join(desktop_dir, "node_modules")):
        print(">>> 未检测到 node_modules，正在执行 npm install ...")
        subprocess.check_call("npm install", shell=True, cwd=desktop_dir)
    else:
        print(">>> node_modules 缓存命中。")

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
    print("   DataBox 智能安全桌面客户端 - 自动化一键启动助手 V1.0")
    print("=================================================================")
    
    # 1. Align environments
    try:
        install_python_dependencies()
        install_node_dependencies()
    except Exception as e:
        print(f"[-] 环境初始化检查遇到阻碍: {str(e)}")
        print("[!] 请检查系统网络环境，或尝试手动安装。")
        sys.exit(1)

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
