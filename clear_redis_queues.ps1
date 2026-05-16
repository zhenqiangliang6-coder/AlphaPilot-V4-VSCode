# AlphaPilot Redis队列清理脚本
# 用途: 清空所有队列中的脏数据,避免Worker收到不匹配的任务

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "AlphaPilot Redis队列清理工具" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 加载环境变量
$envPath = "d:\Copilot_Alphapilot\Copilot_Alphapilot\node-api\.env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Item -Path "env:$name" -Value $value
        }
    }
    Write-Host "✅ 环境变量已加载" -ForegroundColor Green
} else {
    Write-Host "❌ .env文件不存在: $envPath" -ForegroundColor Red
    exit 1
}

$upstashUrl = $env:UPSTASH_REDIS_REST_URL
$upstashToken = $env:UPSTASH_REDIS_REST_TOKEN

if (-not $upstashUrl -or -not $upstashToken) {
    Write-Host "❌ Upstash环境变量未配置" -ForegroundColor Red
    Write-Host "   UPSTASH_REDIS_REST_URL: $($upstashUrl ? '已设置' : '未设置')" -ForegroundColor Yellow
    Write-Host "   UPSTASH_REDIS_REST_TOKEN: $($upstashToken ? '已设置' : '未设置')" -ForegroundColor Yellow
    exit 1
}

# 定义要清理的队列
$queues = @(
    "task_queue:qwen",
    "task_queue:deepseek",
    "task_queue:doubao",
    "task_queue:local",
    "task_queue:openai",
    "task_queue:claude",
    "task_queue:gemini"
)

Write-Host "`n🧹 开始清理队列..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`n" -ForegroundColor DarkGray

foreach ($queue in $queues) {
    try {
        # 获取队列长度
        $body = @{command="LLEN";arguments=@($queue)} | ConvertTo-Json -Compress
        Write-Host "DEBUG: LLEN请求 - $body" -ForegroundColor DarkGray
        $result = Invoke-RestMethod -Uri $upstashUrl -Method POST -Headers @{Authorization="Bearer $upstashToken"} -Body $body -ContentType "application/json"
        $length = $result.result
        
        if ($length -gt 0) {
            Write-Host "🗑️  $queue : $length 个任务" -ForegroundColor Yellow
            
            # 清空队列 (使用DEL命令删除整个key)
            $body = @{command="DEL";arguments=@($queue)} | ConvertTo-Json -Compress
            Write-Host "DEBUG: DEL请求 - $body" -ForegroundColor DarkGray
            $delResult = Invoke-RestMethod -Uri $upstashUrl -Method POST -Headers @{Authorization="Bearer $upstashToken"} -Body $body -ContentType "application/json"
            Write-Host "   ✅ 已清空 (删除了 $($delResult.result) 个key)" -ForegroundColor Green
        } else {
            Write-Host "✓ $queue : 空" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "❌ $queue : 清理失败 - $_" -ForegroundColor Red
        Write-Host "   响应: $_.Exception.Response" -ForegroundColor DarkGray
    }
}

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "✅ 队列清理完成!" -ForegroundColor Green
Write-Host "`n提示: 请重新启动所有Worker以确保它们从干净的状态开始监听`n" -ForegroundColor Cyan
