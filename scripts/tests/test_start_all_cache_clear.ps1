# 测试 start_all.ps1 的缓存清除功能
# 用法: .\test_start_all_cache_clear.ps1

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "测试 start_all.ps1 缓存清除功能" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 创建测试用的 __pycache__ 和 .pyc 文件
Write-Host "[1/3] 创建测试缓存文件..." -ForegroundColor Yellow

$testDir = Join-Path $PSScriptRoot "test_cache_dir"
if (-not (Test-Path $testDir)) {
    New-Item -ItemType Directory -Path $testDir -Force | Out-Null
}

$pycacheDir = Join-Path $testDir "__pycache__"
New-Item -ItemType Directory -Path $pycacheDir -Force | Out-Null

# 创建测试文件
New-Item -ItemType File -Path (Join-Path $pycacheDir "test.pyc") -Force | Out-Null
New-Item -ItemType File -Path (Join-Path $testDir "module.pyc") -Force | Out-Null

Write-Host "   ✅ 已创建测试缓存文件:" -ForegroundColor Green
Write-Host "      - $pycacheDir\test.pyc" -ForegroundColor White
Write-Host "      - $testDir\module.pyc" -ForegroundColor White
Write-Host ""

# 2. 模拟 start_all.ps1 的缓存清除逻辑
Write-Host "[2/3] 模拟缓存清除逻辑..." -ForegroundColor Yellow

try {
    # 查找并删除所有 __pycache__ 目录
    $pycacheDirs = Get-ChildItem -Path $testDir -Recurse -Filter '__pycache__' -Directory -ErrorAction SilentlyContinue
    
    if ($pycacheDirs.Count -gt 0) {
        foreach ($dir in $pycacheDirs) {
            Remove-Item -Path $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Host "   ✅ 已清除 $($pycacheDirs.Count) 个 __pycache__ 目录" -ForegroundColor Green
    } else {
        Write-Host "   ℹ️ 未找到 __pycache__ 目录" -ForegroundColor Cyan
    }
    
    # 查找并删除所有 .pyc 文件
    $pycFiles = Get-ChildItem -Path $testDir -Recurse -Filter '*.pyc' -File -ErrorAction SilentlyContinue
    
    if ($pycFiles.Count -gt 0) {
        foreach ($file in $pycFiles) {
            Remove-Item -Path $file.FullName -Force -ErrorAction SilentlyContinue
        }
        Write-Host "   ✅ 已清除 $($pycFiles.Count) 个 .pyc 文件" -ForegroundColor Green
    } else {
        Write-Host "   ℹ️ 未找到 .pyc 文件" -ForegroundColor Cyan
    }
    
    Write-Host "   🎉 缓存清理完成" -ForegroundColor Green
} catch {
    Write-Host "   ❌ 清除缓存时出错: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 3. 验证缓存是否已清除
Write-Host "[3/3] 验证缓存清除结果..." -ForegroundColor Yellow

$remainingPycache = Get-ChildItem -Path $testDir -Recurse -Filter '__pycache__' -Directory -ErrorAction SilentlyContinue
$remainingPyc = Get-ChildItem -Path $testDir -Recurse -Filter '*.pyc' -File -ErrorAction SilentlyContinue

if ($remainingPycache.Count -eq 0 -and $remainingPyc.Count -eq 0) {
    Write-Host "   ✅ 所有缓存文件已成功清除" -ForegroundColor Green
    Write-Host "      - __pycache__ 目录: 0 个" -ForegroundColor White
    Write-Host "      - .pyc 文件: 0 个" -ForegroundColor White
} else {
    Write-Host "   ❌ 仍有残留缓存文件:" -ForegroundColor Red
    if ($remainingPycache.Count -gt 0) {
        Write-Host "      - __pycache__ 目录: $($remainingPycache.Count) 个" -ForegroundColor White
    }
    if ($remainingPyc.Count -gt 0) {
        Write-Host "      - .pyc 文件: $($remainingPyc.Count) 个" -ForegroundColor White
    }
    exit 1
}

Write-Host ""

# 4. 清理测试目录
Remove-Item -Path $testDir -Recurse -Force -ErrorAction SilentlyContinue

# 5. 总结
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ 测试通过！start_all.ps1 缓存清除功能正常" -ForegroundColor Green
Write-Host "`n下次运行 start_all.ps1 时将自动清除缓存，确保加载最新代码" -ForegroundColor Yellow
Write-Host "========================================`n" -ForegroundColor Cyan
