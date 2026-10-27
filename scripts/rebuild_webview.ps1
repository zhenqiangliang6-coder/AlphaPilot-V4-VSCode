# rebuild_webview.ps1
# Rebuild and reload AlphaPilot Webview

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AlphaPilot Webview Rebuild Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = $PSScriptRoot
$extensionDir = Join-Path $projectRoot "vscode-extension"
$webviewDir = Join-Path $extensionDir "webview"
$distDir = Join-Path $extensionDir "webview-dist"

Push-Location $webviewDir

# Step 1: Check if node_modules exists
Write-Host "[1/4] Checking dependencies..." -ForegroundColor Yellow

if (-not (Test-Path (Join-Path $webviewDir "node_modules"))) {
    Write-Host "Installing dependencies..." -ForegroundColor White
    npm install
    
    if ($?) {
        Write-Host "OK: Dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "FAIL: Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "OK: Dependencies already installed" -ForegroundColor Green
}

# Step 2: Build webview
Write-Host "`n[2/4] Building webview..." -ForegroundColor Yellow

npm run build

if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: Webview built successfully" -ForegroundColor Green
} else {
    Write-Host "FAIL: Build failed" -ForegroundColor Red
    Pop-Location
    exit 1
}

$bundlePath = Join-Path $distDir "assets\index.js"
if (-not (Test-Path $bundlePath)) {
    Write-Host "FAIL: Expected webview bundle not found: $bundlePath" -ForegroundColor Red
    Pop-Location
    exit 1
}

$bundle = Get-Content -Raw $bundlePath
if (-not ($bundle.Contains("maas_generate") -and $bundle.Contains("modelscope_generate"))) {
    Write-Host "FAIL: Built webview bundle does not contain MaaS and ModelScope options" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "OK: MaaS and ModelScope options found in webview bundle" -ForegroundColor Green

Pop-Location

# Compile extension host code (Quick Pick and legacy panel).
Write-Host "`n[3/4] Compiling VS Code extension..." -ForegroundColor Yellow
Push-Location $extensionDir
npm run compile
$compileExitCode = $LASTEXITCODE
Pop-Location
if ($compileExitCode -ne 0) {
    Write-Host "FAIL: Extension compilation failed" -ForegroundColor Red
    exit $compileExitCode
}
Write-Host "OK: VS Code extension compiled" -ForegroundColor Green

# Step 4: Instructions for reloading VSCode
Write-Host "`n[4/4] Next steps..." -ForegroundColor Yellow
Write-Host ""
Write-Host "To apply the changes, please:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Stop the current Extension Development Host (Shift+F5)" -ForegroundColor Cyan
Write-Host "  2. Start it again from the AlphaPilot extension project (F5)" -ForegroundColor Cyan
Write-Host "  3. Close the old AlphaPilot panel and open it again" -ForegroundColor Cyan
Write-Host ""
Write-Host "After reloading:" -ForegroundColor Yellow
Write-Host "  - Open AlphaPilot Chat (Ctrl+Shift+A)" -ForegroundColor White
Write-Host "  - Submit a test task to verify the fix" -ForegroundColor White
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build completed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""