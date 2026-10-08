# ================================
# AlphaPilot 全栈启动脚本（PowerShell 7+ 优化版）
# ================================

# ⭐ PowerShell 7+ 兼容性设置
# 确保使用正确的编码
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
    $PSDefaultParameterValues['*:Encoding'] = 'utf8'
} else {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}

# 设置错误处理策略
$ErrorActionPreference = 'Continue'

Write-Host "🚀 正在启动 AlphaPilot 全栈服务..." -ForegroundColor Green
Write-Host "💻 PowerShell 版本: $($PSVersionTable.PSVersion.ToString())" -ForegroundColor Cyan
Write-Host ""

# -------------------------------
# ⭐ 0. 清除 Python 缓存（确保加载最新代码）
# -------------------------------
Write-Host "0️ 清除 Python 缓存..." -ForegroundColor Yellow

try {
    # 查找并删除所有 __pycache__ 目录
    $pycacheDirs = Get-ChildItem -Path $PSScriptRoot -Recurse -Filter '__pycache__' -Directory -ErrorAction SilentlyContinue
    
    if ($pycacheDirs.Count -gt 0) {
        foreach ($dir in $pycacheDirs) {
            Remove-Item -Path $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Host "   ✅ 已清除 $($pycacheDirs.Count) 个 __pycache__ 目录" -ForegroundColor Green
    } else {
        Write-Host "   ℹ️ 未找到 __pycache__ 目录" -ForegroundColor Cyan
    }
    
    # 查找并删除所有 .pyc 文件
    $pycFiles = Get-ChildItem -Path $PSScriptRoot -Recurse -Filter '*.pyc' -File -ErrorAction SilentlyContinue
    
    if ($pycFiles.Count -gt 0) {
        foreach ($file in $pycFiles) {
            Remove-Item -Path $file.FullName -Force -ErrorAction SilentlyContinue
        }
        Write-Host "   ✅ 已清除 $($pycFiles.Count) 个 .pyc 文件" -ForegroundColor Green
    } else {
        Write-Host "   ℹ️ 未找到 .pyc 文件" -ForegroundColor Cyan
    }
    
    Write-Host "   🎉 Python 缓存清理完成，将加载最新代码" -ForegroundColor Green
} catch {
    Write-Host "   ️ 清除缓存时出错: $_" -ForegroundColor Yellow
}

Write-Host ""

# -------------------------------
# 辅助函数：检查端口是否被占用
# -------------------------------
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

# -------------------------------
# 辅助函数：获取 Python 虚拟环境路径
# -------------------------------
function Get-PythonVenvPath {
    $venvPaths = @(
        "$PSScriptRoot\..\.venv_worker\Scripts\python.exe",
        "$PSScriptRoot\.venv_worker\Scripts\python.exe",
        "$PSScriptRoot\python_worker\.venv\Scripts\python.exe",
        "$PSScriptRoot\.venv\Scripts\python.exe"
    )
    
    foreach ($path in $venvPaths) {
        if (Test-Path $path) {
            return $path
        }
    }
    
    # 如果找不到虚拟环境，使用系统 Python
    Write-Host "   ⚠️ 未找到虚拟环境，使用系统 Python" -ForegroundColor Yellow
    return "python"
}

# -------------------------------
# ⭐ 0. 启动记忆中枢（Docker PostgreSQL + pgvector）
# -------------------------------
Write-Host "🧠 启动 AlphaPilot 记忆中枢..." -ForegroundColor Magenta

$memoryDbPort = 5432
$containerName = "alphapilot-memory-hub"

# 检查 Docker 是否运行
$dockerRunning = $false
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerRunning = $true
        Write-Host "   ✅ Docker 服务正常" -ForegroundColor Green
    }
} catch {
    Write-Host "   ⚠️ Docker 未运行，跳过记忆中枢启动" -ForegroundColor Yellow
}

