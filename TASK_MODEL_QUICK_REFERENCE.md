# 🚀 快速参考指南 - TaskModel 使用

> **中文注释版** - 所有代码示例都有详细中文说明

---

## 📌 Node.js 使用示例

### 1️⃣ 创建任务提交 (Node API)

```javascript
const { TaskModel } = require('./taskModel');
const { v4: uuidv4 } = require('uuid');

// 创建一个新任务
const task = TaskModel.createTaskSubmit(
  uuidv4(),              // task_id: 唯一标识符
  "add_numbers",         // task_type: 任务类型
  { a: 5, b: 3 },       // payload: 业务数据
  "vscode-plugin"        // source: 来源标识
);

// 输出结果
console.log(JSON.stringify(task, null, 2));
// {
//   "version": "1.0",
//   "task_id": "...",
//   "type": "add_numbers",
//   "payload": { "a": 5, "b": 3 },
//   "meta": {
//     "created_at": 1708614000000,
//     "source": "vscode-plugin"
//   }
// }
```

### 2️⃣ 验证任务格式 (Node API)

```javascript
const { validateTaskResult } = require('./taskModel');

// 验证一个结果对象
const validation = validateTaskResult(someResult);

if (!validation.valid) {
  console.error("❌ 格式错误：", validation.errors);
  // 例如: ["status 字段不合法", "type 字段缺失"]
} else {
  console.log("✅ 格式正确");
}
```

### 3️⃣ 创建成功结果 (Node API)

```javascript
const resultSuccess = TaskModel.createTaskResultSuccess(
  "550e8400-e29b-41d4-a716-446655440000",  // task_id
  "add_numbers",                             // task_type
  { value: 8 },                              // result 内容
  "python-worker-1",                         // worker_id
  1708614005000                              // started_at
);

// 输出结果:
// {
//   "version": "1.0",
//   "task_id": "550e8400-e29b-41d4-a716-446655440000",
//   "type": "add_numbers",
//   "status": "done",
//   "result": { "value": 8 },
//   "error": null,
//   "meta": {
//     "started_at": 1708614005000,
//     "finished_at": 1708614006500,    // 自动计算
//     "worker_id": "python-worker-1",
//     "duration_ms": 1500               // 自动计算
//   }
// }
```

### 4️⃣ 创建错误结果 (Node API)

```javascript
const resultError = TaskModel.createTaskResultError(
  "550e8400-e29b-41d4-a716-446655440000",  // task_id
  "add_numbers",                             // task_type
  "参数必须是数字",                         // error_message
  "python-worker-1",                         // worker_id
  "INVALID_INPUT",                           // error_code
  "Traceback...",                            // error_stack
  false,                                     // retryable (不可重试)
  1708614005000,                             // started_at
  3                                          // retry_count
);

// 输出结果:
// {
//   "version": "1.0",
//   "task_id": "550e8400-e29b-41d4-a716-446655440000",
//   "type": "add_numbers",
//   "status": "error",
//   "result": null,
//   "error": {
//     "message": "参数必须是数字",
//     "code": "INVALID_INPUT",
//     "stack": "Traceback...",
//     "retryable": false
//   },
//   "meta": {
//     "started_at": 1708614005000,
//     "finished_at": 1708614006500,
//     "worker_id": "python-worker-1",
//     "duration_ms": 1500,
//     "retry_count": 3
//   }
// }
```

---

## 🐍 Python 使用示例

### 1️⃣ 导入和初始化

```python
from task_model import TaskModel
import json
import uuid

# TaskModel 提供所有静态方法
```

### 2️⃣ 创建任务提交

```python
# 从 Node API 接收并解析
task_json = redis.rpop("task_queue")
task = json.loads(task_json)

# 现在 task 包含完整的标准格式：
# {
#   "version": "1.0",
#   "task_id": "...",
#   "type": "add_numbers",
#   "payload": {"a": 5, "b": 3},
#   "meta": {"created_at": ..., "source": "vscode-plugin"}
# }

task_id = task.get("task_id")
task_type = task.get("type")
payload = task.get("payload")
```

### 3️⃣ 验证任务格式

