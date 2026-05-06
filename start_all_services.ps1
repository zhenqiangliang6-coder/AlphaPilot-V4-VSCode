# start_all_services.ps1
# ============================================================
# AlphaPilot OS v2.5 完整服务启动脚本
# ============================================================

Write-Host "🚀 AlphaPilot OS v2.5 完整服务启动" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 激活Python虚拟环境
$venvPath = "d:\Copilot_Alphapilot\Copilot_Alphapilot\.venv_worker\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    Write-Host "📦 激活Python虚拟环境..." -ForegroundColor Yellow
    & $venvPath
    Write-Host "✅ 虚拟环境已激活`n" -ForegroundColor Green
} else {
    Write-Host "⚠️ 未找到虚拟环境`n" -ForegroundColor Yellow
}

# 2. 检查Redis是否运行
Write-Host "🔍 检查Redis服务..." -ForegroundColor Yellow
try {
    $redisTest = Test-NetConnection -ComputerName localhost -Port 6379 -WarningAction SilentlyContinue
    if ($redisTest.TcpTestSucceeded) {
        Write-Host "✅ Redis服务正在运行`n" -ForegroundColor Green
    } else {
        Write-Host "❌ Redis服务未运行，请先启动Redis" -ForegroundColor Red
        Write-Host "💡 提示: redis-server.exe 或 docker run redis" -ForegroundColor Gray
        exit 1
    }
} catch {
    Write-Host "⚠️ 无法检测Redis状态，继续尝试启动...`n" -ForegroundColor Yellow
}

# 3. 启动Node API
Write-Host "🚀 启动Node API..." -ForegroundColor Yellow

# 检查端口3000是否已被占用
$nodeRunning = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
if ($nodeRunning) {
    Write-Host "⚠️ Node API已在运行 (端口3000)" -ForegroundColor Yellow
} else {
    $nodeApiProcess = Start-Process node `
        -ArgumentList "index.js" `
        -WorkingDirectory "d:\Copilot_Alphapilot\Copilot_Alphapilot\node-api" `
        -PassThru `
        -WindowStyle Normal
    
    Start-Sleep -Seconds 3
    
    if (-not $nodeApiProcess.HasExited) {
        Write-Host "✅ Node API已启动 (PID: $($nodeApiProcess.Id))`n" -ForegroundColor Green
    } else {
        Write-Host "❌ Node API启动失败" -ForegroundColor Red
        exit 1
    }
}

# 4. 启动Qwen Worker
Write-Host "🚀 启动Qwen Worker v2..." -ForegroundColor Yellow

$workerProcess = Start-Process python `
    -ArgumentList "-m", "python_worker.agents.qwen.qwen_worker_v2" `
    -WorkingDirectory "d:\Copilot_Alphapilot\Copilot_Alphapilot" `
    -PassThru `
    -WindowStyle Normal

Start-Sleep -Seconds 3

if (-not $workerProcess.HasExited) {
    Write-Host "✅ Qwen Worker已启动 (PID: $($workerProcess.Id))`n" -ForegroundColor Green
} else {
    Write-Host "❌ Worker启动失败" -ForegroundColor Red
    exit 1
}

# 5. 验证服务连接
Write-Host "🧪 验证服务连接..." -ForegroundColor Yellow

try {
    $response = Invoke-RestMethod `
        -Uri "http://localhost:3000/dlq/items" `
        -Method GET `
        -TimeoutSec 5
    
    Write-Host "✅ Node API响应正常" -ForegroundColor Green
} catch {
    Write-Host "⚠️ Node API连接测试失败: $_" -ForegroundColor Yellow
}

# 6. 完成
Write-Host "`n🎉 所有服务已启动!" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "📊 服务状态:" -ForegroundColor Cyan
Write-Host "   ✅ Node API: http://localhost:3000" -ForegroundColor White
Write-Host "   ✅ Qwen Worker: 监听 task_queue:qwen" -ForegroundColor White
Write-Host "   ✅ Redis: localhost:6379" -ForegroundColor White
Write-Host ""
Write-Host "🎯 下一步操作:" -ForegroundColor Cyan
Write-Host "   1. 在VSCode中按F5启动调试(如果尚未启动)" -ForegroundColor White
Write-Host "   2. 打开AlphaPilot Chat面板" -ForegroundColor White
Write-Host "   3. 输入任务: '写一首关于未来的诗'" -ForegroundColor White
Write-Host "   4. 观察分通道流式输出效果" -ForegroundColor White
Write-Host ""
Write-Host "📖 相关文档:" -ForegroundColor Cyan
Write-Host "   COMPLETE_STREAMING_PROTOCOL_V2.5.md" -ForegroundColor White
Write-Host "   QUICK_START_V2.4.md" -ForegroundColor White
Write-Host ""
