# start_maas_worker.ps1
# =========================
# 腾讯 MaaS (TokenHub) Worker 启动脚本
# =========================

$ScriptDir = $PSScriptRoot

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host " AlphaPilot OS - Tencent MaaS Worker" -ForegroundColor Cyan
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
Write-Host "   - TENCENT_MAAS_API_KEY (腾讯 MaaS 密钥)" -ForegroundColor Cyan
Write-Host "   - TENCENT_MAAS_BASE_URL (OpenAI 兼容端点)" -ForegroundColor Cyan
Write-Host "   - TENCENT_MAAS_MODEL (模型名称，默认 hy4-preview)" -ForegroundColor Cyan
Write-Host ""

$env:WORKER_ID = "maas-worker-1"

Write-Host "✅ Worker ID: $env:WORKER_ID" -ForegroundColor Green
Write-Host ""

$WorkerDir = Join-Path $ScriptDir "python_worker"
Set-Location $WorkerDir

Write-Host "🔧 正在加载 Tencent MaaS Worker 模块..." -ForegroundColor Yellow
Write-Host "   目录: $WorkerDir" -ForegroundColor Gray
Write-Host ""

python -m agents.tencent_maas.maas_worker
