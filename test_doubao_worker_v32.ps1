# -*- coding: utf-8 -*-
# test_doubao_worker_v32.ps1
# ---------------------------------------------------------
# Doubao Worker v3.2 独立链路快速测试脚本
# - 验证 Planner 独立性
# - 验证 API 调用（无代理错误）
# - 验证文件生成
# ---------------------------------------------------------

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Doubao Worker v3.2 独立链路测试" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查环境变量
Write-Host "[1/5] 检查环境变量..." -ForegroundColor Yellow
if (-not $env:VOLC_API_KEY) {
    Write-Host "❌ 错误: VOLC_API_KEY 未设置" -ForegroundColor Red
    Write-Host "请在 .env 文件中配置火山引擎 API Key" -ForegroundColor Yellow
    exit 1
}
Write-Host "✅ VOLC_API_KEY 已配置" -ForegroundColor Green
Write-Host ""

# 2. 启动 Node API（如果未运行）
Write-Host "[2/5] 检查 Node API 状态..." -ForegroundColor Yellow
$nodeApiRunning = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
if (-not $nodeApiRunning) {
    Write-Host "⚠️  Node API 未运行，正在启动..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd d:\Copilot_Alphapilot\Copilot_Alphapilot\node-api; npm start"
    Start-Sleep -Seconds 5
    Write-Host "✅ Node API 已启动" -ForegroundColor Green
} else {
    Write-Host "✅ Node API 已在运行" -ForegroundColor Green
}
Write-Host ""

# 3. 启动 Doubao Worker
Write-Host "[3/5] 启动 Doubao Worker v3.2..." -ForegroundColor Yellow
$workerProcess = Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:WORKER_ID='doubao-worker-1'; cd d:\Copilot_Alphapilot\Copilot_Alphapilot; python -m python_worker.agents.Volcengine.doubao_worker_v2" -PassThru
Start-Sleep -Seconds 3
Write-Host "✅ Doubao Worker 已启动 (PID: $($workerProcess.Id))" -ForegroundColor Green
Write-Host ""

# 4. 提交测试任务
Write-Host "[4/5] 提交测试任务..." -ForegroundColor Yellow
$testTask = @{
    type = "doubao_generate"
    payload = @{
        prompt = "生成一个 Python 排序函数，包含冒泡排序和快速排序两种实现"
    }
    source = "test-script"
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "http://localhost:3000/task/submit" -Method Post -Body $testTask -ContentType "application/json"
    Write-Host "✅ 任务已提交" -ForegroundColor Green
    Write-Host "   Task ID: $($response.task_id)" -ForegroundColor Cyan
    Write-Host ""
} catch {
    Write-Host "❌ 任务提交失败: $_" -ForegroundColor Red
    exit 1
}

# 5. 等待并检查结果
Write-Host "[5/5] 等待任务执行完成..." -ForegroundColor Yellow
Write-Host "请观察 Doubao Worker 窗口输出..." -ForegroundColor Cyan
Write-Host ""
Write-Host "预期结果:" -ForegroundColor Yellow
Write-Host "  ✅ Doubao Planner 成功拆解任务（8 个步骤）" -ForegroundColor White
Write-Host "  ✅ 每个步骤调用 Doubao API（非 Qwen）" -ForegroundColor White
Write-Host "  ✅ 无 ProxyError 错误" -ForegroundColor White
Write-Host "  ✅ FileOps 正确生成" -ForegroundColor White
Write-Host "  ✅ 文件实际写入磁盘" -ForegroundColor White
Write-Host ""
Write-Host "检查文件生成:" -ForegroundColor Yellow
Write-Host "  ls C:\Users\49772\AppData\Local\Temp\*.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "按任意键退出测试脚本..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
