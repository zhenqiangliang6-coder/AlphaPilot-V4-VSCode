# AlphaPilot MVP 快速开始指南

> **版本**: 0.1.0 - MVP 完成版  
> **更新时间**: 2026年2月28日  
> **架构**: HTTP + Redis + Qwen Worker

---

## 🚀 30 秒快速开始

### Step 1: 启动后端服务（3 个终端）

**终端 1 - Node API**
```bash
cd c:\Users\DavidLiang\Desktop\my-distributed-system\node-api
node index.js
# 输出: Server is running at http://localhost:3000
```

**终端 2 - Redis**
```bash
redis-server
# 或使用 Upstash 在线版本（无需本地启动）
```

**终端 3 - Qwen Worker**
```bash
cd c:\Users\DavidLiang\Desktop\my-distributed-system\python-worker
# 确保 .env 包含 DASHSCOPE_API_KEY
python qwen_worker.py
# 输出: 🚀 Qwen Worker 已启动
#      📻 等待任务...
```

### Step 2: 打开 VSCode 并测试

```
1. 打开 VSCode，加载 vscode-extension 文件夹
2. 按 F5 调试（会开启新窗口）
3. 在新窗口中：Ctrl+Shift+P
4. 输入 "AlphaPilot: 代码补全 (MVP)"
5. 输入提示词：比如 "写一个求阶乘的函数"
6. 查看 AI 输出面板：内容会流式显示
```

### Step 3: 查看结果

```
📋 AlphaPilot · 代码补全

🔄 流式输出中...

def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

✅ 完成 | 2048 字
```

---

## 📊 架构流程

**你的输入 → Extension 的 HTTP 调用 → Node API → Redis 队列 → Qwen Worker**

```
VSCode Extension
    │
    ├─ POST /task/submit
    │  {
    │    "type": "qwen_generate",
    │    "payload": { "prompt": "..." },
    │    "source": "vscode-extension"
    │  }
    │
    ↓
Node API
    │
    ├─ LPUSH task_queue
    │
    ↓
Redis
    │
    ├─ RPOP task_queue
    │
    ↓
qwen_worker.py (你现有的)
    │
    ├─ 调用 Qwen API
    ├─ 周期性输出 streaming TaskModel
    ├─ 最终输出 done TaskModel
    │
    ├─ SET task_result:xxx
    │
    ↓
Extension (轮询)
    │
    ├─ GET /task/result/:task_id (每 500ms)
    ├─ 解析 TaskModel
    ├─ 裁剪为简化消息
    │
    ├─ panel.sendAppend(chunk)  ← streaming
    ├─ panel.sendDone()          ← done
    ├─ panel.sendError(msg)      ← error
    │
    ↓
Webview (aiResult.js)
    │
    ├─ 接收简化消息
    ├─ 只做文本显示，无其他逻辑
    │
    ↓
UI 显示内容
```

---

## 🎮 所有命令

| 命令 | 说明 |
|------|------|
| `AlphaPilot: 代码补全 (MVP)` | **主命令** - 流式显示代码 |
| `AlphaPilot: 打开 AI 输出面板` | 手动打开结果面板 |
| `AlphaPilot: 打开任务历史` | 查看历史任务 |

---

## ⚙️ 环境配置

### .env 文件要求（python-worker/.env）

```bash
# Qwen API
DASHSCOPE_API_KEY=sk-xxxxx

# Redis（如果使用在线版本）
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxxxx

# Node API（默认 localhost:3000）
NODE_API_URL=http://localhost:3000

# Worker 标识
WORKER_ID=qwen-worker-1
```

### package.json 依赖检查（vscode-extension）

```bash
cd vscode-extension
npm install
npm run compile
# 编译结果保存到 out/ 目录
```

---

## 🧪 验证 MVP 工作正常

**输出面板中应该看到：**

✅ Task ID 已获取  
✅ 流式输出逐字显示（不是等待后一次性显示）  
✅ 最终显示 "✅ 完成"  
✅ 无 JSON 元数据泄露到 UI  

**如果看到：**

❌ `[object Object]` 或 `undefined`  
❌ `{"version": "1.0", ...}` （JSON 在 UI）  
❌ 等待很久才显示内容（不是流式）  

→ 说明哪个环节出问题了，参考下面的 Debug 部分

---

## 🐛 Debug 指南

### 问题 1: "任务提交失败"

**检查清单：**
```bash
# 1. Node API 是否运行？
curl http://localhost:3000/health
# 应返回 200

# 2. Redis 是否可连接？
redis-cli ping
# 应返回 PONG
```

### 问题 2: "流式输出卡住" 或 "长时间不显示"

**检查清单：**
```bash
# 1. Qwen Worker 是否正在运行？
# 查看 Worker 终端是否显示任务日志

# 2. Qwen API Key 是否正确？
echo $env:DASHSCOPE_API_KEY
# 应显示密钥，而不是空白

# 3. Redis 队列中是否有数据？
redis-cli
> LLEN task_queue
# 应为 0（所有任务已处理）或 > 0（等待处理）
```

### 问题 3: "看到 JSON 在 UI 中"

