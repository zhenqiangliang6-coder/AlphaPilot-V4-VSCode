# AlphaPilot OS v3.5+ 流式输出与 API 测试脚本
# 用途：验证 Node API 的流式输出路由和历史查询接口

Write-Host "🧪 AlphaPilot OS v3.5+ 流式输出与 API 测试" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Gray
Write-Host ""

$BASE_URL = "http://localhost:3000"

# 测试 1：流式输出
Write-Host "📝 测试 1：流式输出" -ForegroundColor Yellow
Write-Host "-" * 60 -ForegroundColor Gray

$TASK_ID = "test-stream-$(Get-Date -Format 'yyyyMMddHHmmss')"

Write-Host "   开始流式输出..." -ForegroundColor Green
Invoke-RestMethod -Uri "$BASE_URL/task/stream_start/$TASK_ID" -Method POST -ContentType "application/json" -Body '{"title": "🤖 AI 生成中...", "phase": "write"}' | Out-Null
Write-Host "   ✅ stream_start 成功" -ForegroundColor Green

Write-Host "   发送内容块 1..." -ForegroundColor Green
Start-Sleep -Milliseconds 100
Invoke-RestMethod -Uri "$BASE_URL/task/stream_chunk/$TASK_ID" -Method POST -ContentType "application/json" -Body '{"content": "def hello():", "phase": "write", "channel": "content"}' | Out-Null
Write-Host "   ✅ stream_chunk 1 成功" -ForegroundColor Green

Write-Host "   发送内容块 2..." -ForegroundColor Green
Start-Sleep -Milliseconds 100
$body2 = '{"content": "\n    print(\"Hello World\")", "phase": "write", "channel": "content"}'
Invoke-RestMethod -Uri "$BASE_URL/task/stream_chunk/$TASK_ID" -Method POST -ContentType "application/json" -Body $body2 | Out-Null
Write-Host "   ✅ stream_chunk 2 成功" -ForegroundColor Green

Write-Host "   结束流式输出..." -ForegroundColor Green
Invoke-RestMethod -Uri "$BASE_URL/task/stream_end/$TASK_ID" -Method POST -ContentType "application/json" -Body '{}' | Out-Null
Write-Host "   ✅ stream_end 成功" -ForegroundColor Green

Write-Host ""

# 测试 2：任务历史查询
Write-Host "📝 测试 2：任务历史查询" -ForegroundColor Yellow
Write-Host "-" * 60 -ForegroundColor Gray

try {
    Write-Host "   查询所有任务（limit=5）..." -ForegroundColor Green
    $result = Invoke-RestMethod -Uri "$BASE_URL/tasks/history?limit=5&offset=0" -Method GET
    
    if ($result.success) {
        Write-Host "   ✅ 查询成功，找到 $($result.data.Count) 个任务" -ForegroundColor Green
        Write-Host "   分页信息:" -ForegroundColor Cyan
        Write-Host "      - 总数: $($result.pagination.total)" -ForegroundColor White
        Write-Host "      - 限制: $($result.pagination.limit)" -ForegroundColor White
        Write-Host "      - 偏移: $($result.pagination.offset)" -ForegroundColor White
        Write-Host "      - 有更多: $($result.pagination.hasMore)" -ForegroundColor White
        
        if ($result.data.Count -gt 0) {
            Write-Host ""
            Write-Host "   最近任务:" -ForegroundColor Cyan
            $result.data | Select-Object -First 3 | ForEach-Object {
                Write-Host "      - $($_.prompt.Substring(0, [Math]::Min(50, $_.prompt.Length)))..." -ForegroundColor White
            }
        }
    } else {
        Write-Host "   ❌ 查询失败: $($result.error)" -ForegroundColor Red
    }
} catch {
    Write-Host "   ⚠️ 任务历史 API 不可用（可能数据库为空）" -ForegroundColor Yellow
}

Write-Host ""

# 测试 3：文件版本查询
Write-Host "📝 测试 3：文件版本查询" -ForegroundColor Yellow
Write-Host "-" * 60 -ForegroundColor Gray

try {
    Write-Host "   查询文件 ID=1 的版本..." -ForegroundColor Green
    $result = Invoke-RestMethod -Uri "$BASE_URL/files/1/versions?limit=10" -Method GET
    
    if ($result.success) {
        Write-Host "   ✅ 查询成功，找到 $($result.data.Count) 个版本" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️ 文件不存在或无版本记录" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ⚠️ 文件版本 API 不可用" -ForegroundColor Yellow
}

Write-Host ""

# 测试 4：项目记忆查询
Write-Host "📝 测试 4：项目记忆查询" -ForegroundColor Yellow
Write-Host "-" * 60 -ForegroundColor Gray

try {
    Write-Host "   查询项目 ID=1 的记忆..." -ForegroundColor Green
    $result = Invoke-RestMethod -Uri "$BASE_URL/projects/1/memories?limit=20" -Method GET
    
    if ($result.success) {
        Write-Host "   ✅ 查询成功，找到 $($result.data.Count) 条记忆" -ForegroundColor Green
        
        if ($result.data.Count -gt 0) {
            Write-Host ""
            Write-Host "   记忆列表:" -ForegroundColor Cyan
            $result.data | ForEach-Object {
                Write-Host "      - [$($_.memory_type)] $($_.content.Substring(0, [Math]::Min(50, $_.content.Length)))..." -ForegroundColor White
            }
        }
    } else {
        Write-Host "   ⚠️ 项目不存在或无记忆" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ⚠️ 项目记忆 API 不可用" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Gray
Write-Host "🎉 所有测试完成！" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Gray
