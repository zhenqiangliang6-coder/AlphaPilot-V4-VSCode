# test_doubao_worker_streaming.ps1
# ---------------------------------------------------------
# 测试豆包 Worker v3.0 流式输出功能
# ---------------------------------------------------------

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  豆包 Worker v3.0 流式输出测试" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 检查豆包 Worker 进程是否运行
Write-Host "[1/5] 检查豆包 Worker 进程..." -ForegroundColor Yellow
$doubaoWorker = Get-Process | Where-Object { $_.Path -like "*python*" -and $_.CommandLine -like "*doubao_worker*" }

if ($doubaoWorker) {
    Write-Host "✅ 豆包 Worker 正在运行 (PID: $($doubaoWorker.Id))" -ForegroundColor Green
} else {
    Write-Host "⚠️  豆包 Worker 未运行，需要启动" -ForegroundColor Yellow
    
    # 启动豆包 Worker
    Write-Host "`n[2/5] 启动豆包 Worker v3.0..." -ForegroundColor Yellow
    Start-Process -FilePath "python" -ArgumentList "-m", "agents.Volcengine.doubao_worker_v3" -WorkingDirectory "d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker" -WindowStyle Normal
    
    Write-Host "⏳ 等待 Worker 启动..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    
    Write-Host "✅ 豆包 Worker 已启动" -ForegroundColor Green
}

# 2. 检查 Redis 队列
Write-Host "`n[3/5] 检查 Redis 队列配置..." -ForegroundColor Yellow
$redisCheck = python -c "
import sys
sys.path.insert(0, 'python_worker')
from worker_config import redis, get_worker_queue
queue_name = get_worker_queue('doubao_generate')
print(f'队列名称: {queue_name}')
queue_length = redis.llen(queue_name)
print(f'队列长度: {queue_length}')
"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Redis 队列配置正常" -ForegroundColor Green
} else {
    Write-Host "❌ Redis 队列配置失败" -ForegroundColor Red
    exit 1
}

# 3. 提交测试任务
Write-Host "`n[4/5] 提交测试任务到豆包 Worker..." -ForegroundColor Yellow

$testTask = @{
    task_id = "test-doubao-streaming-$(Get-Date -Format 'yyyyMMddHHmmss')"
    type = "doubao_generate"
    payload = @{
        prompt = "生成一个简单的 Python 函数，计算两个数的和"
    }
    meta = @{
        model = "doubao-pro"
    }
}

$taskJson = $testTask | ConvertTo-Json -Depth 10

python -c "
import sys
import json
sys.path.insert(0, 'python_worker')
from worker_config import redis, get_worker_queue

task = json.loads('$taskJson')
queue_name = get_worker_queue('doubao_generate')
redis.lpush(queue_name, json.dumps(task))
print(f'任务已推入队列: {queue_name}')
print(f'任务 ID: {task[\"task_id\"]}')
"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 测试任务已提交" -ForegroundColor Green
} else {
    Write-Host "❌ 任务提交失败" -ForegroundColor Red
    exit 1
}

# 4. 监控任务执行
Write-Host "`n[5/5] 监控任务执行（请观察前端是否有流式输出）..." -ForegroundColor Yellow
Write-Host "⏳ 等待任务处理完成..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# 5. 检查结果
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  测试结果总结" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "请检查以下内容：" -ForegroundColor White
Write-Host "1. ✅ 前端 Webview 是否显示流式输出（分析、规划、代码生成等步骤）" -ForegroundColor White
Write-Host "2. ✅ 每个步骤是否有实时内容更新（而不是等待全部完成后才显示）" -ForegroundColor White
Write-Host "3. ✅ 最终结果是否正确显示生成的代码" -ForegroundColor White
Write-Host "4. ✅ FileOps 是否正确执行（文件是否生成）" -ForegroundColor White

Write-Host "`n如果前端没有输出，请检查：" -ForegroundColor Yellow
Write-Host "- 豆包 Worker 控制台是否有错误日志" -ForegroundColor Yellow
Write-Host "- Node API 是否正确转发 WebSocket 消息" -ForegroundColor Yellow
Write-Host "- 前端 Webview 是否正确处理 stream_chunk 事件" -ForegroundColor Yellow

Write-Host "`n测试完成！`n" -ForegroundColor Green