```python
valid, errors = TaskModel.validate_task_result(some_result)

if not valid:
  print(f"❌ 格式错误: {errors}")
  # 例如: ["status 字段不合法", "type 字段缺失"]
else:
  print("✅ 格式正确")
```

### 4️⃣ 返回成功结果

```python
import time

started_at = int(time.time() * 1000)  # 毫秒级时间戳

try:
  # 执行任务逻辑
  result_value = payload['a'] + payload['b']
  
  # 创建标准格式的成功结果
  result_obj = TaskModel.create_task_result_success(
    task_id=task_id,
    task_type=task_type,
    result={"value": result_value},  # 包装在 result 对象中
    worker_id="python-worker-1",
    started_at=started_at
  )
  
  # 保存到 Redis
  redis.set(f"task_result:{task_id}", json.dumps(result_obj))
  
  # 通知 Node API （推送完整的标准格式）
  response = requests.post(
    f"http://localhost:3000/task/notify/{task_id}",
    json=result_obj,  # ✅ 推送完整对象
    timeout=5
  )
  
except Exception as e:
  # 创建标准格式的错误结果
  result_obj = TaskModel.create_task_result_error(
    task_id=task_id,
    task_type=task_type,
    error_message=str(e),
    worker_id="python-worker-1",
    error_code="EXECUTION_ERROR",
    error_stack=traceback.format_exc(),
    retryable=True,
    started_at=started_at,
    retry_count=0
  )
```

### 5️⃣ 返回失败结果（超过重试次数）

```python
import traceback

# 在多次重试都失败后
result_obj = TaskModel.create_task_result_error(
  task_id=task_id,
  task_type=task_type,
  error_message=last_error_message,
  worker_id="python-worker-1",
  error_code=error_code,
  error_stack=last_error_stack,
  retryable=False,  # ⚠️ 不再重试
  started_at=started_at,
  retry_count=MAX_RETRIES
)

# 创建 DLQ 项目
dlq_item = TaskModel.create_dlq_item(
  original_task=task,
  failure_record=result_obj["error"],
  retry_count=MAX_RETRIES,
  first_failed_at=started_at
)

# 保存 DLQ 项目
redis.lpush("dlq", json.dumps(dlq_item))

# 发送最终错误结果
requests.post(
  f"http://localhost:3000/task/notify/{task_id}",
  json=result_obj
)
```

---

## 🔵 TypeScript 使用示例

### 1️⃣ 导入接口

```typescript
import {
  TaskSubmit,
  TaskResultSuccess,
  TaskResultError,
  TaskResult,
  validateTaskResult,
  getResultDescription,
  isTaskSuccess,
  isTaskError,
  isTaskPending
} from './taskModel';
```

### 2️⃣ 验证接收的结果

```typescript
websocket.on("task_result", (data: any) => {
  // 验证数据格式
  const validation = validateTaskResult(data);
  
  if (!validation.valid) {
    console.error("❌ 格式不符合规范:", validation.errors);
    output.appendLine(`⚠️ 数据格式问题: ${validation.errors.join(", ")}`);
    return;
  }
  
  console.log("✅ 格式验证成功");
});
```

### 3️⃣ 使用类型守卫处理结果

```typescript
websocket.on("task_result", (data: any) => {
  // 先验证格式
  const { valid } = validateTaskResult(data);
  if (!valid) return;
  
  // 强类型化处理
  const result: TaskResult = data;
  
  if (isTaskSuccess(result)) {
    // 现在 result 被类型化为 TaskResultSuccess
    const value = result.result.value;  // ✅ 完整的类型检查
    const duration = result.meta.duration_ms;
    const worker = result.meta.worker_id;
    
    vscode.window.showInformationMessage(
      `✅ 完成！值=${value}，耗时${duration}ms (${worker})`
    );
    
  } else if (isTaskError(result)) {
    // 现在 result 被类型化为 TaskResultError
    const message = result.error.message;
    const retryable = result.error.retryable;
    
    if (retryable) {
      vscode.window.showWarningMessage(
        `⚠️ 可重试错误: ${message}`
      );
    } else {
      vscode.window.showErrorMessage(
        `❌ 不可恢复错误: ${message}`
      );
    }
    
  } else if (isTaskPending(result)) {
    // still waiting...
  }
});
```