**这是架构问题！**
```bash
# 检查 aiResult.js 中是否有：
# ❌ JSON.parse(TaskModel)
# ❌ taskModel.status
# ❌ taskModel.meta

# 这些都会导致 JSON 泄露到前端
# 前端只应该接收 append/done/error 三种消息
```

---

## 📝 修改记录（2026年2月28日）

### ✅ 改动内容

1. **Webview (aiResult.js)**
   - 只接收 `{ type: "append", content: string }`
   - 移除 JSON 解析，只做文本显示

2. **Extension (extension.ts)**
   - 改为 HTTP 调用（POST /task/submit）
   - 轮询获取结果（GET /task/result/:task_id）
   - 自动进行状态裁剪

3. **移除的文件**
   - `workerManager.ts` (不再需要 spawn Worker)
   - `worker_mvp.py` (直接使用 qwen_worker.py)

### ✅ 编译状态

```bash
npm run compile
# 输出: no errors
# 文件保存到: out/
```

---

## ✨ 次数功能检查

- [x] Webview 层实现完成
- [x] Extension HTTP 集成完成
- [x] 协议裁剪逻辑完成
- [x] 编译无错误
- [ ] 端到端功能测试（需要运行）
- [ ] qwen_worker.py 验证（已存在，保持原样）

---

## 🚀 下一步

### 验证步骤
1. 按上面的 30 秒快速开始运行
2. 输入 prompt，观察流式输出
3. 检查浏览器控制台（F12 Developer Tools）是否有错误

### 扩展步骤（未来）
- 添加更多 Worker（openai_worker.py、deepseek_worker.py）
- 实现 Persona 模块
- 支持更多任务类型
- **不需要修改 Webview！** 因为架构分离得很好

---

## 💡 核心原则（必读）

> **Webview 只是投影，Extension 做映射，Backend 才是真相**

- Webview 永远不知道 TaskModel
- Extension 永远不修改 TaskModel 内容
- Backend (qwen_worker.py) 永远遵守 TaskModel 格式

违反这些原则会导致架构污染！

2. 搜索之前的任务
3. 点击查看详情
4. 复制 prompt
5. 新建 AI 任务，粘贴 prompt ✓
```

### 场景 3：监控长任务执行

```
需求：想看 AI 生成的过程，不全是等等等
步骤：
1. 启动 AI 任务
2. 流式看内容一个字一个字出现
3. 如果中间结果满足要求，点 ⏸️
4. 继续工作，稍后再 ⏵️ 看后面的 ✓
```

---

## 💾 数据存储

### 历史数据
- **存储位置**：VS Code globalState（用户本地）
- **保留数量**：最多 50 条最新任务
- **生命周期**：永久保存（除非手动清空）

### 清理历史

如果想清空所有任务历史：
1. 打开任务历史面板
2. 点击 🗑️ 清空
3. 确认清空 → 完成

---

## ⚙️ 配置和自定义

目前默认配置，暂无用户配置选项。

如需以下功能，可以提需求：
- [ ] 调整保留的最大历史数
- [ ] 导出任务历史为 JSON
- [ ] 按日期/周/月归档
- [ ] 流式输出速度控制

---

## 🐛 故障排查

### 问题 1：打开命令面板找不到命令

**解决：**
确保插件已激活。激活条件：
- 已安装插件
- 已启用插件
- VS Code 版本 ≥ 1.80.0

### 问题 2：历史面板打不开

**解决：**
- 检查 WebSocket 连接（Ctrl+Shift+P → 查看输出）
- 确保 localhost:3000 后端服务运行中

### 问题 3：流式输出显示不全

**解决：**
- 检查后端是否发送了 `stream_chunk` 事件
- 查看浏览器控制台（插件窗口的 DevTools）

### 问题 4：暂停按钮不工作

**解决：**
- 确保 AI 任务正在流式传输中
- 刷新插件窗口后重试

---

## 📚 更多资源

- **功能详解**：见 [FEATURE_GUIDE.md](./FEATURE_GUIDE.md)
- **后端集成**：见 [BACKEND_INTEGRATION.md](./BACKEND_INTEGRATION.md)
- **核心代码**：
  - [taskHistory.ts](./src/taskHistory.ts) - 历史管理
  - [streamingManager.ts](./src/streamingManager.ts) - 流式管理
  - [aiResultPanel.ts](./src/panels/aiResultPanel.ts) - 输出面板

---

## 💡 设计理念

这次升级遵循几个核心原则：

1. **不改底层** ✓
   - 所有新功能都是加法，不修改现有接口
   - 完全向后兼容

2. **工程师友好** ✓
   - 流式输出像 ChatGPT/Cursor
   - 暂停功能像 Copilot
   - 历史面板像 GitHub Copilot

3. **开箱即用** ✓
   - 无需配置，装上即用
   - 数据自动保存
   - UI 自适应 VS Code 主题

4. **性能优化** ✓
   - 异步处理，不阻塞主线程
   - 事件驱动架构
   - 5 万+ 字符流仍然流畅

---

## 智能体执行引擎目标（2026-03-02）

1) 打造真正的“智能体执行引擎”
让我的助手不仅能执行任务，还能：

自主拆解任务

规划步骤

监控执行状态

失败自动恢复

多 worker 协同

这是从“工具”到“智能体”的关键跨越。

---

祝你使用愉快！有问题可以反馈。🎉
