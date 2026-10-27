# Qwen Worker v2 测试与启动脚本
# ---------------------------------------------------------
# 用途：快速切换内存模式和云 Redis 模式
# ---------------------------------------------------------

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Qwen Worker v2 测试与启动工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 设置工作目录
$ProjectRoot = "d:\Copilot_Alphapilot\Copilot_Alphapilot"
$PythonExe = "$ProjectRoot\.venv_worker\Scripts\python.exe"
$EnvFile = "$ProjectRoot\python_worker\.env"

# 设置环境变量
$env:WORKER_ID = "qwen-worker-1"

function Show-Menu {
    Write-Host "请选择操作：" -ForegroundColor Yellow
    Write-Host "1. 运行完整诊断测试（云 Redis）" -ForegroundColor Green
    Write-Host "2. 运行完整诊断测试（内存模式）" -ForegroundColor Green
    Write-Host "3. 启动 Worker（云 Redis 模式）" -ForegroundColor Blue
    Write-Host "4. 启动 Worker（内存模式）" -ForegroundColor Blue
    Write-Host "5. 查看当前配置" -ForegroundColor Magenta
    Write-Host "6. 退出" -ForegroundColor Red
    Write-Host ""
}

function Test-CloudRedis {
    Write-Host "`n>>> 运行云 Redis 诊断测试..." -ForegroundColor Cyan
    & $PythonExe "$ProjectRoot\python_worker\test_qwen_worker_v2_redis.py" --verbose
}

function Test-MemoryMode {
    Write-Host "`n>>> 运行内存模式诊断测试..." -ForegroundColor Cyan
    & $PythonExe "$ProjectRoot\python_worker\test_qwen_worker_v2_redis.py" --use-memory --verbose
}

function Start-Worker {
    param(
        [string]$Mode
    )
    
    if ($Mode -eq "memory") {
        Write-Host "`n>>> 使用内存模式启动 Worker..." -ForegroundColor Cyan
        Write-Host "⚠️  注意：内存模式仅用于调试，重启后数据会丢失" -ForegroundColor Yellow
        
        # 临时设置环境变量
        $originalContent = Get-Content $EnvFile -Raw
        $newContent = $originalContent + "`nUSE_MEMORY_REDIS=true"
        Set-Content $EnvFile -Value $newContent -NoNewline
        
        try {
            & $PythonExe -m python_worker.agents.qwen.qwen_worker_v2
        }
        finally {
            # 恢复原始配置
            Set-Content $EnvFile -Value $originalContent -NoNewline
            Write-Host "`n✅ 已恢复云 Redis 配置" -ForegroundColor Green
        }
    }
    else {
        Write-Host "`n>>> 使用云 Redis 模式启动 Worker..." -ForegroundColor Cyan
        
        # 确保使用云 Redis
        $originalContent = Get-Content $EnvFile -Raw
        $newContent = $originalContent -replace "USE_MEMORY_REDIS=true", "# USE_MEMORY_REDIS=true"
        Set-Content $EnvFile -Value $newContent -NoNewline
        
        try {
            & $PythonExe -m python_worker.agents.qwen.qwen_worker_v2
        }
        finally {
            # 恢复原始配置
            Set-Content $EnvFile -Value $originalContent -NoNewline
        }
    }
}

function Show-Config {
    Write-Host "`n>>> 当前配置：" -ForegroundColor Cyan
    
    # 读取 .env 文件
    $envContent = Get-Content $EnvFile
    
    # 显示关键配置
    $redisUrl = ($envContent | Where-Object { $_ -match "^UPSTASH_REDIS_REST_URL=" }) -replace "^UPSTASH_REDIS_REST_URL=", ""
    $memoryMode = ($envContent | Where-Object { $_ -match "^USE_MEMORY_REDIS=" }) -replace "^USE_MEMORY_REDIS=", ""
    
    Write-Host "  Redis URL: $redisUrl" -ForegroundColor White
    Write-Host "  内存模式: $(if ($memoryMode -eq 'true') { '启用' } else { '禁用' })" -ForegroundColor White
    Write-Host "  Worker ID: $env:WORKER_ID" -ForegroundColor White
    Write-Host ""
}

# 主循环
do {
    Show-Menu
    $choice = Read-Host "请输入选项 (1-6)"
    
    switch ($choice) {
        "1" { Test-CloudRedis }
        "2" { Test-MemoryMode }
        "3" { Start-Worker -Mode "cloud" }
        "4" { Start-Worker -Mode "memory" }
        "5" { Show-Config }
        "6" { 
            Write-Host "`n再见！👋" -ForegroundColor Green
            break 
        }
        default { 
            Write-Host "`n❌ 无效选项，请重新选择" -ForegroundColor Red 
        }
    }
    
    if ($choice -ne "6") {
        Write-Host "`n按回车键继续..." -ForegroundColor Gray
        Read-Host
    }
} while ($choice -ne "6")
