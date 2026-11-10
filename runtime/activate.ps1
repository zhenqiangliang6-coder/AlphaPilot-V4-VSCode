# =============================================================================
# Activate Runtime Environment
# 在当前终端加载 Worker 运行时，不影响系统 PATH
#
# 自动发现优先级:
#   1. runtime/java/  (便携安装)
#   2. VS Code 扩展 (/java, /maven, /gradle)
#   3. 系统 PATH / JAVA_HOME
#
# Usage:
#   . .\runtime\activate.ps1
#   java --version      # 验证 JDK 就绪
# =============================================================================

$RUNTIME_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$VSCODE_EXT = "$env:USERPROFILE\.vscode\extensions"

# ── JDK 发现 ──
$JDK_HOME = $null
$jdkCandidates = @(
    (Join-Path $RUNTIME_ROOT "java\jdk-17"),
    (Get-ChildItem "$VSCODE_EXT\redhat.java-*" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Get-ChildItem "$($_.FullName)\jre" -Directory -ErrorAction SilentlyContinue } |
        Select-Object -First 1 -ExpandProperty FullName)
)

foreach ($c in $jdkCandidates) {
    if ($c -and (Test-Path (Join-Path $c "bin\javac.exe"))) {
        $JDK_HOME = $c
        break
    }
}

if (-not $JDK_HOME -and $env:JAVA_HOME) {
    if (Test-Path (Join-Path $env:JAVA_HOME "bin\javac.exe")) {
        $JDK_HOME = $env:JAVA_HOME
    }
}

if ($JDK_HOME) {
    $env:JAVA_HOME = $JDK_HOME
    $env:Path = "$JDK_HOME\bin;$env:Path"
    $jdkVer = & "$JDK_HOME\bin\java.exe" --version 2>&1 | Select-Object -First 1
    Write-Host "[Runtime] JAVA_HOME: $JDK_HOME  ($jdkVer)" -ForegroundColor Green
} else {
    Write-Host "[Runtime] JDK 未找到，请运行 setup.ps1 或安装 VS Code Java 扩展" -ForegroundColor Yellow
}

# ── Maven 发现 ──
$MVN_HOME = $null
$mvnCandidates = @(
    (Join-Path $RUNTIME_ROOT "maven\apache-maven-3.9"),
    (Get-ChildItem "$VSCODE_EXT\vscjava.vscode-maven-*" -Directory -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName)
)

foreach ($c in $mvnCandidates) {
    if ($c -and (Test-Path (Join-Path $c "bin\mvn.cmd"))) {
        $MVN_HOME = $c
        break
    }
}

if (-not $MVN_HOME) {
    $mvnOnPath = (Get-Command mvn -ErrorAction SilentlyContinue).Source
    if ($mvnOnPath) {
        $MVN_HOME = Split-Path (Split-Path $mvnOnPath) -Parent
    }
}

if ($MVN_HOME -and $MVN_HOME -ne $JDK_HOME) {
    $env:M2_HOME = $MVN_HOME
    $env:MAVEN_HOME = $MVN_HOME
    $env:Path = "$MVN_HOME\bin;$env:Path"
    Write-Host "[Runtime] MAVEN_HOME: $MVN_HOME" -ForegroundColor Green
} else {
    Write-Host "[Runtime] Maven 未安装 (E2E 路由验证无需 Maven)" -ForegroundColor Yellow
}

# ── Node.js ──
try {
    $nodeVer = & node --version 2>$null
    if ($nodeVer) {
        Write-Host "[Runtime] Node.js: $nodeVer" -ForegroundColor Green
    }
} catch {}

Write-Host "[Runtime] 环境已激活" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Java E2E 路由验证 (无需 Maven):" -ForegroundColor Gray
Write-Host "    python -m smoke_tests.runner_expert --role java_expert" -ForegroundColor Gray
Write-Host ""
Write-Host "  完整编译 E2E (需要 Maven):" -ForegroundColor Gray
Write-Host "    .\runtime\setup.ps1  # 先安装 Maven" -ForegroundColor Gray
Write-Host "    python -m smoke_tests.runner_expert --full --role java_expert" -ForegroundColor Gray