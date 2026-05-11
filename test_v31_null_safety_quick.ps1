# AlphaPilot OS v3.1.1 空值保护修复 - 快速验证脚本
# 使用方法: .\test_v31_null_safety_quick.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AlphaPilot OS v3.1.1 空值保护修复验证" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查文件修改
Write-Host "📋 步骤 1: 检查 docstring_step.py 修复..." -ForegroundColor Yellow
$docstringStepPath = "python_worker\agents\qwen\step_executor\docstring_step.py"
$content = Get-Content $docstringStepPath -Raw

if ($content -match "valid_file_ops") {
    Write-Host "✅ docstring_step.py 已包含 valid_file_ops 过滤逻辑" -ForegroundColor Green
} else {
    Write-Host "❌ docstring_step.py 未找到修复代码" -ForegroundColor Red
    exit 1
}

if ($content -match "_internal") {
    Write-Host "✅ docstring_step.py 已包含 _internal 元数据过滤" -ForegroundColor Green
} else {
    Write-Host "❌ docstring_step.py 未找到 _internal 过滤逻辑" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 2. 运行单元测试
Write-Host "🧪 步骤 2: 运行单元测试..." -ForegroundColor Yellow
python test_v31_null_safety.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 单元测试通过" -ForegroundColor Green
} else {
    Write-Host "❌ 单元测试失败" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 3. 验证模块导入
Write-Host "🔍 步骤 3: 验证模块导入..." -ForegroundColor Yellow
python -c "from python_worker.agents.qwen.step_executor.docstring_step import run_docstring_step; print('✅ 模块导入成功')"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 模块导入成功" -ForegroundColor Green
} else {
    Write-Host "❌ 模块导入失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "🎉 v3.1.1 空值保护修复验证完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步操作:" -ForegroundColor Yellow
Write-Host "1. 重启 Qwen Worker: Stop-AlphaPilot && Start-AlphaPilot" -ForegroundColor White
Write-Host "2. 重新提交之前的失败任务进行端到端测试" -ForegroundColor White
Write-Host "3. 查看完整报告: code V31_NULL_SAFETY_FIX_REPORT.md" -ForegroundColor White
Write-Host ""
