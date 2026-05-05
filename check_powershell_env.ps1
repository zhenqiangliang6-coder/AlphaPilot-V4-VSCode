# ================================
# PowerShell 环境检查脚本
# ================================

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "PowerShell 环境检查" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 1. PowerShell 版本
Write-Host "1️⃣ PowerShell 版本信息:" -ForegroundColor Yellow
Write-Host "   版本: $($PSVersionTable.PSVersion.ToString())" -ForegroundColor White
Write-Host "   引擎: $($PSVersionTable.PSEdition)" -ForegroundColor White

if ($PSVersionTable.PSVersion.Major -ge 7) {
    Write-Host "   ✅ 使用 PowerShell 7+ (推荐)" -ForegroundColor Green
} else {
    Write-Host "   ⚠️ 使用 Windows PowerShell (建议升级到 PowerShell 7+)" -ForegroundColor Yellow
}

Write-Host ""

# 2. 编码设置
Write-Host "2️⃣ 编码设置:" -ForegroundColor Yellow
Write-Host "   输出编码: $([Console]::OutputEncoding.WebName)" -ForegroundColor White

if ([Console]::OutputEncoding.WebName -eq "utf-8") {
    Write-Host "   ✅ UTF-8 编码已启用" -ForegroundColor Green
} else {
    Write-Host "   ⚠️ 建议设置为 UTF-8" -ForegroundColor Yellow
    Write-Host "   运行: [Console]::OutputEncoding = [System.Text.Encoding]::UTF8" -ForegroundColor Gray
}

Write-Host ""

# 3. Python 环境
Write-Host "3️⃣ Python 环境:" -ForegroundColor Yellow

$pythonPaths = @(
    "$PSScriptRoot\.venv_worker\Scripts\python.exe",
    "$PSScriptRoot\python_worker\.venv\Scripts\python.exe",
    "$PSScriptRoot\.venv\Scripts\python.exe"
)

$foundVenv = $false
foreach ($path in $pythonPaths) {
    if (Test-Path $path) {
        Write-Host "   ✅ 找到虚拟环境: $path" -ForegroundColor Green
        
        # 检查 Python 版本
        try {
            $version = & $path --version 2>&1
            Write-Host "   Python 版本: $version" -ForegroundColor White
        } catch {
            Write-Host "   ⚠️ 无法获取 Python 版本" -ForegroundColor Yellow
        }
        
        $foundVenv = $true
        break
    }
}

if (-not $foundVenv) {
    Write-Host "   ⚠️ 未找到虚拟环境" -ForegroundColor Yellow
    Write-Host "   建议运行: setup_worker_env.ps1 创建虚拟环境" -ForegroundColor Gray
    
    # 检查系统 Python
    try {
        $systemPython = Get-Command python -ErrorAction SilentlyContinue
        if ($systemPython) {
            $version = python --version 2>&1
            Write-Host "   系统 Python: $version" -ForegroundColor White
        } else {
            Write-Host "   ❌ 未安装 Python" -ForegroundColor Red
        }
    } catch {
        Write-Host "   ❌ 无法检测 Python" -ForegroundColor Red
    }
}

Write-Host ""

# 4. Node.js 环境
Write-Host "4️⃣ Node.js 环境:" -ForegroundColor Yellow

try {
    $nodeVersion = node --version 2>&1
    Write-Host "   Node.js 版本: $nodeVersion" -ForegroundColor White
    
    $npmVersion = npm --version 2>&1
    Write-Host "   npm 版本: $npmVersion" -ForegroundColor White
    
    Write-Host "   ✅ Node.js 已安装" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Node.js 未安装或不在 PATH 中" -ForegroundColor Red
}

Write-Host ""

# 5. 关键目录检查
Write-Host "5️⃣ 项目目录结构:" -ForegroundColor Yellow

$directories = @(
    @{Path="node-api"; Name="Node API"},
    @{Path="python_worker"; Name="Python Workers"},
    @{Path="vscode-extension"; Name="VSCode Extension"}
)

foreach ($dir in $directories) {
    $fullPath = Join-Path $PSScriptRoot $dir.Path
    if (Test-Path $fullPath) {
        Write-Host "   ✅ $($dir.Name): $fullPath" -ForegroundColor Green
    } else {
        Write-Host "   ❌ $($dir.Name) 目录不存在: $fullPath" -ForegroundColor Red
    }
}

Write-Host ""

# 6. 环境变量检查
Write-Host "6️⃣ 关键环境变量:" -ForegroundColor Yellow

$envFile = Join-Path $PSScriptRoot "python_worker\.env"
if (Test-Path $envFile) {
    Write-Host "   ✅ .env 文件存在: $envFile" -ForegroundColor Green
    
    # 读取并显示关键变量（隐藏敏感信息）
    $envContent = Get-Content $envFile
    $varsToCheck = @("UPSTASH_REDIS_REST_URL", "DASHSCOPE_API_KEY", "USE_MEMORY_REDIS")
    
    foreach ($var in $varsToCheck) {
        $line = $envContent | Where-Object { $_ -match "^$var=" }
        if ($line) {
            $value = $line -replace "^$var=", ""
            if ($value -match "KEY|TOKEN|PASSWORD") {
                $masked = if ($value.Length -gt 12) { "$($value.Substring(0, 8))...$($value.Substring($value.Length - 4))" } else { "***" }
                Write-Host "   $var=$masked" -ForegroundColor White
            } else {
                Write-Host "   $var=$value" -ForegroundColor White
            }
        } else {
            Write-Host "   ⚠️ $var 未设置" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "   ❌ .env 文件不存在: $envFile" -ForegroundColor Red
    Write-Host "   请复制 .env.example 为 .env 并配置" -ForegroundColor Gray
}

Write-Host ""

# 7. 端口检查
Write-Host "7️⃣ 端口占用情况:" -ForegroundColor Yellow

function Test-PortInUse {
    param([int]$Port)
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $tcpClient.Connect("localhost", $Port)
        $tcpClient.Close()
        return $true
    } catch {
        return $false
    }
}

$ports = @(
    @{Port=3000; Service="Node API"},
    @{Port=5173; Service="Vite Dev Server"}
)

foreach ($portInfo in $ports) {
    $inUse = Test-PortInUse -Port $portInfo.Port
    if ($inUse) {
        Write-Host "   ⚠️ 端口 $($portInfo.Port) ($($portInfo.Service)): 已被占用" -ForegroundColor Yellow
    } else {
        Write-Host "   ✅ 端口 $($portInfo.Port) ($($portInfo.Service)): 空闲" -ForegroundColor Green
    }
}

Write-Host ""

# 8. 总结
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "检查完成!" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "💡 建议操作:" -ForegroundColor Magenta
Write-Host "   1. 确保所有 ✅ 项都通过" -ForegroundColor White
Write-Host "   2. 修复所有 ❌ 项" -ForegroundColor White
Write-Host "   3. 处理所有 ⚠️ 警告" -ForegroundColor White
Write-Host "   4. 运行: .\start_all.ps1 启动服务" -ForegroundColor White
Write-Host ""
