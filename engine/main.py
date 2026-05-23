import logging
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from engine.api import router
from engine.db import init_db
from engine.errors import DataBoxError
from engine.runtime_paths import private_runtime_file, write_private_text

logger = logging.getLogger("databox.main")

ENGINE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ENGINE_DIR.parent

# 1. Local Engine Security: Generate Local Secure Access Token
LEGACY_TOKEN_FILE = ENGINE_DIR / ".local_token"
TOKEN_FILE = private_runtime_file("auth", ".local_token")


def get_or_create_local_token() -> str:
    # Under packaged frozen sidecars, check if build-time static token preset exists
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        try:
            from engine import token_preset
            if token_preset.STATIC_TOKEN:
                return token_preset.STATIC_TOKEN
        except ImportError:
            pass

    if not TOKEN_FILE.exists() and LEGACY_TOKEN_FILE.exists():
        write_private_text(TOKEN_FILE, LEGACY_TOKEN_FILE.read_text("utf-8").strip())

    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text("utf-8").strip()
    token = secrets.token_hex(32)
    write_private_text(TOKEN_FILE, token)
    return token


LOCAL_SECURE_TOKEN = get_or_create_local_token()

# Write the token to the React frontend folder as .env.local (development only)
is_frozen = getattr(sys, "frozen", False)
if not is_frozen:
    FRONTEND_ENV_FILE = PROJECT_DIR / "desktop" / ".env.local"
    try:
        expected_content = f"VITE_LOCAL_ENGINE_PORT=18625\nVITE_LOCAL_ENGINE_TOKEN={LOCAL_SECURE_TOKEN}\n"
        existing_content = ""
        if FRONTEND_ENV_FILE.exists():
            existing_content = FRONTEND_ENV_FILE.read_text("utf-8")

        if existing_content != expected_content:
            FRONTEND_ENV_FILE.write_text(expected_content, "utf-8")
    except OSError:
        logger.warning(
            "Unable to write frontend .env.local file; the frontend may need manual token configuration."
        )


@asynccontextmanager
async def lifespan(application: FastAPI) -> Any:
    init_db()
    print("===========================================================")
    print("DataBox Local Engine initialized successfully.")
    print("Listening address: http://127.0.0.1:18625")
    print(f"Access token file: {TOKEN_FILE}")
    print("===========================================================")
    yield
    from engine.datasource import close_all_tunnels
    close_all_tunnels()



app = FastAPI(
    title="DataBox Local Engine",
    description="Secured Database Client Core for DataBox Desktop Shell",
    version="1.0.0",
    lifespan=lifespan,
)

# 2. Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 3. Security Guard Middleware
@app.middleware("http")
async def verify_local_access_token(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.method == "OPTIONS":
        return await call_next(request)

    if request.url.path in ["/", "/docs", "/openapi.json", "/api/v1/health"]:
        return await call_next(request)

    token_header = request.headers.get("X-Local-Token")
    if not token_header or token_header != LOCAL_SECURE_TOKEN:
        return JSONResponse(
            status_code=401,
            content={
                "code": "UNAUTHORIZED_ENGINE_ACCESS",
                "message": "Access blocked: Invalid or missing local authentication token.",
            },
        )

    return await call_next(request)


# 4. Exception Handler for Custom DataBox Exceptions
@app.exception_handler(DataBoxError)
async def databox_error_handler(request: Request, exc: DataBoxError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"code": exc.code, "message": exc.message},
    )


# 5. Core Routes
@app.get("/")
def read_root() -> dict[str, str]:
    return {"name": "DataBox Local Engine", "status": "running"}


@app.get("/api/v1/health")
def api_health() -> dict[str, str]:
    return {"status": "healthy", "version": "1.0.0", "mode": "standalone"}


app.include_router(router)

if __name__ == "__main__":
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        uvicorn.run(app, host="127.0.0.1", port=18625)
    else:
        uvicorn.run("engine.main:app", host="127.0.0.1", port=18625, reload=True)
