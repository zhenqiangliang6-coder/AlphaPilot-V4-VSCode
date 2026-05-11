# test_qwen_worker_v3.ps1
# Qwen Worker v3.0 Import Error Fix - Quick Verification Script

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Qwen Worker v3.0 Import Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$venvPython = ".\.venv_worker\Scripts\python.exe"

# Check virtual environment
if (-Not (Test-Path $venvPython)) {
    Write-Host "ERROR: Python virtual environment not found" -ForegroundColor Red
    Write-Host "Please run: python -m venv .venv_worker" -ForegroundColor Yellow
    exit 1
}

Write-Host "Running import tests..." -ForegroundColor Green
& $venvPython test_qwen_worker_import.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Import tests FAILED!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "All verifications PASSED!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Worker is ready to start. Use command:" -ForegroundColor White
Write-Host '$env:WORKER_ID="qwen-worker-1"' -ForegroundColor Gray
Write-Host '.\.venv_worker\Scripts\python.exe -m python_worker.agents.qwen.qwen_worker_v2' -ForegroundColor Gray
Write-Host ""
