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
from typing import Any

from engine import __version__
from engine.runtime_env import load_runtime_env

# Load runtime configuration before provider and database clients initialize.
load_runtime_env()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from engine.json_codec import dumps
from fastapi.responses import JSONResponse

from engine.api import router
from engine.db import SessionLocal, initialize_metadata_database
from engine.agent.coordinator import SessionCoordinator
from engine.agent.loop import RunLoop
from engine.app.request_limits import AgentInputRequestBodyLimitMiddleware
from engine.diagnostics.logs import configure_diagnostic_logging
from engine.errors import BackupSourceMismatchError, DBFoxError, NotFoundError
from engine.schemas import ErrorResponse
from engine.engine_runtime.credentials import RuntimeCredentialPolicy
from engine.runtime_paths import private_runtime_file
from engine.security.credential_vault import CredentialVaultUnavailableError

# 创建当前模块的日志记录器
logger = logging.getLogger("dbfox.main")


def _emit_startup_stage(stage: str) -> None:
    """Publish optional startup progress without making service health depend on it."""
    try:
        print(
            f"DBFOX_ENGINE_STAGE {dumps({'stage': stage})}",
            flush=True,
        )
    except OSError:
        logger.warning("Unable to publish engine startup stage=%s", stage)


DIAGNOSTIC_LOG_FILE = configure_diagnostic_logging()
SAFE_DBFOX_ERROR_MESSAGE = "Request could not be completed."
_SAFE_DBFOX_ERROR_CODES: tuple[tuple[type[DBFoxError], str], ...] = (
    (CredentialVaultUnavailableError, "CREDENTIAL_VAULT_UNAVAILABLE"),
    (BackupSourceMismatchError, "BACKUP_SOURCE_MISMATCH"),
)


def _safe_dbfox_error_code(exc: DBFoxError) -> str:
    """Map only static, type-owned error codes; never trust instance values."""
    for error_type, code in _SAFE_DBFOX_ERROR_CODES:
        if isinstance(exc, error_type):
            return code
    return "DBFOX_ERROR"

TOKEN_FILE = private_runtime_file("auth", ".local_token")
is_frozen = getattr(sys, "frozen", False)


def get_or_create_local_token() -> str:
    """Resolve the process-local authentication token."""
    return RuntimeCredentialPolicy(token_file=TOKEN_FILE, is_frozen=is_frozen).resolve_token()


LOCAL_SECURE_TOKEN = get_or_create_local_token()
ALLOWED_TAURI_ORIGINS = {
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
}

@asynccontextmanager
async def lifespan(application: FastAPI) -> Any:
    """Initialize durable runtime services and stop them in dependency order."""
    agent_coordinator: SessionCoordinator | None = None
    startup_stage = "migrating"
    try:
        _emit_startup_stage(startup_stage)
        initialize_metadata_database()

        from engine.security.credential_lease import reconcile_credential_leases
        reconcile_credential_leases(SessionLocal)

        # Security audit is local product data with an explicit bounded lifecycle.
        # Prune before the coordinator starts so startup recovery cannot race it.
        startup_stage = "maintaining"
        _emit_startup_stage(startup_stage)
        from engine.agent.repositories.write_transaction import begin_agent_write
        from engine.security.audit import SecurityAuditService
        with SessionLocal() as audit_session:
            begin_agent_write(audit_session)
            SecurityAuditService(audit_session).enforce_retention()
            audit_session.commit()

        # Agent execution is independent from HTTP/SSE connections. Session leases
        # and the event log are database-owned; this coordinator only schedules work.
        startup_stage = "recovering"
        _emit_startup_stage(startup_stage)
        agent_coordinator = SessionCoordinator(
            session_factory=SessionLocal,
            run_loop=RunLoop(session_factory=SessionLocal),
        )
        agent_coordinator.start()
        application.state.agent_coordinator = agent_coordinator
        _emit_startup_stage("ready")
    except Exception:
        logger.exception("Engine startup failed during stage=%s", startup_stage)
        if agent_coordinator is not None:
            agent_coordinator.stop()
        application.state.agent_coordinator = None
        raise

    port = os.environ.get("DBFOX_ENGINE_PORT", "18625")
    logger.info("DBFox Local Engine is ready on 127.0.0.1:%s", port)

    try:
        yield
    finally:
        agent_coordinator.stop()
        application.state.agent_coordinator = None
        from engine.connectivity.lifecycle import close_all_managed_datasource_resources
        from engine.llm.http_clients import close_llm_http_clients
        close_all_managed_datasource_resources()
        await close_llm_http_clients()


app = FastAPI(
    title="DBFox Local Engine",
    description="专为 DBFox 桌面外壳设计的安全数据库客户端核心引擎",
    version=__version__,
    lifespan=lifespan,
    docs_url=None if is_frozen else "/docs",
    redoc_url=None if is_frozen else "/redoc",
    openapi_url=None if is_frozen else "/openapi.json",
)

app.add_middleware(AgentInputRequestBodyLimitMiddleware)

@app.middleware("http")
async def verify_local_access_token(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Enforce local token and trusted-origin policy."""
    if request.method == "OPTIONS":
        return await call_next(request)

    # Native startup probes use raw local HTTP and do not send browser
    # Origin/Referer headers, so health must be public before frozen-origin gates.
    if request.url.path == "/api/v1/health":
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
    if request.url.path in ["/", "/docs", "/openapi.json", "/redoc"]:
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


@app.exception_handler(DBFoxError)
async def dbfox_error_handler(request: Request, exc: DBFoxError) -> JSONResponse:
    """Map trusted domain error classes to fixed public responses."""
    # DBFoxError instances may wrap arbitrary provider or driver exceptions,
    # so neither their message nor caller-supplied code is trusted here.
    code = _safe_dbfox_error_code(exc)
    logger.warning(
        "DBFoxError (%s) at %s %s code=%s",
        type(exc).__name__,
        request.method,
        request.url.path,
        code,
    )
    return JSONResponse(
        status_code=(
            404
            if isinstance(exc, NotFoundError)
            else 409
            if isinstance(exc, BackupSourceMismatchError)
            else 400
        ),
        content={
            "detail": ErrorResponse(
                code=code,
                message=SAFE_DBFOX_ERROR_MESSAGE,
                checks=[],
            ).model_dump()
        },
    )


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底全局异常处理器 — 防止未预期的内部错误暴露敏感调用栈。

    所有未被 @app.exception_handler(DBFoxError) 或 FastAPI 默认 HTTPException
    拦截 of 异常最终都会落到这里，统一返回 500 Internal Server Error。
    API 路由层只需 ``db.rollback(); raise``，不再需要逐个构造 HTTPException(status_code=500)。
    """
    logger.error(
        "Unhandled exception (%s) at %s %s",
        type(exc).__name__,
        request.method,
        request.url.path,
    )
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
    return {"status": "healthy", "version": __version__, "mode": "standalone"}


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

