# test_fix_step_signature.ps1
# Qwen Worker v3.0 fix_step 函数签名修复 - 快速验证脚本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Qwen Worker v3.0 fix_step Signature Fix Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$venvPython = ".\.venv_worker\Scripts\python.exe"

# Check virtual environment
if (-Not (Test-Path $venvPython)) {
    Write-Host "ERROR: Python virtual environment not found" -ForegroundColor Red
    Write-Host "Please run: python -m venv .venv_worker" -ForegroundColor Yellow
    exit 1
}

Write-Host "Step 1: Running import tests..." -ForegroundColor Green
& $venvPython test_qwen_worker_import.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Import tests FAILED!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 2: Checking fix_step.py function signature..." -ForegroundColor Green
$content = Get-Content "python_worker/agents/qwen/step_executor/fix_step.py" -Raw
if ($content -match "def run_fix_step\(step, context, events, task_id=None\)") {
    Write-Host "✅ fix_step.py signature is CORRECT" -ForegroundColor Green
} else {
    Write-Host "❌ fix_step.py signature is INCORRECT" -ForegroundColor Red
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
Write-Host "To test the full 8-step execution chain, send a complex task from VSCode." -ForegroundColor Yellow
