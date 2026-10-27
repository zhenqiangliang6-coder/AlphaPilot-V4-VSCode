# Local Worker v3.2.3 ASCII 文件树功能 - 快速验证脚本
# 用法: .\test_local_worker_v323_ascii_tree.ps1

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Local Worker v3.2.3 ASCII 文件树功能验证" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 清除 Python 缓存
Write-Host "[1/4] 清除 Python 缓存..." -ForegroundColor Yellow
Get-ChildItem -Path . -Recurse -Filter '__pycache__' -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -Filter '*.pyc' -File | Remove-Item -Force
Write-Host "✅ Python 缓存已清除`n" -ForegroundColor Green

# 2. 运行单元测试
Write-Host "[2/4] 运行单元测试..." -ForegroundColor Yellow
python test_local_worker_ascii_tree.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ 单元测试失败！" -ForegroundColor Red
    exit 1
}
Write-Host "`n✅ 单元测试通过`n" -ForegroundColor Green

# 3. 检查代码修改
Write-Host "[3/4] 检查代码修改..." -ForegroundColor Yellow

$write_step_path = "python_worker\agents\local_llm\step_executor\write_step.py"
$prompts_path = "python_worker\agents\local_llm\step_executor\prompts.py"

# 检查 extract_ascii_tree 函数是否存在
if (Select-String -Path $write_step_path -Pattern "def extract_ascii_tree" -Quiet) {
    Write-Host "✅ write_step.py: extract_ascii_tree 函数已添加" -ForegroundColor Green
} else {
    Write-Host "❌ write_step.py: extract_ascii_tree 函数缺失" -ForegroundColor Red
    exit 1
}

# 检查 FILE_TREE 解析逻辑是否存在
if (Select-String -Path $write_step_path -Pattern "ascii_tree = extract_ascii_tree" -Quiet) {
    Write-Host "✅ write_step.py: ASCII 树解析逻辑已集成" -ForegroundColor Green
} else {
    Write-Host "❌ write_step.py: ASCII 树解析逻辑缺失" -ForegroundColor Red
    exit 1
}

# 检查 write_prompt 是否包含 FILE_TREE 要求
if (Select-String -Path $prompts_path -Pattern "### FILE_TREE" -Quiet) {
    Write-Host "✅ prompts.py: write_prompt 包含 FILE_TREE 要求" -ForegroundColor Green
} else {
    Write-Host "❌ prompts.py: write_prompt 缺少 FILE_TREE 要求" -ForegroundColor Red
    exit 1
}

Write-Host "`n✅ 代码修改检查通过`n" -ForegroundColor Green

# 4. 总结
Write-Host "[4/4] 验证总结" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ 所有检查通过！Local Worker v3.2.3 ASCII 文件树功能就绪！" -ForegroundColor Green
Write-Host "`n下一步操作:" -ForegroundColor Yellow
Write-Host "1. 重启 Local Worker: `$env:WORKER_ID='local-worker-1'; python -m python_worker.agents.local_llm.local_worker_v3" -ForegroundColor White
Write-Host "2. 提交测试任务，观察日志中是否出现 ASCII 文件树" -ForegroundColor White
Write-Host "3. 预期输出: [INFO] 成功提取 ASCII 文件树 (XX 字符)" -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor Cyan
