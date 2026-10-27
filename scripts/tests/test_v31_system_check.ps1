# AlphaPilot OS v3.1.1 系统级检查 - 完整验证脚本
# 使用方法: .\test_v31_system_check.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AlphaPilot OS v3.1.1 系统级检查" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allPassed = $true

# 1. 检查工具函数
Write-Host "📋 步骤 1: 检查 file_ops.py 工具函数..." -ForegroundColor Yellow
$fileOpsPath = "python_worker\file_ops.py"
$content = Get-Content $fileOpsPath -Raw

if ($content -match "def filter_valid_file_ops") {
    Write-Host "✅ filter_valid_file_ops() 函数已添加" -ForegroundColor Green
} else {
    Write-Host "❌ filter_valid_file_ops() 函数未找到" -ForegroundColor Red
    $allPassed = $false
}

if ($content -match "def get_python_files") {
    Write-Host "✅ get_python_files() 函数已添加" -ForegroundColor Green
} else {
    Write-Host "❌ get_python_files() 函数未找到" -ForegroundColor Red
    $allPassed = $false
}

Write-Host ""

# 2. 检查 docstring_step.py
Write-Host "📋 步骤 2: 检查 docstring_step.py..." -ForegroundColor Yellow
$docstringPath = "python_worker\agents\qwen\step_executor\docstring_step.py"
$content = Get-Content $docstringPath -Raw

if ($content -match "filter_valid_file_ops") {
    Write-Host "✅ docstring_step.py 使用 filter_valid_file_ops()" -ForegroundColor Green
} else {
    Write-Host "❌ docstring_step.py 未使用 filter_valid_file_ops()" -ForegroundColor Red
    $allPassed = $false
}

if ($content -match "get_python_files") {
    Write-Host "✅ docstring_step.py 使用 get_python_files()" -ForegroundColor Green
} else {
    Write-Host "❌ docstring_step.py 未使用 get_python_files()" -ForegroundColor Red
    $allPassed = $false
}

Write-Host ""

# 3. 检查 refine_step.py
Write-Host "📋 步骤 3: 检查 refine_step.py..." -ForegroundColor Yellow
$refinePath = "python_worker\agents\qwen\step_executor\refine_step.py"
$content = Get-Content $refinePath -Raw

if ($content -match "filter_valid_file_ops") {
    Write-Host "✅ refine_step.py 使用 filter_valid_file_ops()" -ForegroundColor Green
} else {
    Write-Host "❌ refine_step.py 未使用 filter_valid_file_ops()" -ForegroundColor Red
    $allPassed = $false
}

Write-Host ""

# 4. 运行单元测试
Write-Host "🧪 步骤 4: 运行单元测试..." -ForegroundColor Yellow
python test_v31_tool_functions.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 单元测试通过" -ForegroundColor Green
} else {
    Write-Host "❌ 单元测试失败" -ForegroundColor Red
    $allPassed = $false
}

Write-Host ""

# 5. 验证模块导入
Write-Host "🔍 步骤 5: 验证模块导入..." -ForegroundColor Yellow

python -c "from python_worker.file_ops import filter_valid_file_ops, get_python_files; print('✅ file_ops 工具函数导入成功')"
if ($LASTEXITCODE -ne 0) { $allPassed = $false }

python -c "from python_worker.agents.qwen.step_executor.docstring_step import run_docstring_step; print('✅ docstring_step 模块导入成功')"
if ($LASTEXITCODE -ne 0) { $allPassed = $false }

python -c "from python_worker.agents.qwen.step_executor.refine_step import run_refine_step; print('✅ refine_step 模块导入成功')"
if ($LASTEXITCODE -ne 0) { $allPassed = $false }

Write-Host ""

# 6. 总结
Write-Host "========================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "🎉 v3.1.1 系统级检查全部通过！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "下一步操作:" -ForegroundColor Yellow
    Write-Host "1. 重启 Qwen Worker: Stop-AlphaPilot && Start-AlphaPilot" -ForegroundColor White
    Write-Host "2. 重新提交之前的失败任务进行端到端测试" -ForegroundColor White
    Write-Host "3. 查看完整报告: code V31_SYSTEM_WIDE_CHECK_REPORT.md" -ForegroundColor White
} else {
    Write-Host "❌ 部分检查失败，请查看上述错误信息" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    exit 1
}
Write-Host ""
