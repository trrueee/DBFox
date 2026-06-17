# -*- coding: utf-8 -*-
"""
DBFox 本地引擎主入口模块 (Main Entrypoint Module)
---------------------------------------------
这是 DBFox 后端服务的核心入口文件。
它基于 FastAPI 异步 Web 框架构建，提供了：
- 安全策略（CORS 跨域控制、本地 Token 令牌鉴权中间件）
- 异步生命周期管理（启动时连接 SQLite 数据库，退出时关闭 SSH 隧道）
- 异常处理器（拦截全局业务异常）
- 路由挂载
"""

import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from engine.runtime_env import load_runtime_env

# Load env files before any LangChain imports so tracing configuration is active.
load_runtime_env()

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from engine.api import router
from engine.db import init_db
from engine.errors import DBFoxError, NotFoundError
from engine.schemas import ErrorResponse
from engine.runtime_paths import private_runtime_file, write_private_text

# 创建当前模块的日志记录器
logger = logging.getLogger("dbfox.main")

# 计算当前 main.py 所在的 engine 目录以及项目根目录
ENGINE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ENGINE_DIR.parent

# 1. 本地引擎安全性：生成或读取本地安全访问令牌 (Local Secure Token)
TOKEN_FILE = private_runtime_file("auth", ".local_token")


def get_or_create_local_token() -> str:
    """
    获取现有的或者创建全新的本地高强度安全认证 Token。
    
    Python 知识点:
      - `getattr(sys, "frozen", False)`：检测当前 Python 程序是否被打包成了单文件可执行文件（比如用 PyInstaller 或 Tauri 打包）。
        如果是打包后的独立程序，该值为 True，否则为 False。
      - `secrets.token_hex(32)`：利用 Python 的密码学安全随机数生成器生成一个 32 字节（64 个字符）的十六进制随机字符串，极其难被暴力破解。
    """
    # 优先使用 Rust/Tauri 动态传入的 Token
    env_token = os.environ.get("DBFOX_ENGINE_TOKEN")
    if env_token:
        return env_token.strip()

    # 如果是在 Tauri 打包后的“冷冻（frozen）”环境下运行，尝试读取打包时预设的静态 Token
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        try:
            from engine import token_preset
            if token_preset.STATIC_TOKEN:
                return token_preset.STATIC_TOKEN
        except ImportError:
            pass

    # 如果安全 Token 文件存在，直接读取并返回它
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text("utf-8").strip()
        
    # 如果都不存在，生成一个 32 字节高强度随机 Token，并持久化保存
    token = secrets.token_hex(32)
    write_private_text(TOKEN_FILE, token)
    return token


# 初始化并保存当前运行周期的安全令牌
LOCAL_SECURE_TOKEN = get_or_create_local_token()
ALLOWED_TAURI_ORIGINS = {
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
}

# Frontend dev env file helpers.
FRONTEND_ENV_KEYS = {"VITE_LOCAL_ENGINE_PORT", "VITE_LOCAL_ENGINE_TOKEN"}


def _frontend_env_content(token: str) -> str:
    return f"VITE_LOCAL_ENGINE_PORT=18625\nVITE_LOCAL_ENGINE_TOKEN={token}\n"


def _is_dbfox_owned_frontend_env(content: str) -> bool:
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, _value = line.partition("=")
        if separator != "=" or key not in FRONTEND_ENV_KEYS:
            return False
    return True


def _write_frontend_env_file_if_owned(env_file: Path, token: str) -> None:
    expected_content = _frontend_env_content(token)
    existing_content = ""
    if env_file.exists():
        existing_content = env_file.read_text("utf-8")
        if existing_content == expected_content:
            return
        if not _is_dbfox_owned_frontend_env(existing_content):
            logger.info("Skipping automatic desktop/.env.local write; custom content is present.")
            return

    env_file.write_text(expected_content, "utf-8")


# Only write the frontend dev env file in source-mode local development.
is_frozen = getattr(sys, "frozen", False)
if not is_frozen:
    FRONTEND_ENV_FILE = PROJECT_DIR / "desktop" / ".env.local"
    try:
        _write_frontend_env_file_if_owned(FRONTEND_ENV_FILE, LOCAL_SECURE_TOKEN)
    except OSError:
        logger.warning(
            "无法自动将 Token 写入前端 .env.local 配置文件，前端可能需要手动配置环境变量。"
        )


