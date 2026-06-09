# AlphaPilot MVP 后端集成指南

> **版本**: 0.1.0 MVP  
> **架构**: HTTP + Redis + Worker  
> **更新**: 2026年2月28日

---

## 🔄 整体流程

```
VSCode Extension
    │ POST /task/submit
    │ {
    │   "type": "qwen_generate",
    │   "payload": { "prompt": "..." },
    │   "source": "vscode-extension"
    │ }
    ↓
Node API (index.js)
    │ LPUSH task_queue
    │ HSET tasks:{task_id} { state, status, result, ... }
    ↓
Redis
    │
    ├─ RPOP task_queue
    │
    ↓
qwen_worker.py（你现有的）
    │ 1. 读取任务
    │ 2. 调用 Qwen API
    │ 3. 周期性输出 TaskModel
    │    {
    │      "version": "1.0",
    │      "task_id": "...",
    │      "status": "streaming",
    │      "result": { "value": "..." }
    │    }
    │ 4. SET task_result:{task_id} <TaskModel>
    │
    ↓
Extension (轮询)
    │ GET /task/result/{task_id} (每 500ms)
    │
    ↓ 解析 TaskModel
    │
    ├─ if status === "streaming"
    │    panel.sendAppend(result.value)
    │
    ├─ if status === "done"
    │    panel.sendDone()
    │
    ├─ if status === "error"
    │    panel.sendError(error.message)
    │
    ↓
Webview (aiResult.js)
    │ 接收简化消息
    │ { type: "append", content: "..." }
    │ { type: "done" }
    │ { type: "error", message: "..." }
    │
    ↓
UI 显示
```

---

## 📡 Node API 示例（index.js）

### POST /task/submit

**请求：**
```javascript
POST /task/submit
Content-Type: application/json

{
  "type": "code_completion",
  "payload": { 
    "prompt": "写一个阶乘函数"
  },
  "source": "vscode-extension"
}
```

**响应：**
```javascript
200 OK
{
  "task_id": "task-uuid-xxx",
  "status": "queued"
}
```

**实现示例：**
```javascript
app.post('/task/submit', async (req, res) => {
  const { type, payload, source } = req.body;
  
  // 1. 生成唯一的 task ID
  const taskId = generateUUID();
  
  // 2. 将任务推入 Redis 队列
  const task = {
    task_id: taskId,
    type: type,
    payload: payload,
    source: source,
    created_at: Date.now()
  };
  
  await redis.lpush('task_queue', JSON.stringify(task));
  
  // 3. 初始化任务状态
  await redis.hset(`tasks:${taskId}`, {
    task_id: taskId,
    status: 'queued',
    created_at: Date.now()
  });
  
  // 4. 返回 task_id 给前端
  res.json({
    task_id: taskId,
    status: 'queued'
  });
});
```

---

### GET /task/result/{task_id}

**请求：**
```javascript
GET /task/result/task-uuid-xxx
```

**响应（流式中）：**
```javascript
200 OK
{
  "task_id": "task-uuid-xxx",
  "version": "1.0",
  "type": "qwen_generate",
  "status": "streaming",
  "result": {
    "value": "def factorial(n):\n    if n <= 1:\n        return 1"
  },
  "meta": {
    "worker_id": "qwen-worker-1",
    "elapsed": 1500
  }
}
```

**响应（完成）：**
```javascript
200 OK
{
  "task_id": "task-uuid-xxx",
  "version": "1.0",
  "type": "qwen_generate",
  "status": "done",
  "result": {
    "value": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)"
  },
  "meta": {
    "worker_id": "qwen-worker-1",
    "elapsed": 3200,
    "total_tokens": 156
  }
}
```

**响应（错误）：**
```javascript
200 OK
{
  "task_id": "task-uuid-xxx",
  "version": "1.0",
  "type": "qwen_generate",
  "status": "error",
  "error": {
    "type": "api_error",
    "message": "Qwen API 超时"
  }
}
```

**实现示例：**
```javascript
app.get('/task/result/:task_id', async (req, res) => {
  const { task_id } = req.params;
  
  // 1. 从 Redis 获取结果
  const result = await redis.get(`task_result:${task_id}`);
  
  // 2. 返回 TaskModel
  if (result) {
    res.json(JSON.parse(result));
  } else {
    // 3. 如果还没有结果，检查任务状态
    const task = await redis.hgetall(`tasks:${task_id}`);
    
    if (!task) {
      return res.status(404).json({
        error: "Task not found"
      });
    }
    
    res.json(task);
  }
});
```

---

## 🐍 Worker（qwen_worker.py）实现指南

### 核心框架

你现有的 qwen_worker.py 要做的事：

1. **读取任务** - 从 Redis `task_queue` RPOP
2. **调用 API** - 使用 DashScope API 调用 Qwen
3. **周期性输出** - 每收到一段内容就 SET 到 Redis
4. **完成输出** - 发送 status=done

