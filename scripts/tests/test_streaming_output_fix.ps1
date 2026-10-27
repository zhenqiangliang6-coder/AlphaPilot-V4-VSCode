# test_streaming_output_fix.ps1
# Streaming Output Fix Verification Test Script

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AlphaPilot Streaming Output Fix Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check current directory
$projectRoot = "d:\Copilot_Alphapilot\Copilot_Alphapilot"
if (-not (Test-Path $projectRoot)) {
    Write-Host "ERROR: Project root not found: $projectRoot" -ForegroundColor Red
    exit 1
}

Set-Location $projectRoot

# Step 1: Check and setup environment
Write-Host "[1/5] Checking Python environment..." -ForegroundColor Yellow

$venvActivate = Join-Path $projectRoot ".venv_worker\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    Write-Host "Virtual environment found, activating..." -ForegroundColor White
    & $venvActivate
    
    # Verify critical packages
    try {
        python -c "import dotenv" 2>$null
        if ($?) {
            Write-Host "OK: Environment is ready" -ForegroundColor Green
        } else {
            Write-Host "WARNING: Missing dependencies. Running setup script..." -ForegroundColor Yellow
            Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$projectRoot'; .\setup_worker_env.ps1"
            Start-Sleep -Seconds 5
        }
    } catch {
        Write-Host "ERROR: Python not available in virtual environment" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "WARNING: Virtual environment not found. Creating..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$projectRoot'; .\setup_worker_env.ps1"
    Start-Sleep -Seconds 5
}

# Step 2: Stop existing Worker processes
Write-Host "`n[2/5] Stopping existing Python Worker processes..." -ForegroundColor Yellow
$workers = Get-Process | Where-Object { 
    $_.ProcessName -like "*python*" -and 
    $_.Path -like "*Copilot_Alphapilot*" 
}

if ($workers) {
    $workers | Stop-Process -Force
    Write-Host "Stopped $($workers.Count) Worker process(es)" -ForegroundColor Green
    Start-Sleep -Seconds 2
} else {
    Write-Host "No running Worker processes found" -ForegroundColor Yellow
}

# Step 3: Verify fix files
Write-Host "`n[3/5] Verifying fix files..." -ForegroundColor Yellow

$workerConfig = Join-Path $projectRoot "python_worker\worker_config.py"
$appTsx = Join-Path $projectRoot "vscode-extension\webview\src\App.tsx"

if (Test-Path $workerConfig) {
    $content = Get-Content $workerConfig -Raw
    if ($content -match "def stream_chunk\(task_id: str, content: str, phase: str = None, channel: str = None\)") {
        Write-Host "OK: worker_config.py - stream_chunk signature updated" -ForegroundColor Green
    } else {
        Write-Host "FAIL: worker_config.py - stream_chunk signature not updated" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "FAIL: worker_config.py file not found" -ForegroundColor Red
    exit 1
}

if (Test-Path $appTsx) {
    $content = Get-Content $appTsx -Raw
    if ($content -match "const hasStreamingContent = prev\.contentChannel \|\| prev\.content") {
        Write-Host "OK: App.tsx - handleTaskCompleted fixed" -ForegroundColor Green
    } else {
        Write-Host "FAIL: App.tsx - handleTaskCompleted not fixed" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "FAIL: App.tsx file not found" -ForegroundColor Red
    exit 1
}

# Step 4: Start Worker with Virtual Environment
Write-Host "`n[4/5] Starting Qwen Worker (with virtual environment)..." -ForegroundColor Yellow

$workerScript = Join-Path $projectRoot "python_worker\agents\qwen\qwen_worker_v2.py"
$venvActivate = Join-Path $projectRoot ".venv_worker\Scripts\Activate.ps1"

if (Test-Path $workerScript) {
    if (Test-Path $venvActivate) {
        Write-Host "Activating virtual environment and starting Worker..." -ForegroundColor White
        
        # ⭐ 关键修复: 在新窗口中先激活虚拟环境,再启动 Worker
        $startCommand = "cd '$projectRoot'; & '$venvActivate'; python -m python_worker.agents.qwen.qwen_worker_v2"
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $startCommand
        
        Start-Sleep -Seconds 3
        Write-Host "Worker started in background with virtual environment activated" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Virtual environment not found at: $venvActivate" -ForegroundColor Yellow
        Write-Host "Attempting to start Worker without virtual environment..." -ForegroundColor Yellow
        
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$projectRoot'; python -m python_worker.agents.qwen.qwen_worker_v2"
        Start-Sleep -Seconds 3
        Write-Host "Worker started (may fail if dependencies missing)" -ForegroundColor Yellow
    }
} else {
    Write-Host "FAIL: Worker script not found: $workerScript" -ForegroundColor Red
    exit 1
}

# Step 5: Testing Guide
Write-Host "`n[5/5] Testing Guide" -ForegroundColor Yellow
Write-Host ""
Write-Host "Please follow these steps to test:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Open VSCode" -ForegroundColor Cyan
Write-Host "     - Ensure AlphaPilot extension is loaded" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Open Chat Panel" -ForegroundColor Cyan
Write-Host "     - Shortcut: Ctrl+Shift+A" -ForegroundColor Gray
Write-Host "     - Or Command Palette: AlphaPilot: Open React Panel" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Submit Test Task" -ForegroundColor Cyan
Write-Host "     - Input: Please write a modern poem about the future" -ForegroundColor Gray
Write-Host "     - Click send button" -ForegroundColor Gray
Write-Host ""
Write-Host "  4. Observe Output (Expected Results)" -ForegroundColor Cyan
Write-Host "     OK - AI Thinking Process (purple background)" -ForegroundColor Green
Write-Host "        - Shows analysis, planning thoughts" -ForegroundColor Gray
Write-Host ""
Write-Host "     OK - Step Tree (visual progress)" -ForegroundColor Green
Write-Host "        - analyze -> plan -> write -> refine -> test" -ForegroundColor Gray
Write-Host "        - Each step shows execution status" -ForegroundColor Gray
Write-Host ""
Write-Host "     OK - Final Poem Content (Markdown rendered)" -ForegroundColor Green
Write-Host "        - Complete modern poem content" -ForegroundColor Gray
Write-Host "        - Supports code highlighting and formatting" -ForegroundColor Gray
Write-Host ""
Write-Host "  5. Check Console Logs (Optional)" -ForegroundColor Cyan
Write-Host "     - Open browser DevTools (F12)" -ForegroundColor Gray
Write-Host "     - View Console tab" -ForegroundColor Gray
Write-Host "     - Should see:" -ForegroundColor Gray
Write-Host "       handleStreamChunk - phase: write channel: content" -ForegroundColor DarkGray
Write-Host "       content update - length: XXXX" -ForegroundColor DarkGray
Write-Host "       Keep streaming output content, length: XXXX" -ForegroundColor DarkGray
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Expected: Poem content displays completely without being overwritten!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "If you encounter issues, please check:" -ForegroundColor Yellow
Write-Host "  - STREAMING_OUTPUT_FIX_REPORT.md (detailed fix report)" -ForegroundColor White
Write-Host "  - ARCHITECTURE_MANIFESTO.md (architecture manifesto)" -ForegroundColor White
Write-Host ""
