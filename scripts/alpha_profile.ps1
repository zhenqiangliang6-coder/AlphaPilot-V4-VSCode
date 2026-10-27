# AlphaPilot PowerShell 配置文件
# 将此文件保存为: $PROFILE.CurrentUserAllHosts
# 或运行: New-Item -Path $PROFILE.CurrentUserAllHosts -ItemType File -Force
# 然后将以下内容复制到该文件中

# ================================
# 1. 编码设置（修复中文乱码）
# ================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

# ================================
# 2. AlphaPilot 项目路径配置
# ================================
$AlphaPilotRoot = "d:\Copilot_Alphapilot\Copilot_Alphapilot"

# ================================
# 3. 别名设置（提高效率）
# ================================
Set-Alias -Name start-alpha -Value "$AlphaPilotRoot\start_all.ps1"
Set-Alias -Name check-env -Value "$AlphaPilotRoot\check_powershell_env.ps1"
Set-Alias -Name test-qwen -Value "$AlphaPilotRoot\run_qwen_worker_test.ps1"

# ================================
# 4. 函数定义
# ================================

# 快速启动 AlphaPilot
function Start-AlphaPilot {
    param(
        [switch]$NoWorkers,
        [switch]$OnlyQwen
    )
    
    $scriptPath = Join-Path $PSScriptRoot "start_all.ps1"
    if (Test-Path $scriptPath) {
        & $scriptPath
    } else {
        Write-Host "❌ 找不到 start_all.ps1" -ForegroundColor Red
    }
}

# 检查环境
function Test-AlphaPilotEnv {
    $scriptPath = Join-Path $PSScriptRoot "check_powershell_env.ps1"
    if (Test-Path $scriptPath) {
        & $scriptPath
    } else {
        Write-Host "❌ 找不到 check_powershell_env.ps1" -ForegroundColor Red
    }
}

# 停止所有服务
function Stop-AlphaPilot {
    Write-Host "🛑 正在停止 AlphaPilot 服务..." -ForegroundColor Yellow
    
    # 停止 Node.js 进程
    Get-Process | Where-Object { $_.ProcessName -eq "node" } | ForEach-Object {
        Write-Host "   停止 Node 进程 (PID: $($_.Id))" -ForegroundColor Cyan
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    
    # 停止 Python 进程
    Get-Process | Where-Object { $_.ProcessName -eq "python" } | ForEach-Object {
        Write-Host "   停止 Python 进程 (PID: $($_.Id))" -ForegroundColor Cyan
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    
    Write-Host "✅ 所有服务已停止" -ForegroundColor Green
}

# 查看 Worker 状态
function Get-WorkerStatus {
    Write-Host "📊 Worker 状态:" -ForegroundColor Cyan
    
    $workers = @(
        @{Name="Qwen"; Id="qwen-worker-1"},
        @{Name="DeepSeek"; Id="deepseek-worker-1"},
        @{Name="Doubao"; Id="doubao-worker-1"}
    )
    
    foreach ($worker in $workers) {
        $processes = Get-Process | Where-Object {
            $_.ProcessName -eq "python" -and $_.CommandLine -like "*$($worker.Id)*"
        }
        
        if ($processes) {
            Write-Host "   ✅ $($worker.Name): 运行中 (PID: $($processes.Id -join ', '))" -ForegroundColor Green
        } else {
            Write-Host "   ❌ $($worker.Name): 未运行" -ForegroundColor Red
        }
    }
}

# ================================
# 5. 欢迎信息
# ================================
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "AlphaPilot PowerShell 环境已加载" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "可用命令:" -ForegroundColor Yellow
Write-Host "  Start-AlphaPilot     - 启动所有服务" -ForegroundColor White
Write-Host "  Test-AlphaPilotEnv   - 检查环境配置" -ForegroundColor White
Write-Host "  Stop-AlphaPilot      - 停止所有服务" -ForegroundColor White
Write-Host "  Get-WorkerStatus     - 查看 Worker 状态" -ForegroundColor White
Write-Host ""
Write-Host "快捷别名:" -ForegroundColor Yellow
Write-Host "  start-alpha          - 启动服务" -ForegroundColor Gray
Write-Host "  check-env            - 检查环境" -ForegroundColor Gray
Write-Host "  test-qwen            - 测试 Qwen Worker" -ForegroundColor Gray
Write-Host ""
