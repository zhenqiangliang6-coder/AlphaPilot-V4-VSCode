# Local LLM Worker v3.0 执行链路修复验证脚本
# =========================================================
# 用途: 验证 Local LLM Worker v3.0 的执行链路修复是否成功
# 参考: Qwen Worker v2（当前运行最好的 Worker）
# =========================================================

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Local LLM Worker v3.0 执行链路修复验证" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 检查 Python 环境
Write-Host "[1/5] 检查 Python 环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python 版本: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python 未安装或不在 PATH 中" -ForegroundColor Red
    exit 1
}

# 2. 检查 Redis 连接
Write-Host "`n[2/5] 检查 Redis 连接..." -ForegroundColor Yellow
try {
    $redisCheckScript = @"
import redis
r = redis.Redis(host='localhost', port=6379, db=0)
r.ping()
print('Redis 连接正常')
"@
    $redisCheckScript | Out-File -FilePath "check_redis_temp.py" -Encoding UTF8
    python check_redis_temp.py 2>&1 | Out-Null
    Remove-Item "check_redis_temp.py" -ErrorAction SilentlyContinue
    Write-Host "✅ Redis 连接正常" -ForegroundColor Green
} catch {
    Write-Host "⚠️ Redis 连接失败，请确保 Redis 正在运行" -ForegroundColor Yellow
    Remove-Item "check_redis_temp.py" -ErrorAction SilentlyContinue
}

# 3. 检查代码语法
Write-Host "`n[3/5] 检查代码语法..." -ForegroundColor Yellow
$filesToCheck = @(
    "python_worker\agents\local_llm\step_executor\execute_step.py",
    "python_worker\agents\local_llm\step_executor\write_step.py",
    "python_worker\agents\local_llm\step_executor\plan_step.py",
    "python_worker\agents\local_llm\step_executor\analyze_step.py",
    "python_worker\agents\local_llm\step_executor\refine_step.py",
    "python_worker\agents\local_llm\step_executor\test_step.py",
    "python_worker\agents\local_llm\step_executor\fix_step.py",
    "python_worker\agents\local_llm\step_executor\doc_step.py",
    "python_worker\agents\local_llm\step_executor\docstring_step.py",
    "python_worker\agents\local_llm\step_executor\profile_step.py",
    "python_worker\agents\local_llm\local_worker_v3.py"
)

$syntaxError = $false
foreach ($file in $filesToCheck) {
    try {
        python -m py_compile $file 2>&1 | Out-Null
        Write-Host "  ✅ $file" -ForegroundColor Green
    } catch {
        Write-Host "  ❌ $file - 语法错误" -ForegroundColor Red
        $syntaxError = $true
    }
}

if ($syntaxError) {
    Write-Host "`n❌ 发现语法错误，请先修复" -ForegroundColor Red
    exit 1
} else {
    Write-Host "✅ 所有文件语法检查通过" -ForegroundColor Green
}

# 4. 启动 Local LLM Worker（后台运行）
Write-Host "`n[4/5] 启动 Local LLM Worker v3.0..." -ForegroundColor Yellow
Write-Host "提示: Worker 将在后台运行，按 Ctrl+C 停止" -ForegroundColor Gray

$workerProcess = Start-Process -FilePath "python" `
    -ArgumentList "python_worker\agents\local_llm\local_worker_v3.py" `
    -WorkingDirectory (Get-Location) `
    -RedirectStandardOutput "local_worker_output.log" `
    -RedirectStandardError "local_worker_error.log" `
    -PassThru `
    -NoNewWindow

Start-Sleep -Seconds 3

# 检查 Worker 是否启动
if (Get-Process -Id $workerProcess.Id -ErrorAction SilentlyContinue) {
    Write-Host "✅ Local LLM Worker 已启动 (PID: $($workerProcess.Id))" -ForegroundColor Green
    
    # 显示最近的日志
    if (Test-Path "local_worker_output.log") {
        Write-Host "`n--- Worker 启动日志 ---" -ForegroundColor Cyan
        Get-Content "local_worker_output.log" -Tail 10 | ForEach-Object { Write-Host $_ }
        Write-Host "--- 日志结束 ---`n" -ForegroundColor Cyan
    }
} else {
    Write-Host "❌ Local LLM Worker 启动失败" -ForegroundColor Red
    if (Test-Path "local_worker_error.log") {
        Write-Host "`n错误日志:" -ForegroundColor Red
        Get-Content "local_worker_error.log" | ForEach-Object { Write-Host $_ }
    }
    exit 1
}

# 5. 提交测试任务
Write-Host "`n[5/5] 提交测试任务..." -ForegroundColor Yellow

# 创建测试任务脚本
$testTaskScript = @"
import sys
import os
import json
import time

# 添加 python_worker 到路径
sys.path.insert(0, os.path.abspath('python_worker'))

from worker_config import create_redis_client, get_worker_queue

redis = create_redis_client()
queue_name = get_worker_queue("local_generate")

# 构建测试任务
task = {
    "task_id": f"test_local_llm_{int(time.time())}",
    "task_type": "local_generate",
    "payload": {
        "prompt": "写一个 Python 排序函数，支持升序和降序"
    },
    "meta": {
        "retry_count": 0,
        "started_at": int(time.time() * 1000)
    }
}

# 推送到队列
redis.lpush(queue_name, json.dumps(task))
print(f"✅ 测试任务已提交到队列: {queue_name}")
print(f"   Task ID: {task['task_id']}")
print(f"   Prompt: {task['payload']['prompt']}")
"@

# 保存并执行测试任务脚本
$testTaskScript | Out-File -FilePath "submit_test_task_temp.py" -Encoding UTF8
python submit_test_task_temp.py

# 清理临时文件
Remove-Item "submit_test_task_temp.py" -ErrorAction SilentlyContinue

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "验证完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`n📋 下一步操作:" -ForegroundColor Yellow
Write-Host "1. 观察 Worker 日志输出 (local_worker_output.log)" -ForegroundColor White
Write-Host "2. 检查是否生成 FileOps" -ForegroundColor White
Write-Host "3. 在 VSCode 中重新加载窗口并测试前端展示" -ForegroundColor White
Write-Host "4. 停止 Worker: Stop-Process -Id $($workerProcess.Id)`n" -ForegroundColor White

Write-Host "💡 提示: 如果看到以下输出，说明修复成功：" -ForegroundColor Green
Write-Host "   - 🧠 Local LLM Worker v3.0 决策：" -ForegroundColor Gray
Write-Host "   - 意图: write_code / simple_code" -ForegroundColor Gray
Write-Host "   - 执行链: write → test" -ForegroundColor Gray
Write-Host "   - ✅ Local LLM write_step 生成 X 个 FileOp" -ForegroundColor Gray
Write-Host "   - 📡 正在通知 Node.js: ..." -ForegroundColor Gray
