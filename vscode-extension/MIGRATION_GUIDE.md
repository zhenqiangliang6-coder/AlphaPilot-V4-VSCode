# AlphaPilot MVP 文档迁移说明

> **日期**: 2026年2月28日  
> **版本**: MVP 0.1.0  
> **状态**: 文档更新完成

---

## 📋 文档更新汇总

### ✅ 已更新文档

| 文件名 | 变化 | 说明 |
|--------|------|------|
| **README.md** | 🔄 重写 | 添加 MVP 架构说明、修改清单、禁止清单 |
| **QUICKSTART.md** | 🔄 重写 | 从旧的流式特性改为 HTTP/Redis 架构 |

### ✨ 新增文档（MVP 专用）

| 文件名 | 用途 |
|--------|------|
| **FEATURE_GUIDE_MVP.md** | MVP 功能详细说明（3 个命令） |
| **BACKEND_INTEGRATION_MVP.md** | 后端集成指南（HTTP + Redis） |
| **（本文件）** | 文档迁移说明 |

### ⚠️ 旧文档保留

以下旧文档**保持不动**，以防后续版本需要参考：

- `FEATURE_GUIDE.md`（旧版本）
- `BACKEND_INTEGRATION.md`（WebSocket 版本）
- `STREAMING_TEST_GUIDE.md`（旧的生成文使用指南）

---

## 🎯 文档导航

### 快速开始
→ **[QUICKSTART.md](QUICKSTART.md)** 
- 30 秒启动三个服务
- 运行第一个命令
- 故障排除

### 功能和架构
→ **[FEATURE_GUIDE_MVP.md](FEATURE_GUIDE_MVP.md)**
- 3 个 MVP 命令说明
- 数据流图
- 三层架构细节

### 后端集成
→ **[BACKEND_INTEGRATION_MVP.md](BACKEND_INTEGRATION_MVP.md)**
- API 端点说明
- Worker 实现示例
- 本地测试清单

### 项目全景
→ **[README.md](README.md)**
- 整体设计思想
- 禁止清单（不要做什么）
- 后续扩展路线

---

## 🔄 核心改动

### 从旧版本迁移的用户，重点关注：

#### ❌ 旧方式（已弃用）

```typescript
// ❌ 直接生成进程（不再使用）
const { spawn } = require('child_process');
const worker = spawn('python', ['qwen_worker.py']);
worker.stdout.on('data', (data) => { ... });
```

```
弊端：
- 扩展层直接管理进程（职责混乱）
- 难以横向扩展（每个扩展发起一个进程）
- 前端收到原始 JSON（结构混乱）
```

#### ✅ 新方式（HTTP + Redis）

```typescript
// ✅ HTTP 调用（现在使用）
const response = await fetch('http://localhost:3000/task/submit', {
  method: 'POST',
  body: JSON.stringify({ type: 'qwen_generate', payload: { prompt } })
});

// ✅ 轮询结果（自动）
const result = await fetch(`http://localhost:3000/task/result/${taskId}`);
```

```
优点：
- 清晰的三层分离
- 易于添加新 Worker（redis.rpop 自动竞争）
- 前端只接收简化消息（append/done/error）
```

---

## 🛠️ 文件清理检查清单

### 应该删除的文件

以下文件是架构错误的产物，应该删除：

```
vscode-extension/
├── src/
│   └── workerManager.ts  ← 删除（不再使用）
│   └── out/workerManager.js  ← 删除（编译产物）

python-worker/
├── worker_mvp.py  ← 删除（不必要）
```

**删除命令：**
```bash
# Windows PowerShell
Remove-Item "c:\Users\DavidLiang\Desktop\my-distributed-system\vscode-extension\src\workerManager.ts"
Remove-Item "c:\Users\DavidLiang\Desktop\my-distributed-system\vscode-extension\out\workerManager.js"
Remove-Item "c:\Users\DavidLiang\Desktop\my-distributed-system\python-worker\worker_mvp.py"
```

### 应该保留的文件

```
vscode-extension/src/
├── extension.ts ✓ （已更新 HTTP 版本）
├── aiResultPanel.ts ✓ （已简化）
├── streamingManager.ts ✓ （已更新）
├── panels/
│   └── aiResultPanel.ts ✓
├── webviews/
│   ├── aiResult.js ✓ （已简化）
│   └── aiResult.html ✓ （已简化）

python-worker/
├── qwen_worker.py ✓ （保持不变，这是真相）
└── requirements.txt ✓