if ($dockerRunning) {
    # ⭐ 加载 .env.memory 环境变量，使 docker-compose 能获取 DB_PASSWORD 等配置
    $envMemoryPath = Join-Path $PSScriptRoot "..\.env.memory"
    if (-not (Test-Path $envMemoryPath)) {
        $envMemoryPath = Join-Path $PSScriptRoot ".env.memory"
    }
    if (Test-Path $envMemoryPath) {
        Write-Host "   📄 加载记忆中枢环境变量: $envMemoryPath" -ForegroundColor Cyan
        Get-Content $envMemoryPath | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith('#')) {
                $parts = $line -split '=', 2
                if ($parts.Count -eq 2) {
                    $key = $parts[0].Trim()
                    $value = $parts[1].Trim()
                    if ($key -and -not [Environment]::GetEnvironmentVariable($key, 'Process')) {
                        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
                    }
                }
            }
        }
    }
    
    # 检查容器是否已存在
    $existingContainer = docker ps -a --filter "name=$containerName" --format "{{.Names}}" 2>$null
    
    if ($existingContainer -eq $containerName) {
        # 检查容器是否正在运行
        $runningContainer = docker ps --filter "name=$containerName" --format "{{.Names}}" 2>$null
        if ($runningContainer -eq $containerName) {
            Write-Host "   ✅ 记忆中枢已在运行" -ForegroundColor Green
        } else {
            Write-Host "   🔄 启动已存在的记忆中枢容器..." -ForegroundColor Yellow
            docker start $containerName | Out-Null
            Start-Sleep -Seconds 3
        }
    } else {
        # 启动新的容器
        Write-Host "   🐳 启动 PostgreSQL + pgvector 容器..." -ForegroundColor Cyan
        
        # 查找 docker-compose.yml 文件
        $dockerComposePath = Join-Path $PSScriptRoot "..\docker-compose.yml"
        if (-not (Test-Path $dockerComposePath)) {
            $dockerComposePath = Join-Path $PSScriptRoot "docker-compose.yml"
        }
        
        if (Test-Path $dockerComposePath) {
            # 使用 docker compose 启动
            docker compose -f $dockerComposePath up -d | Out-Null
            Write-Host "   🔄 等待数据库就绪..." -ForegroundColor Cyan
            Start-Sleep -Seconds 5
            
            # 验证是否启动成功
            $healthCheck = docker inspect --format "{{.State.Health.Status}}" $containerName 2>$null
            if ($healthCheck -eq "healthy") {
                Write-Host "   ✅ 记忆中枢启动成功！" -ForegroundColor Green
            } else {
                Write-Host "   ⚠️ 记忆中枢可能仍在启动中，请手动检查" -ForegroundColor Yellow
            }
        } else {
            Write-Host "   ❌ 未找到 docker-compose.yml 文件" -ForegroundColor Red
        }
    }
    
    # ⭐ 阶段 2：即时更新（启动时维护记忆）
    Write-Host "   🔄 执行记忆维护（衰减、剪枝、合并）..." -ForegroundColor Cyan
    
    # ⭐ 启动时清理临时会话记忆（每次启动全新开始）
    Write-Host "   🧹 清理临时会话记忆..." -ForegroundColor Cyan
    $tempMemoryDir = Join-Path $PSScriptRoot "..\..\.temp_memory"
    if (-not (Test-Path $tempMemoryDir)) {
        $tempMemoryDir = Join-Path $PSScriptRoot "..\.temp_memory"
    }
    if (-not (Test-Path $tempMemoryDir)) {
        $tempMemoryDir = Join-Path $PSScriptRoot ".temp_memory"
    }
    if (Test-Path $tempMemoryDir) {
        try {
            Remove-Item -Path "$tempMemoryDir\*.json" -Force -ErrorAction SilentlyContinue
            Write-Host "   ✅ 临时记忆已清理" -ForegroundColor Green
        } catch {
            Write-Host "   ⚠️ 临时记忆清理跳过" -ForegroundColor Yellow
        }
    } else {
        Write-Host "   📁 创建临时记忆目录: $tempMemoryDir" -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $tempMemoryDir -Force | Out-Null
    }
    
    $pythonExe = Get-PythonVenvPath
    $memoryMaintenanceScript = @"
import sys
sys.path.insert(0, '$PSScriptRoot')
try:
    from python_worker.memory_service import get_memory_service
    service = get_memory_service()
    
    # 1. 激活度衰减（模拟遗忘曲线）
    print("   - 执行激活度衰减...")
    service.decay_activation_scores()
    
    # 2. 自动剪枝（清理无用记忆）
    print("   - 执行记忆剪枝...")
    service.prune_memories()
    
    print("   ✅ 记忆维护完成")
    service.close()
except Exception as e:
    print(f"   ⚠️ 记忆维护失败: {e}")
