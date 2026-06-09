# AlphaPilot 后端集成指南

## 🔄 后端流式输出集成

后端目前支持两种通知方式：通过 WebSocket 事件或者通过 HTTP 回调。插件默认使用 WebSocket（它比轮询更高效），
如果你更倾向于 REST 接口，也可以在前端发起简单轮询或把扩展改成接收 HTTP POST。旧接口仍然返回完整结果，
未升级的前端依旧可用，只是看不到中间过程。

### 后端发出的三类通知
| 阶段 | 路径 | 说明 |
|------|------|------|
| 开始 | `POST /task/stream_start/:taskId` | AI 开始生成，前端可以显示 loading、清空旧内容、设置标题等 |
| 中间 | `POST /task/stream_chunk/:taskId` | 每次收到一段增量文本，返回 `{ task_id, content }`，前端把 `content` 追加到显示区域 |
| 结束 | `POST /task/stream_end/:taskId` | 生成完成，前端可以隐藏 loading、启用按钮、做后续处理 |

插件通过 WebSocket 订阅 `stream_start`/`stream_chunk`/`stream_end` 三个事件，或者在没有 WS 的情况下
可以轮询这些接口（例如 `GET /task/stream_events/:taskId` 或自行实现小型 HTTP 服务器以接收 POST）。

插件现在支持流式输出，但**完全向后兼容**。如果你的后端不实现流式功能，插件会自动使用现有的 `task_result` 事件。

---

## 📡 可选的流式事件集成

如果你想让 AI 输出一边生成一边显示，按以下方式在后端实现：

### 1. 在开始生成时发送 `stream_start`

以上表格列出的路径在 worker.py 中调用，原理与下面示例的 WebSocket 实现类似。前端只要在
WebSocket 客户端绑定同名事件即可，也可以用 `fetch` 轮询上述 REST 端点获取相同信息。

```
# Python 例子（使用 python-socketio）
@sio.on('subscribe_task')
async def on_subscribe(sid, task_id):
    # 通知前端开始流式输出
    await sio.emit('stream_start', {
        'task_id': task_id,
        'title': '🤖 AI 生成中...'
    }, to=sid)
```

### 2. 逐步发送数据块 `stream_chunk`

当你的 LLM（如 Qwen）返回内容时，逐个块地发送：

```
from qwen_api import generate_stream

async def generate_ai_response(prompt, task_id, client_sid):
    """流式生成 AI 响应"""
    
    # 通知开始流式输出
    await sio.emit('stream_start', {
        'task_id': task_id,
        'title': '🤖 Qwen 生成中...'
    }, to=client_sid)
    
    # 流式生成内容
    async for chunk in generate_stream(prompt):
        # 发送每个数据块给客户端
        await sio.emit('stream_chunk', {
            'task_id': task_id,
            'content': chunk
        }, to=client_sid)
        
        # 小延迟（可选，用于演示效果）
        await asyncio.sleep(0.05)
    
    # 通知流完成
    await sio.emit('stream_end', {
        'task_id': task_id
    }, to=client_sid)
```

### 3. 最后发送完整的 `task_result`

```
# 流式输出完成后，仍然发送完整的 task_result
# 这样可以更新历史记录和状态

await sio.emit('task_result', {
    'version': '1.0',
    'task_id': task_id,
    'type': 'qwen_generate',
    'status': 'done',
    'result': {
        'value': full_generated_text  # 完整文本
    },
    'error': None,
    'meta': {
        'started_at': int(start_time * 1000),
        'finished_at': int(time.time() * 1000),
        'worker_id': 'qwen-api',
        'duration_ms': int((time.time() - start_time) * 1000)
    }
}, to=client_sid)
```

---

## 🎯 完整的流式任务处理示例