node-api/
├── index.js ✓ （保持不变）
```

---

## 📝 编码规范更新

### Extension 层（src/extension.ts）

**规则：**
```typescript
✅ 允许:
- HTTP fetch() 调用
- 轮询逻辑（setInterval）
- TaskModel 解析和字段提取
- panel 方法调用

❌ 禁止:
- process.spawn()
- 启动子进程
- 修改 TaskModel 内容
- JSON.stringify(TaskModel) 直接发送给 Webview
```

### Webview 层（webviews/aiResult.js）

**规则：**
```javascript
✅ 允许:
- textContent += msg.content  // 纯文本拼接
- addEventListener('message', ...)
- DOM 操作（textContent, innerHTML for text only）

❌ 禁止:
- JSON.parse()  // 不要解析 TaskModel
- taskModel.status  // 不要访问 TaskModel 字段
- 任何与协议相关的逻辑  // 协议由 Extension 负责
```

### Worker 层（python-worker/qwen_worker.py）

**规则：**
```python
✅ 必须:
- redis.rpop('task_queue')  // 读取任务
- JSON 输出 TaskModel（包含 version, task_id, type, status）
- redis.set(f'task_result:{task_id}', json_output)  // 保存结果

❌ 禁止:
- 修改 TaskModel 版本号
- 省略必要字段（version, task_id, type, status）
- 直接写 stdout 给 Extension（应该通过 Redis）
```

---

## 🚀 验证完成情况

### ✅ MVP 代码完成

- [x] Webview 简化完成（3 个消息类型）
- [x] Extension HTTP 集成完成
- [x] aiResultPanel 简化完成
- [x] streamingManager 方法更新完成
- [x] TypeScript 编译成功（Exit Code 0）

### ✅ 文档更新完成

- [x] README.md 更新
- [x] QUICKSTART.md 更新
- [x] FEATURE_GUIDE_MVP.md 创建
- [x] BACKEND_INTEGRATION_MVP.md 创建
- [x] 本迁移指南创建

### ⏳ 待完成

- [ ] 删除 workerManager.ts 和 worker_mvp.py
- [ ] 端到端功能测试（实际运行）
- [ ] 检查 worker.py 是否需要恢复/修复
- [ ] 性能测试（轮询 500ms 的实际影响）

---

## 📞 常见问题

### Q: 为什么要重写这些文档？

**A:** 
原来的文档描述的是带流式特性的复杂版本：
- 包含暂停/继续按钮
- WebSocket 通信
- 复杂的状态管理

MVP 目标是放弃这些，回到最简单的工作版本：
- HTTP 轮询（不需要 WebSocket）
- 无状态管理（无需暂停/继续）
- 三层清晰分离

### Q: 旧文档会被删除吗？

**A:** 不会。旧文档保留作参考。新用户应该看 QUICKSTART.md。

### Q: 能用新代码+旧 Worker 吗？

**A:** 不能。新代码假设 Worker 输出标准 TaskModel（version 1.0）。如果你用旧 Worker，需要确保它输出这个格式。

### Q: 什么时候可以添加更多 Worker？

**A:** 任何时候。因为 Redis 队列天然支持多 Worker。只需：
1. 启动新的 Worker（比如 openai_worker.py）
2. 让它也读 task_queue RPOP
3. 无需改 Extension 或 Webview

---

## 📚 下一步行动

### 推荐顺序

1. **阅读新文档**
   - [QUICKSTART.md](QUICKSTART.md) - 了解怎么运行
   - [FEATURE_GUIDE_MVP.md](FEATURE_GUIDE_MVP.md) - 了解做了什么

2. **清理代码**
   - 删除 workerManager.ts
   - 删除 worker_mvp.py

3. **运行和测试**
   - 启动 Node API + Redis + Qwen Worker
   - 运行 VSCode Extension (F5)
   - 执行代码补全命令

4. **验证**
   - 输出是否流式了？
   - 历史是否自动保存了？
   - 编译是否通过了？

---

## 🎯 设计哲学总结

> **三层：投影 (Webview) → 映射 (Extension) → 真相 (Worker)**

- **Webview** 尽可能傻：只拼接文本，只知道 append/done/error
- **Extension** 职责清晰：只做状态转换（TaskModel → 简化消息）
- **Worker** 完整输出：完整的 TaskModel，包含所有元数据

违反这个原则会导致：
- 功能污染（Webview 也知道业务逻辑）
- 版本问题（Webview 和 TaskModel 版本耦合）
- 扩展困难（添加新 Worker 需要改 Webview）

坚持这个原则，系统就很容易扩展 ✨
