# AlphaPilot OS v3.1 - Worker 升级验证 PowerShell 脚本
# 测试 DeepSeek Worker v3.0 和 Doubao Worker v3.0

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "AlphaPilot OS v3.1 - Worker 升级验证" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 检查 Python 环境
Write-Host "🔍 检查 Python 环境..." -ForegroundColor Yellow
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "❌ 未找到 Python，请先安装 Python 3.8+" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Python 已安装: $($pythonCmd.Version)`n" -ForegroundColor Green

# 检查 Redis 连接
Write-Host "🔍 检查 Redis 连接..." -ForegroundColor Yellow
try {
    $redisCheck = python -c "from python_worker.worker_config import redis; print('OK' if redis.ping() else 'FAIL')" 2>&1
    if ($redisCheck -eq "OK") {
        Write-Host "✅ Redis 连接正常`n" -ForegroundColor Green
    } else {
        Write-Host "❌ Redis 连接失败: $redisCheck`n" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Redis 检查失败: $_`n" -ForegroundColor Red
    exit 1
}

# 显示测试选项
Write-Host "请选择测试类型:" -ForegroundColor Cyan
Write-Host "  1. 测试 DeepSeek Worker v3.0" -ForegroundColor White
Write-Host "  2. 测试 Doubao Worker v3.0" -ForegroundColor White
Write-Host "  3. 测试 Doubao Worker v3.0 - 多模态任务" -ForegroundColor White
Write-Host "  4. 全部测试" -ForegroundColor White
Write-Host "  0. 退出`n" -ForegroundColor White

$choice = Read-Host "请输入选项 (0-4)"

switch ($choice) {
    "1" {
        Write-Host "`n🧪 启动 DeepSeek Worker v3.0 测试..." -ForegroundColor Yellow
        python test_worker_v3_upgrade.py
    }
    "2" {
        Write-Host "`n🧪 启动 Doubao Worker v3.0 测试..." -ForegroundColor Yellow
        python test_worker_v3_upgrade.py
    }
    "3" {
        Write-Host "`n🧪 启动 Doubao Worker v3.0 多模态测试..." -ForegroundColor Yellow
        python test_worker_v3_upgrade.py
    }
    "4" {
        Write-Host "`n🧪 启动全部测试..." -ForegroundColor Yellow
        python test_worker_v3_upgrade.py
    }
    "0" {
        Write-Host "`n👋 退出测试`n" -ForegroundColor Cyan
        exit 0
    }
    default {
        Write-Host "`n❌ 无效选项`n" -ForegroundColor Red
        exit 1
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "测试完成！" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
