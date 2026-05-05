# 🧪 端到端验证清单

> 使用本清单验证分布式任务系统的 TaskModel 统一格式实现

**执行日期**: _______________  
**执行者**: _______________  
**系统状态**: [ ] 开发环境 [ ] 测试环境 [ ] 生产环境

---

## 📋 Phase 0: 环境准备

- [ ] Node API 已启动（探听 localhost:3000）
- [ ] Python Worker 已启动（已连接到 Redis）
- [ ] VS Code 插件已加载（开发模式）
- [ ] Redis 已启动（探听 localhost:6379 或 Upstash）
- [ ] WebSocket 连接正常（/socket.io）

**验证命令:**
```bash
# Node API
curl http://localhost:3000/health

# Redis
redis-cli ping
# 或
curl https://api.upstash.io/v2/redis/...

# VS Code
在命令面板输入: "Tasks: Run Task" → 选择调试任务
```

---

## 📋 Phase 1: 任务提交格式验证

### Test 1.1: Node API 创建标准格式的提交请求

**操作步骤:**
1. 调用 POST /task/submit
```bash
curl -X POST http://localhost:3000/task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "a": 5,
    "b": 3,
    "type": "add_numbers",
    "source": "vscode-plugin"
  }'
```

**验证项:**
- [ ] 响应状态码为 200
- [ ] 响应包含 `task_id` 字段
- [ ] 响应包含 `status: "queued"` 或 `{ queued: true }`

**记录响应 task_id**: _______________

---

### Test 1.2: Redis 队列中的格式验证

**操作步骤:**
1. 查看 Redis task_queue 中的第一个项目
```bash
redis-cli
> LINDEX task_queue 0
```

或使用 Upstash Web 界面查看

**验证项:**
- [ ] 队列中包含完整的任务对象（JSON）
- [ ] JSON 包含以下字段：
  - [ ] `version: "1.0"`
  - [ ] `task_id: "<UUID>"`
  - [ ] `type: "add_numbers"`
  - [ ] `payload: { a: 5, b: 3 }`
  - [ ] `meta: { created_at: <timestamp>, source: "vscode-plugin" }`

**记录 Redis 中的任务格式（第一个 200 字符左右）:**
```json
{
  // 粘贴这里
}
```

---

## 📋 Phase 2: Worker 执行和结果格式验证

### Test 2.1: Python Worker 读取并处理任务

**操作步骤:**
1. 观看 Python Worker 的日志输出
2. 确认 Worker 已消费上一个任务

**验证项:**
- [ ] Worker 日志显示: "消费任务: ..." （或等价信息）
- [ ] Worker 日志显示任务 ID
- [ ] Worker 日志显示任务类型
- [ ] Worker 日志显示 payload 数据

**记录 Worker 日志片段:**
```
[时间] 消费任务: task_id=..., type=add_numbers
[时间] 执行结果: 8
```

---

### Test 2.2: Redis 中的结果格式验证

**操作步骤:**
1. 查看 Redis 中的结果

```bash
redis-cli
> GET task_result:<task_id>
```

或使用 Web 界面

**验证项 - 成功结果 (status: "done"):**
- [ ] 结果是完整的 JSON 对象
- [ ] 包含以下字段：
  - [ ] `version: "1.0"`
  - [ ] `task_id: "<与提交一致>"`
  - [ ] `type: "add_numbers"`
  - [ ] `status: "done"`
  - [ ] `result: { value: 8 }`（数值正确）
  - [ ] `error: null`
  - [ ] `meta.started_at: <timestamp>`
  - [ ] `meta.finished_at: <timestamp>`（晚于 started_at）
  - [ ] `meta.worker_id: "python-worker-1"` 或类似
  - [ ] `meta.duration_ms: <number>` （>0）

**记录结果格式:**
```json
{
  // 粘贴这里
}
```

---

### Test 2.3: HTTP 通知验证

**操作步骤:**
1. 检查 Node API 日志
2. 确认收到 Python Worker 的 POST /task/notify 请求

**验证项:**
- [ ] Node API 日志显示: "收到任务结果通知: ..." 或等价信息
- [ ] Node API 日志显示任务 ID
- [ ] Node API 日志显示格式验证结果: "✅ 格式有效" 或 "❌ 格式错误"
  - [ ] 如果显示 "❌ 格式错误"，必须失败此测试（返回上一步检查格式）

**记录 Node API 日志:**
```
[时间] [POST] /task/notify/... 
[时间] 收到任务结果通知: task_id=..., status=done
[时间] ✅ 格式验证成功
```

---

## 📋 Phase 3: WebSocket 推送验证

### Test 3.1: VS Code 插件接收 WebSocket 消息

**操作步骤:**
1. 打开 VS Code 调试控制台
2. 观看输出面板（或开发者工具）
3. 执行一个新的任务（重复 Test 1.1）
4. 等待 3-5 秒

