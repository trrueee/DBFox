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

# 检查 Python 环境：优先使用开发环境 .venv，否则回退到系统 Python。
# .build_venv 只属于 Frozen Sidecar 发布构建，开发脚本不使用。
$PythonCmd = $null
if (Test-Path "$ScriptDir\.venv\Scripts\python.exe") {
    $PythonCmd = "$ScriptDir\.venv\Scripts\python.exe"
} else {
    $PythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $PythonCmd) {
    Write-Host "[DBFox] ERROR: Python not found. Install Python 3.12+ and create .venv (see CONTRIBUTING.md)." -ForegroundColor Red
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

function Initialize-SharedDevToken {
    $Token = (& $PythonCmd "$ScriptDir\scripts\dev_environment.py").Trim()
    if (-not $Token) {
        throw "Failed to generate the local development token."
    }
    $env:DBFOX_ENGINE_TOKEN = $Token
}

function Wait-BackendReady {
    param([System.Diagnostics.Process]$Process)

    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $Deadline) {
        if ($Process.HasExited) {
            throw "Backend exited before becoming healthy."
        }
        try {
            $Headers = @{ "X-Local-Token" = $env:DBFOX_ENGINE_TOKEN; "Origin" = "http://127.0.0.1:5173" }
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:18625/api/v1/health" -Headers $Headers -TimeoutSec 1
            if ($Health.status -eq "healthy") {
                return
            }
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    throw "Backend health check timed out."
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
        Initialize-SharedDevToken
        $pyArgs = @("-m", "engine.main")
        if ($NoReload) { $pyArgs += "--no-reload" }

        $BackendProcess = Start-Process -FilePath $PythonCmd -ArgumentList $pyArgs -WorkingDirectory $ScriptDir -PassThru
        Write-Host "[DBFox] Waiting for backend to be ready..."
        try {
            Wait-BackendReady -Process $BackendProcess
        } catch {
            if (-not $BackendProcess.HasExited) {
                Stop-Process -Id $BackendProcess.Id
            }
            throw
        }
        Write-Host "[DBFox] Backend is healthy." -ForegroundColor Green

        Start-Frontend
    }
}
