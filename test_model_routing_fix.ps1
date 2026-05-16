# test_model_routing_fix.ps1
# AlphaPilot 模型路由修复验证脚本
# 用途: 验证local_generate任务是否正确路由到task_queue:local队列

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "AlphaPilot 模型路由修复验证" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 检查前端构建状态
Write-Host "📦 步骤1: 检查前端构建状态..." -ForegroundColor Yellow
$webviewDistPath = "d:\Copilot_Alphapilot\AlphaPilot-Frontend\vscode-extension\webview-dist\assets\index.js"
if (Test-Path $webviewDistPath) {
    $content = Get-Content $webviewDistPath -Raw
    if ($content -match "local_generate") {
        Write-Host "✅ 前端已包含 local_generate 选项" -ForegroundColor Green
    } else {
        Write-Host "❌ 前端未找到 local_generate,需要重新构建!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "❌ webview-dist 目录不存在" -ForegroundColor Red
    exit 1
}

# 2. 启动Node API(如果未运行)
Write-Host "`n🚀 步骤2: 检查Node API状态..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:3000/health" -Method GET -ErrorAction Stop
    Write-Host "✅ Node API 正在运行" -ForegroundColor Green
} catch {
    Write-Host "⚠️ Node API 未运行,请先执行: .\start_all.ps1" -ForegroundColor Yellow
    exit 1
}

# 3. 提交测试任务
Write-Host "`n📤 步骤3: 提交测试任务 (type=local_generate)..." -ForegroundColor Yellow
$body = @{
    type = "local_generate"
    payload = @{ prompt = "用python写一个排序函数" }
    source = "test-script"
} | ConvertTo-Json -Depth 10

try {
    $result = Invoke-RestMethod -Uri "http://localhost:3000/task/submit" -Method POST -Body $body -ContentType "application/json"
    Write-Host "✅ 任务提交成功" -ForegroundColor Green
    Write-Host "   Task ID: $($result.task_id)" -ForegroundColor Cyan
    Write-Host "   Model: $($result.model)" -ForegroundColor Cyan
    
    # 验证model字段
    if ($result.model -eq "local-gemma4b") {
        Write-Host "✅ Model推断正确: local-gemma4b" -ForegroundColor Green
    } else {
        Write-Host "❌ Model推断错误: $($result.model) (期望: local-gemma4b)" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ 任务提交失败: $_" -ForegroundColor Red
    exit 1
}

# 4. 验证队列路由
Write-Host "`n🎯 步骤4: 验证队列路由..." -ForegroundColor Yellow
Write-Host "预期: task_queue:local" -ForegroundColor Cyan
Write-Host "请观察Node API终端输出,确认显示:" -ForegroundColor Yellow
Write-Host "   🎯 路由到队列: task_queue:local (模型: local-gemma4b)" -ForegroundColor White

# 5. 检查Local Worker状态
Write-Host "`n👷 步骤5: 检查Local Worker状态..." -ForegroundColor Yellow
Write-Host "请确保Local LLM Worker正在运行并监听 task_queue:local" -ForegroundColor Cyan
Write-Host "预期日志:" -ForegroundColor Yellow
Write-Host "   📡 Local LLM Worker v3.0 监听队列: task_queue:local" -ForegroundColor White
Write-Host "   收到任务: { `"type`": `"local_generate`", ... }" -ForegroundColor White
Write-Host "   (不应该出现 '收到不匹配的任务类型' 错误)" -ForegroundColor White

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "验证完成! 请检查上述输出" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
