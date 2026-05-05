# Qwen Worker 快速测试脚本
# ---------------------------------------------------------
# 用途：一键启动 Worker 并运行测试

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Qwen Worker 快速测试" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 设置工作目录
$ProjectRoot = "d:\Copilot_Alphapilot\Copilot_Alphapilot"
$PythonExe = "$ProjectRoot\.venv_worker\Scripts\python.exe"

# 设置环境变量
$env:WORKER_ID = "qwen-worker-1"

Write-Host "步骤 1: 检查配置..." -ForegroundColor Yellow

# 检查 .env 文件
$EnvFile = "$ProjectRoot\python_worker\.env"
if (Test-Path $EnvFile) {
    Write-Host "✅ .env 文件存在" -ForegroundColor Green
    
    # 检查 USE_MEMORY_REDIS
    $envContent = Get-Content $EnvFile
    $memoryMode = ($envContent | Where-Object { $_ -match "^USE_MEMORY_REDIS=" }) -replace "^USE_MEMORY_REDIS=", ""
    
    if ($memoryMode -eq "true") {
        Write-Host "⚠️  当前使用内存模式" -ForegroundColor Yellow
        Write-Host "   提示: 内存模式仅用于调试，不支持多 Worker" -ForegroundColor Gray
    } else {
        Write-Host "✅ 当前使用云 Redis 模式" -ForegroundColor Green
    }
} else {
    Write-Host "❌ .env 文件不存在" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "步骤 2: 选择测试模式..." -ForegroundColor Yellow
Write-Host "1. 简单测试（推荐）- 提交一个任务并等待结果" -ForegroundColor White
Write-Host "2. 启动 Worker - 只启动 Worker，手动提交任务" -ForegroundColor White
Write-Host "3. 完整诊断 - 运行完整的 Redis 连接测试" -ForegroundColor White
Write-Host ""

$choice = Read-Host "请选择 (1-3)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host ">>> 运行简单测试..." -ForegroundColor Cyan
        Write-Host ""
        
        # 先运行环境检查
        & $PythonExe "$ProjectRoot\python_worker\test_qwen_worker_simple.py"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "✅ 测试通过！Worker 工作正常" -ForegroundColor Green
            Write-Host ""
            Write-Host "是否启动 Worker 继续监听新任务？(Y/N)" -ForegroundColor Yellow
            $startWorker = Read-Host
            
            if ($startWorker -eq "Y" -or $startWorker -eq "y") {
                Write-Host ""
                Write-Host ">>> 启动 qwen-worker-1..." -ForegroundColor Cyan
                Write-Host "按 Ctrl+C 停止 Worker" -ForegroundColor Gray
                Write-Host ""
                
                & $PythonExe -m python_worker.agents.qwen.qwen_worker_v2
            }
        } else {
            Write-Host ""
            Write-Host "❌ 测试失败，请检查上述错误信息" -ForegroundColor Red
        }
    }
    
    "2" {
        Write-Host ""
        Write-Host ">>> 启动 qwen-worker-1..." -ForegroundColor Cyan
        Write-Host "按 Ctrl+C 停止 Worker" -ForegroundColor Gray
        Write-Host ""
        
        & $PythonExe -m python_worker.agents.qwen.qwen_worker_v2
    }
    
    "3" {
        Write-Host ""
        Write-Host ">>> 运行完整诊断测试..." -ForegroundColor Cyan
        Write-Host ""
        
        & $PythonExe "$ProjectRoot\python_worker\test_qwen_worker_v2_redis.py" --verbose
    }
    
    default {
        Write-Host ""
        Write-Host "❌ 无效选项" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "测试完成！" -ForegroundColor Green
