# start_all_v4.ps1
# 一键启动：Node API (V4) + V4 Worker（前端请手动启动）

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

# 默认环境变量（可在外部覆盖）
if (-not $env:WORKER_ID) { $env:WORKER_ID = "qwen-worker-1" }
if (-not $env:NODE_API_URL) { $env:NODE_API_URL = "http://localhost:3000" }
if (-not $env:WORKSPACE_ROOT) { $env:WORKSPACE_ROOT = $scriptDir }

Write-Host "[start_all_v4] Workspace: $scriptDir"
Write-Host "[start_all_v4] WORKER_ID=$env:WORKER_ID  NODE_API_URL=$env:NODE_API_URL"

## Only start Qwen V4 Worker (no Node / frontend)
$venvPython = Join-Path $scriptDir ".venv_worker\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host "[start_all_v4] Starting V4 Worker using: $venvPython"
    Start-Process -FilePath $venvPython -ArgumentList "-u","-m","python_worker.worker_v4.worker_v4" -WorkingDirectory $scriptDir
} else {
    Write-Host "[start_all_v4] .venv_worker python not found, starting with system python"
    Start-Process -FilePath "python" -ArgumentList "-u","-m","python_worker.worker_v4.worker_v4" -WorkingDirectory $scriptDir
}

Write-Host "[start_all_v4] V4 Worker start requested. Check Worker logs or run Get-WorkerStatus to verify."