**验证项:**
- [ ] 输出面板或控制台显示收到的任务结果
- [ ] 消息格式显示为完整的 JSON 对象（不是片段）
- [ ] 日志包含类似 "📡 收到任务结果推送" 的消息
- [ ] VS Code 显示一个 notification（通知）或在输出中显示结果

**记录 VS Code 输出:**
```
[时间] 📡 收到任务结果推送（标准格式）: {
  "version": "1.0",
  "task_id": "...",
  // ...
}
```

---

### Test 3.2: VS Code 格式验证

**操作步骤:**
1. 在 extension.ts 中查看验证日志
2. 或观看开发控制台输出

**验证项:**
- [ ] 显示 "✅ 格式验证成功" 或等价消息
- [ ] 如果格式有效，显示 "📊 任务结果: ..." 的易读描述
- [ ] 如果有错误，显示完整的 JSON 用于调试

**记录验证结果:**
```
[时间] 📊 任务结果: ✅ 任务成功 | 结果: 8 | 耗时: 1234ms | Worker: python-worker-1
```

---

## 📋 Phase 4: 错误场景验证

### Test 4.1: 创建错误的任务（触发失败）

**操作步骤:**
1. 修改 POST /task/submit 请求，使 payload 因数
```bash
curl -X POST http://localhost:3000/task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "a": "not_a_number",
    "b": 3,
    "type": "add_numbers",
    "source": "test-error"
  }'
```

**验证项:**
- [ ] 任务被提交（返回 200 和 task_id）
- [ ] Python Worker 尝试处理但失败
- [ ] Worker 日志显示错误信息

**记录 task_id**: _______________

**记录 Worker 错误日志:**
```
[时间] 错误: ...
[时间] 重试 1/3...
```

---

### Test 4.2: Redis 中的错误结果格式

**操作步骤:**
1. 查看 Redis 中的结果

```bash
redis-cli
> GET task_result:<error_task_id>
```

**验证项 - 错误结果 (status: "error"):**
- [ ] 结果包含以下字段：
  - [ ] `version: "1.0"`
  - [ ] `task_id: "<与提交一致>"`
  - [ ] `type: "add_numbers"`
  - [ ] `status: "error"`
  - [ ] `result: null`
  - [ ] `error.message: "<错误信息>"`
  - [ ] `error.code: "INVALID_INPUT"` 或其他合理的错误码
  - [ ] `error.stack: "<错误堆栈>"` 或 null
  - [ ] `error.retryable: <true|false>`（根据错误类型）
  - [ ] `meta.retry_count: 3` 或其他重试次数

**记录错误结果:**
```json
{
  // 粘贴这里
}
```

---

### Test 4.3: WebSocket 推送错误结果

**操作步骤:**
1. 观看 VS Code 输出面板
2. 确认收到错误结果的 WebSocket 推送

**验证项:**
- [ ] VS Code 显示错误提示（红色通知）
- [ ] 输出面板显示 "❌ 任务失败" 的消息
- [ ] 显示错误消息和错误码
- [ ] 如果 retryable=true，显示 "⚠️ 可重试错误"
- [ ] 如果 retryable=false，显示 "❌ 不可恢复错误"

**记录 VS Code 错误输出:**
```
[时间] ❌ 任务失败 | 错误: ... | 不可重试 | 耗时: ...
[时间] 原始数据: {...}
```

---

## 📋 Phase 5: DLQ（死亡队列）验证

### Test 5.1: 查看 DLQ 中的项目

**操作步骤:**
1. 查看 Redis 中的 DLQ

```bash
redis-cli
> LINDEX dlq 0
```

**验证项 - DLQ 项目格式:**
- [ ] DLQ 包含完整的 JSON 对象
- [ ] 包含以下字段：
  - [ ] `version: "1.0"`
  - [ ] `task_id: "<error_task_id>"`
  - [ ] `original_task: { ... }` 完整的原始任务对象
  - [ ] `failure_record: { message, code, stack, retryable }`
  - [ ] `retry_count: 3` 或其他重试次数
  - [ ] `first_failed_at: <timestamp>`
  - [ ] `last_failed_at: <timestamp>`（晚于 first_failed_at）
  - [ ] `meta.reason: "exceeded_max_retries"` 或 "non_retryable"`

**记录 DLQ 项目:**
```json
{
  // 粘贴这里
}
```

---

### Test 5.2: 验证 DLQ 端点

**操作步骤:**
1. 调用 GET /dlq 获取所有 DLQ 项目

```bash
curl http://localhost:3000/dlq
```

**验证项:**
- [ ] 返回状态码 200
- [ ] 返回数组（至少 1 个项目）
- [ ] 每个项目都是标准格式的 DLQ 对象

---

## 📋 Phase 6: 轮询模式验证（无 WebSocket）

### Test 6.1: 禁用 WebSocket 并使用轮询

**操作步骤:**
1. 临时禁用 VS Code 中的 WebSocket 连接
2. 提交一个新任务
3. 观看 VS Code 是否使用轮询模式获取结果

或手动轮询：
```bash
# 提交任务
curl -X POST http://localhost:3000/task/submit ...

