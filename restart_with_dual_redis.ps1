# ================================
# AlphaPilot OS v2.8 双云 Redis 架构 - 快速重启脚本
# ================================

Write-Host "🔄 AlphaPilot OS v2.8 双云 Redis 架构 - 快速重启" -ForegroundColor Green
Write-Host ""

# -------------------------------
# 1. 停止现有服务
# -------------------------------
Write-Host "1️⃣ 停止现有服务..." -ForegroundColor Yellow

# 停止 Node API
$nodeApiProcesses = Get-Process | Where-Object { 
    $_.ProcessName -eq "node" -and $_.CommandLine -like "*node-api*" 
}
if ($nodeApiProcesses) {
    Write-Host "   🔄 停止 Node API..." -ForegroundColor Cyan
    $nodeApiProcesses | Stop-Process -Force
    Write-Host "   ✅ Node API 已停止" -ForegroundColor Green
} else {
    Write-Host "   ℹ️  Node API 未运行" -ForegroundColor Gray
}

# 停止 Workers
$workerProcesses = Get-Process | Where-Object { 
    $_.ProcessName -eq "python" -and (
        $_.CommandLine -like "*qwen_worker*" -or
        $_.CommandLine -like "*deepseek_worker*" -or
        $_.CommandLine -like "*doubao_worker*"
    )
}
if ($workerProcesses) {
    Write-Host "   🔄 停止 Workers..." -ForegroundColor Cyan
    $workerProcesses | Stop-Process -Force
    Write-Host "   ✅ Workers 已停止" -ForegroundColor Green
} else {
    Write-Host "   ℹ️  Workers 未运行" -ForegroundColor Gray
}

Start-Sleep -Seconds 2

# -------------------------------
# 2. 清理 Python 缓存
# -------------------------------
Write-Host ""
Write-Host "2️⃣ 清理 Python 缓存..." -ForegroundColor Yellow

Get-ChildItem -Path "d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker" -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path "d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker" -Recurse -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "   ✅ 缓存已清理" -ForegroundColor Green

# -------------------------------
# 3. 启动新服务
# -------------------------------
Write-Host ""
Write-Host "3️⃣ 启动新服务..." -ForegroundColor Yellow

Write-Host "   🚀 正在启动所有服务..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; .\start_all.ps1" -WindowStyle Normal

Start-Sleep -Seconds 3

# -------------------------------
# 4. 验证启动
# -------------------------------
Write-Host ""
Write-Host "4️⃣ 验证启动..." -ForegroundColor Yellow

# 检查 Node API
$nodeApiPort = 3000
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $tcpClient.Connect("localhost", $nodeApiPort)
    $tcpClient.Close()
    Write-Host "   ✅ Node API 已启动 (端口 $nodeApiPort)" -ForegroundColor Green
} catch {
    Write-Host "   ⚠️  Node API 可能仍在启动中..." -ForegroundColor Yellow
}

# 检查 Workers
$workerCount = (Get-Process | Where-Object { 
    $_.ProcessName -eq "python" -and (
        $_.CommandLine -like "*qwen_worker*" -or
        $_.CommandLine -like "*deepseek_worker*" -or
        $_.CommandLine -like "*doubao_worker*"
    )
}).Count

if ($workerCount -ge 3) {
    Write-Host "   ✅ Workers 已启动 ($workerCount 个)" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Workers 可能仍在启动中... (当前: $workerCount)" -ForegroundColor Yellow
}

# -------------------------------
# 5. 完成
# -------------------------------
Write-Host ""
Write-Host "✅ 重启完成!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 下一步:" -ForegroundColor Magenta
Write-Host "   1. 检查各个终端窗口的日志" -ForegroundColor White
Write-Host "   2. 确认每个 Worker 使用了正确的 Redis" -ForegroundColor White
Write-Host "   3. 发送测试任务验证端到端流程" -ForegroundColor White
Write-Host ""
Write-Host "💡 预期日志:" -ForegroundColor Cyan
Write-Host "   Qwen Worker: ✅ 使用 Upstash Redis" -ForegroundColor Gray
Write-Host "   DeepSeek Worker: ✅ 使用阿里云 Tair Redis" -ForegroundColor Gray
Write-Host "   Doubao Worker: ✅ 使用阿里云 Tair Redis" -ForegroundColor Gray
Write-Host ""