# AlphaPilot OS v3.2 前端 UI 升级快速测试脚本
# 用途：验证4个核心升级方向的功能

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AlphaPilot OS v3.2 前端 UI 升级测试" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查服务状态
Write-Host "[1/5] 检查服务状态..." -ForegroundColor Yellow
$nodeApiPort = 3000
$pythonWorkerPort = 8000

try {
    $nodeApi = Test-NetConnection -ComputerName localhost -Port $nodeApiPort -WarningAction SilentlyContinue
    $pythonWorker = Test-NetConnection -ComputerName localhost -Port $pythonWorkerPort -WarningAction SilentlyContinue
    
    if ($nodeApi.TcpTestSucceeded) {
        Write-Host "✅ Node API 服务运行中 (端口 $nodeApiPort)" -ForegroundColor Green
    } else {
        Write-Host "❌ Node API 服务未运行 (端口 $nodeApiPort)" -ForegroundColor Red
        Write-Host "   请先运行: .\start_all.ps1" -ForegroundColor Yellow
    }
    
    if ($pythonWorker.TcpTestSucceeded) {
        Write-Host "✅ Python Worker 服务运行中 (端口 $pythonWorkerPort)" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Python Worker 服务未运行 (端口 $pythonWorkerPort)" -ForegroundColor Yellow
        Write-Host "   建议运行: .\start_all.ps1" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  无法检查服务状态" -ForegroundColor Yellow
}

Write-Host ""

# 2. 检查 Webview 构建状态
Write-Host "[2/5] 检查 Webview 构建状态..." -ForegroundColor Yellow
$webviewDistPath = "vscode-extension\webview-dist\index.html"

if (Test-Path $webviewDistPath) {
    Write-Host "✅ Webview 已构建 ($webviewDistPath)" -ForegroundColor Green
    
    # 检查构建时间
    $buildTime = (Get-Item $webviewDistPath).LastWriteTime
    $timeDiff = (Get-Date) - $buildTime
    if ($timeDiff.TotalHours -gt 1) {
        Write-Host "⚠️  Webview 构建时间较早 ($($buildTime.ToString('yyyy-MM-dd HH:mm:ss')))" -ForegroundColor Yellow
        Write-Host "   建议重新构建: cd vscode-extension\webview && npm run build" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ Webview 未构建" -ForegroundColor Red
    Write-Host "   请运行: cd vscode-extension\webview && npm run build" -ForegroundColor Yellow
}

Write-Host ""

# 3. 检查新增组件文件
Write-Host "[3/5] 检查新增组件文件..." -ForegroundColor Yellow
$components = @(
    "vscode-extension\webview\src\components\EnhancedStreamingOutput.tsx",
    "vscode-extension\webview\src\components\ChatBubble.tsx",
    "vscode-extension\webview\src\components\FilePreview.tsx",
    "vscode-extension\webview\src\components\StepPanel.tsx"
)

$allComponentsExist = $true
foreach ($component in $components) {
    if (Test-Path $component) {
        $fileName = Split-Path $component -Leaf
        Write-Host "✅ $fileName" -ForegroundColor Green
    } else {
        $fileName = Split-Path $component -Leaf
        Write-Host "❌ $fileName (缺失)" -ForegroundColor Red
        $allComponentsExist = $false
    }
}

if ($allComponentsExist) {
    Write-Host "✅ 所有新增组件文件存在" -ForegroundColor Green
} else {
    Write-Host "❌ 部分组件文件缺失" -ForegroundColor Red
}

Write-Host ""

# 4. 检查依赖安装状态
Write-Host "[4/5] 检查依赖安装状态..." -ForegroundColor Yellow
$packageJsonPath = "vscode-extension\webview\package.json"

if (Test-Path $packageJsonPath) {
    $packageJson = Get-Content $packageJsonPath -Raw | ConvertFrom-Json
    
    $requiredDeps = @(
        "react-markdown",
        "react-syntax-highlighter",
        "@types/react-syntax-highlighter"
    )
    
    $allDepsInstalled = $true
    foreach ($dep in $requiredDeps) {
        if ($packageJson.dependencies.$dep -or $packageJson.devDependencies.$dep) {
            $version = $packageJson.dependencies.$dep ?? $packageJson.devDependencies.$dep
            Write-Host "✅ $dep ($version)" -ForegroundColor Green
        } else {
            Write-Host " $dep (未安装)" -ForegroundColor Red
            $allDepsInstalled = $false
        }
    }
    
    if ($allDepsInstalled) {
        Write-Host "✅ 所有必需依赖已安装" -ForegroundColor Green
    } else {
        Write-Host "❌ 部分依赖缺失" -ForegroundColor Red
        Write-Host "   请运行: cd vscode-extension\webview && npm install" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ package.json 未找到" -ForegroundColor Red
}

Write-Host ""

# 5. 生成测试清单
Write-Host "[5/5] 生成手动测试清单..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  手动测试清单（请在 VSCode 中执行）" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "📋 测试步骤：" -ForegroundColor Yellow
Write-Host ""

Write-Host "1️⃣  启动 VSCode 扩展" -ForegroundColor Green
Write-Host "   - 按 F5 启动调试模式" -ForegroundColor Gray
Write-Host "   - 或者重新加载窗口 (Ctrl+Shift+P → Reload Window)" -ForegroundColor Gray
Write-Host ""

Write-Host "2️⃣  测试流式输出（打字机效果）" -ForegroundColor Green
Write-Host "   任务描述: 生成一个 Python 快速排序算法" -ForegroundColor Gray
Write-Host "   预期结果:" -ForegroundColor Gray
Write-Host "   ✅ 看到逐字流动的打字机效果" -ForegroundColor Cyan
Write-Host "   ✅ 思考过程在紫色背景区域显示" -ForegroundColor Cyan
Write-Host "   ✅ 加载动画显示'AI 正在思考...'" -ForegroundColor Cyan
Write-Host "   ✅ 最终产出使用 Markdown 渲染" -ForegroundColor Cyan
Write-Host ""

Write-Host "3️⃣  测试拟人化界面（气泡对话框）" -ForegroundColor Green
Write-Host "   任务描述: 写一首关于春天的诗" -ForegroundColor Gray
Write-Host "   预期结果:" -ForegroundColor Gray
Write-Host "   ✅ 看到 AI 头像（🚀）和用户头像（👤）" -ForegroundColor Cyan
Write-Host "   ✅ 人格标签显示（如'创作者'）" -ForegroundColor Cyan
Write-Host "   ✅ 意图徽章显示（如'创意写作'）" -ForegroundColor Cyan
Write-Host "   ✅ 气泡对话框样式正确（圆角 + 阴影）" -ForegroundColor Cyan
Write-Host ""

Write-Host "4️⃣  测试文件预览（蓝色高亮 + 展开）" -ForegroundColor Green
Write-Host "   任务描述: 生成 hello.py / utils.py / main.py" -ForegroundColor Gray
Write-Host "   预期结果:" -ForegroundColor Gray
Write-Host "   ✅ 文件名蓝色高亮显示" -ForegroundColor Cyan
Write-Host "   ✅ 点击文件名展开文件内容" -ForegroundColor Cyan
Write-Host "   ✅ 代码语法高亮正确（Python）" -ForegroundColor Cyan
Write-Host "   ✅ 复制按钮悬浮显示" -ForegroundColor Cyan
Write-Host "   ✅ 文件统计信息正确（行数、字符数）" -ForegroundColor Cyan
Write-Host ""

Write-Host "5️⃣  测试步骤面板（Cursor 风格）" -ForegroundColor Green
Write-Host "   操作: 点击工具栏的' 步骤'按钮" -ForegroundColor Gray
Write-Host "   预期结果:" -ForegroundColor Gray
Write-Host "   ✅ 侧边栏从右侧滑入（带动画）" -ForegroundColor Cyan
Write-Host "   ✅ 进度条显示正确（渐变色）" -ForegroundColor Cyan
Write-Host "   ✅ 步骤卡片状态正确（图标 + 编号）" -ForegroundColor Cyan
Write-Host "   ✅ 展开详情显示 FileOps 操作" -ForegroundColor Cyan
Write-Host "   ✅ 当前阶段标签高亮" -ForegroundColor Cyan
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  测试完成检查清单" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$checklist = @(
    "流式输出（打字机效果）",
    "拟人化界面（气泡对话框）",
    "文件预览（蓝色高亮 + 展开）",
    "步骤面板（Cursor 风格）",
    "所有功能正常工作",
    "无控制台错误",
    "性能流畅（无卡顿）"
)

foreach ($item in $checklist) {
    Write-Host "☐  $item" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  常见问题排查" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host " 流式输出不工作？" -ForegroundColor Yellow
Write-Host "   → 检查 Node API 是否正确转发 stream_chunk 事件" -ForegroundColor Gray
Write-Host "   → 检查 Worker 是否启用 meta.stream=true" -ForegroundColor Gray
Write-Host "   → 查看浏览器控制台（F12）是否有错误" -ForegroundColor Gray
Write-Host ""

Write-Host "❓ 文件预览不显示？" -ForegroundColor Yellow
Write-Host "   → 检查 FileOps 数据是否正确传递" -ForegroundColor Gray
Write-Host "   → 检查 FilePreview 组件是否正确导入" -ForegroundColor Gray
Write-Host "   → 查看 Webview 控制台是否有错误" -ForegroundColor Gray
Write-Host ""

Write-Host " 步骤面板不显示？" -ForegroundColor Yellow
Write-Host "   → 检查步骤数据是否正确添加到 message.steps" -ForegroundColor Gray
Write-Host "   → 检查 StepPanel 组件是否正确导入" -ForegroundColor Gray
Write-Host "   → 查看 Toolbar 按钮是否点击生效" -ForegroundColor Gray
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  测试脚本执行完毕" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 请按照上述清单在 VSCode 中进行手动测试" -ForegroundColor Green
Write-Host "📊 测试完成后，请记录测试结果和发现的问题" -ForegroundColor Green
Write-Host ""
