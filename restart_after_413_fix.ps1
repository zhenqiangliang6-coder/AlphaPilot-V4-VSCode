# restart_after_413_fix.ps1
# ============================================================
# 修复413错误后的快速重启脚本
# ============================================================

Write-Host "🔄 AlphaPilot OS v2.4.1 系统扩容重启" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 停止现有进程
Write-Host "🛑 停止现有服务..." -ForegroundColor Yellow

# 查找并停止Node API进程
$nodeProcesses = Get-Process | Where-Object { $_.ProcessName -eq "node" -and $_.Path -like "*Copilot_Alphapilot*" }
if ($nodeProcesses) {
    Write-Host "   找到 $($nodeProcesses.Count) 个Node.js进程" -ForegroundColor Gray
    $nodeProcesses | Stop-Process -Force
    Write-Host "   ✅ Node API已停止" -ForegroundColor Green
} else {
    Write-Host "   ⚠️ 未找到运行中的Node API" -ForegroundColor Yellow
}

# 查找并停止Worker进程
$pythonProcesses = Get-Process | Where-Object { $_.ProcessName -eq "python" -and $_.CommandLine -like "*qwen_worker_v2*" }
if ($pythonProcesses) {
    Write-Host "   找到 $($pythonProcesses.Count) 个Worker进程" -ForegroundColor Gray
    $pythonProcesses | Stop-Process -Force
    Write-Host "   ✅ Worker已停止" -ForegroundColor Green
} else {
    Write-Host "   ⚠️ 未找到运行中的Worker" -ForegroundColor Yellow
}

Start-Sleep -Seconds 2

# 2. 验证修复
Write-Host "`n🔍 验证body-parser配置..." -ForegroundColor Yellow

$indexJsPath = "d:\Copilot_Alphapilot\Copilot_Alphapilot\node-api\index.js"
$content = Get-Content $indexJsPath -Raw

if ($content -match 'express\.json\(\s*\{\s*limit:\s*["'']10mb["'']') {
    Write-Host "   ✅ body-parser限制已设置为10MB" -ForegroundColor Green
} else {
    Write-Host "   ❌ 未找到10MB配置,请检查index.js" -ForegroundColor Red
    exit 1
}

# 3. 启动Node API
Write-Host "`n🚀 启动Node API..." -ForegroundColor Yellow

$nodeApiProcess = Start-Process node `
    -ArgumentList "index.js" `
    -WorkingDirectory "d:\Copilot_Alphapilot\Copilot_Alphapilot\node-api" `
    -PassThru `
    -WindowStyle Normal

Start-Sleep -Seconds 3

if (-not $nodeApiProcess.HasExited) {
    Write-Host "   ✅ Node API已启动 (PID: $($nodeApiProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "   ❌ Node API启动失败" -ForegroundColor Red
    exit 1
}

# 4. 启动Worker
Write-Host "`n🚀 启动Qwen Worker v2..." -ForegroundColor Yellow

$workerProcess = Start-Process python `
    -ArgumentList "-m", "python_worker.agents.qwen.qwen_worker_v2" `
    -WorkingDirectory "d:\Copilot_Alphapilot\Copilot_Alphapilot" `
    -PassThru `
    -WindowStyle Normal

Start-Sleep -Seconds 3

if (-not $workerProcess.HasExited) {
    Write-Host "   ✅ Worker已启动 (PID: $($workerProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "   ❌ Worker启动失败" -ForegroundColor Red
    exit 1
}

# 5. 测试连接
Write-Host "`n🧪 测试API连接..." -ForegroundColor Yellow

try {
    $response = Invoke-RestMethod `
        -Uri "http://localhost:3000/dlq/items" `
        -Method GET `
        -TimeoutSec 5
    
    Write-Host "   ✅ Node API响应正常" -ForegroundColor Green
} catch {
    Write-Host "   ⚠️ API连接测试失败: $_" -ForegroundColor Yellow
    Write-Host "   提示: 可能需要更多时间启动" -ForegroundColor Gray
}

# 6. 完成
Write-Host "`n🎉 重启完成!" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "📖 下一步操作:" -ForegroundColor Cyan
Write-Host "   1. 在VSCode中按F5启动调试(如果尚未启动)" -ForegroundColor White
Write-Host "   2. 打开AlphaPilot Chat面板" -ForegroundColor White
Write-Host "   3. 输入任务: '写一道关于未来的诗'" -ForegroundColor White
Write-Host "   4. 观察流式输出效果(无413错误)" -ForegroundColor White
Write-Host ""
Write-Host "📊 监控日志:" -ForegroundColor Cyan
Write-Host "   - Node API终端: 查看stream_chunk接收情况" -ForegroundColor White
Write-Host "   - Worker终端: 查看stream_chunk发送情况" -ForegroundColor White
Write-Host "   - Webview控制台: 查看消息渲染情况" -ForegroundColor White
Write-Host ""
Write-Host "📝 相关文档:" -ForegroundColor Cyan
Write-Host "   SYSTEM_SCALING_GUIDE_413_FIX.md" -ForegroundColor White
Write-Host ""
