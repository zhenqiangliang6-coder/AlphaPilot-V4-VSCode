# ================================
# AlphaPilot OS v2.8 双云 Redis 架构验证脚本
# ================================

Write-Host "🚀 AlphaPilot OS v2.8 双云 Redis 架构验证" -ForegroundColor Green
Write-Host ""

# -------------------------------
# 1. 检查 Node API 依赖
# -------------------------------
Write-Host "1️⃣ 检查 Node API 依赖..." -ForegroundColor Yellow

$ioredisPath = Join-Path $PSScriptRoot "node-api\node_modules\ioredis"
if (Test-Path $ioredisPath) {
    Write-Host "   ✅ ioredis 已安装" -ForegroundColor Green
} else {
    Write-Host "   ❌ ioredis 未安装，正在安装..." -ForegroundColor Yellow
    Set-Location (Join-Path $PSScriptRoot "node-api")
    npm install ioredis
    Set-Location $PSScriptRoot
}

# -------------------------------
# 2. 检查配置文件
# -------------------------------
Write-Host ""
Write-Host "2️⃣ 检查配置文件..." -ForegroundColor Yellow

$envFile = Join-Path $PSScriptRoot "node-api\.env"
if (Test-Path $envFile) {
    Write-Host "   ✅ node-api/.env 存在" -ForegroundColor Green
    
    $content = Get-Content $envFile -Raw
    if ($content -match "TAIR_HOST=") {
        Write-Host "   ✅ 阿里云 Tair 配置已添加" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  阿里云 Tair 配置缺失" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ❌ node-api/.env 不存在" -ForegroundColor Red
}

$workerEnvFile = Join-Path $PSScriptRoot "python_worker\.env"
if (Test-Path $workerEnvFile) {
    Write-Host "   ✅ python_worker/.env 存在" -ForegroundColor Green
} else {
    Write-Host "   ❌ python_worker/.env 不存在" -ForegroundColor Red
}

# -------------------------------
# 3. 重启服务
# -------------------------------
Write-Host ""
Write-Host "3️⃣ 重启服务..." -ForegroundColor Yellow

Write-Host "   🔄 请先手动停止现有的 Node API 和 Workers" -ForegroundColor Cyan
Write-Host "   🔄 然后运行 start_all.ps1 重新启动" -ForegroundColor Cyan

# -------------------------------
# 4. 验证步骤
# -------------------------------
Write-Host ""
Write-Host "📋 验证步骤:" -ForegroundColor Magenta
Write-Host ""
Write-Host "   1. 启动 Node API，检查日志是否显示:" -ForegroundColor White
Write-Host "      ✅ 阿里云 Tair Redis 已配置（国内模型）" -ForegroundColor Gray
Write-Host ""
Write-Host "   2. 启动 Qwen Worker，检查日志是否显示:" -ForegroundColor White
Write-Host "      ✅ 使用 Upstash Redis（国际模型/全球 CDN）" -ForegroundColor Gray
Write-Host "      💡 Worker 类型: qwen" -ForegroundColor Gray
Write-Host ""
Write-Host "   3. 启动 DeepSeek Worker，检查日志是否显示:" -ForegroundColor White
Write-Host "      ✅ 使用阿里云 Tair Redis（国内模型/国内加速）" -ForegroundColor Gray
Write-Host "      💡 Worker 类型: deepseek" -ForegroundColor Gray
Write-Host ""
Write-Host "   4. 启动 Doubao Worker，检查日志是否显示:" -ForegroundColor White
Write-Host "      ✅ 使用阿里云 Tair Redis（国内模型/国内加速）" -ForegroundColor Gray
Write-Host "      💡 Worker 类型: doubao" -ForegroundColor Gray
Write-Host ""

Write-Host "💡 提示:" -ForegroundColor Cyan
Write-Host "   - 所有 Worker 应该根据类型连接到不同的 Redis" -ForegroundColor White
Write-Host "   - Qwen → Upstash, DeepSeek/Doubao → 阿里云 Tair" -ForegroundColor White
Write-Host ""

Write-Host "✅ 验证脚本执行完成!" -ForegroundColor Green
Write-Host ""