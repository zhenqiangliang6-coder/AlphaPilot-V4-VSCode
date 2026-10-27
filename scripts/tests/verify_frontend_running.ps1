# AlphaPilot Frontend Running Verification Script v3.0
# Purpose: Automatically check all service status to ensure frontend can run properly

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "AlphaPilot Frontend Verification" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$ErrorCount = 0
$WarningCount = 0

# -------------------------------
# 1. Check Node.js version
# -------------------------------
Write-Host "[1/7] Checking Node.js version..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    Write-Host "  [OK] Node.js version: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Node.js not installed or not in PATH" -ForegroundColor Red
    $ErrorCount++
}
Write-Host ""

# -------------------------------
# 2. Check Python version
# -------------------------------
Write-Host "[2/7] Checking Python version..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  [OK] $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Python not installed or not in PATH" -ForegroundColor Red
    $ErrorCount++
}
Write-Host ""

# -------------------------------
# 3. Check React Webview build artifacts
# -------------------------------
Write-Host "[3/7] Checking React Webview build artifacts..." -ForegroundColor Yellow
$webviewDistPath = "vscode-extension\webview-dist"
if (Test-Path $webviewDistPath) {
    $hasIndexHtml = Test-Path "$webviewDistPath\index.html"
    $hasAssets = Test-Path "$webviewDistPath\assets"
    
    if ($hasIndexHtml -and $hasAssets) {
        Write-Host "  [OK] Webview build artifacts exist" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Webview build artifacts incomplete" -ForegroundColor Yellow
        $WarningCount++
    }
} else {
    Write-Host "  [ERROR] Webview build artifacts not found" -ForegroundColor Red
    $ErrorCount++
}
Write-Host ""

# -------------------------------
# 4. Check Extension compilation artifacts
# -------------------------------
Write-Host "[4/7] Checking VSCode Extension compilation artifacts..." -ForegroundColor Yellow
$outPath = "vscode-extension\out"
if (Test-Path $outPath) {
    $hasExtensionJs = Test-Path "$outPath\extension.js"
    if ($hasExtensionJs) {
        Write-Host "  [OK] Extension compilation artifacts exist" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Extension compilation artifacts incomplete" -ForegroundColor Yellow
        $WarningCount++
    }
} else {
    Write-Host "  [ERROR] Extension compilation artifacts not found" -ForegroundColor Red
    $ErrorCount++
}
Write-Host ""

# -------------------------------
# 5. Check Node API port
# -------------------------------
Write-Host "[5/7] Checking Node API (Port 3000)..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:3000/health" -Method GET -TimeoutSec 2 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "  [OK] Node API is running" -ForegroundColor Green
    }
} catch {
    Write-Host "  [ERROR] Node API not started or inaccessible" -ForegroundColor Red
    $ErrorCount++
}
Write-Host ""

# -------------------------------
# 6. Check WebSocket service
# -------------------------------
Write-Host "[6/7] Checking WebSocket service..." -ForegroundColor Yellow
Write-Host "  [INFO] WebSocket will be tested automatically during F5 debugging" -ForegroundColor Gray
Write-Host ""

# -------------------------------
# 7. Check Python Worker virtual environment
# -------------------------------
Write-Host "[7/7] Checking Python Worker virtual environment..." -ForegroundColor Yellow
$venvPath = ".venv_worker\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    Write-Host "  [OK] Worker virtual environment exists" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Worker virtual environment not found" -ForegroundColor Red
    $ErrorCount++
}
Write-Host ""

# -------------------------------
# Summary
# -------------------------------
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Verification Summary" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

if ($ErrorCount -eq 0 -and $WarningCount -eq 0) {
    Write-Host "[SUCCESS] All checks passed! Frontend is ready to run." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Open vscode-extension directory in VSCode" -ForegroundColor White
    Write-Host "  2. Press F5 to start debugging" -ForegroundColor White
    Write-Host "  3. Press Ctrl+Shift+R to open AlphaPilot panel" -ForegroundColor White
    Write-Host "  4. Start chatting!" -ForegroundColor White
} elseif ($ErrorCount -eq 0) {
    Write-Host "[WARN] $WarningCount warnings found, but core functionality is available." -ForegroundColor Yellow
} else {
    Write-Host "[ERROR] $ErrorCount errors found, please fix before running." -ForegroundColor Red
}

Write-Host ""
Write-Host "Detailed documentation: FRONTEND_RUNNING_GUIDE.md" -ForegroundColor Cyan
Write-Host ""