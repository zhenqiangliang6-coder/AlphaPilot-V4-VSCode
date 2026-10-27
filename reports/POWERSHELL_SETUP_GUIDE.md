# PowerShell 7+ 配置指南

## 📋 目录
1. [为什么需要配置 PowerShell？](#为什么需要配置-powershell)
2. [快速配置（推荐）](#快速配置推荐)
3. [手动配置](#手动配置)
4. [常见问题](#常见问题)

---

## 为什么需要配置 PowerShell？

### 问题背景

在运行 AlphaPilot 时，你可能会遇到以下问题：

1. **中文乱码** - 输出显示为 `???` 或乱码字符
2. **环境变量传递失败** - Worker 无法接收到 `WORKER_ID` 等环境变量
3. **命令执行错误** - PowerShell 语法兼容性问题
4. **编码不一致** - 不同脚本使用不同编码导致问题

### 解决方案

通过配置 PowerShell 7+，可以：
- ✅ 统一使用 UTF-8 编码（解决中文乱码）
- ✅ 设置常用命令别名（提高效率）
- ✅ 自动加载环境配置
- ✅ 提供便捷的辅助函数

---

## 快速配置（推荐）⭐

### 步骤 1: 找到 PowerShell 配置文件路径

在 PowerShell 中运行：

```powershell
$PROFILE.CurrentUserAllHosts
```

你会看到类似这样的路径：
```
C:\Users\YourName\Documents\PowerShell\Microsoft.PowerShell_profile.ps1
```

### 步骤 2: 创建或编辑配置文件

```powershell
# 如果文件不存在，先创建
if (-not (Test-Path $PROFILE.CurrentUserAllHosts)) {
    New-Item -Path $PROFILE.CurrentUserAllHosts -ItemType File -Force
}

# 用记事本打开
notepad $PROFILE.CurrentUserAllHosts
```

### 步骤 3: 复制配置内容

将 [`alpha_profile.ps1`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\alpha_profile.ps1) 的内容复制到配置文件中：

```powershell
# 复制 alpha_profile.ps1 的内容
Get-Content "d:\Copilot_Alphapilot\Copilot_Alphapilot\alpha_profile.ps1" | Set-Content $PROFILE.CurrentUserAllHosts
```

### 步骤 4: 重新加载配置

```powershell
# 方法 1: 重启 PowerShell
# 关闭当前窗口，重新打开

# 方法 2: 立即生效
. $PROFILE.CurrentUserAllHosts
```

### 步骤 5: 验证配置

```powershell
# 应该看到欢迎信息
# ======================================
# AlphaPilot PowerShell 环境已加载
# ======================================

# 测试命令
check-env      # 检查环境
start-alpha    # 启动服务
```

---

## 手动配置

如果你不想使用配置文件，可以在每次启动时手动运行：

### 设置 UTF-8 编码

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
```

### 创建快捷函数

```powershell
# 启动 AlphaPilot
function Start-AlphaPilot {
    & "d:\Copilot_Alphapilot\Copilot_Alphapilot\start_all.ps1"
}

# 检查环境
function Test-AlphaPilotEnv {
    & "d:\Copilot_Alphapilot\Copilot_Alphapilot\check_powershell_env.ps1"
}
```

---

## 优化后的 start_all.ps1

我已经为你优化了 [`start_all.ps1`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\start_all.ps1)，主要改进：

### ✅ 修复的问题

1. **PowerShell 7+ 兼容性**
   ```powershell
   # 检测 PowerShell 版本
   if ($PSVersionTable.PSVersion.Major -ge 7) {
       $PSDefaultParameterValues['*:Encoding'] = 'utf8'
   }
   ```

2. **正确的环境变量传递**
   ```powershell
   # 修复前（可能失败）
   $cmd = "& { $env:WORKER_ID='qwen-worker-1'; ... }"
   
   # 修复后（可靠）
   $cmdArgs = @(
       "-NoExit",
       "-Command",
       "`$env:WORKER_ID='qwen-worker-1'; ..."
   )
   Start-Process pwsh -ArgumentList $cmdArgs
   ```

3. **Python 虚拟环境自动检测**
   ```powershell
   function Get-PythonVenvPath {
       # 自动查找虚拟环境
       # 如果找不到，使用系统 Python
   }
   ```

4. **端口占用检查**
   ```powershell
   function Test-PortInUse {
       # 检查端口是否被占用
       # 避免重复启动服务
   }
   ```

5. **更好的错误处理**
   ```powershell
   try {
       Start-Process ...
       Write-Host "✅ 启动成功"
   } catch {
       Write-Host "❌ 启动失败: $_"
   }
   ```

---

## 常见问题

### Q1: 中文仍然乱码怎么办？

**A**: 确保以下几点：

1. **PowerShell 版本 >= 7**
   ```powershell
   $PSVersionTable.PSVersion
   ```

2. **编码设置为 UTF-8**
   ```powershell
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   ```

3. **VSCode 终端设置**
   
   在 VSCode 设置中添加：
   ```json
   "terminal.integrated.profiles.windows": {
       "PowerShell": {
           "source": "PowerShell",
           "icon": "terminal-powershell",
           "args": ["-NoExit", "-Command", "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8"]
       }
   }
   ```

### Q2: Worker 启动后立即关闭？

**A**: 可能的原因：

1. **Python 路径错误**
   ```powershell
   # 检查 Python 是否存在
   Test-Path "D:\Copilot_Alphapilot\Copilot_Alphapilot\.venv_worker\Scripts\python.exe"
   ```

2. **.env 文件未加载**
   ```powershell
   # 检查 .env 文件
   Test-Path "d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\.env"
   ```

3. **查看错误日志**
   - Worker 会在新窗口中运行
   - 查看窗口中的错误信息

### Q3: 如何停止所有服务？

**A**: 三种方法：

**方法 1: 使用辅助函数**
```powershell
Stop-AlphaPilot
```

**方法 2: 手动停止进程**
```powershell
# 停止 Node.js
Get-Process node | Stop-Process -Force

# 停止 Python
Get-Process python | Stop-Process -Force
```

**方法 3: 关闭窗口**
- 直接关闭每个服务的窗口

### Q4: 端口 3000 已被占用怎么办？

**A**: 

**检查哪个进程占用**:
```powershell
Get-NetTCPConnection -LocalPort 3000 | Select-Object OwningProcess
Get-Process -Id <PID>
```

**停止占用进程**:
```powershell
Stop-Process -Id <PID> -Force
```

**或者修改端口**:
```javascript
// 在 node-api/index.js 中修改
const PORT = process.env.PORT || 3001;  // 改为 3001
```

### Q5: 如何让配置永久生效？

**A**: 使用 PowerShell 配置文件（见上文"快速配置"部分）。

配置文件会在每次启动 PowerShell 时自动加载。

---

## 🎯 推荐工作流程

### 日常开发

```powershell
# 1. 打开 PowerShell 7+
# 自动加载 alpha_profile.ps1

# 2. 检查环境
check-env

# 3. 启动服务
start-alpha

# 4. 在 VSCode 中按 F5 调试扩展

# 5. 完成后停止服务
Stop-AlphaPilot
```

### 调试 Worker

```powershell
# 只测试 Qwen Worker
test-qwen

# 选择选项 1: 简单测试
```

### 监控状态

```powershell
# 查看 Worker 状态
Get-WorkerStatus
```

---

## 📚 相关文档

- [start_all.ps1](start_all.ps1) - 优化后的启动脚本
- [check_powershell_env.ps1](check_powershell_env.ps1) - 环境检查工具
- [alpha_profile.ps1](alpha_profile.ps1) - PowerShell 配置文件模板
- [QWEN_WORKER_TEST_REPORT.md](python_worker/QWEN_WORKER_TEST_REPORT.md) - Worker 测试报告

---

## 💡 最佳实践

1. **始终使用 PowerShell 7+** - 更好的性能和兼容性
2. **配置 UTF-8 编码** - 避免中文乱码
3. **使用虚拟环境** - 隔离依赖，避免冲突
4. **定期检查环境** - 运行 `check-env` 确保配置正确
5. **阅读错误日志** - Worker 窗口的错误信息很有价值

---

**配置完成！现在可以愉快地使用 AlphaPilot 了！** 🎉
