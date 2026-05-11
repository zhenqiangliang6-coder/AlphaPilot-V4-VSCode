# -*- coding: utf-8 -*-
# restart_doubao_worker.ps1
# ---------------------------------------------------------
# 重启 Doubao Worker v2（清除 Python 缓存）
# ---------------------------------------------------------

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "重启 Doubao Worker v2" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 1. 停止所有 Python 进程
Write-Host "[1/3] 停止旧的 Worker 进程..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*doubao*" -or $_.CommandLine -like "*doubao_worker*" } | Stop-Process -Force
Start-Sleep -Seconds 2
Write-Host "✅ 旧进程已停止" -ForegroundColor Green
Write-Host ""

# 2. 清除 Python 缓存
Write-Host "[2/3] 清除 Python 缓存..." -ForegroundColor Yellow
Get-ChildItem -Path "d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker" -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path "d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker" -Recurse -Filter "*.pyc" | Remove-Item -Force
Write-Host "✅ 缓存已清除" -ForegroundColor Green
Write-Host ""

# 3. 启动新的 Worker
Write-Host "[3/3] 启动新的 Doubao Worker v2..." -ForegroundColor Yellow
Write-Host "Worker ID: doubao-worker-1" -ForegroundColor Cyan
Write-Host "Model: doubao-seed-2-0-lite-260215" -ForegroundColor Cyan
Write-Host ""

cd d:\Copilot_Alphapilot\Copilot_Alphapilot
$env:WORKER_ID="doubao-worker-1"
python -m python_worker.agents.Volcengine.doubao_worker_v2
