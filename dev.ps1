<#
.SYNOPSIS
    DBFox 开发环境一键启动脚本
.DESCRIPTION
    启动 DBFox 后端引擎 (FastAPI) 和/或前端 (Vite) 开发服务器。
.PARAMETER Target
    backend  - 仅启动后端 (http://127.0.0.1:18625)
    frontend - 仅启动前端 (http://localhost:5173)
    both     - 同时启动后端和前端 (默认)
.PARAMETER NoReload
    禁用后端的自动重载 (默认启用)
.EXAMPLE
    ./dev.ps1              # 启动后端和前端
    ./dev.ps1 backend      # 仅启动后端
    ./dev.ps1 frontend     # 仅启动前端
    ./dev.ps1 -NoReload    # 启动全部，后端不自动重载
#>

param(
    [ValidateSet("backend", "frontend", "both")]
    [string]$Target = "both",
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# 检查 Python 环境
$PythonCmd = $null
if (Test-Path "$ScriptDir\.build_venv\Scripts\python.exe") {
    $PythonCmd = "$ScriptDir\.build_venv\Scripts\python.exe"
} else {
    $PythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $PythonCmd) {
    Write-Host "[DBFox] ERROR: Python not found. Install Python 3.12+ and create .build_venv." -ForegroundColor Red
    exit 1
}

Write-Host "[DBFox] Python: $PythonCmd" -ForegroundColor Gray

function Start-Backend {
    Write-Host "[DBFox] Starting backend engine on http://127.0.0.1:18625 ..." -ForegroundColor Cyan
    $pyArgs = @("-m", "engine.main")
    if ($NoReload) { $pyArgs += "--no-reload" }
    & $PythonCmd @pyArgs
}

function Start-Frontend {
    Write-Host "[DBFox] Starting frontend (Vite) on http://localhost:5173 ..." -ForegroundColor Cyan
    Set-Location "$ScriptDir\desktop"
    npm run dev
}

switch ($Target) {
    "backend" {
        Start-Backend
    }
    "frontend" {
        Start-Frontend
    }
    "both" {
        Write-Host "[DBFox] Starting backend in a new window..." -ForegroundColor Cyan
        $pyArgs = @("-m", "engine.main")
        if ($NoReload) { $pyArgs += "--no-reload" }

        Start-Process -FilePath $PythonCmd -ArgumentList $pyArgs -WorkingDirectory $ScriptDir

        # Wait for backend to write .env.local before starting frontend
        Write-Host "[DBFox] Waiting for backend to be ready..."
        $EnvFile = "$ScriptDir\desktop\.env.local"
        $Timeout = 30
        $Elapsed = 0
        while (-not (Test-Path $EnvFile) -and $Elapsed -lt $Timeout) {
            Start-Sleep -Seconds 1
            $Elapsed++
        }
        if (Test-Path $EnvFile) {
            Start-Sleep -Seconds 1  # give it a moment to finish writing
            Write-Host "[DBFox] Backend env file ready." -ForegroundColor Green
        }

        Start-Frontend
    }
}
