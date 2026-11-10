# =============================================================================
# Runtime Setup — 一键安装所有 Worker 运行环境（便携式，零系统污染）
#
# 安装内容:
#   - Amazon Corretto JDK 17  (Java Worker 编译 + 运行)
#   - Apache Maven 3.9        (Java Worker 构建)
#   - Node.js 已全局安装       (检查确认)
#
# 设计原则:
#   - 不写注册表、不弹安装向导、不改系统 PATH
#   - 所有文件在 runtime/ 目录内，删掉即完全卸载
#   - 每个 Worker 通过 $env:ALPHA_RUNTIME_ROOT 找到自己的运行时
#
# Usage:
#   .\runtime\setup.ps1              # 全量安装
#   .\runtime\setup.ps1 -JavaOnly    # 仅装 Java 相关
# =============================================================================
param(
    [switch] $JavaOnly,
    [switch] $Force
)

$ErrorActionPreference = "Stop"
$RUNTIME_ROOT = Join-Path $PSScriptRoot ""
$TEMP_DOWNLOAD = Join-Path $env:TEMP "alphapilot_runtime_dl"

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   AlphaPilot Runtime Environment Setup                   ║" -ForegroundColor Cyan
Write-Host "║   便携安装 — 零系统污染 — 删 runtime/ 即卸载               ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ---- 工具函数 ----

function Write-Step($msg) {
    Write-Host "  >> $msg" -ForegroundColor Yellow
}
function Write-OK($msg) {
    Write-Host "     ✓ $msg" -ForegroundColor Green
}
function Write-Skip($msg) {
    Write-Host "     ○ $msg (已存在，跳过)" -ForegroundColor DarkGray
}
function Write-Err($msg) {
    Write-Host "     ✗ $msg" -ForegroundColor Red
}

function Download-File($url, $dest) {
    Write-Step "下载: $url"
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        Write-OK "下载完成: $dest"
        return $true
    } catch {
        Write-Err "下载失败: $_"
        return $false
    }
}

function Extract-TarGz($archive, $dest) {
    Write-Step "解压: $archive -> $dest"
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    tar -xzf $archive -C (Split-Path $dest -Parent)
    Write-OK "解压完成"
}

function Extract-Zip($archive, $dest) {
    Write-Step "解压: $archive -> $dest"
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Expand-Archive -Path $archive -DestinationPath (Split-Path $dest -Parent) -Force
    # Expand-Archive may create a nested folder, find and rename if needed
    $extracted = Get-ChildItem (Split-Path $dest -Parent) -Directory |
        Where-Object { $_.Name -match "^corretto|^amazon" } |
        Select-Object -First 1
    if ($extracted -and $extracted.FullName -ne $dest) {
        Rename-Item $extracted.FullName (Split-Path $dest -Leaf)
    }
    Write-OK "解压完成"
}

# ---- 准备临时目录 ----
New-Item -ItemType Directory -Force -Path $TEMP_DOWNLOAD | Out-Null

# ═══════════════════════════════════════════════════════════════
# 1. Node.js — 检查
# ═══════════════════════════════════════════════════════════════
Write-Host "── 1. Node.js ───────────────────────────────────────────" -ForegroundColor Magenta
try {
    $nodeVer = & node --version 2>$null
    if ($nodeVer) {
        Write-OK "Node.js $nodeVer (已全局安装)"
    } else {
        Write-Err "Node.js 未找到，请从 https://nodejs.org 安装 LTS 版本"
    }
} catch {
    Write-Err "Node.js 未找到，请从 https://nodejs.org 安装 LTS 版本"
}

# ═══════════════════════════════════════════════════════════════
# 2. Amazon Corretto JDK 17
# ═══════════════════════════════════════════════════════════════
Write-Host "── 2. JDK 17 (Amazon Corretto) ──────────────────────────" -ForegroundColor Magenta

$JDK_DIR = Join-Path $RUNTIME_ROOT "java\jdk-17"
$JDK_BIN = Join-Path $JDK_DIR "bin\javac.exe"

if ((Test-Path $JDK_BIN) -and -not $Force) {
    Write-Skip "JDK 17"
} else {
    # Amazon Corretto 17.0.9 LTS for Windows x64
    $JDK_URL = "https://corretto.aws/downloads/resources/17.0.9.8.1/amazon-corretto-17.0.9.8.1-windows-x64-jdk.zip"
    $JDK_ZIP = Join-Path $TEMP_DOWNLOAD "amazon-corretto-17-jdk.zip"

    if (Download-File $JDK_URL $JDK_ZIP) {
        Extract-Zip $JDK_ZIP $JDK_DIR
        # Verify
        if (Test-Path $JDK_BIN) {
            $jdkInfo = & $JDK_BIN --version 2>&1
            Write-OK "JDK: $jdkInfo"
        } else {
            Write-Err "JDK 安装后验证失败，javac.exe 未找到"
        }
    }
}

