#!/usr/bin/env pwsh
Write-Host "Starting P1 targeted run orchestration..."

# 1. Bring up docker compose
docker compose -f .agent_eval/docker-compose.spider.yml up -d

Write-Host "Waiting for MySQL (127.0.0.1:3307) to be ready..."
$i = 0
while ($i -lt 60) {
    try {
        $sock = New-Object System.Net.Sockets.TcpClient
        $sock.Connect("127.0.0.1", 3307)
        $sock.Close()
        break
    } catch {
        Start-Sleep -Seconds 1
        $i++
    }
}

Write-Host "Running spider import and schema sync (if provided)..."
if (Test-Path .agent_eval/spider_import_mysql.py) {
    python .agent_eval/spider_import_mysql.py
}

Write-Host "Starting backend..."
python .agent_eval/start_eval_backend.py

Write-Host "Checking environment..."
python .agent_eval/check_eval_env.py

Write-Host "Running targeted agent cases..."
python .agent_eval/quick_agent_run.py --cases .agent_eval/cases.smoke_subset.json --out .agent_eval/outputs/agent_only_results.jsonl --execute false

Write-Host "Done. Results at .agent_eval/outputs/agent_only_results.jsonl"
