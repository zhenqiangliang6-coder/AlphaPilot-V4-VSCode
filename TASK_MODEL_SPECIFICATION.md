# 📋 分布式任务系统 - 统一 JSON 格式架构（最终版）

**执行状态**：✅ 完全落地  
**更新时间**：2026年2月23日  
**架构版本**：1.0

---

## 📌 核心目标

在分布式任务处理系统中实现**彻底的 JSON 格式统一**，确保：
- ✅ 所有模块之间数据结构一致
- ✅ 未来扩展不破坏现有逻辑
- ✅ 每一层（Node、Python、TypeScript）都有规范定义
- ✅ 完整的格式验证和类型检查

---

## 🏗️ 系统架构

```
VS Code 插件
    ↓ (task_submit 格式)
Node API (Express/Socket.IO)
    ↓ (task_queue)
Redis (Upstash)
    ↓ (task_result/dlq)
  Python Worker
    ↓ (task_notify)
  WebSocket 推送
    ↓
  VS Code 插件 (接收结果)
```

---

## 📦 数据格式规范

### 【1】任务提交格式（VSCode → Node API → Redis → Worker）

**JSON Schema:**
```json
{
  "version": "1.0",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "add_numbers",
  "payload": {
    "a": 5,
    "b": 3
  },
  "meta": {
    "created_at": 1708614000000,
    "source": "vscode-plugin"
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | string | 数据格式版本（固定 "1.0"） |
| `task_id` | string | 唯一任务标识（UUID） |
| `type` | string | 任务类型（add_numbers、subtract、multiply 等） |
| `payload` | object | 业务数据（具体内容因任务类型而异） |
| `meta.created_at` | number | 创建时间（毫秒时间戳） |
| `meta.source` | string | 来源（vscode-plugin / web / api） |

**代码生成示例：**

Node.js (taskModel.js):
```javascript
TaskModel.createTaskSubmit(
  "550e8400-e29b-41d4-a716-446655440000",
  "add_numbers",
  { a: 5, b: 3 },
  "vscode-plugin"
)
```

Python (task_model.py):
```python
TaskModel.create_task_submit(
  task_id="550e8400-e29b-41d4-a716-446655440000",
  task_type="add_numbers",
  payload={"a": 5, "b": 3},
  source="vscode-plugin"
)
```

TypeScript (taskModel.ts):
```typescript
{
  version: "1.0",
  task_id: "550e8400-e29b-41d4-a716-446655440000",
  type: "add_numbers",
  payload: { a: 5, b: 3 },
  meta: {
    created_at: Date.now(),
    source: "vscode-plugin"
  }
}
```

---

### 【2】任务执行成功（Worker → Redis → WebSocket → VSCode）

**JSON Schema:**
```json
{
  "version": "1.0",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "add_numbers",
  "status": "done",
  "result": {
    "value": 8
  },
  "error": null,
  "meta": {
    "started_at": 1708614005000,
    "finished_at": 1708614006500,
    "worker_id": "python-worker-1",
    "duration_ms": 1500
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | string | 数据格式版本 |
| `task_id` | string | 对应的任务 ID |
| `type` | string | 任务类型（与原始提交一致） |
| `status` | string | 执行状态：`"done"` |
| `result` | object | 执行结果（具体内容因任务类型而异） |
| `error` | null | 成功时必须为 null |
| `meta.started_at` | number | 执行开始时间（毫秒） |
| `meta.finished_at` | number | 执行完成时间（毫秒） |
| `meta.worker_id` | string | 执行该任务的 Worker ID |
| `meta.duration_ms` | number | 执行耗时（毫秒） |

---

### 【3】任务执行失败（Worker → Redis → WebSocket → VSCode）

**JSON Schema:**
```json
{
  "version": "1.0",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "add_numbers",
  "status": "error",
  "result": null,
  "error": {
    "message": "参数必须是数字",
    "code": "INVALID_INPUT",
    "stack": "Traceback (most recent call last):\n  ...",
    "retryable": false
  },
  "meta": {
    "started_at": 1708614005000,
    "finished_at": 1708614006500,
    "worker_id": "python-worker-1",
    "duration_ms": 1500,
    "retry_count": 3
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 执行状态：`"error"` |
| `result` | null | 失败时必须为 null |
| `error.message` | string | 错误描述信息 |
| `error.code` | string | 错误代码（INVALID_INPUT、TIMEOUT 等） |
| `error.stack` | string/null | 错误堆栈（用于调试） |
| `error.retryable` | boolean | 是否可重试（程序化处理） |
| `meta.retry_count` | number | 已重试次数 |

---

### 【4】DLQ（死亡队列）项目格式

**JSON Schema:**
```json
{
  "version": "1.0",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "original_task": {
    "version": "1.0",
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "add_numbers",
    "payload": { "a": 5, "b": 3 },
    "meta": { "created_at": 1708614000000, "source": "vscode-plugin" }
  },
  "failure_record": {
    "message": "参数必须是数字",
    "code": "INVALID_INPUT",
    "stack": null,
    "retryable": false
  },
  "retry_count": 3,
  "first_failed_at": 1708614005000,
  "last_failed_at": 1708614007000,
  "meta": {
    "created_at": 1708614007000,
    "reason": "non_retryable"
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `original_task` | object | 原始的任务提交（完整保存） |
| `failure_record` | object | 最后一次失败的错误信息 |
| `retry_count` | number | 已重试次数 |
| `first_failed_at` | number | 第一次失败时间 |
| `last_failed_at` | number | 最后一次失败时间 |
| `meta.reason` | string | 进入 DLQ 的原因（exceeded_max_retries / non_retryable） |

---

## 🔄 端到端数据流

### 完整流程示例

#### 步骤 1：VSCode 插件提交任务

```javascript
// VS Code 插件发送（extension.ts）
fetch("http://localhost:3000/task/submit", {
  method: "POST",
  body: JSON.stringify({
    a: 5,
    b: 3,
    type: "add_numbers",
    source: "vscode-plugin"
  })
})
```

Node API 生成：
```javascript
// 使用 TaskModel 创建标准格式
const task = TaskModel.createTaskSubmit(
  "550e8400-e29b-41d4-a716-446655440000",
  "add_numbers",
  { a: 5, b: 3 },
  "vscode-plugin"
);

// 推入 Redis 队列
redis.lpush("task_queue", JSON.stringify(task));
```

#### 步骤 2：Python Worker 消费任务

```python
# Python Worker 从 Redis 读取（worker.py）
task_json = redis.rpop("task_queue")
task = json.loads(task_json)

# 注意：task 现在是完整的标准格式
task_id = task.get("task_id")
task_type = task.get("type")
payload = task.get("payload")
```

#### 步骤 3：Worker 执行并返回结果

**成功路径：**
```python
# 创建标准格式的成功结果
result_obj = TaskModel.create_task_result_success(
  task_id=task_id,
  task_type=task_type,
  result={"value": result_value},
  worker_id="python-worker-1",
  started_at=started_at
)

# 保存到 Redis
redis.set(f"task_result:{task_id}", json.dumps(result_obj))

# 通知 Node API 推送 WebSocket（推送完整的标准格式）
requests.post(
  f"http://localhost:3000/task/notify/{task_id}",
  json=result_obj  # ✅ 推送完整的标准格式
)
```

**失败路径：**
```python
# 创建标准格式的失败结果
error_result = TaskModel.create_task_result_error(
  task_id=task_id,
  task_type=task_type,
  error_message=last_error,
  worker_id="python-worker-1",
  error_code=last_error_code,
  error_stack=last_error_stack,
  retryable=True,
  started_at=started_at,
  retry_count=MAX_RETRIES
)

# 创建 DLQ 项目（标准格式）
dlq_item = TaskModel.create_dlq_item(
  original_task=task,
  failure_record=error_result["error"],
  retry_count=MAX_RETRIES,
  first_failed_at=started_at
)

# 推送到 Node API（同样发送完整的标准格式）
requests.post(
  f"http://localhost:3000/task/notify/{task_id}",
  json=error_result
)
```

#### 步骤 4：Node API 接收并广播

```javascript
// Node API /task/notify/:task_id 端点
app.post("/task/notify/:task_id", async (req, res) => {
  const result = req.body;  // ✅ 接收完整的标准格式

  // ✅ 验证格式
  const validation = validateTaskResult(result);
  if (!validation.valid) {
    return res.status(400).json({ error: "Invalid format", errors: validation.errors });
  }

  // 保存到 Redis
  await redis.set(`task_result:${task_id}`, JSON.stringify(result));

  // 广播给所有订阅者（WebSocket）
  await broadcastTaskResult(task_id, result);  // ✅ 推送完整的标准格式

  res.json({ status: "notified" });
});
```

#### 步骤 5：VS Code 插件接收结果

```typescript
// VS Code 插件（extension.ts）
websocket.on("task_result", (data: any) => {
  // ✅ 接收完整的标准格式

  // 验证格式
  const validation = TaskModel.validateTaskResult(data);

  // 根据状态处理
  if (isTaskSuccess(data)) {
    const value = data.result?.value;
    vscode.window.showInformationMessage(`✅ 结果: ${value}`);
  } else if (isTaskError(data)) {
    vscode.window.showErrorMessage(`❌ 错误: ${data.error.message}`);
  }

  // 显示完整的元数据
  console.log(`耗时: ${data.meta.duration_ms}ms`);
  console.log(`Worker: ${data.meta.worker_id}`);
});
```

---

## 📁 文件清单

### Node API 模块
- **[taskModel.js](node-api/taskModel.js)** - Node.js 数据模型定义
  - `createTaskSubmit()` - 创建提交格式
  - `createTaskResultSuccess()` - 创建成功结果
  - `createTaskResultError()` - 创建失败结果
  - `validateTaskResult()` - 验证格式

- **[index.js](node-api/index.js)** - Express 服务器
  - `/task/submit` - 接收任务（使用 `createTaskSubmit`）
  - `/task/result/:task_id` - 查询结果（返回标准格式）
  - `/task/notify/:task_id` - 接收 Worker 推送（验证 `validateTaskResult`）
  - `/dlq/*` - DLQ 管理接口

### Python Worker 模块
- **[task_model.py](python-worker/task_model.py)** - Python 数据模型定义
  - `TaskModel.create_task_submit()` - 创建提交格式
  - `TaskModel.create_task_result_success()` - 创建成功结果
  - `TaskModel.create_task_result_error()` - 创建失败结果
  - `TaskModel.validate_task_result()` - 验证格式

- **[worker.py](python-worker/worker.py)** - Worker 实现
  - 从 Redis 读取标准格式任务
  - 创建标准格式结果
  - 推送标准格式到 Node API

### VS Code 插件模块
- **[taskModel.ts](vscode-extension/src/taskModel.ts)** - TypeScript 数据模型定义
  - `TaskSubmit` 接口
  - `TaskResultSuccess` 接口
  - `TaskResultError` 接口
  - `validateTaskResult()` - 验证格式
  - `getResultDescription()` - 获取易读描述

- **[extension.ts](vscode-extension/src/extension.ts)** - VS Code 扩展
  - 提交任务时包含 `type` 和 `source`
  - WebSocket 接收标准格式
  - 轮询模式也支持标准格式

---

## 🔐 数据验证

### 所有模块都支持格式验证

**Node.js:**
```javascript
const { valid, errors } = TaskModel.validateTaskResult(result);
if (!valid) {
  console.warn("格式问题：", errors);
}
```

**Python:**
```python
valid, errors = TaskModel.validate_task_result(result)
if not valid:
    print("格式问题：", errors)
```

**TypeScript:**
```typescript
const { valid, errors } = TaskModel.validateTaskResult(result);
if (!valid) {
  console.warn("格式问题：", errors);
}
```

---

## 🚀 扩展性设计

该结构的优点是**完全面向未来**：

### 添加新的任务类型
```javascript
// 只需新增 type 和对应的 payload 处理
TaskModel.createTaskSubmit(
  uuid,
  "multiply_matrices",          // ✅ 新任务类型
  { matrix_a: [[1,2],[3,4]], matrix_b: [[5,6],[7,8]] },
  "vscode-plugin"
);
```

### 添加新的字段
```javascript
// 在 meta 中添加新字段，不影响现有逻辑
{
  ...taskSubmit,
  meta: {
    ...taskSubmit.meta,
    priority: "high",
    tags: ["analytics", "critical"]
  }
}
```

### 添加新的 Worker
```python
# 新的 Worker 只需遵守相同的格式
# 无需修改 Node API 或 VS Code 插件
TaskModel.create_task_result_success(
  task_id=task_id,
  task_type=task_type,
  result=new_worker_result,
  worker_id="go-worker-1"  # ✅ 新的 Worker
)
```

---

## ✅ 验证清单

- [x] **Node API**：完全使用 TaskModel 定义的格式
- [x] **Python Worker**：接收和输出标准格式
- [x] **VS Code 插件**：解析和显示标准格式
- [x] **WebSocket 推送**：传递完整的标准格式
- [x] **DLQ 管理**：存储标准格式的失败任务
- [x] **格式验证**：所有模块都支持验证函数
- [x] **轮询模式**：同样支持标准格式
- [x] **向后兼容**：现有代码可无缝升级

---

## 📊 版本信息

| 组件 | 格式版本 | 实现状态 |
|------|---------|--------|
| Node API | 1.0 | ✅ 完成 |
| Python Worker | 1.0 | ✅ 完成 |
| VS Code Plugin | 1.0 | ✅ 完成 |
| 数据模型定义 | 1.0 | ✅ 完成 |

---

## 🎯 总结

这是一个**世界顶级架构**的体现：
1. **统一性** - 所有系统使用相同的 JSON 结构
2. **可维护性** - 每个模块都有清晰的模型定义
3. **可扩展性** - 新任务类型、新字段无需修改现有逻辑
4. **可靠性** - 每层都有格式验证
5. **文档完善** - 每个字段都有明确的含义

从此刻起，你的分布式系统具备了**企业级的数据规范**！🚀
