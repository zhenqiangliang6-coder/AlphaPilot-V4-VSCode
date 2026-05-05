# PowerShell 脚本：创建虚拟环境并安装依赖
# 用法（以管理员或普通用户的 PowerShell 运行）：
# .\setup_worker_env.ps1

$venvDir = ".venv_worker"
$reqFile = "worker_requirements.txt"

# Resolve paths relative to the script location
$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
$venvPath = Join-Path $scriptRoot $venvDir
$reqPath = Join-Path $scriptRoot $reqFile

Write-Host "Checking for Python executable (allows Python 3.11)..."
$pythonCmd = "python"
$pythonArgs = ""
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        Write-Host "'python' not found, will try 'py -3.11'"
        $pythonCmd = "py"
        $pythonArgs = "-3.11"
    } else {
        Write-Error "Python executable not found. Please install Python 3.8+ and add to PATH."
        exit 1
    }
}

# 检查版本号
try {
    $ver = & $pythonCmd $pythonArgs -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>&1
} catch {
    Write-Error "Failed to invoke Python to check version: $_"
    exit 1
}
try { [version]$pyver = [version]$ver } catch { $pyver = [version]"0.0" }
if ($pyver -lt [version]"3.8") {
    Write-Error "Detected Python version $ver; minimum required is 3.8. Please install a suitable Python version."
    exit 1
}
Write-Host "Using Python version: $ver"

if (-not (Test-Path $reqPath)) {
    Write-Error "Requirements file $reqPath not found."
    exit 1
}

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment: $venvPath"
    & $pythonCmd $pythonArgs -m venv $venvPath
} else {
    Write-Host "Virtual environment already exists: $venvPath"
}

Write-Host "Activating virtual environment and upgrading pip..."
$activate = Join-Path $venvPath "Scripts/Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Error "Activate script not found: $activate"
    exit 1
}

# Activate the virtual environment in current session
. $activate

Write-Host "Upgrading pip and installing dependencies..."
& $pythonCmd $pythonArgs -m pip install --upgrade pip setuptools wheel
# Use full path for requirements
& $pythonCmd $pythonArgs -m pip install -r $reqPath

# Export installed packages list
$installedList = "installed_packages.txt"
try {
    & $pythonCmd $pythonArgs -m pip freeze | Out-File -FilePath $installedList -Encoding utf8
    Write-Host "Generated installed packages list: $installedList"
} catch {
    Write-Warning "Failed to generate installed packages list: $_"
}

Write-Host 'Done. To activate the venv in a new session run:'
Write-Host '    & .\.venv_worker\Scripts\Activate.ps1'
Write-Host 'To verify: run pytest python_worker or start your worker entry script.'