@asynccontextmanager
async def lifespan(application: FastAPI) -> Any:
    """
    异步生命周期管理器 (Lifespan Context Manager)
    
    FastAPI 推荐使用这种方式来执行应用“启动前（Startup）”和“关闭后（Shutdown）”的勾子任务。
    
    Python & FastAPI 知识点:
      - `@asynccontextmanager`：装饰器，用于将一个生成器函数转为异步上下文管理器。
      - `async def`：定义一个异步协程函数。
      - `yield` 关键字是分水岭：
        - `yield` 之前的代码会在 FastAPI 接收请求**启动前**执行（比如执行数据库初始化/迁移）。
        - `yield` 之后的代码会在 FastAPI 接收到关闭信号、退出**停机时**执行（比如清理释放资源）。
    """
    # --- 【启动时任务】 ---
    init_db()  # 初始化本地 SQLite 数据库（自动检查并运行表结构迁移）
    
    port = os.environ.get("DBFOX_ENGINE_PORT", "18625")
    print("===========================================================")
    print("DBFox Local Engine 成功初始化并启动。")
    print(f"服务监听地址: http://127.0.0.1:{port}")
    print(f"安全令牌路径: {TOKEN_FILE}")
    print("===========================================================")
    
    yield  # 此时程序处于运行态，等待并处理前端的所有 API 请求
    
    # --- 【停机时任务】 ---
    from engine.datasource import close_all_tunnels
    close_all_tunnels()  # 安全关闭并释放所有已建立的数据源 SSH 加密隧道连接，防止僵尸进程


# 实例化 FastAPI 核心应用对象
is_frozen = getattr(sys, "frozen", False)
app = FastAPI(
    title="DBFox Local Engine",
    description="专为 DBFox 桌面外壳设计的安全数据库客户端核心引擎",
    version="1.0.0",
    lifespan=lifespan,
    # 如果是在生产打包（frozen）模式下，关闭自动生成的交互式接口文档，提高安全性
    docs_url=None if is_frozen else "/docs",
    redoc_url=None if is_frozen else "/redoc",
    openapi_url=None if is_frozen else "/openapi.json",
)

# 2. 核心安全防护中间件 (Security Guard Middleware)
# 拦截所有请求，校验请求来源 Origin 并且强制校验 X-Local-Token 头部，防止 CSRF 或非法调用
@app.middleware("http")
async def verify_local_access_token(request: Request, call_next):  # type: ignore[no-untyped-def]
    """
    请求校验中间件

    FastAPI 知识点:
      - `verify_local_access_token` 被 `@app.middleware("http")` 装饰后，会在每一次 HTTP 请求到达具体接口路由前被自动调用。
      - `call_next` 是一个协程函数，调用它表示把请求放行并传递给下一个处理器或目标路由，并返回路由生成的 Response。
    """
    # 允许所有 CORS 预检请求（OPTIONS 方法）直接通过，由 CORSMiddleware 处理
    if request.method == "OPTIONS":
        return await call_next(request)

    # 🔒 在生产环境（Tauri 容器内）强制检查请求的 Origin 来源头部
    if is_frozen:
        origin = request.headers.get("origin")
        if not origin:
            # 某些 WebView 请求可能不发送 Origin 头（如 redirect、no-cors），
            # 此时检查 Referer 是否为已知合法来源，避免误杀合理请求。
            referer = request.headers.get("referer", "")
            is_local_referer = any(
                referer.startswith(prefix)
                for prefix in (
                    "http://127.0.0.1",
                    "http://localhost",
                    "https://127.0.0.1",
                    "https://localhost",
                    "tauri://localhost",
                    "http://tauri.localhost",
                    "https://tauri.localhost",
                )
            )
            if not is_local_referer:
                logger.warning(
                    "拦截到缺失 Origin 且 Referer 非本地的请求，Referer: %s", referer
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": "FORBIDDEN_ORIGIN",
                        "message": "拒绝访问：必须从合法的 Origin 发起请求！"
                    }
                )
        elif origin not in ALLOWED_TAURI_ORIGINS:
            logger.warning("拦截到非法的跨域恶意连接请求，尝试来源: %s", origin)
            return JSONResponse(
                status_code=403,
                content={
                    "code": "FORBIDDEN_ORIGIN",
                    "message": "拒绝访问：必须从合法的 Origin 发起请求！"
                }
            )

    # 排除部分不需要 Token 鉴权的公开路由和文档页面
    if request.url.path in ["/", "/docs", "/openapi.json", "/redoc", "/api/v1/health"]:
        if is_frozen and request.url.path in ["/docs", "/openapi.json", "/redoc"]:
            return JSONResponse(
                status_code=404,
                content={"message": "Not Found"}
            )
        return await call_next(request)

    # 🔒 核心 Token 令牌安全校验
    token_header = request.headers.get("X-Local-Token", "")
    if not secrets.compare_digest(token_header, LOCAL_SECURE_TOKEN):
        return JSONResponse(
            status_code=401,
            content={
                "code": "UNAUTHORIZED_ENGINE_ACCESS",
                "message": "拒绝访问：缺少合法或有效的本地认证 Token。",
            },
        )

    # 校验通过，放行请求，返回响应
    return await call_next(request)