**示例框架：**
```python
import redis
import json
import uuid
from http import HTTPStatus
from dashscope import TextGeneration

# Redis 连接
redis_client = redis.StrictRedis(
    host='localhost',
    port=6379,
    decode_responses=True
)

def process_task(task):
    """处理单个任务"""
    task_id = task['task_id']
    prompt = task['payload']['prompt']
    
    # 标记为处理中
    update_task_status(task_id, 'processing')
    
    try:
        # 调用 Qwen API（流式）
        current_output = ""
        
        response = TextGeneration.call(
            api_key=os.getenv('DASHSCOPE_API_KEY'),
            model='qwen-turbo',
            prompt=prompt,
            stream=True
        )
        
        for chunk in response:
            if chunk.status_code == HTTPStatus.OK:
                # 逐块输出
                delta = chunk.output.choices[0].delta
                if delta:
                    current_output += delta
                    
                    # 定期保存到 Redis（例如每 100 字符）
                    if len(current_output) % 100 == 0:
                        save_task_result(task_id, {
                            "version": "1.0",
                            "task_id": task_id,
                            "type": "qwen_generate",
                            "status": "streaming",
                            "result": { "value": current_output },
                            "meta": {
                                "worker_id": "qwen-worker-1",
                                "elapsed": time.time() - start_time
                            }
                        })
            else:
                raise Exception(f"API Error: {chunk.message}")
        
        # 最终输出
        save_task_result(task_id, {
            "version": "1.0",
            "task_id": task_id,
            "type": "qwen_generate",
            "status": "done",
            "result": { "value": current_output },
            "meta": {
                "worker_id": "qwen-worker-1",
                "elapsed": time.time() - start_time,
                "total_tokens": count_tokens(current_output)
            }
        })
        
    except Exception as e:
        # 错误处理
        save_task_result(task_id, {
            "version": "1.0",
            "task_id": task_id,
            "type": "qwen_generate",
            "status": "error",
            "error": {
                "type": "api_error",
                "message": str(e)
            }
        })

def save_task_result(task_id, result):
    """保存任务结果到 Redis"""
    redis_client.set(
        f'task_result:{task_id}',
        json.dumps(result),
        ex=3600  # 1 小时过期
    )

def main():
    """主循环"""
    print("🚀 Qwen Worker 启动")
    
    while True:
        try:
            # 从队列读取任务
            task_json = redis_client.rpop('task_queue')
            
            if task_json:
                task = json.loads(task_json)
                print(f"📦 处理任务: {task['task_id']}")
                process_task(task)
            else:
                # 队列为空，等待
                time.sleep(1)
        
        except Exception as e:
            print(f"❌ 错误: {e}")

if __name__ == '__main__':
    main()
```

### 关键点

✅ **必须输出的格式**
```python
{
    "version": "1.0",           # 必须
    "task_id": "...",           # 必须
    "type": "qwen_generate",  # 必须
    "status": "streaming|done|error",  # 必须
    "result": { "value": "..." },  # 可选（streaming/done）
    "error": { "type": "...", "message": "..." },  # 可选（error）
    "meta": { ... }             # 可选
}
```

⚠️ **常见错误**
- ❌ 不输出 version/task_id/type（Extension 需要校验）
- ❌ 每次都更新完整结果，而不是增量（浪费）
- ❌ 不设置 Redis key 过期时间（内存泄漏）
- ❌ status 值拼写错误（streaming != stream, done != complete）

---

## 🔐 错误处理

### Extension 如何处理错误

```typescript
// extension.ts
async pollTaskResult(taskId, panel) {
    // ...
    const taskResult = await fetch(`/task/result/${taskId}`);
    
    if (!taskResult.ok) {
        // HTTP 错误（404, 500 等）
        panel.sendError("无法获取任务结果");
        return;
    }
    
    const { status, error, result } = await taskResult.json();
    
    if (status === "error") {
        // Worker 返回业务错误
        panel.sendError(error?.message || "未知错误");
    }
}
```

**Webview 显示**
```
❌ Qwen API 超时
```

---

## 📊 监控和调试

### 查看 Redis 队列状态

```bash
redis-cli

# 查看等待队列
> LLEN task_queue
(integer) 3

# 查看队列内容
> LRANGE task_queue 0 -1

# 查看已完成的结果
> KEYS task_result:*

# 查看单个结果
> GET task_result:task-uuid-xxx
```

### 查看 Worker 日志

```bash
# 终端输出应该显示：
🚀 Qwen Worker 启动
📻 等待任务...
📦 处理任务: task-uuid-xxx
✅ 完成
📻 等待任务...
```

---

## ✅ 本地测试清单

**启动顺序：**
1. ✅ Redis：`redis-server`
2. ✅ Node API：`node index.js`
3. ✅ Qwen Worker：`python qwen_worker.py`
4. ✅ VSCode Extension：F5 调试

**测试流程：**
```
Ctrl+Shift+P → AlphaPilot: 代码补全 (MVP)
输入: "写一个 hello world"
观察:
  - 输出面板打开
  - 内容逐字显示
  - 最后显示 ✅ 完成
  - 历史面板有新任务
```

---

## 🚀 后续扩展

### 添加新 Worker

新的 Worker（比如 openai_worker.py）只需要：
1. 读 `task_queue` RPOP
2. 调用你的 API
3. SET `task_result:{task_id}`

**完全不需要修改：**
- VSCode Extension ✓
- Webview ✓
- Node API ✓

### 性能优化

- 改 HTTP 轮询为 WebSocket（后续）
- 改单 Worker 为多 Worker 抢队列（已支持）
- 添加任务优先级队列（后续）
- 缓存热门 prompt（后续）