# ═══════════════════════════════════════════════════════════════
# 3. Apache Maven 3.9
# ═══════════════════════════════════════════════════════════════
Write-Host "── 3. Apache Maven 3.9 ──────────────────────────────────" -ForegroundColor Magenta

$MVN_DIR = Join-Path $RUNTIME_ROOT "maven\apache-maven-3.9"
$MVN_BIN = Join-Path $MVN_DIR "bin\mvn.cmd"

if ((Test-Path $MVN_BIN) -and -not $Force) {
    Write-Skip "Maven 3.9"
} else {
    $MVN_URL = "https://dlcdn.apache.org/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.zip"
    $MVN_ZIP = Join-Path $TEMP_DOWNLOAD "apache-maven-3.9.zip"

    if (Download-File $MVN_URL $MVN_ZIP) {
        # Maven zip contains apache-maven-3.9.x/ folder at root
        Extract-Zip $MVN_ZIP $MVN_DIR
        # Fix: Expand-Archive creates nested folder -> rename
        $parent = Split-Path $MVN_DIR -Parent
        $actual = Get-ChildItem $parent -Directory | Where-Object { $_.Name -match "^apache-maven" } | Select-Object -First 1
        if ($actual -and $actual.FullName -ne $MVN_DIR) {
            if (Test-Path $MVN_DIR) { Remove-Item -Recurse -Force $MVN_DIR }
            Rename-Item $actual.FullName (Split-Path $MVN_DIR -Leaf)
        }
        if (Test-Path $MVN_BIN) {
            Write-OK "Maven 已安装"
        } else {
            Write-Err "Maven 安装后验证失败，mvn.cmd 未找到"
        }
    }
}

# ═══════════════════════════════════════════════════════════════
# 4. 清理 + 生成 activate 脚本
# ═══════════════════════════════════════════════════════════════
Write-Host "── 4. 清理 + 环境激活脚本 ────────────────────────────────" -ForegroundColor Magenta

# 清理临时文件
Remove-Item -Recurse -Force $TEMP_DOWNLOAD -ErrorAction SilentlyContinue

# 生成 activate.ps1 (如果不存在则创建)
$ACTIVATE = Join-Path $RUNTIME_ROOT "activate.ps1"
@'
# =============================================================================
# Activate Runtime Environment
# 在当前终端加载 Worker 运行时，不影响系统 PATH
#
# Usage:
#   . .\runtime\activate.ps1
#   mvn --version       # 验证 Java 就绪
#   node --version      # 验证 Node.js 就绪
# =============================================================================

$script:RUNTIME_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

# JDK 17
$JDK_HOME = Join-Path $script:RUNTIME_ROOT "java\jdk-17"
if (Test-Path $JDK_HOME) {
    $env:JAVA_HOME = $JDK_HOME
    $env:Path = "$JDK_HOME\bin;$env:Path"
    Write-Host "[Runtime] JAVA_HOME: $JDK_HOME" -ForegroundColor Green
} else {
    Write-Host "[Runtime] JDK 未安装，请先运行 setup.ps1" -ForegroundColor Yellow
}

# Maven
$MVN_HOME = Join-Path $script:RUNTIME_ROOT "maven\apache-maven-3.9"
if (Test-Path $MVN_HOME) {
    $env:M2_HOME = $MVN_HOME
    $env:MAVEN_HOME = $MVN_HOME
    $env:Path = "$MVN_HOME\bin;$env:Path"
    Write-Host "[Runtime] MAVEN_HOME: $MVN_HOME" -ForegroundColor Green
} else {
    Write-Host "[Runtime] Maven 未安装，请先运行 setup.ps1" -ForegroundColor Yellow
}

# Node.js (全局检查)
try {
    $nodeVer = & node --version 2>$null
    if ($nodeVer) {
        Write-Host "[Runtime] Node.js: $nodeVer" -ForegroundColor Green
    }
} catch {}

Write-Host "[Runtime] 环境已激活 — 可以运行 E2E 测试" -ForegroundColor Cyan
'@ | Set-Content -Path $ACTIVATE -Encoding UTF8

Write-OK "activate.ps1 已生成"

# ═══════════════════════════════════════════════════════════════
# 完成报告
# ═══════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  安装完成！                                               ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  使用方式:" -ForegroundColor White
Write-Host "    . .\runtime\activate.ps1       # 激活环境" -ForegroundColor Gray
Write-Host "    mvn --version                  # 验证 Java/Maven" -ForegroundColor Gray
Write-Host ""
Write-Host "  运行 E2E 测试:" -ForegroundColor White
Write-Host "    python -m smoke_tests.runner_expert --full --role java" -ForegroundColor Gray
Write-Host "    python -m smoke_tests.runner_expert --full --role javascript" -ForegroundColor Gray
Write-Host "    python -m smoke_tests.runner_expert --full --role typescript" -ForegroundColor Gray
Write-Host ""