### 4️⃣ 使用描述工具显示结果

```typescript
websocket.on("task_result", (data: any) => {
  const { valid, errors } = validateTaskResult(data);
  if (!valid) {
    output.appendLine(`❌ 格式错误: ${errors.join(", ")}`);
    return;
  }
  
  // 获取易读的描述
  const description = getResultDescription(data);
  output.appendLine(`\n📊 ${description}`);
  
  // 例如输出:
  // 📊 ✅ 任务成功 | 结果: 8 | 耗时: 1500ms | Worker: python-worker-1
  // 或
  // 📊 ❌ 任务失败 | 错误: 参数必须是数字 | 不可重试 | 耗时: 150ms
  
  // 同时保存完整的 JSON
  output.appendLine(`\n原始数据:\n${JSON.stringify(data, null, 2)}`);
});
```

### 5️⃣ 提交任务时包含标准字段

```typescript
async function submitTask(a: number, b: number) {
  const response = await fetch("http://localhost:3000/task/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      a,
      b,
      type: "add_numbers",              // ✅ 指定任务类型
      source: "vscode-plugin"           // ✅ 指定来源
    })
  });
  
  const result = await response.json();
  const taskId = result.task_id;  // 返回的 task_id (注意: 可能是在响应中)
  
  return taskId;
}
```

### 6️⃣ 轮询模式也支持标准格式

```typescript
async function pollTaskResult(taskId: string): Promise<TaskResult | undefined> {
  try {
    const response = await fetch(
      `http://localhost:3000/task/result/${taskId}`
    );
    const data = await response.json();
    
    // 数据已经是标准格式
    const { valid, errors } = validateTaskResult(data);
    if (!valid) {
      console.error("❌ 格式不符合规范:", errors);
      return undefined;
    }
    
    if (isTaskPending(data)) {
      console.log("⏳ 任务还在执行中...");
      return undefined;
    }
    
    if (isTaskSuccess(data)) {
      console.log(`✅ 完成: ${data.result.value}`);
    } else if (isTaskError(data)) {
      console.log(`❌ 错误: ${data.error.message}`);
    }
    
    return data;
    
  } catch (error) {
    console.error("轮询失败:" , error);
    return undefined;
  }
}
```

---

## ✅ 快速检查清单

在开发时，按照这个清单确保正确使用 TaskModel：

### 提交任务时 ✓
- [ ] 包含 `type` 字段（task_type）
- [ ] 包含 `source` 字段（来源标识）
- [ ] payload 包含所有必要的输入参数

### 返回成功结果时 ✓
- [ ] 调用 `createTaskResultSuccess()` 或 Python/TS 等价方法
- [ ] 传入 `started_at` 时间戳（毫秒）
- [ ] 返回值包装在 `result: { value: ... }` 中
- [ ] 设置正确的 `worker_id`

### 返回错误结果时 ✓
- [ ] 调用 `createTaskResultError()` 或等价方法
- [ ] 包含完整的错误信息（message, code, stack）
- [ ] 设置 `retryable` 标志（是否可重试）
- [ ] 包含当前重试次数 `retry_count`

### 验证格式时 ✓
- [ ] 在接收结果前调用 `validateTaskResult()`
- [ ] 检查 `valid` 标志
- [ ] 如果不合法，查看 `errors` 数组准确定位问题

### 显示结果时 ✓
- [ ] 使用 `getResultDescription()` 获取易读格式（TypeScript）
- [ ] 使用 `isTaskSuccess()`, `isTaskError()` 类型守卫
- [ ] 根据 `status` 和 `error.retryable` 选择不同的 UI 提示

---

## 🔗 更多参考

详细的规范文档: [TASK_MODEL_SPECIFICATION.md](./TASK_MODEL_SPECIFICATION.md)

核心实现文件:
- Node.js: [node-api/taskModel.js](node-api/taskModel.js)
- Python: [python-worker/task_model.py](python-worker/task_model.py)
- TypeScript: [vscode-extension/src/taskModel.ts](vscode-extension/src/taskModel.ts)
