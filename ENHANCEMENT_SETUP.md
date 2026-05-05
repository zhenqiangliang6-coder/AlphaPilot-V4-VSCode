# 分布式任务系统 - 4 个增强功能配置指南

## ✅ 已完成的增强功能

### 【任务 1】任务超时机制 ✓
- **位置**：`node-api/index.js` - `/task/submit` 和 `/task/result` 接口
- **功能**：记录任务开始时间，超过 10 秒返回 `{ status: "timeout", result: null }`
- **Redis 存储**：`task_start_time:{task_id}`

### 【任务 2】失败重试机制 ✓
- **位置**：`python-worker/worker.py` - 主循环中
- **功能**：捕获异常后自动重试最多 3 次，每次间隔 1 秒
- **失败处理**：写入 DLQ 队列

### 【任务 3】死信队列（DLQ） ✓
- **位置**：`node-api/index.js` - `/dlq/*` 接口
- **功能**：管理永远失败的任务
- **Redis 队列**：`dlq`
- **数据格式**：`{ task_id, error, payload }`
- **可用 API**：
  - `GET /dlq/items` - 查询所有 DLQ 项目
  - `GET /dlq/item/:task_id` - 查询特定项目
  - `DELETE /dlq/item/:task_id` - 删除项目

### 【任务 4】WebSocket 实时推送 ✓
- **位置**：`node-api/index.js` 和 `vscode-extension/src/extension.ts`
- **功能**：替代轮询，实时推送任务结果
- **通信流程**：
  1. 插件连接 WebSocket
  2. 订阅任务结果
  3. Worker 完成后通知 Node API
  4. Node API 推送给插件

---

## 🚀 安装依赖

### Node API
```bash
cd node-api
npm install
```

### Python Worker
```bash
cd python-worker
pip install -r requirements.txt
```

### VS Code 插件
```bash
cd vscode-extension
npm install
```

---

## ⚙️ 环境变量配置

在项目根目录或各子文件夹创建 `.env` 文件：

### `.env`（根目录）
```env
# Upstash Redis 配置
UPSTASH_REDIS_REST_URL=your_redis_url
UPSTASH_REDIS_REST_TOKEN=your_redis_token

# Node API 地址（供 Worker 调用）
NODE_API_URL=http://localhost:3000
```

---

## 🏃 启动步骤

1. **启动 Node API**（WebSocket + REST）
   ```bash
   cd node-api
   npm install
   node index.js
   ```
   端口：3000
   - HTTP：`http://localhost:3000`
   - WebSocket：`ws://localhost:3000`

2. **启动 Python Worker**（监听队列）
   ```bash
   cd python-worker
   pip install -r requirements.txt
   python worker.py
   ```

3. **启动 VS Code 插件**（自动连接 WebSocket）
   ```bash
   cd vscode-extension
   npm install
   npm run compile
   # 然后在 VS Code 中按 F5 启动调试
   ```

---

## 📊 各功能的技术栈

| 功能 | 实现位置 | 技术 | 存储 |
|------|---------|------|------|
| **超时检测** | Node API | 时间戳 + 条件判断 | Redis hash |
| **重试机制** | Worker | Try-catch + 循环 | 内存 |
| **DLQ 管理** | Node API + Worker | REST API | Redis list |
| **WebSocket** | Node API + 插件 | socket.io | 内存 map |

---

## 🔍 测试各功能

### 测试超时机制（10 秒）
```bash
# 提交任务后立即查询
curl http://localhost:3000/task/submit -H "Content-Type: application/json" -d '{"a":10,"b":5}'

# 等待超过 10 秒后再查询
curl http://localhost:3000/task/result/{task_id}
# 返回：{ "status": "timeout", "result": null }
```

### 测试重试机制
在 Worker 中提交包含错误类型的任务（如字符串），Worker 会：
1. 尝试执行，捕获类型错误
2. 重试 3 次，每次间隔 1 秒
3. 全部失败后写入 DLQ

### 查询 DLQ
```bash
# 查询所有失败任务
curl http://localhost:3000/dlq/items

# 查询特定任务
curl http://localhost:3000/dlq/item/{task_id}

# 删除任务
curl -X DELETE http://localhost:3000/dlq/item/{task_id}
```

### 测试 WebSocket
插件会自动连接 WebSocket 并订阅任务结果。提交任务时：
1. 插件显示"已连接"
2. 任务提交后自动订阅
3. Worker 完成即时推送结果
4. 插件输出面板实时显示结果

---

## 📝 关键代码片段

### 超时检查（Node API）
```javascript
// 检查 10 秒超时
if (elapsedTime > 10) {
  return res.json({ status: "timeout", result: null });
}
```

### 重试逻辑（Worker）
```python
for attempt in range(1, MAX_RETRIES + 1):
    try:
        result_value = a - b
        success = True
        break
    except Exception as e:
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
```

### WebSocket 推送（Node API）
```javascript
socket.emit("task_result", {
  task_id: taskId,
  status: result.status,
  result: result.result,
});
```

### 订阅任务（插件）
```typescript
websocket.emit("subscribe_task", taskId);
websocket.on("task_result", (data) => {
  // 处理结果
});
```

---

## ⚡ 快速对比

### 旧系统 vs 新系统

| 特性 | 旧系统 | 新系统 |
|------|--------|--------|
| 结果获取 | 轮询（1秒间隔） | WebSocket 实时推送 |
| 任务超时 | 无限等待 | 10 秒超时限制 |
| 失败处理 | 直接失败 | 最多重试 3 次 |
| 失败记录 | 丢弃 | 写入 DLQ 专用队列 |

---

## 🆘 常见问题

**Q：WebSocket 连接失败？**
A：确保 Node API 已启动，地址为 `http://localhost:3000`

**Q：Worker 无法连接 Node API？**
A：检查 `.env` 文件中的 `NODE_API_URL`，确保 Node API 正在运行

**Q：DLQ 队列不显示失败任务？**
A：检查 Worker 日志，确认任务是否真的失败了 3 次

**Q：超时时间太短？**
A：修改 `node-api/index.js` 中的 `if (elapsedTime > 10)` 条件

---

## 📌 下次修改需求

如需修改：
- 超时时间：编辑 `node-api/index.js` 第 165 行
- 重试次数：编辑 `python-worker/worker.py` 第 27 行
- WebSocket 连接地址：编辑 `vscode-extension/src/extension.ts` 第 25 行

```
# 智能体执行引擎目标（2026-03-02）

1) 打造真正的“智能体执行引擎”
让我的助手不仅能执行任务，还能：

自主拆解任务

规划步骤

监控执行状态

失败自动恢复

多 worker 协同

这是从“工具”到“智能体”的关键跨越。