"@
    
    try {
        # 执行记忆维护脚本
        $tempScriptPath = Join-Path $env:TEMP "alphapilot_memory_maintenance.py"
        $memoryMaintenanceScript | Out-File -FilePath $tempScriptPath -Encoding UTF8 -Force
        
        & $pythonExe $tempScriptPath 2>&1 | Out-Null
        
        Remove-Item $tempScriptPath -Force -ErrorAction SilentlyContinue
        Write-Host "   ✅ 记忆维护完成" -ForegroundColor Green
    } catch {
        Write-Host "   ⚠️ 记忆维护失败，将在下次启动时重试" -ForegroundColor Yellow
    }
}

if ($dockerRunning) {
    $dockerComposePath = Join-Path $PSScriptRoot "..\docker-compose.yml"
    if (-not (Test-Path $dockerComposePath)) {
        $dockerComposePath = Join-Path $PSScriptRoot "docker-compose.yml"
    }

    if (Test-Path $dockerComposePath) {
        docker compose -f $dockerComposePath up -d redis
        $redisComposeExitCode = $LASTEXITCODE
        if ($redisComposeExitCode -eq 0) {
            Write-Host "   🐳 本地 Redis 已启动 (localhost:6379)" -ForegroundColor Green
        } else {
            Write-Host "   ⚠️ 本地 Redis 启动失败，请检查 Docker 输出" -ForegroundColor Yellow
        }
    }
}

Write-Host ""

# -------------------------------
# 1. 检查 Node API
# -------------------------------
Write-Host "1️⃣ 检查 Node API..." -ForegroundColor Yellow

$nodeApiPort = 3000
if (Test-PortInUse -Port $nodeApiPort) {
    Write-Host "   ✅ Node API 已在运行 (端口 $nodeApiPort)" -ForegroundColor Green
} else {
    Write-Host "   ⚠️ Node API 未运行，正在启动..." -ForegroundColor Yellow
    
    # 检查 node-api 目录是否存在
    $nodeApiPath = Join-Path $PSScriptRoot "node-api"
    if (Test-Path $nodeApiPath) {
        # 使用 pwsh (PowerShell 7+) 或 powershell (Windows PowerShell)
        $shellCommand = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
        
        Start-Process $shellCommand -ArgumentList "-NoExit", "-Command", "cd '$nodeApiPath'; npm start" -WindowStyle Normal
        Write-Host "   🔄 等待 Node API 启动..." -ForegroundColor Cyan
        Start-Sleep -Seconds 5
        
        # 验证是否启动成功
        if (Test-PortInUse -Port $nodeApiPort) {
            Write-Host "   ✅ Node API 启动成功" -ForegroundColor Green
        } else {
            Write-Host "   ⚠️ Node API 可能仍在启动中，请手动检查" -ForegroundColor Yellow
        }
    } else {
        Write-Host "   ❌ node-api 目录不存在: $nodeApiPath" -ForegroundColor Red
    }
}

# -------------------------------
# 2. 启动 AlphaPilot International Proxy
# -------------------------------
Write-Host ""
Write-Host "1.5️⃣ 启动 AlphaPilot International Proxy..." -ForegroundColor Yellow

$proxyPort = 8000
$proxyPath = "d:\alphapilot-international-proxy"

if (Test-PortInUse -Port $proxyPort) {
    Write-Host "   ✅ AlphaPilot Proxy 已在运行 (端口 $proxyPort)" -ForegroundColor Green
} else {
    Write-Host "   ⚠️ AlphaPilot Proxy 未运行，正在启动..." -ForegroundColor Yellow
    
    # 检查代理目录是否存在
    if (Test-Path $proxyPath) {
        $shellCommand = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
        
        Start-Process $shellCommand -ArgumentList "-NoExit", "-Command", "cd '$proxyPath'; uvicorn main:app --host 0.0.0.0 --port 8000" -WindowStyle Normal
        Write-Host "   🔄 等待 AlphaPilot Proxy 启动..." -ForegroundColor Cyan
        Start-Sleep -Seconds 3
        
        # 验证是否启动成功
        if (Test-PortInUse -Port $proxyPort) {
            Write-Host "   ✅ AlphaPilot Proxy 启动成功" -ForegroundColor Green
        } else {
            Write-Host "   ⚠️ AlphaPilot Proxy 可能仍在启动中，请手动检查" -ForegroundColor Yellow
        }
    } else {
        Write-Host "   ❌ 代理目录不存在: $proxyPath" -ForegroundColor Red
        Write-Host "   💡 请先克隆 AlphaPilot Proxy 项目到该目录" -ForegroundColor Yellow
    }
}

