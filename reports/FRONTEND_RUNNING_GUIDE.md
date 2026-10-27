# AlphaPilot 前端运行完整指南 🚀

## 📋 目录

1. [快速开始](#快速开始)
2. [架构概览](#架构概览)
3. [环境准备](#环境准备)
4. [运行步骤](#运行步骤)
5. [验证方法](#验证方法)
6. [常见问题](#常见问题)
7. [调试技巧](#调试技巧)

---

## 🚀 快速开始

### 一键启动（推荐）

```powershell
# 在项目根目录执行
cd D:\Copilot_Alphapilot\Copilot_Alphapilot

# 使用 PowerShell 快捷命令
start-alpha
```

这会自动启动：
- ✅ Node API (port 3000)
- ✅ Python Worker (Qwen)
- ✅ VSCode Extension (F5 调试模式)

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────┐
│                  VSCode Extension                    │
│  ┌───────────────────────────────────────────────┐  │
│  │         React Webview (Frontend UI)           │  │
│  │  • ChatInput.tsx    - 智能输入框              │  │
│  │  • MessageList.tsx  - 消息列表                │  │
│  │  • StepTree.tsx     - 步骤追踪树 ⭐           │  │
│  │  • ModelSelector.tsx - 模型选择器             │  │
│  │  • Toolbar.tsx      - 工具栏                  │  │
│  └───────────────────────────────────────────────┘  │
│                        ↓ postMessage                 │
│  ┌───────────────────────────────────────────────┐  │
│  │         ReactPanel.tsx (Extension Layer)      │  │
│  │  • 转发用户请求 → Node API                    │  │
│  │  • 接收 WebSocket 事件 → Webview              │  │
│  │  • 状态映射与协议转换                         │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                        ↓ HTTP / WebSocket
┌─────────────────────────────────────────────────────┐
│                  Node.js API (Port 3000)            │
│  • /task/submit          - 任务提交                 │
│  • /task/notify/:id      - 任务通知 ⭐              │
│  • /fileops/execute      - FileOps 执行             │
│  • WebSocket Server      - 实时通信                 │
│  • Upstash Redis Client  - 队列管理                 │
└─────────────────────────────────────────────────────┘
                        ↓ Redis Queue
┌─────────────────────────────────────────────────────┐
│               Python Worker (Backend Truth)         │
│  • Intent Router       - 意图识别                   │
│  • 5-Step Pipeline     - analyze/plan/write/test/refine │
│  • FileOps Parser      - 文件操作解析               │
│  • Code Executor       - 代码执行引擎               │
└─────────────────────────────────────────────────────┘
```

**核心信条**：
```
Worker = 真相      → 执行真实任务，产生真实结果
Extension = 映射   → 透明转发，不篡改数据
Webview = 投影    → 声明式渲染，响应式更新
协议 = 宪法       → TypeScript 类型定义不可违背
```

---

## 🛠️ 环境准备

### 1. 检查 Node.js 版本

```powershell
node --version
# 预期输出: v18.x 或更高
```

### 2. 检查 Python 版本

```powershell
python --version
# 预期输出: Python 3.9+
```

### 3. 激活虚拟环境

```powershell
# Worker 虚拟环境
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
.\.venv_worker\Scripts\Activate.ps1
```

### 4. 安装依赖

#### Node API 依赖
```powershell
cd node-api
npm install
```

#### VSCode Extension 依赖
```powershell
cd ..\vscode-extension
npm install
```

#### React Webview 依赖
```powershell
cd webview
npm install
```

---

## ▶️ 运行步骤

### 方案 A：开发模式（推荐用于调试）⭐

#### 第 1 步：构建 React Webview

```powershell
cd D:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\webview
npm run build
```

**预期输出**：
```
✓ built in 2.3s
dist/index.html                  0.45 kB
dist/assets/index-abc123.js    150.23 kB
dist/assets/index-def456.css    12.45 kB
```

**产物位置**：`webview-dist/` 目录

---

#### 第 2 步：编译 VSCode Extension

```powershell
cd ..\vscode-extension
npm run compile
```

**预期输出**：
```
[compile] TypeScript compilation successful
Output directory: out/
```

---

#### 第 3 步：启动 Node API

```powershell
cd ..\node-api
node index.js
```

**预期输出**：
```
🚀 AlphaPilot Node API v3.0 已启动 on port 3000
   · FileOps Handler 已就绪 (Workspace: C:\Users\49772\AppData\Local\Temp)
   · WebSocket 服务已开启
   · Redis: Upstash
```

**验证**：
```powershell
curl http://localhost:3000/health
# 预期返回: {"status":"ok","version":"3.0"}
```

---

#### 第 4 步：启动 Python Worker

```powershell
cd ..\python_worker
.\.venv_worker\Scripts\Activate.ps1
python -m python_worker.agents.qwen.qwen_worker_v2
```

**预期输出**：
```
🚀 Qwen Worker v2 已启动
   · Worker ID: qwen-worker-1
   · Node API: 已连接
   · 正在监听任务队列...

📡 监听队列: task_queue:qwen
```

---

#### 第 5 步：启动 VSCode Extension（F5 调试）

1. **在 VSCode 中打开项目**：
   ```
   File → Open Folder → D:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension
   ```

2. **按 F5 启动调试**：
   - 会打开一个新的 VSCode 窗口（Extension Host）
   - 查看 `Debug Console` 确认无报错

3. **打开 AlphaPilot 面板**：
   ```
   Ctrl+Shift+P → "AlphaPilot: Open React Panel"
   ```
   或使用快捷键：`Ctrl+Shift+R`

---

### 方案 B：生产模式（用于日常使用）

#### 第 1 步：一键启动所有服务

```powershell
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
.\start_all.ps1
```

这会并行启动：
- Node API
- Python Worker
- VSCode Extension

---

#### 第 2 步：在 VSCode 中使用

1. 打开任意项目文件夹
2. 按 `Ctrl+Shift+R` 打开 AlphaPilot 面板
3. 开始对话！

---

## ✅ 验证方法

### 验证 1：检查服务状态

```powershell
# 检查 Node API
curl http://localhost:3000/health

# 检查 WebSocket 连接
# 在浏览器开发者工具 → Network → WS 查看

# 检查 Redis 队列
# 登录 Upstash Console 查看队列长度
```

---

### 验证 2：测试任务提交流程

在 AlphaPilot Chat 中输入：
```
创建一个 hello.py 文件，内容是 print("Hello AlphaPilot")
```

**预期流程**：

1. **前端发送请求**：
   ```
   Webview → ReactPanel → POST /task/submit
   ```

2. **Node API 接收**：
   ```
   [Node API] 收到任务提交请求: qwen_generate
   [Node API] 推送到 Redis: task_queue:qwen
   ```

3. **Worker 接收任务**：
   ```
   📡 监听队列: task_queue:qwen
   ============================================================
   收到任务:
   {
     "task_id": "xxx-xxx-xxx",
     "type": "qwen_generate",
     "payload": {
       "prompt": "创建一个 hello.py 文件..."
     }
   }
   ============================================================
   ```

4. **Worker 执行 5 步流程**：
   ```
   🧠 Intent Router 决策:
     意图: write_code
     人格: engineer
     执行链: analyze → plan → write → test → refine

   📋 动态生成 5 个步骤
   🎨 analyze_step 使用人格: 工程师人格 (👨‍💻)
   🎨 plan_step 使用人格: 工程师人格 (👨‍💻)
   🎨 write_step 使用人格: 工程师人格 (👨‍💻)
   ✅ 解析 FileOp: create hello.py
   ✅ 生成 1 个 FileOp(s)
   ```

5. **Worker 通知 Node API**：
   ```
   正在通知 Node.js: http://localhost:3000/task/notify/xxx-xxx-xxx
   ✅ Node.js 返回状态码: 200
   ```

6. **Node API 转发给前端**：
   ```
   [Node API] 通过 WebSocket 推送结果给 Webview
   ```

7. **前端渲染 StepTree**：
   ```
   ✅ StepTree 显示 5 个步骤
   ✅ 状态图标正确（✅ completed）
   ✅ 进度条实时更新
   ✅ 点击步骤可展开查看详情
   ```

---

### 验证 3：检查 StepTree 渲染

**关键指标**：

| 检查项 | 预期结果 | 说明 |
|--------|---------|------|
| 步骤数量 | 5 个 | analyze/plan/write/test/refine |
| 步骤状态 | ✅ completed | 符合 TypeScript 协议 |
| 步骤图标 | 🔍📋✏️✅💎 | 对应不同步骤类型 |
| 耗时统计 | 显示毫秒数 | 如 "1234ms" |
| 当前高亮 | 蓝色边框 | 正在执行的步骤 |
| 进度条 | 0% → 100% | 随步骤完成递增 |

---

## ❓ 常见问题

### Q1: Webview 显示空白？

**原因**：React Webview 未构建或路径错误

**解决**：
```powershell
# 重新构建
cd vscode-extension/webview
npm run build

# 检查输出目录
ls ..\webview-dist
# 应该看到: index.html, assets/, favicon.svg, icons.svg
```

---

### Q2: StepTree 不显示步骤？

**原因**：Worker 返回的状态值与前端协议不匹配

**检查**：
```typescript
// 前端期望 (chatStore.ts)
status: 'pending' | 'running' | 'completed' | 'failed';
```

**修复**：
确保 Worker 返回的是 `"completed"` 而不是 `"success"`。

**验证**：
在 Worker 日志中查找：
```
step["status"] = "completed"  # ✅ 正确
step["status"] = "success"    # ❌ 错误
```

---

### Q3: WebSocket 连接失败？

**原因**：Node API 未启动或端口被占用

**解决**：
```powershell
# 检查端口占用
netstat -ano | findstr :3000

# 如果被占用，杀死进程
taskkill /PID <PID> /F

# 重新启动 Node API
cd node-api
node index.js
```

---

### Q4: Worker 收不到任务？

**原因**：Redis 配置错误或 Node API 未推送任务

**检查**：
1. **Node API 日志**：
   ```
   [Node API] 推送到 Redis: task_queue:qwen  # 应该有这条日志
   ```

2. **Worker 日志**：
   ```
   📡 监听队列: task_queue:qwen  # 应该有这条日志
   ```

3. **Upstash Console**：
   - 登录 https://console.upstash.com
   - 查看队列长度是否增加

**修复**：
检查 `.env` 文件中的 Redis 配置：
```env
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxx
```

---

### Q5: TypeScript 编译错误？

**原因**：类型定义不匹配

**解决**：
```powershell
cd vscode-extension
npm run compile

# 查看详细错误
# 根据错误提示修复类型问题
```

**常见错误**：
- 缺少导入：`import { EventType } from '../core/eventBus';`
- 类型不匹配：检查 `protocol.ts` 中的定义

---

## 🔍 调试技巧

### 技巧 1：查看 Webview 控制台

1. 在 AlphaPilot 面板中按 `F12`
2. 打开开发者工具
3. 查看 `Console` 标签

**关键日志**：
```javascript
// 消息发送
[Webview] 提交任务: { prompt: "...", model: "qwen-turbo" }

// 消息接收
[Webview] 收到事件: step_started { step_type: "analyze" }
[Webview] 收到事件: step_finished { step_type: "analyze", status: "completed" }
```

---

### 技巧 2：查看 Extension 日志

在 VSCode 中：
```
View → Output → AlphaPilot (Extension Host)
```

**关键日志**：
```typescript
[ReactPanel] 收到 Webview 消息: submit_task
[ReactPanel] 转发到 Node API: POST /task/submit
[ReactPanel] 收到 WebSocket 事件: step_started
[ReactPanel] 转发给 Webview: postMessage({ type: "step_started", ... })
```

---

### 技巧 3：查看 Node API 日志

在终端中直接观察：
```
[Node API] 收到任务提交请求: qwen_generate
[Node API] 推送到 Redis: task_queue:qwen
[Node API] Webview 已连接: xxx-xxx-xxx
[Node API] 通过 WebSocket 推送结果
```

---

### 技巧 4：查看 Worker 日志

在 Worker 终端中观察：
```
📡 监听队列: task_queue:qwen
============================================================
收到任务: { ... }
============================================================

🧠 Intent Router 决策:
  意图: write_code
  人格: engineer

📋 动态生成 5 个步骤
🎨 analyze_step 使用人格: 工程师人格 (👨‍💻)
✅ 解析 FileOp: create hello.py

============================================================
任务完成，结果已写入 Redis:
{
  "version": "2.0",
  "steps": [
    { "id": "step-1", "type": "analyze", "status": "completed" },
    { "id": "step-2", "type": "plan", "status": "completed" },
    ...
  ]
}
============================================================
```

---

### 技巧 5：使用 Postman/curl 测试 API

```bash
# 测试健康检查
curl http://localhost:3000/health

# 测试任务提交
curl -X POST http://localhost:3000/task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "type": "qwen_generate",
    "payload": {
      "prompt": "创建一个 hello.py 文件"
    },
    "model": "qwen-turbo"
  }'
```

---

## 📊 性能监控

### 监控 1：构建速度

```powershell
cd vscode-extension/webview
npm run build

# 预期时间: 2-3s
# 如果超过 5s，检查是否有不必要的依赖
```

---

### 监控 2：HMR 速度

在开发模式下修改代码：
```
预期 HMR 时间: <100ms
如果超过 500ms，检查 Vite 配置
```

---

### 监控 3：内存占用

在 VSCode 开发者工具中：
```
Help → Toggle Developer Tools → Performance Monitor

预期内存:
- EventBus: ~50KB
- Dispatcher: ~100KB
- Zustand Store: ~80KB
- 总计: ~230KB
```

---

## 🎯 最佳实践

### 1. 开发工作流

```
修改代码 → npm run build → F5 重启 → 测试 → 观察日志
```

**不要**：
- ❌ 假设代码没问题就能运行
- ❌ 跳过构建步骤
- ❌ 忽略 TypeScript 错误

**要**：
- ✅ 每次修改后立即构建
- ✅ 观察实际运行输出
- ✅ 根据日志定位问题

---

### 2. 调试原则

```
从下往上排查：
Worker → Node API → Extension → Webview
```

**步骤**：
1. 先确认 Worker 收到任务
2. 再确认 Node API 推送成功
3. 再确认 Extension 转发正确
4. 最后确认 Webview 渲染无误

---

### 3. 协议遵守

**TypeScript 类型定义就是宪法**：
```typescript
// chatStore.ts - 不可违背的契约
interface Step {
  status: 'pending' | 'running' | 'completed' | 'failed';
}
```

**Worker 必须严格遵守**：
```python
# ✅ 正确
step["status"] = "completed"

# ❌ 错误
step["status"] = "success"
```

---

## 📝 总结

### 快速启动清单

```powershell
# 1. 构建 React Webview
cd vscode-extension/webview && npm run build

# 2. 编译 Extension
cd .. && npm run compile

# 3. 启动 Node API
cd ..\node-api && node index.js

# 4. 启动 Worker
cd ..\python_worker && python -m python_worker.agents.qwen.qwen_worker_v2

# 5. F5 启动 Extension
# 在 VSCode 中按 F5

# 6. 打开面板
# Ctrl+Shift+R
```

### 验证清单

- [ ] Node API 监听 port 3000
- [ ] Worker 监听 Redis 队列
- [ ] WebSocket 连接成功
- [ ] 任务提交流程通畅
- [ ] StepTree 正确渲染
- [ ] 步骤状态符合协议

---

*文档版本: v3.0*  
*最后更新: 2026-05-09*  
*守护者: AlphaPilot 开发团队*

**"稳扎稳打，步步为营"** —— 每一步都要验证，每一个环节都要确认。
