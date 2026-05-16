# start_local_worker.ps1
# =========================
# Local LLM Worker 启动脚本
# =========================

# 获取脚本所在目录（项目根目录）
$ScriptDir = $PSScriptRoot

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host " AlphaPilot OS - Local LLM Worker v3.0" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 .env 文件是否存在
$envFile = Join-Path $ScriptDir "python_worker\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "❌ 错误：未找到 python_worker\.env 文件" -ForegroundColor Red
    Write-Host " 请确保统一配置中心 .env 文件存在" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ 检测到统一配置中心 .env 文件" -ForegroundColor Green
Write-Host "   配置项将从 .env 文件自动加载：" -ForegroundColor Gray
Write-Host "   - UPSTASH_REDIS_REST_URL (Redis 队列)" -ForegroundColor Cyan
Write-Host "   - LOCAL_LLM_BASE_URL (LM Studio API)" -ForegroundColor Cyan
Write-Host "   - LOCAL_LLM_MODEL (模型名称)" -ForegroundColor Cyan
Write-Host ""

# 设置 Worker 环境变量（仅需要 Worker ID）
$env:WORKER_ID = "local-worker-1"

# 可选：调试模式（使用内存 Redis）
# $env:USE_MEMORY_REDIS = "true"

Write-Host "✅ Worker ID: $env:WORKER_ID" -ForegroundColor Green
Write-Host ""

# 进入 python_worker 目录（使用绝对路径）
$WorkerDir = Join-Path $ScriptDir "python_worker"
Set-Location $WorkerDir

Write-Host "🔧 正在加载 Local LLM Worker 模块..." -ForegroundColor Yellow
Write-Host "   目录: $WorkerDir" -ForegroundColor Gray
Write-Host ""

# 启动 Worker（自动从 .env 读取所有配置）
python -m agents.local_llm.local_worker_v3
