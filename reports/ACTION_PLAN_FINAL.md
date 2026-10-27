#  AlphaPilot 前端输出问题完整解决方案

## ✅ 已完成的修复

### 1. ✅ Worker v2 添加 /task/notify 调用
- 文件: `python_worker/agents/qwen/qwen_worker_v2.py`
- 状态: ✅ 已完成
- 内容: 在任务成功和失败时都调用 `/task/notify` 通知 Node.js

### 2. ✅ Extension 使用 Socket.IO 客户端
- 文件: `vscode-extension/src/services/websocketService.ts`
- 状态: ✅ 已完成 (已安装 `socket.io-client`)
- 内容: 使用 `socket.io-client` 连接 Node.js Socket.IO 服务器

### 3. ✅ 前端事件名称修复
- 文件: `vscode-extension/src/panels/reactPanel.ts`
- 状态: ✅ 已完成并编译
- 内容: 添加 `task_result` 事件监听,并正确映射到 `task_completed`/`task_failed`

---

## 🚨 当前问题

**Worker v2 还没有重启,所以 `/task/notify` 还没有被调用!**

从日志可以看到:
```
任务完成，结果已写入 Redis
```
**但没有看到:**
```
📡 正在通知 Node.js: http://localhost:3000/task/notify/{task_id}
✅ Node.js 已成功接收通知，将推送给前端
```

---

## ️ 现在必须执行的步骤

### 步骤 1: 重启 Qwen Worker v2

```powershell
# 在运行 Worker 的终端按 Ctrl+C 停止
# 然后重新启动
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker
python agents/qwen/qwen_worker_v2.py
```

**预期看到:**
```
🚀 Qwen Worker v2 已启动
   · Worker ID: qwen-worker-1
   · Node API: 已连接
   · 正在监听任务队列...
 监听队列: task_queue:qwen
```

### 步骤 2: 提交新任务测试

1. 打开 AlphaPilot Chat 面板 (`Ctrl+Shift+A`)
2. 输入: **"请用python帮我写一个简单的冒泡排序"**
3. 选择模型: **Qwen**
4. 点击发送

### 步骤 3: 观察日志

#### ✅ Qwen Worker 控制台应该看到:
```
 监听队列: task_queue:qwen
============================================================
收到任务: {...}
============================================================
[WARN] extract_code failed to extract code from text (length=79)
[INFO] Fallback to original code (optimization failed)
任务完成，结果已写入 Redis:
{...}
📡 正在通知 Node.js: http://localhost:3000/task/notify/22cc411c-...
✅ Node.js 已成功接收通知，将推送给前端
```

#### ✅ Node.js 控制台应该看到:
```
📡 收到任务完成通知：22cc411c-f985-4982-a700-3d13c4b37ff1
📦 推送完整的标准格式数据：
{...}
📡 向 1 个订阅者推送任务结果：22cc411c-f985-4982-a700-3d13c4b37ff1
```

#### ✅ VSCode 开发者工具应该看到:
```
🔌 正在连接 Socket.io: ws://localhost:3000
✅ Socket.io 已连接
📡 订阅任务：22cc411c-f985-4982-a700-3d13c4b37ff1
 收到事件: subscribed {...}
 WebSocket: task_started {...}
 WebSocket: step_started {...}
📥 WebSocket: step_finished {...}
📥 WebSocket: task_result {...}
📤 转发到 Webview - task_id: 22cc411c-...
📥 Extension → Webview: {type: 'task_completed', ...}
```

#### ✅ 前端 Webview 应该看到:
- ✅ 用户消息: "请用python帮我写一个简单的冒泡排序"
- ✅ AI 开始思考 (status: "AI 思考中...")
- ✅ 步骤进度显示:
  - ✅ analyze (分析)
  - ✅ plan (规划)
  - ✅ write (编写)
  - ✅ refine (优化)
- ✅ 最终代码显示在消息气泡中

---

## 🔍 如果还是没有输出,按以下步骤排查

### 检查点 1: Worker 是否调用了 /task/notify?

**在 Worker 控制台搜索:**
```
正在通知 Node.js
```

**如果没有看到:**
- Worker 可能还在运行旧代码
- 必须重启 Worker

### 检查点 2: Node.js 是否收到通知?

**在 Node.js 控制台搜索:**
```
收到任务完成通知
```

**如果没有看到:**
- Worker 的 `/task/notify` 调用失败
- 检查 Worker 控制台的错误信息

### 检查点 3: Node.js 是否推送了 WebSocket 消息?

**在 Node.js 控制台搜索:**
```
向 X 个订阅者推送任务结果
```

**如果看到 "向 0 个订阅者推送":**
- 前端没有订阅任务
- 检查 `websocketService.subscribeTask(taskId)` 是否被调用

### 检查点 4: Extension 是否收到 Socket.IO 事件?

**在 VSCode 开发者工具 Console 搜索:**
```
📥 收到事件: task_result
```

**如果没有看到:**
- Socket.IO 连接断开
- 重新加载 VSCode 窗口 (`Ctrl+Shift+P` → "Reload Window")

### 检查点 5: Webview 是否收到 Extension 消息?

**在 VSCode 开发者工具 Console 搜索:**
```
📥 Extension → Webview
```

**如果没有看到:**
- reactPanel.ts 没有转发消息
- 检查 `this.panel.webview.postMessage` 是否被调用

---

## 🎯 快速验证命令

### 验证 Worker 是否更新了代码
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker
Select-String -Path "agents/qwen/qwen_worker_v2.py" -Pattern "task/notify"
```
**应该看到 2 处匹配:**
- 成功时调用
- 失败时调用

### 验证 Extension 是否编译了最新代码
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension
Select-String -Path "out/panels/reactPanel.js" -Pattern "task_result"
```
**应该看到 3 处匹配:**
- `task_result` 监听器
- 状态判断逻辑
- `task_completed` 转发

---

##  完整的数据流

```
1. 用户提交任务
   ↓
2. Extension → Node.js (HTTP POST /task/submit)
   ↓
3. Node.js → Redis 队列 (LPUSH task_queue:qwen)
   ↓
4. Worker 从队列获取任务 (RPOP)
   ↓
5. Worker 执行任务 (analyze → plan → write → refine → test)
   ↓
6. Worker 写入 Redis (SET task_result:{task_id})
   ↓
7. ⭐ Worker 调用 Node.js /task/notify (HTTP POST)  ← 新修复!
   ↓
8. Node.js 通过 Socket.IO 广播 (socket.emit("task_result"))
   ↓
9. Extension 的 Socket.IO 客户端收到事件 (onAny)
   ↓
10. websocketService 触发 'task_result' 事件
   ↓
11. reactPanel.ts 监听到 'task_result'  ← 新修复!
   ↓
12. reactPanel 转发给 Webview (postMessage)
   ↓
13. Webview React 收到消息 (window.addEventListener)
   ↓
14. App.tsx 更新状态 (handleTaskCompleted)
   ↓
15. ✅ 用户看到最终代码!
```

---

##  总结

**所有代码修复已完成,现在只需要:**

1. **重启 Qwen Worker v2** (加载新代码)
2. **提交新任务测试** (验证完整流程)
3. **观察日志** (确认每个环节都正常工作)

**如果还是有问题,按检查点 1-5 逐步排查!**

---

*修复完成时间: 2026-05-04*  
*下一步: 重启 Worker 并测试*