# 3. 配置跨域资源共享 (CORS Middleware)
# 必须放在安全中间件之后注册，确保 CORS 在最外层包装所有响应（包括安全中间件直接返回的错误响应）
# FastAPI/Starlette 的中间件栈是从后往前应用的——最后注册的中间件成为最外层
_dev_cors_env = os.environ.get("DBFOX_DEV_CORS_ORIGINS", "")
_dev_cors_origins: list[str] = (
    [o.strip() for o in _dev_cors_env.split(",") if o.strip()]
    if _dev_cors_env
    else ["http://localhost:5173", "http://127.0.0.1:5173"]
)
if not is_frozen:
    logger.info("Dev CORS origins: %s", _dev_cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        *_dev_cors_origins,
        *ALLOWED_TAURI_ORIGINS,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 4. 全局业务异常捕获器 (Global Exception Handler)
# 拦截所有继承自 DBFoxError 的自定义业务错误，将其转换为标准的 HTTP 400 JSON 错误响应，避免程序崩溃或暴露敏感调用栈
@app.exception_handler(DBFoxError)
async def dbfox_error_handler(request: Request, exc: DBFoxError) -> JSONResponse:
    """
    全局自定义异常捕获

    FastAPI 知识点:
      - `@app.exception_handler(异常类型)` 使得每当接口运行期间抛出此类型异常时，FastAPI 就会直接跳过默认报错行为，
        调用这个装饰的函数来生成自定义 HTTP 响应给客户端。
    """
    from engine.policy.error_sanitizer import sanitize_error_message
    logger.warning("DBFoxError at %s %s: [%s] %s", request.method, request.url.path, exc.code, exc.message)
    return JSONResponse(
        status_code=404 if isinstance(exc, NotFoundError) else 400,
        content={"detail": ErrorResponse(code=exc.code, message=sanitize_error_message(exc.message), checks=getattr(exc, "checks", [])).model_dump()},
    )


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底全局异常处理器 — 防止未预期的内部错误暴露敏感调用栈。

    所有未被 @app.exception_handler(DBFoxError) 或 FastAPI 默认 HTTPException
    拦截 of 异常最终都会落到这里，统一返回 500 Internal Server Error。
    API 路由层只需 ``db.rollback(); raise``，不再需要逐个构造 HTTPException(status_code=500)。
    """
    logger.exception("Unhandled exception at %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误，请稍后重试。如果问题持续出现，请检查引擎日志。",
            }
        },
    )


# 5. 极简基础健康路由 (Core Routes)
@app.get("/")
def read_root() -> dict[str, str]:
    """
    根目录状态接口
    """
    return {"name": "DBFox Local Engine", "status": "running"}


@app.get("/api/v1/health")
def api_health() -> dict[str, str]:
    """
    系统健康检查接口
    """
    return {"status": "healthy", "version": "1.0.0", "mode": "standalone"}


# 将 api 目录下的多模块业务路由（路由组）挂载进应用
app.include_router(router)

# 6. 本地运行脚本守护 (Uvicorn CLI Web Server)
if __name__ == "__main__":
    import argparse

    from engine.dev_server import default_reload_enabled, run_engine_server

    parser = argparse.ArgumentParser(description="DBFox local engine")
    parser.add_argument(
        "--reload",
        action=argparse.BooleanOptionalAction,
        default=default_reload_enabled(),
        help="Watch engine/*.py and auto-restart on save (default: on in dev)",
    )
    args = parser.parse_args()
    run_engine_server(reload=args.reload)

