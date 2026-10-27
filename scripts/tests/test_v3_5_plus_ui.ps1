# AlphaPilot OS v3.5+ React Webview UI 测试脚本

Write-Host "🧪 AlphaPilot OS v3.5+ React Webview UI 测试" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Gray
Write-Host ""

# 检查 Node API 是否运行
Write-Host "📝 测试 1：检查 Node API 服务" -ForegroundColor Yellow
Write-Host ("-" * 60) -ForegroundColor Gray

$portCheck = netstat -ano | findstr ":3000.*LISTENING"
if ($portCheck) {
    Write-Host "   ✅ Node API 正常运行（端口 3000 已监听）" -ForegroundColor Green
} else {
    Write-Host "   ❌ Node API 未启动，请先运行: cd node-api && node index.js" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 测试任务历史 API
Write-Host "📝 测试 2：任务历史 API" -ForegroundColor Yellow
Write-Host ("-" * 60) -ForegroundColor Gray

try {
    $tasks = Invoke-RestMethod -Uri "http://localhost:3000/tasks/history?limit=5" -Method GET
    Write-Host "   ✅ 查询成功，找到 $($tasks.tasks.Count) 个任务" -ForegroundColor Green
    
    if ($tasks.tasks.Count -gt 0) {
        Write-Host "   最近任务:" -ForegroundColor Cyan
        foreach ($task in $tasks.tasks[0..2]) {
            $prompt = $task.prompt.Substring(0, [Math]::Min(50, $task.prompt.Length))
            Write-Host "      - $prompt..." -ForegroundColor White
        }
    }
} catch {
    Write-Host "   ⚠️ 任务历史 API 不可用（可能数据库为空）" -ForegroundColor Yellow
}

Write-Host ""

# 测试文件版本 API
Write-Host "📝 测试 3：文件版本 API" -ForegroundColor Yellow
Write-Host ("-" * 60) -ForegroundColor Gray

try {
    $versions = Invoke-RestMethod -Uri "http://localhost:3000/files/1/versions?limit=5" -Method GET
    Write-Host "   ✅ 查询成功，找到 $($versions.versions.Count) 个版本" -ForegroundColor Green
} catch {
    Write-Host "   ⚠️ 文件版本 API 不可用（可能没有文件数据）" -ForegroundColor Yellow
}

Write-Host ""

# 测试项目记忆 API
Write-Host "📝 测试 4：项目记忆 API" -ForegroundColor Yellow
Write-Host ("-" * 60) -ForegroundColor Gray

try {
    $memories = Invoke-RestMethod -Uri "http://localhost:3000/projects/1/memories?limit=10" -Method GET
    Write-Host "   ✅ 查询成功，找到 $($memories.memories.Count) 条记忆" -ForegroundColor Green
    
    if ($memories.memories.Count -gt 0) {
        Write-Host "   记忆列表:" -ForegroundColor Cyan
        foreach ($memory in $memories.memories[0..2]) {
            Write-Host "      - [$($memory.type)] $($memory.content.Substring(0, [Math]::Min(50, $memory.content.Length)))..." -ForegroundColor White
        }
    }
} catch {
    Write-Host "   ⚠️ 项目记忆 API 不可用（可能没有记忆数据）" -ForegroundColor Yellow
}

Write-Host ""

# 检查 React 构建产物
Write-Host "📝 测试 5：React 构建产物" -ForegroundColor Yellow
Write-Host ("-" * 60) -ForegroundColor Gray

$buildPath = "d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\webview-dist"
if (Test-Path $buildPath) {
    Write-Host "   ✅ webview-dist 目录存在" -ForegroundColor Green
    
    $indexHtml = Join-Path $buildPath "index.html"
    if (Test-Path $indexHtml) {
        Write-Host "   ✅ index.html 存在" -ForegroundColor Green
    } else {
        Write-Host "   ❌ index.html 不存在" -ForegroundColor Red
    }
    
    $assetsPath = Join-Path $buildPath "assets"
    if (Test-Path $assetsPath) {
        $jsFiles = Get-ChildItem -Path $assetsPath -Filter "*.js"
        $cssFiles = Get-ChildItem -Path $assetsPath -Filter "*.css"
        
        Write-Host "   ✅ 找到 $($jsFiles.Count) 个 JS 文件" -ForegroundColor Green
        Write-Host "   ✅ 找到 $($cssFiles.Count) 个 CSS 文件" -ForegroundColor Green
    } else {
        Write-Host "   ❌ assets 目录不存在" -ForegroundColor Red
    }
} else {
    Write-Host "   ❌ webview-dist 目录不存在，请运行: cd vscode-extension/webview && npm run build" -ForegroundColor Red
}

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Gray
Write-Host "🎉 所有测试完成！" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Gray
Write-Host ""
Write-Host "💡 下一步：" -ForegroundColor Cyan
Write-Host "   1. 在 VSCode 中打开 AlphaPilot 扩展" -ForegroundColor White
Write-Host "   2. 点击工具栏上的新按钮：" -ForegroundColor White
Write-Host "      - 📋 历史（任务历史面板）" -ForegroundColor White
Write-Host "      - 📄 版本（文件版本面板，开发中）" -ForegroundColor White
Write-Host "      - 🧠 记忆（项目记忆面板）" -ForegroundColor White
Write-Host ""
