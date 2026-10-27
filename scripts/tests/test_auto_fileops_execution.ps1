# -*- coding: utf-8 -*-
# test_auto_fileops_execution.ps1
# 测试 VS Code 扩展自动执行 FileOps 的完整链路

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "AlphaPilot FileOps 自动执行链路测试" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Node API 是否运行
Write-Host "[1/5] 检查 Node API 状态..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:3000/workspace/set" -Method Post -Body '{"path":"d:\\Copilot_Alphapilot\\Copilot_Alphapilot"}' -ContentType "application/json" -ErrorAction Stop
    Write-Host "PASS: Node API 正常运行" -ForegroundColor Green
} catch {
    Write-Host "FAIL: Node API 未启动" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 检查工作区设置
Write-Host "[2/5] 验证工作区配置..." -ForegroundColor Yellow
$workspacePath = "d:\Copilot_Alphapilot\Copilot_Alphapilot"
$body = @{path=$workspacePath} | ConvertTo-Json
$response = Invoke-RestMethod -Uri "http://localhost:3000/workspace/set" -Method Post -Body $body -ContentType "application/json"

if ($response.status -eq "ok") {
    Write-Host "PASS: 工作区已设置为: $($response.workspace)" -ForegroundColor Green
} else {
    Write-Host "FAIL: 工作区设置失败" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 测试 FileOps 执行
Write-Host "[3/5] 测试 FileOps 执行..." -ForegroundColor Yellow
$testFileOps = @(
    @{op="create"; path="test_auto_hello.py"; content="def greet(name):`n    return f'Hello, {name}!'"},
    @{op="create"; path="test_auto_utils.py"; content="def format_output(text):`n    return f'[INFO] {text}'"}
)

$body = @{file_ops=$testFileOps} | ConvertTo-Json -Depth 10
$response = Invoke-RestMethod -Uri "http://localhost:3000/fileops/execute" -Method Post -Body $body -ContentType "application/json"

if ($response.success) {
    Write-Host "PASS: FileOps 执行成功" -ForegroundColor Green
    Write-Host "   生成文件:" -ForegroundColor Cyan
    foreach ($file in $response.files) {
        Write-Host "      - $($file.path)" -ForegroundColor White
    }
} else {
    Write-Host "FAIL: FileOps 执行失败" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 验证文件存在性
Write-Host "[4/5] 验证文件写入磁盘..." -ForegroundColor Yellow
$testFiles = @("test_auto_hello.py", "test_auto_utils.py")
$allExist = $true

foreach ($file in $testFiles) {
    $fullPath = Join-Path $workspacePath $file
    if (Test-Path $fullPath) {
        Write-Host "PASS: $file 存在" -ForegroundColor Green
    } else {
        Write-Host "FAIL: $file 不存在" -ForegroundColor Red
        $allExist = $false
    }
}
Write-Host ""

# 清理测试文件
Write-Host "[5/5] 清理测试文件..." -ForegroundColor Yellow
foreach ($file in $testFiles) {
    $fullPath = Join-Path $workspacePath $file
    if (Test-Path $fullPath) {
        Remove-Item $fullPath -Force
        Write-Host "   已删除: $file" -ForegroundColor Gray
    }
}
Write-Host ""

# 总结
Write-Host "======================================" -ForegroundColor Cyan
if ($allExist) {
    Write-Host "SUCCESS: 所有测试通过！FileOps 自动执行链路正常工作" -ForegroundColor Green
    Write-Host ""
    Write-Host "下一步操作:" -ForegroundColor Yellow
    Write-Host "1. 重新加载 VS Code 扩展 (Ctrl+Shift+P -> Developer: Reload Window)" -ForegroundColor White
    Write-Host "2. 在 Webview 中提交任务，观察自动执行" -ForegroundColor White
    Write-Host "3. 检查生成的文件是否出现在工作区目录" -ForegroundColor White
} else {
    Write-Host "FAILURE: 部分测试失败，请检查日志" -ForegroundColor Red
}
Write-Host "======================================" -ForegroundColor Cyan



