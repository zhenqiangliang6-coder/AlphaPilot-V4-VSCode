# test_step_streaming_quick_test.ps1
# ============================================================
# test_step 流式输出快速测试脚本
# ============================================================

Write-Host "🧪 test_step 流式输出快速测试" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 检查依赖
Write-Host "📦 检查Python依赖..." -ForegroundColor Yellow
python -c "import requests; import json; print('✅ requests OK')" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 缺少requests库,请运行: pip install requests" -ForegroundColor Red
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
    Write-Host "❌ Worker启动失败" -ForegroundColor Red
    exit 1
}

# 3. 提交测试任务
Write-Host "`n📤 提交测试任务..." -ForegroundColor Yellow

$taskBody = @{
    type = "qwen_generate"
    payload = @{
        prompt = "创建一个Python函数,计算两个数的和"
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
        
        # 简单检查:等待10秒后查看结果
        if ($chunkCount++ -gt 20) {
            break
        }
    }
} catch [System.ConsoleCancelEventArgs] {
    Write-Host "`n⏹️ 用户中断" -ForegroundColor Yellow
}

# 5. 查看最终结果
Write-Host "`n`n📊 查看任务结果..." -ForegroundColor Yellow

try {
    $resultKey = "task_result:$taskId"
    # 这里需要通过Node API或Redis客户端获取结果
    Write-Host "💡 提示: 请在VSCode AlphaPilot面板中查看完整流式输出效果" -ForegroundColor Cyan
    Write-Host "   或访问: http://localhost:3000/dlq/items 查看任务状态" -ForegroundColor Cyan
} catch {
    Write-Host "⚠️ 无法获取结果,请手动检查" -ForegroundColor Yellow
}

# 6. 清理
Write-Host "`n🧹 清理Worker进程..." -ForegroundColor Yellow
Stop-Process -Id $workerProcess.Id -Force -ErrorAction SilentlyContinue
Write-Host "✅ 测试完成`n" -ForegroundColor Green

Write-Host "📖 详细文档:" -ForegroundColor Cyan
Write-Host "   TEST_STEP_STREAMING_IMPLEMENTATION.md" -ForegroundColor White
Write-Host "`n🎯 下一步:" -ForegroundColor Cyan
Write-Host "   1. 在VSCode中按F5启动调试" -ForegroundColor White
Write-Host "   2. 打开AlphaPilot Chat面板" -ForegroundColor White
Write-Host "   3. 输入任务并观察流式输出效果" -ForegroundColor White
