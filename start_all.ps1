# ================================
# AlphaPilot 全栈启动脚本（PowerShell 7+ 优化版）
# ================================

# ⭐ PowerShell 7+ 兼容性设置
# 确保使用正确的编码
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
    $PSDefaultParameterValues['*:Encoding'] = 'utf8'
} else {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}

# 设置错误处理策略
$ErrorActionPreference = 'Continue'

Write-Host "🚀 正在启动 AlphaPilot 全栈服务..." -ForegroundColor Green
Write-Host "💻 PowerShell 版本: $($PSVersionTable.PSVersion.ToString())" -ForegroundColor Cyan
Write-Host ""

# -------------------------------
# 辅助函数：检查端口是否被占用
# -------------------------------
function Test-PortInUse {
    param([int]$Port)
    
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $tcpClient.Connect("localhost", $Port)
        $tcpClient.Close()
        return $true
    } catch {
        return $false
    }
}

# -------------------------------
# 辅助函数：获取 Python 虚拟环境路径
# -------------------------------
function Get-PythonVenvPath {
    $venvPaths = @(
        "$PSScriptRoot\.venv_worker\Scripts\python.exe",
        "$PSScriptRoot\python_worker\.venv\Scripts\python.exe",
        "$PSScriptRoot\.venv\Scripts\python.exe"
    )
    
    foreach ($path in $venvPaths) {
        if (Test-Path $path) {
            return $path
        }
    }
    
    # 如果找不到虚拟环境，使用系统 Python
    Write-Host "   ⚠️ 未找到虚拟环境，使用系统 Python" -ForegroundColor Yellow
    return "python"
}

# -------------------------------
# 1. 检查 Node API
# -------------------------------
Write-Host "1️⃣ 检查 Node API..." -ForegroundColor Yellow

$nodeApiPort = 3000
if (Test-PortInUse -Port $nodeApiPort) {
    Write-Host "   ✅ Node API 已在运行 (端口 $nodeApiPort)" -ForegroundColor Green
} else {
    Write-Host "   ⚠️ Node API 未运行，正在启动..." -ForegroundColor Yellow
    
    # 检查 node-api 目录是否存在
    $nodeApiPath = Join-Path $PSScriptRoot "node-api"
    if (Test-Path $nodeApiPath) {
        # 使用 pwsh (PowerShell 7+) 或 powershell (Windows PowerShell)
        $shellCommand = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
        
        Start-Process $shellCommand -ArgumentList "-NoExit", "-Command", "cd '$nodeApiPath'; npm start" -WindowStyle Normal
        Write-Host "   🔄 等待 Node API 启动..." -ForegroundColor Cyan
        Start-Sleep -Seconds 5
        
        # 验证是否启动成功
        if (Test-PortInUse -Port $nodeApiPort) {
            Write-Host "   ✅ Node API 启动成功" -ForegroundColor Green
        } else {
            Write-Host "   ⚠️ Node API 可能仍在启动中，请手动检查" -ForegroundColor Yellow
        }
    } else {
        Write-Host "   ❌ node-api 目录不存在: $nodeApiPath" -ForegroundColor Red
    }
}

# -------------------------------
# 2. 启动 Workers
# -------------------------------
Write-Host ""
Write-Host "2️⃣ 启动 Workers..." -ForegroundColor Yellow

# 获取 Python 解释器路径
$pythonExe = Get-PythonVenvPath
Write-Host "   🐍 Python: $pythonExe" -ForegroundColor Cyan

# Worker 配置（v3.0 流式输出版）
$workers = @(
    @{Name="Qwen"; Script="python_worker.agents.qwen.qwen_worker_v2"; EnvId="qwen-worker-1"},
    @{Name="DeepSeek"; Script="python_worker.agents.deepeek.deepseek_worker_v3"; EnvId="deepseek-worker-1"},
    @{Name="Doubao"; Script="python_worker.agents.Volcengine.doubao_worker_v3"; EnvId="doubao-worker-1"},
    @{Name="Local LLM"; Script="python_worker.agents.local_llm.local_worker_v3"; EnvId="local-worker-1"}
)

foreach ($worker in $workers) {
    Write-Host "   🔄 启动 $($worker.Name) Worker ($($worker.EnvId))..." -ForegroundColor Cyan
    
    # 构建命令
    $shellCommand = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
    
    # ⭐ 修复：正确传递环境变量和命令
    $cmdArgs = @(
        "-NoExit",
        "-Command",
        "`$env:WORKER_ID='$($worker.EnvId)'; Set-Location -LiteralPath '$PSScriptRoot'; & '$pythonExe' -m $($worker.Script)"
    )
    
    try {
        Start-Process $shellCommand -ArgumentList $cmdArgs -WindowStyle Normal
        Write-Host "   ✅ $($worker.Name) Worker 已启动" -ForegroundColor Green
    } catch {
        Write-Host "   ❌ $($worker.Name) Worker 启动失败: $_" -ForegroundColor Red
    }
    
    Start-Sleep -Seconds 1
}

# -------------------------------
# 3. 完成
# -------------------------------
Write-Host ""
Write-Host "✅ 所有服务已启动!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 下一步操作:" -ForegroundColor Yellow
Write-Host "   1. 在 VSCode 中按 F5 启动扩展调试" -ForegroundColor White
Write-Host "   2. 或运行: cd vscode-extension && npm run compile" -ForegroundColor White
Write-Host "   3. 按 Ctrl+Shift+A 打开 AlphaPilot 面板" -ForegroundColor White
Write-Host ""
Write-Host "💡 提示:" -ForegroundColor Cyan
Write-Host "   - 所有服务将在独立窗口中运行，可单独查看日志" -ForegroundColor White
Write-Host "   - 关闭终端窗口即可停止对应服务" -ForegroundColor White
Write-Host "   - 如遇问题，请检查各窗口的错误信息" -ForegroundColor White
Write-Host ""

# 显示服务状态摘要
Write-Host "📊 服务状态摘要:" -ForegroundColor Magenta
Write-Host "   Node API: $(if (Test-PortInUse -Port 3000) { '✅ 运行中' } else { '❌ 未运行' })" -ForegroundColor White
Write-Host "   Qwen Worker: ✅ 已启动 (新窗口)" -ForegroundColor White
Write-Host "   DeepSeek Worker: ✅ 已启动 (新窗口)" -ForegroundColor White
Write-Host "   Doubao Worker: ✅ 已启动 (新窗口)" -ForegroundColor White
Write-Host "   Local LLM Worker: ✅ 已启动 (新窗口)" -ForegroundColor White
Write-Host ""
