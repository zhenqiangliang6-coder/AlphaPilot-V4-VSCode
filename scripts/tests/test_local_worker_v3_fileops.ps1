# Local Worker v3.0 FileOps 修复快速验证脚本
# 用法: .\test_local_worker_v3_fileops.ps1

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Local Worker v3.0 FileOps 修复验证" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 检查文件是否已修改
Write-Host "[1/3] 检查 write_step.py 是否已修复..." -ForegroundColor Yellow
$file_path = "python_worker\agents\local_llm\step_executor\write_step.py"
$content = Get-Content $file_path -Raw

if ($content -match 'action="create"') {
    Write-Host "✅ write_step.py 已修复 (使用 action=`"create`")" -ForegroundColor Green
} elseif ($content -match 'type="create"') {
    Write-Host "❌ write_step.py 未修复 (仍使用 type=`"create`")" -ForegroundColor Red
    exit 1
} else {
    Write-Host "⚠️ 无法检测到 create_file_op 调用" -ForegroundColor Yellow
}

# 2. 运行单元测试
Write-Host "`n[2/3] 运行单元测试..." -ForegroundColor Yellow
python test_local_worker_fileops_fix.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 单元测试通过" -ForegroundColor Green
} else {
    Write-Host "❌ 单元测试失败" -ForegroundColor Red
    exit 1
}

# 3. 提示下一步
Write-Host "`n[3/3] 端到端测试准备就绪" -ForegroundColor Yellow
Write-Host "`n📋 下一步操作:" -ForegroundColor Cyan
Write-Host "1. 启动 Local Worker:" -ForegroundColor White
Write-Host "   `$env:WORKER_ID='local-worker-1'" -ForegroundColor Gray
Write-Host "   python -m python_worker.agents.local_llm.local_worker_v3" -ForegroundColor Gray
Write-Host "`n2. 提交任务生成多文件（通过前端或 Node API）" -ForegroundColor White
Write-Host "`n3. 观察日志是否出现:" -ForegroundColor White
Write-Host "   [SUCCESS] write_step 生成 X 个 FileOps" -ForegroundColor Green
Write-Host "   ✅ context[`"final_file_ops`"] 包含 X 个 FileOp" -ForegroundColor Green
Write-Host "`n========================================`n" -ForegroundColor Cyan
