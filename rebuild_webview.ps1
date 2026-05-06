# rebuild_webview.ps1
# Rebuild and reload AlphaPilot Webview

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AlphaPilot Webview Rebuild Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = "d:\Copilot_Alphapilot\Copilot_Alphapilot"
$webviewDir = Join-Path $projectRoot "vscode-extension\webview"

Set-Location $webviewDir

# Step 1: Check if node_modules exists
Write-Host "[1/3] Checking dependencies..." -ForegroundColor Yellow

if (-not (Test-Path "node_modules")) {
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
Write-Host "`n[2/3] Building webview..." -ForegroundColor Yellow

npm run build

if ($?) {
    Write-Host "OK: Webview built successfully" -ForegroundColor Green
    
    # Show build output size
    $distDir = Join-Path $webviewDir "dist"
    if (Test-Path $distDir) {
        $files = Get-ChildItem $distDir -Recurse -File | Measure-Object -Property Length -Sum
        $sizeMB = [math]::Round($files.Sum / 1MB, 2)
        Write-Host "Build size: $sizeMB MB" -ForegroundColor Gray
    }
} else {
    Write-Host "FAIL: Build failed" -ForegroundColor Red
    exit 1
}

# Step 3: Instructions for reloading VSCode
Write-Host "`n[3/3] Next steps..." -ForegroundColor Yellow
Write-Host ""
Write-Host "To apply the changes, please:" -ForegroundColor White
Write-Host ""
Write-Host "  1. In VSCode, press Ctrl+Shift+P" -ForegroundColor Cyan
Write-Host "  2. Type 'Reload Window' and press Enter" -ForegroundColor Cyan
Write-Host "  3. Or use shortcut: Ctrl+R (if configured)" -ForegroundColor Cyan
Write-Host ""
Write-Host "After reloading:" -ForegroundColor Yellow
Write-Host "  - Open AlphaPilot Chat (Ctrl+Shift+A)" -ForegroundColor White
Write-Host "  - Submit a test task to verify the fix" -ForegroundColor White
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build completed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""