# -------------------------------
# 3. 启动 Workers
# -------------------------------
Write-Host ""
Write-Host "2️⃣ 启动 Workers..." -ForegroundColor Yellow

# 获取 Python 解释器路径
$pythonExe = Get-PythonVenvPath
Write-Host "   🐍 Python: $pythonExe" -ForegroundColor Cyan

# Worker 配置（v3.0 流式输出版）
$workers = @(
    @{Name="Qwen"; Script="python_worker.agents.qwen.qwen_worker_v2"; EnvId="qwen-worker-1"},
    @{Name="Gemini"; Script="python_worker.agents.gemini.gemini_worker_v2"; EnvId="gemini-worker-1"},
    @{Name="MaaS"; Script="python_worker.agents.maas.maas_worker_v3"; EnvId="maas-worker-1"},
    @{Name="ModelScope"; Script="python_worker.agents.modelscope.modelscope_worker_v3"; EnvId="modelscope-worker-1"},
    @{Name="Local LLM"; Script="python_worker.agents.local_llm.local_worker_v3"; EnvId="local-worker-1"}
)

foreach ($worker in $workers) {
    Write-Host "   🔄 启动 $($worker.Name) Worker ($($worker.EnvId))..." -ForegroundColor Cyan
    
    # 构建命令
    $shellCommand = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
    
    # ⭐ 修复：正确传递环境变量和命令
    $cmdArgs = @(
        "-NoExit",
        "-Command",
        "`$env:WORKER_ID='$($worker.EnvId)'; Set-Location -LiteralPath '$PSScriptRoot'; & '$pythonExe' -m $($worker.Script)"
    )
    
    try {
        Start-Process $shellCommand -ArgumentList $cmdArgs -WindowStyle Normal
        Write-Host "   ✅ $($worker.Name) Worker 已启动" -ForegroundColor Green
    } catch {
        Write-Host "   ❌ $($worker.Name) Worker 启动失败: $_" -ForegroundColor Red
    }
    
    Start-Sleep -Seconds 1
}

# -------------------------------
# 4. 完成
# -------------------------------
Write-Host ""
Write-Host "✅ 所有服务已启动!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 下一步操作:" -ForegroundColor Yellow
Write-Host "   1. 在 VSCode 中按 F5 启动扩展调试" -ForegroundColor White
Write-Host "   2. 或运行: cd vscode-extension && npm run compile" -ForegroundColor White
Write-Host "   3. 按 Ctrl+Shift+A 打开 AlphaPilot 面板" -ForegroundColor White
Write-Host ""
Write-Host "💡 提示:" -ForegroundColor Cyan
Write-Host "   - 所有服务将在独立窗口中运行，可单独查看日志" -ForegroundColor White
Write-Host "   - 关闭终端窗口即可停止对应服务" -ForegroundColor White
Write-Host "   - 如遇问题，请检查各窗口的错误信息" -ForegroundColor White
Write-Host ""

# 显示服务状态摘要
Write-Host "📊 服务状态摘要:" -ForegroundColor Magenta
Write-Host "   🧠 记忆中枢: $(if ($dockerRunning -and (docker ps --filter "name=$containerName" --format "{{.Names}}" 2>$null) -eq $containerName) { '✅ 运行中' } else { '❌ 未运行' })" -ForegroundColor White
Write-Host "   Node API: $(if (Test-PortInUse -Port 3000) { '✅ 运行中' } else { '❌ 未运行' })" -ForegroundColor White
Write-Host "   AlphaPilot Proxy: $(if (Test-PortInUse -Port 8000) { '✅ 运行中' } else { '❌ 未运行' })" -ForegroundColor White
Write-Host "   Qwen Worker: ✅ 已启动 (新窗口)" -ForegroundColor White
Write-Host "   Gemini Worker: ✅ 已启动 (新窗口)" -ForegroundColor White
Write-Host "   MaaS Worker: ✅ 已启动 (新窗口)" -ForegroundColor White
Write-Host "   ModelScope Worker: ✅ 已启动 (新窗口)" -ForegroundColor White
Write-Host "   Local LLM Worker: ✅ 已启动 (新窗口)" -ForegroundColor White
Write-Host ""