# test_dynamic_workspace.ps1
# 测试 VS Code 扩展动态工作区设置功能

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "AlphaPilot 动态工作区测试" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 步骤 1: 创建测试目录
$testDir = "C:\Temp\AlphaPilot_Test_Workspace"
Write-Host "[1/4] 创建测试工作区目录..." -ForegroundColor Yellow
if (!(Test-Path $testDir)) {
    New-Item -ItemType Directory -Path $testDir -Force | Out-Null
    Write-Host "✅ 已创建: $testDir" -ForegroundColor Green
} else {
    Write-Host "ℹ️  目录已存在: $testDir" -ForegroundColor Cyan
}
Write-Host ""

# 步骤 2: 提示用户在 VS Code 中打开该目录
Write-Host "[2/4] 请在 VS Code 中执行以下操作:" -ForegroundColor Yellow
Write-Host "   1. File → Open Folder" -ForegroundColor White
Write-Host "   2. 选择目录: $testDir" -ForegroundColor White
Write-Host "   3. 按 Ctrl+Shift+P → Developer: Reload Window" -ForegroundColor White
Write-Host ""
Write-Host "   完成后按任意键继续..." -ForegroundColor Cyan
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
Write-Host ""

# 步骤 3: 检查工作区设置
Write-Host "[3/4] 检查工作区配置..." -ForegroundColor Yellow
try {
    # 尝试从 Node API 获取当前工作区（需要添加一个查询接口）
    Write-Host "ℹ️  请观察 Node API 终端输出，确认工作区已更新为:" -ForegroundColor Cyan
    Write-Host "   $testDir" -ForegroundColor White
    Write-Host ""
    Write-Host "预期日志:" -ForegroundColor Gray
    Write-Host "[FileOpsHandler] ✅ 工作区已更新: $testDir" -ForegroundColor Gray
} catch {
    Write-Host "⚠️  无法自动验证，请手动检查 Node API 日志" -ForegroundColor Yellow
}
Write-Host ""

# 步骤 4: 测试 FileOps 执行
Write-Host "[4/4] 测试 FileOps 执行..." -ForegroundColor Yellow
$testFileOps = @(
    @{op="create"; path="test_dynamic_workspace.txt"; content="这个文件应该出现在你当前打开的 VS Code 工作区目录中"}
)

$body = @{file_ops=$testFileOps} | ConvertTo-Json -Depth 10
try {
    $response = Invoke-RestMethod -Uri "http://localhost:3000/fileops/execute" -Method Post -Body $body -ContentType "application/json"
    
    if ($response.success) {
        Write-Host "✅ FileOps 执行成功" -ForegroundColor Green
        
        # 检查文件是否出现在测试目录
        $expectedPath = Join-Path $testDir "test_dynamic_workspace.txt"
        if (Test-Path $expectedPath) {
            Write-Host "✅ 文件已正确写入测试目录: $expectedPath" -ForegroundColor Green
            Write-Host "   内容: $(Get-Content $expectedPath -Raw)" -ForegroundColor Gray
            
            # 清理测试文件
            Remove-Item $expectedPath -Force
            Write-Host "   已清理测试文件" -ForegroundColor Gray
        } else {
            Write-Host "❌ 文件未出现在测试目录，请检查工作区设置" -ForegroundColor Red
            Write-Host "   预期路径: $expectedPath" -ForegroundColor Yellow
        }
    } else {
        Write-Host "❌ FileOps 执行失败: $($response.error)" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ 请求失败: $_" -ForegroundColor Red
}
Write-Host ""

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "测试完成！" -ForegroundColor Cyan
Write-Host ""
Write-Host "关键验证点:" -ForegroundColor Yellow
Write-Host "1. VS Code 打开的文件夹 = Node API 工作区" -ForegroundColor White
Write-Host "2. FileOps 生成的文件出现在该文件夹" -ForegroundColor White
Write-Host "3. 不会污染 AlphaPilot 项目本身" -ForegroundColor White
Write-Host "======================================" -ForegroundColor Cyan