# 获取 task_id 后，轮询结果
curl http://localhost:3000/task/result/<task_id>
```

**验证项:**
- [ ] 轮询请求返回完整的结果对象
- [ ] 如果任务未完成，返回 `{ status: "pending" }`
- [ ] 如果任务完成，返回标准格式的结果
- [ ] 轮询也能正确解析标准格式

**记录轮询响应:**
```json
{
  // 粘贴这里
}
```

---

## 📋 Phase 7: 数据格式验证总结

### 验证检查列表

检查以下 4 个关键的数据流点：

**点 1: 任务提交 (Task Submit)**
```json
{
  "version": "1.0",
  "task_id": "UUID",
  "type": "add_numbers",
  "payload": { "a": 5, "b": 3 },
  "meta": {
    "created_at": <timestamp>,
    "source": "vscode-plugin"
  }
}
```
- [ ] 格式正确
- [ ] 所有必需字段都存在
- [ ] 时间戳是毫秒级整数

**点 2: 成功结果 (Task Result Success)**
```json
{
  "version": "1.0",
  "task_id": "UUID",
  "type": "add_numbers",
  "status": "done",
  "result": { "value": 8 },
  "error": null,
  "meta": {
    "started_at": <timestamp>,
    "finished_at": <timestamp>,
    "worker_id": "python-worker-1",
    "duration_ms": <number>
  }
}
```
- [ ] 格式正确
- [ ] status="done"（不是 "success"）
- [ ] result 包装在对象中
- [ ] error 明确设为 null（不是省略）
- [ ] duration_ms 是正数

**点 3: 错误结果 (Task Result Error)**
```json
{
  "version": "1.0",
  "task_id": "UUID",
  "type": "add_numbers",
  "status": "error",
  "result": null,
  "error": {
    "message": "错误信息",
    "code": "ERROR_CODE",
    "stack": null,
    "retryable": false
  },
  "meta": {
    "started_at": <timestamp>,
    "finished_at": <timestamp>,
    "worker_id": "python-worker-1",
    "duration_ms": <number>,
    "retry_count": 3
  }
}
```
- [ ] 格式正确
- [ ] status="error"
- [ ] result 明确设为 null
- [ ] error 是完整对象（不是字符串）
- [ ] retryable 是布尔值

**点 4: DLQ 项目 (DLQ Item)**
```json
{
  "version": "1.0",
  "task_id": "UUID",
  "original_task": { ... },
  "failure_record": { message, code, stack, retryable },
  "retry_count": 3,
  "first_failed_at": <timestamp>,
  "last_failed_at": <timestamp>,
  "meta": {
    "created_at": <timestamp>,
    "reason": "exceeded_max_retries"
  }
}
```
- [ ] 格式正确
- [ ] original_task 完整保存
- [ ] 时间戳一致

---

## 📋 Phase 8: 验证总结

完成所有测试后，填写以下总结：

### 成功率

| 测试阶段 | 测试数量 | 通过数量 | 失败数量 | 成功率 |
|---------|--------|--------|--------|------|
| Phase 1: 提交格式 | 2 | __ | __ | __% |
| Phase 2: Worker 执行 | 3 | __ | __ | __% |
| Phase 3: WebSocket 推送 | 2 | __ | __ | __% |
| Phase 4: 错误场景 | 3 | __ | __ | __% |
| Phase 5: DLQ 验证 | 2 | __ | __ | __% |
| Phase 6: 轮询模式 | 1 | __ | __ | __% |
| **总计** | **13** | __ | __ | __%  |

### 发现的问题

**问题 1:**
- 描述: _______________
- 位置: _______________（Node / Worker / Plugin）
- 严重程度: [ ] 严重 [ ] 中等 [ ] 轻微
- 解决方案: _______________

**问题 2:**
- 描述: _______________
- 位置: _______________
- 严重程度: [ ] 严重 [ ] 中等 [ ] 轻微
- 解决方案: _______________

### 验证结论

- [ ] **全部通过** - 系统完全符合 TaskModel 1.0 规范
- [ ] **大部分通过** - 系统符合规范，但有 __ 个小问题需要修复
- [ ] **部分通过** - 系统基本符合规范，但有重要问题需要修复
- [ ] **未通过** - 系统与规范有重大差异，需要重新实现

### 签名

验证人: _______________  
日期: _______________  
环境: _______________（localhost / staging / production）

---

## 📖 参考文档

- [完整规范](./TASK_MODEL_SPECIFICATION.md)
- [快速参考](./TASK_MODEL_QUICK_REFERENCE.md)
- Node.js 实现: [taskModel.js](./node-api/taskModel.js)
- Python 实现: [task_model.py](./python-worker/task_model.py)
- TypeScript 实现: [taskModel.ts](./vscode-extension/src/taskModel.ts)
