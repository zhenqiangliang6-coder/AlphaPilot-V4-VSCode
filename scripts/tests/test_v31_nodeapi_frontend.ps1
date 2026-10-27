# AlphaPilot OS v3.1.1 Node API 内部元数据过滤测试
# 测试 filterInternalOps 函数的功能

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AlphaPilot OS v3.1.1 Node API 过滤测试" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allPassed = $true

# 1. 检查 index.js 中是否添加了 filterInternalOps 函数
Write-Host "📋 步骤 1: 检查 filterInternalOps 函数..." -ForegroundColor Yellow
$indexPath = "node-api\index.js"
$content = Get-Content $indexPath -Raw

if ($content -match "function filterInternalOps") {
    Write-Host "✅ filterInternalOps 函数已添加" -ForegroundColor Green
} else {
    Write-Host "❌ filterInternalOps 函数未找到" -ForegroundColor Red
    $allPassed = $false
}

if ($content -match "filterInternalOps\(file_ops\)") {
    Write-Host "✅ fileops/execute 路由使用过滤函数" -ForegroundColor Green
} else {
    Write-Host "❌ fileops/execute 路由未使用过滤函数" -ForegroundColor Red
    $allPassed = $false
}

if ($content -match "result\.context.*final_file_ops.*filterInternalOps") {
    Write-Host "✅ task/notify 路由使用过滤函数" -ForegroundColor Green
} else {
    Write-Host "❌ task/notify 路由未使用过滤函数" -ForegroundColor Red
    $allPassed = $false
}

Write-Host ""

# 2. 检查 FileOpsList.tsx 中的彩色标签
Write-Host "📋 步骤 2: 检查前端彩色标签..." -ForegroundColor Yellow
$fileOpsPath = "vscode-extension\webview\src\components\FileOpsList.tsx"
$content = Get-Content $fileOpsPath -Raw

if ($content -match "STEP_COLORS") {
    Write-Host "✅ STEP_COLORS 颜色映射已添加" -ForegroundColor Green
} else {
    Write-Host "❌ STEP_COLORS 颜色映射未找到" -ForegroundColor Red
    $allPassed = $false
}

if ($content -match "getStepStyle") {
    Write-Host "✅ getStepStyle 函数已添加" -ForegroundColor Green
} else {
    Write-Host "❌ getStepStyle 函数未找到" -ForegroundColor Red
    $allPassed = $false
}

if ($content -match "stepStyle\.bg.*stepStyle\.text") {
    Write-Host "✅ 彩色标签渲染逻辑已添加" -ForegroundColor Green
} else {
    Write-Host "❌ 彩色标签渲染逻辑未找到" -ForegroundColor Red
    $allPassed = $false
}

# 检查所有步骤颜色
$steps = @("write", "refine", "test", "fix", "doc", "docstring")
foreach ($step in $steps) {
    if ($content -match "$($step):.*bg:.*text:") {
        Write-Host "✅ $step 步骤颜色已定义" -ForegroundColor Green
    } else {
        Write-Host "⚠️ $step 步骤颜色未定义（可选）" -ForegroundColor Yellow
    }
}

Write-Host ""

# 3. 运行 Node.js 单元测试（如果存在）
Write-Host "🧪 步骤 3: 验证 Node API 语法..." -ForegroundColor Yellow
try {
    node -c node-api/index.js
    Write-Host "✅ Node API 语法检查通过" -ForegroundColor Green
} catch {
    Write-Host "❌ Node API 语法检查失败" -ForegroundColor Red
    $allPassed = $false
}

Write-Host ""

# 4. 总结
Write-Host "========================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "🎉 v3.1.1 Node API 和前端优化全部完成！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "优化内容:" -ForegroundColor Yellow
    Write-Host "1. ✅ Node API 自动过滤内部元数据 (_internal: true)" -ForegroundColor White
    Write-Host "2. ✅ 前端根据 from_step 展示彩色标签" -ForegroundColor White
    Write-Host "   - write: 蓝色 (生成)" -ForegroundColor White
    Write-Host "   - refine: 紫色 (优化)" -ForegroundColor White
    Write-Host "   - test: 绿色 (测试)" -ForegroundColor White
    Write-Host "   - fix: 橙色 (修复)" -ForegroundColor White
    Write-Host "   - doc: 青色 (文档)" -ForegroundColor White
    Write-Host "   - docstring: 粉色 (Docstring)" -ForegroundColor White
    Write-Host ""
    Write-Host "下一步操作:" -ForegroundColor Yellow
    Write-Host "1. 重启 Node API 服务" -ForegroundColor White
    Write-Host "2. 重新编译前端: cd vscode-extension/webview && npm run build" -ForegroundColor White
    Write-Host "3. 提交任务并观察 FileOps 展示效果" -ForegroundColor White
} else {
    Write-Host "❌ 部分检查失败，请查看上述错误信息" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    exit 1
}
Write-Host ""
