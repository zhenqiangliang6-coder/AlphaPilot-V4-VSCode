# setup_worker_env.ps1
# AlphaPilot Worker Environment Setup Script
# This script ensures the virtual environment is properly configured

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AlphaPilot Worker Environment Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = "d:\Copilot_Alphapilot\Copilot_Alphapilot"
$venvPath = Join-Path $projectRoot ".venv_worker"
$venvActivate = Join-Path $venvPath "Scripts\Activate.ps1"
$requirementsFile = Join-Path $projectRoot "python_worker\requirements.txt"

Set-Location $projectRoot

# Step 1: Check if virtual environment exists
Write-Host "[1/4] Checking virtual environment..." -ForegroundColor Yellow

if (Test-Path $venvActivate) {
    Write-Host "OK: Virtual environment found at: $venvPath" -ForegroundColor Green
} else {
    Write-Host "Virtual environment not found. Creating..." -ForegroundColor Yellow
    python -m venv $venvPath
    
    if (Test-Path $venvActivate) {
        Write-Host "OK: Virtual environment created successfully" -ForegroundColor Green
    } else {
        Write-Host "FAIL: Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
}

# Step 2: Activate virtual environment
Write-Host "`n[2/4] Activating virtual environment..." -ForegroundColor Yellow

& $venvActivate

if ($?) {
    Write-Host "OK: Virtual environment activated" -ForegroundColor Green
    Write-Host "Python path: $(Get-Command python).Source" -ForegroundColor Gray
} else {
    Write-Host "FAIL: Failed to activate virtual environment" -ForegroundColor Red
    exit 1
}

# Step 3: Install/Update dependencies
Write-Host "`n[3/4] Installing dependencies..." -ForegroundColor Yellow

if (Test-Path $requirementsFile) {
    Write-Host "Installing from requirements.txt..." -ForegroundColor White
    pip install -r $requirementsFile
    
    if ($?) {
        Write-Host "OK: Dependencies installed successfully" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Some dependencies may have failed to install" -ForegroundColor Yellow
    }
} else {
    Write-Host "requirements.txt not found, installing common dependencies..." -ForegroundColor Yellow
    
    # Install essential packages
    $packages = @("python-dotenv", "redis", "requests")
    foreach ($pkg in $packages) {
        Write-Host "Installing $pkg..." -ForegroundColor White
        pip install $pkg
    }
    
    Write-Host "OK: Essential dependencies installed" -ForegroundColor Green
}

# Step 4: Verify critical packages
Write-Host "`n[4/4] Verifying critical packages..." -ForegroundColor Yellow

$criticalPackages = @("dotenv", "redis", "requests")
$allInstalled = $true

foreach ($pkg in $criticalPackages) {
    try {
        python -c "import $pkg" 2>$null
        if ($?) {
            Write-Host "OK: $pkg is installed" -ForegroundColor Green
        } else {
            Write-Host "FAIL: $pkg is NOT installed" -ForegroundColor Red
            $allInstalled = $false
        }
    } catch {
        Write-Host "FAIL: $pkg is NOT installed" -ForegroundColor Red
        $allInstalled = $false
    }
}

Write-Host ""
if ($allInstalled) {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Environment setup completed successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "You can now start the Worker with:" -ForegroundColor Yellow
    Write-Host "  python -m python_worker.agents.qwen.qwen_worker_v2" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  WARNING: Some packages are missing!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Please check the error messages above and install missing packages manually." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}