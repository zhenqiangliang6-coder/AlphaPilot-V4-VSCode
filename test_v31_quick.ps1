# AlphaPilot OS v3.1 FileOps 生命周期修复 - 快速验证脚本
# 使用方法: .\test_v31_quick.ps1

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "AlphaPilot OS v3.1 FileOps 修复验证" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 检查虚拟环境
if (-not $env:VIRTUAL_ENV) {
    Write-Host "⚠️  未检测到虚拟环境，正在激活..." -ForegroundColor Yellow
    & d:\Copilot_Alphapilot\Copilot_Alphapilot\.venv_worker\Scripts\Activate.ps1
}

# 运行自动化测试
Write-Host "🚀 运行自动化测试...`n" -ForegroundColor Green
python test_v31_fileops_lifecycle.py

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "`n✅ 所有测试通过！修复成功！" -ForegroundColor Green
    Write-Host "`n下一步操作:" -ForegroundColor Cyan
    Write-Host "1. 重启 Qwen Worker 服务" -ForegroundColor White
    Write-Host "2. 提交新的多文件生成任务" -ForegroundColor White
    Write-Host "3. 观察 docstring_step 是否正常执行" -ForegroundColor White
} else {
    Write-Host "`n❌ 测试失败，请检查错误信息" -ForegroundColor Red
    Write-Host "`n建议操作:" -ForegroundColor Cyan
    Write-Host "1. 查看 V31_FILEOPS_LIFECYCLE_FIX_REPORT.md 了解详情" -ForegroundColor White
    Write-Host "2. 检查修改的文件是否有语法错误" -ForegroundColor White
    Write-Host "3. 联系架构团队寻求支持" -ForegroundColor White
}

Write-Host "`n========================================`n" -ForegroundColor Cyan

exit $exitCode
