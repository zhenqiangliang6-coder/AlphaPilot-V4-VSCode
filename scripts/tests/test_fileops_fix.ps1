# test_fileops_fix.ps1
# AlphaPilot FileOps META/DEPENDS Parsing Enhancement - Quick Verification Script

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AlphaPilot FileOps Parsing Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$venvPython = ".\.venv_worker\Scripts\python.exe"

# Check virtual environment
if (-Not (Test-Path $venvPython)) {
    Write-Host "ERROR: Python virtual environment not found" -ForegroundColor Red
    Write-Host "Please run: python -m venv .venv_worker" -ForegroundColor Yellow
    exit 1
}

Write-Host "Running unit tests..." -ForegroundColor Green
& $venvPython test_fileops_json_parsing.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Unit tests FAILED!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Running real scenario tests..." -ForegroundColor Green
& $venvPython test_refine_scenario.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Real scenario tests FAILED!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "All verifications PASSED!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Fix is active. Next task will use enhanced parser." -ForegroundColor White
Write-Host ""
Write-Host "Tip: Test in VSCode with task:" -ForegroundColor Yellow
Write-Host '   "Create a simple calculator module"' -ForegroundColor Gray
Write-Host ""