```
import asyncio
import time
from socketio import AsyncServer

sio = AsyncServer(async_mode='asgi')

@sio.on('subscribe_task')
async def on_subscribe(sid, task_id):
    """当客户端订阅任务时，流式生成响应"""
    
    # 从数据库获取任务信息
    task = get_task_from_db(task_id)
    
    if task['type'] == 'qwen_generate':
        await stream_qwen_response(task_id, task['payload']['prompt'], sid)
    elif task['type'] == 'add_numbers':
        await handle_add_task(task_id, task['payload'], sid)


async def stream_qwen_response(task_id, prompt, client_sid):
    """流式处理 Qwen 响应"""
    
    start_time = time.time()
    
    try:
        # 1️⃣ 通知前端流开始
        await sio.emit('stream_start', {
            'task_id': task_id,
            'title': '🤖 Qwen 生成中...'
        }, to=client_sid)
        
        generated_text = []
        
        # 2️⃣ 流式生成并发送数据块
        async for chunk in qwen_api.generate_stream(prompt):
            generated_text.append(chunk)
            
            # 发送流式块
            await sio.emit('stream_chunk', {
                'task_id': task_id,
                'content': chunk
            }, to=client_sid)
            
            # 模拟流式效果（可选）
            await asyncio.sleep(0.02)
        
        # 3️⃣ 通知流完成
        await sio.emit('stream_end', {
            'task_id': task_id
        }, to=client_sid)
        
        # 4️⃣ 发送完整结果
        full_text = ''.join(generated_text)
        
        await sio.emit('task_result', {
            'version': '1.0',
            'task_id': task_id,
            'type': 'qwen_generate',
            'status': 'done',
            'result': {
                'value': full_text
            },
            'error': None,
            'meta': {
                'started_at': int(start_time * 1000),
                'finished_at': int(time.time() * 1000),
                'worker_id': 'qwen-api',
                'duration_ms': int((time.time() - start_time) * 1000)
            }
        }, to=client_sid)
        
    except Exception as e:
        # 错误处理
        await sio.emit('task_result', {
            'version': '1.0',
            'task_id': task_id,
            'type': 'qwen_generate',
            'status': 'error',
            'result': None,
            'error': {
                'message': str(e),
                'code': 'STREAM_ERROR',
                'stack': None,
                'retryable': True
            },
            'meta': {
                'started_at': int(start_time * 1000),
                'finished_at': int(time.time() * 1000),
                'worker_id': 'qwen-api',
                'duration_ms': int((time.time() - start_time) * 1000),
                'retry_count': 0
            }
        }, to=client_sid)
```

---

## 🔄 向后兼容说明

### 如果你不实现流式功能

✅ **插件仍然正常工作**

- 插件会忽略缺失的 `stream_*` 事件
- 切换到普通模式：等待 `task_result` 后一次显示所有内容
- 任务历史仍然保存和显示
- 用户体验降级为"看结果"而不是"看过程"

### 推荐的逐步实现方案

**第 1 阶段（现在）**
- ✅ 保持现有的 `task_result` 事件
- ✅ 插件完全兼容

**第 2 阶段（可选）**
- 添加 `stream_start` 和 `stream_end` 事件
- 用户会看到加载动画

**第 3 阶段（可选）**
- 实现 `stream_chunk` 事件
- 用户会看到流式输出效果

---

## 📊 事件流图表

### 流式模式
```
[客户端]                            [服务器]
  |                                    |
  | subscribe_task(task_id)            |
  |----------------------------------->|
  |                                    | 开始 LLM 流
  |                   stream_start      |
  |<-----------------------------------|
  |        [开始流式输出]              |
  |                                    |
  |    stream_chunk (content: "你好")  |
  |<-----------------------------------|
  |        [显示: 你好]               |
  |                                    |
  |    stream_chunk (content: "世界") |
  |<-----------------------------------|
  |        [显示: 你好世界]            |
  |                                    |
  |            stream_end              |
  |<-----------------------------------|
  |        [流完成]                   |
  |                                    |
  |         task_result                |
  |<-----------------------------------|
  |        [保存历史]                 |
```

### 非流式模式（后向兼容）
```
[客户端]                            [服务器]
  |                                    |
  | subscribe_task(task_id)            |
  |----------------------------------->|
  |                                    | 生成完整结果
  |         task_result                |
  |<-----------------------------------|
  |    [一次显示全部内容]              |
  |       [保存历史]                   |
```

---

## 🛠️ 测试清单

- [ ] 确保 `task_result` 事件仍然正常触发
- [ ] 测试流式事件（如果实现）
- [ ] 检查错误处理
- [ ] 验证任务历史保存
- [ ] 测试暂停/继续按钮（客户端功能）

---

## 📞 常见问题

### Q: 必须实现流式功能吗？
**A:** 不需要。插件完全向后兼容，可以继续使用现有的 `task_result` 事件。

### Q: 如果同时发送 `stream_*` 和 `task_result` 会怎样？
**A:** 两者不冲突。前端会先显示流式内容，然后用 `task_result` 更新最终状态和历史。

### Q: 我的 LLM 不支持流式生成怎么办？
**A:** 没问题，使用普通模式。用户会在任务完成时看到完整结果。

### Q: 如何处理用户点击暂停按钮？
**A:** 暂停/继续是前端功能，前端会暂停显示新数据块，但不会停止后端处理。用户继续后，新块会立即显示。

---

更多技术细节请查看 [FEATURE_GUIDE.md](./FEATURE_GUIDE.md)

# 智能体执行引擎目标（2026-03-02）

1) 打造真正的“智能体执行引擎”
让我的助手不仅能执行任务，还能：

自主拆解任务

规划步骤

监控执行状态

失败自动恢复

多 worker 协同

这是从“工具”到“智能体”的关键跨越。
