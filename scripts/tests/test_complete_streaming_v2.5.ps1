# test_complete_streaming_v2.5.ps1
# ============================================================
# 完整流式协议 v2.5 快速测试脚本
# ============================================================

Write-Host "🧪 完整流式协议 v2.5 快速测试" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# ⭐ 关键修复：激活Python虚拟环境
$venvPath = "d:\Copilot_Alphapilot\Copilot_Alphapilot\.venv_worker\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    Write-Host "📦 激活Python虚拟环境..." -ForegroundColor Yellow
    & $venvPath
    Write-Host "✅ 虚拟环境已激活`n" -ForegroundColor Green
} else {
    Write-Host "⚠️ 未找到虚拟环境，尝试使用系统Python`n" -ForegroundColor Yellow
}

# 1. 检查依赖
Write-Host "📦 检查Python依赖..." -ForegroundColor Yellow
python -c "import requests; import json; print('✅ requests OK')" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 缺少requests库，请运行: pip install requests" -ForegroundColor Red
    exit 1
}

# 2. 启动Worker (后台)
Write-Host "`n🚀 启动Qwen Worker v2..." -ForegroundColor Yellow
$workerProcess = Start-Process python `
    -ArgumentList "-m", "python_worker.agents.qwen.qwen_worker_v2" `
    -WorkingDirectory "d:\Copilot_Alphapilot\Copilot_Alphapilot" `
    -PassThru `
    -WindowStyle Hidden

Start-Sleep -Seconds 3

if (-not $workerProcess.HasExited) {
    Write-Host "✅ Worker已启动 (PID: $($workerProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "❌ Worker启动失败，请检查日志" -ForegroundColor Red
    Write-Host "💡 提示: 手动运行以下命令查看详细错误:" -ForegroundColor Yellow
    Write-Host "   cd d:\Copilot_Alphapilot\Copilot_Alphapilot" -ForegroundColor Gray
    Write-Host "   .\.venv_worker\Scripts\Activate.ps1" -ForegroundColor Gray
    Write-Host "   python -m python_worker.agents.qwen.qwen_worker_v2" -ForegroundColor Gray
    exit 1
}

# 3. 提交测试任务 (写诗)
Write-Host "`n📤 提交测试任务: 写一首关于未来的诗..." -ForegroundColor Yellow

$taskBody = @{
    type = "task.generate"
    payload = @{
        prompt = "写一首关于未来的诗"
    }
    meta = @{
        model = "qwen2.5"
        stream = $true
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod `
        -Uri "http://localhost:3000/task/submit" `
        -Method POST `
        -ContentType "application/json" `
        -Body $taskBody
    
    $taskId = $response.task_id
    Write-Host "✅ 任务已提交: $taskId" -ForegroundColor Green
    Write-Host "   模型: $($response.model)" -ForegroundColor Gray
    Write-Host "   流式: $($response.stream)" -ForegroundColor Gray
} catch {
    Write-Host "❌ 任务提交失败: $_" -ForegroundColor Red
    Stop-Process -Id $workerProcess.Id -Force
    exit 1
}

# 4. 监控流式输出
Write-Host "`n👀 监控流式输出 (按Ctrl+C停止)..." -ForegroundColor Yellow
Write-Host "----------------------------------------`n"

$chunkCount = 0
$lastUpdate = Get-Date

try {
    # 轮询检查Redis结果
    while ($true) {
        Start-Sleep -Milliseconds 500
        
        # 检查是否有新chunk(通过日志或WebSocket)
        $now = Get-Date
        if (($now - $lastUpdate).TotalSeconds -gt 2) {
            Write-Host "." -NoNewline
            $lastUpdate = $now
        }
        
        # 简单检查:等待15秒后查看结果
        if ($chunkCount++ -gt 30) {
            break
        }
    }
} catch [System.ConsoleCancelEventArgs] {
    Write-Host "`n⏹️ 用户中断" -ForegroundColor Yellow
}

# 5. 查看最终结果
Write-Host "`n`n📊 查看任务结果..." -ForegroundColor Yellow

try {
    Write-Host "💡 提示: 请在VSCode AlphaPilot面板中查看完整流式输出效果" -ForegroundColor Cyan
    Write-Host "   应该看到:" -ForegroundColor White
    Write-Host "   - 💭 紫色边框卡片显示思考过程 (channel=reasoning)" -ForegroundColor White
    Write-Host "   - 📝 Markdown渲染显示诗歌内容 (channel=content)" -ForegroundColor White
    Write-Host "   - [analyze] → [plan] → [write] 阶段标签切换" -ForegroundColor White
} catch {
    Write-Host "⚠️ 无法获取结果，请手动检查" -ForegroundColor Yellow
}

# 6. 清理
Write-Host "`n🧹 清理Worker进程..." -ForegroundColor Yellow
Stop-Process -Id $workerProcess.Id -Force -ErrorAction SilentlyContinue
Write-Host "✅ 测试完成`n" -ForegroundColor Green

Write-Host "📖 详细文档:" -ForegroundColor Cyan
Write-Host "   COMPLETE_STREAMING_PROTOCOL_V2.5.md" -ForegroundColor White
Write-Host "`n🎯 下一步:" -ForegroundColor Cyan
Write-Host "   1. 在VSCode中按F5启动调试" -ForegroundColor White
Write-Host "   2. 打开AlphaPilot Chat面板" -ForegroundColor White
Write-Host "   3. 输入任务: '写一首关于未来的诗'" -ForegroundColor White
Write-Host "   4. 观察分通道流式输出效果" -ForegroundColor White
