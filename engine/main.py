# -*- coding: utf-8 -*-
"""
DBFox 本地引擎主入口模块 (Main Entrypoint Module)
---------------------------------------------
这是 DBFox 后端服务的核心入口文件。
它基于 FastAPI 异步 Web 框架构建，提供了：
- 安全策略（CORS 跨域控制、本地 Token 令牌鉴权中间件）
- 异步生命周期管理（启动时验证本地元数据库，退出时停止 Agent Runtime）
- 异常处理器（拦截全局业务异常）
- 路由挂载
"""

import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

from engine import __version__
from engine.runtime_env import load_runtime_env

# Load runtime configuration before provider and database clients initialize.
load_runtime_env()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from engine.json_codec import dumps
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from engine.api import router
from engine.db import SessionLocal, initialize_metadata_database
from engine.agent.coordinator import SessionCoordinator
from engine.runtime_composition import (
    build_product_run_loop,
    default_credential_reference_probes,
    get_active_runtime_snapshot,
)
from engine.app.request_limits import AgentInputRequestBodyLimitMiddleware
from engine.app.safe_errors import (
    FixedErrorCode,
    diagnostic_fingerprint,
    fixed_error_detail,
)
from engine.diagnostics.logs import configure_diagnostic_logging
from engine.dlc.errors import DlcError
from engine.errors import DBFoxError, NotFoundError
from engine.engine_runtime.credentials import RuntimeCredentialPolicy
from engine.problem_details import REQUEST_ID_HEADER, new_request_id, problem_response
from engine.schemas import ProblemDetails
from engine.runtime_paths import private_runtime_file

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


def _startup_failure_code(exc: Exception) -> str:
    if isinstance(exc, DBFoxError):
        return exc.code
    if isinstance(exc, DlcError):
        return f"DBFOX_DLC_{exc.code.value.upper()}"
    message = str(exc)
    if message.startswith("DBFOX_ALEMBIC_SQLITE_FOREIGN_KEY_VIOLATIONS"):
        return "DBFOX_METADATA_FOREIGN_KEY_VIOLATION"
    if message.startswith("DBFOX_ALEMBIC_"):
        return "DBFOX_METADATA_MIGRATION_FAILED"
    return "ENGINE_STARTUP_FAILED"


def _emit_startup_fatal(stage: str, exc: Exception) -> None:
    """Publish only cataloged startup diagnostics; full details stay private."""
    payload = {
        "stage": stage,
        "code": _startup_failure_code(exc),
        "fingerprint": diagnostic_fingerprint(exc),
    }
    try:
        print(f"DBFOX_ENGINE_FATAL {dumps(payload)}", flush=True)
    except OSError:
        logger.warning("Unable to publish engine startup fatal stage=%s", stage)


DIAGNOSTIC_LOG_FILE = configure_diagnostic_logging()

TOKEN_FILE = private_runtime_file("auth", ".local_token")
is_frozen = getattr(sys, "frozen", False)


def get_or_create_local_token() -> str:
    """Resolve the process-local authentication token."""
    return RuntimeCredentialPolicy(token_file=TOKEN_FILE, is_frozen=is_frozen).resolve_token()


LOCAL_SECURE_TOKEN = get_or_create_local_token()
ALLOWED_DESKTOP_ORIGINS = {
    "dbfox-app://localhost",
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

        startup_stage = "bootstrapping"
        _emit_startup_stage(startup_stage)
        runtime_snapshot = get_active_runtime_snapshot()
        reconcile_credential_leases(
            SessionLocal,
            reference_probes=default_credential_reference_probes(runtime_snapshot),
        )

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
            run_loop=build_product_run_loop(session_factory=SessionLocal),
        )
        agent_coordinator.start()
        application.state.agent_coordinator = agent_coordinator

        # Artifact payload contracts freeze after every built-in/extension
        # module has imported and registered its concrete validators.
        from engine.agent.artifact import freeze_artifact_payload_contracts
        freeze_artifact_payload_contracts()

        _emit_startup_stage("ready")

    except Exception as exc:
        logger.exception("Engine startup failed during stage=%s", startup_stage)
        _emit_startup_fatal(startup_stage, exc)
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
        from engine.llm.http_clients import close_llm_http_clients
        await close_llm_http_clients()


_PROBLEM_RESPONSES = {
    status: {
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/ProblemDetails"},
            }
        },
        "description": f"RFC 9457 error response ({status})",
    }
    for status in (400, 401, 403, 404, 409, 422, 500, 503)
}


app = FastAPI(
    title="DBFox Local Engine",
    description="专为 DBFox 桌面外壳设计的安全数据库客户端核心引擎",
    version=__version__,
    lifespan=lifespan,
    docs_url=None if is_frozen else "/docs",
    redoc_url=None if is_frozen else "/redoc",
    openapi_url=None if is_frozen else "/openapi.json",
    responses=_PROBLEM_RESPONSES,
)

app.add_middleware(AgentInputRequestBodyLimitMiddleware)


def _is_allowed_local_referer(value: str) -> bool:
    """Validate a frozen WebView Referer structurally, not by string prefix."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    return (
        parsed.scheme == "dbfox-app"
        and parsed.hostname == "localhost"
        and parsed.port is None
    )

@app.middleware("http")
async def verify_local_access_token(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Enforce local token and trusted-origin policy."""
    if request.method == "OPTIONS":
        return await call_next(request)

    # 🔒 在冻结桌面容器内强制检查请求的 Origin 来源头部。
    if is_frozen:
        origin = request.headers.get("origin")
        if not origin:
            # 某些 WebView 请求可能不发送 Origin 头（如 redirect、no-cors），
            # 此时检查 Referer 是否为已知合法来源，避免误杀合理请求。
            referer = request.headers.get("referer", "")
            if not _is_allowed_local_referer(referer):
                logger.warning(
                    "拦截到缺失 Origin 且 Referer 非本地的请求，Referer: %s", referer
                )
                return problem_response(
                    request,
                    status=403,
                    code="FORBIDDEN_ORIGIN",
                    detail="The request origin is not allowed.",
                )
        elif origin not in ALLOWED_DESKTOP_ORIGINS:
            logger.warning("拦截到非法的跨域恶意连接请求，尝试来源: %s", origin)
            return problem_response(
                request,
                status=403,
                code="FORBIDDEN_ORIGIN",
                detail="The request origin is not allowed.",
            )

    # Development API documentation is public only in source mode. Runtime
    # status endpoints, including `/`, always use the same token boundary.
    if request.url.path in ["/docs", "/openapi.json", "/redoc"]:
        if is_frozen:
            return problem_response(
                request,
                status=404,
                code="NOT_FOUND",
                detail="The requested resource was not found.",
            )
        return await call_next(request)

    # 🔒 核心 Token 令牌安全校验
    token_header = request.headers.get("X-Local-Token", "")
    if not secrets.compare_digest(token_header, LOCAL_SECURE_TOKEN):
        return problem_response(
            request,
            status=401,
            code="UNAUTHORIZED_ENGINE_ACCESS",
            detail="A valid local engine token is required.",
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
        *ALLOWED_DESKTOP_ORIGINS,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Give every HTTP response a local, non-identifying correlation ID."""
    request_id = new_request_id()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def _http_exception_fields(exc: StarletteHTTPException) -> tuple[str, str, list[dict[str, Any]]]:
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or "HTTP_ERROR")
        message = str(detail.get("message") or detail.get("detail") or "Request failed.")
        raw_checks = detail.get("checks")
        checks = [item for item in raw_checks if isinstance(item, dict)] if isinstance(raw_checks, list) else []
        return code, message, checks
    if isinstance(detail, str) and detail.strip():
        return "HTTP_ERROR", detail.strip(), []
    return "HTTP_ERROR", "Request failed.", []


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, detail, checks = _http_exception_fields(exc)
    return problem_response(
        request,
        status=exc.status_code,
        code=code,
        detail=detail,
        checks=checks,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "location": [str(part) for part in error.get("loc", ())],
            "message": str(error.get("msg") or "Invalid value."),
            "error_type": str(error.get("type") or "validation_error"),
        }
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status=422,
        code="VALIDATION_ERROR",
        detail="Request validation failed.",
        errors=errors,
    )


@app.exception_handler(DBFoxError)
async def dbfox_error_handler(request: Request, exc: DBFoxError) -> JSONResponse:
    """Map domain errors through the single fixed public-error catalog."""
    # DBFoxError instances may wrap arbitrary provider or driver exceptions,
    # so neither their message nor an unregistered caller-supplied code is
    # trusted here.  ``fixed_error_detail`` fails closed to INTERNAL_ERROR.
    detail = fixed_error_detail(exc.code)
    code = detail["code"]
    logger.warning(
        "DBFoxError (%s) at %s %s code=%s",
        type(exc).__name__,
        request.method,
        request.url.path,
        code,
    )
    status = 500 if code == FixedErrorCode.INTERNAL_ERROR.value else 400
    if isinstance(exc, NotFoundError) and status != 500:
        status = 404
    return problem_response(
        request,
        status=status,
        code=code,
        detail=detail["message"],
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
    return problem_response(
        request,
        status=500,
        code="INTERNAL_ERROR",
        detail="The server could not complete the request. Check the engine logs if the problem persists.",
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


_fastapi_openapi = app.openapi


def dbfox_openapi() -> dict[str, Any]:
    """Publish the shared Problem Details schema without copying it into every operation."""
    schema = _fastapi_openapi()
    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    schemas["ProblemDetails"] = ProblemDetails.model_json_schema(
        ref_template="#/components/schemas/{model}",
    )
    return schema


app.openapi = dbfox_openapi  # type: ignore[method-assign]

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
    parser.add_argument(
        "--runtime-manifest",
        action="store_true",
        help="Print final Python/SQLite runtime facts and exit",
    )
    parser.add_argument(
        "--release-contracts",
        action="store_true",
        help="Execute frozen provider-neutral release contracts and exit",
    )
    args = parser.parse_args()
    if args.runtime_manifest:
        from engine.runtime_manifest import collect_runtime_manifest

        print(f"DBFOX_RUNTIME_MANIFEST {dumps(collect_runtime_manifest())}", flush=True)
        raise SystemExit(0)
    if args.release_contracts:
        from engine.runtime_manifest import collect_release_contracts

        print(
            f"DBFOX_RELEASE_CONTRACTS {dumps(collect_release_contracts())}",
            flush=True,
        )
        raise SystemExit(0)
    run_engine_server(reload=args.reload)



