# Step Executor 前端集成指南

## 🎯 概述

本文档详细说明如何将 Python `step_executor` 模块与 VS Code 前端集成，实现强大的智能体执行能力。

---

## 📋 Step Executor 能力矩阵

### 支持的步骤类型

| 步骤类型 | 功能描述 | 输入 | 输出 |
|---------|---------|------|------|
| **analyze** | 需求分析 | 用户 prompt | 分析报告 |
| **plan** | 步骤规划 | 分析结果 | 执行计划 |
| **write** | 代码编写 | 计划 | 代码实现 |
| **refine** | 优化改进 | 代码 | 优化版本 |
| **test** | 测试验证 | 代码 | 测试结果 |
| **fix** | 错误修复 | 错误信息 + 代码 | 修复后的代码 |
| **profile** | 性能分析 | 代码 | 性能报告 |
| **doc** | 文档生成 | 代码 | 文档/注释 |

---

## 🏗️ 集成架构

```
┌─────────────────────────────────────────────────────┐
│              VS Code Extension (前端)                │
│  ┌───────────────────────────────────────────────┐  │
│  │ TaskPanel                                     │  │
│  │  - 展示步骤树                                 │  │
│  │  - 流式输出                                   │  │
│  │  - 用户交互                                   │  │
│  └───────────────────────────────────────────────┘  │
│                        ↓                             │
│  ┌───────────────────────────────────────────────┐  │
│  │ WebSocketService                              │  │
│  │  - 订阅任务事件                               │  │
│  │  - 接收实时通知                               │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                        ↓ WebSocket
┌─────────────────────────────────────────────────────┐
│              Node API / Python Worker (后端)         │
│  ┌───────────────────────────────────────────────┐  │
│  │ Task Orchestrator                             │  │
│  │  - 编排步骤流程                               │  │
│  │  - 状态管理                                   │  │
│  └───────────────────────────────────────────────┘  │
│                        ↓                             │
│  ┌───────────────────────────────────────────────┐  │
│  │ Step Executor (Python)                        │  │
│  │  ├─ analyze_step                              │  │
│  │  ├─ plan_step                                 │  │
│  │  ├─ write_step                                │  │
│  │  ├─ refine_step                               │  │
│  │  ├─ test_step                                 │  │
│  │  ├─ fix_step                                  │  │
│  │  ├─ profile_step                              │  │
│  │  └─ doc_step                                  │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 后端实现示例

### Python Worker 集成代码

```python
# worker.py
from step_executor import execute_step
import json
import asyncio
from datetime import datetime

class TaskOrchestrator:
    def __init__(self, task_id: str, websocket):
        self.task_id = task_id
        self.websocket = websocket
        self.events = []
        self.context = {}
        
    async def emit_event(self, event_type: str, data: dict):
        """发送事件到前端"""
        event = {
            'event': event_type,
            'task_id': self.task_id,
            'timestamp': datetime.now().isoformat(),
            **data
        }
        
        # 发送到 WebSocket
        await self.websocket.send(json.dumps(event))
        
        # 记录到 events 列表
        self.events.append(event)
    
    async def execute_task(self, prompt: str):
        """执行完整任务流程"""
        
        # 1. 任务开始
        await self.emit_event('task_started', {})
        
        try:
            # ========== 步骤 1: 需求分析 ==========
            step_analyze = {
                'id': 'step_1',
                'type': 'analyze',
                'status': 'pending',
                'input': {'prompt': prompt}
            }
            
            await self.emit_event('step_started', {
                'step_id': step_analyze['id'],
                'step_type': step_analyze['type']
            })
            
            # 执行分析步骤
            execute_step(
                task_id=self.task_id,
                step=step_analyze,
                events=self.events,
                context=self.context
            )
            
            await self.emit_event('step_finished', {
                'step_id': step_analyze['id'],
                'step_type': step_analyze['type'],
                'output': step_analyze.get('output', {})
            })
            
            # ========== 步骤 2: 制定计划 ==========
            step_plan = {
                'id': 'step_2',
                'type': 'plan',
                'status': 'pending',
                'input': {'analysis': step_analyze['output']}
            }
            
            await self.emit_event('step_started', {
                'step_id': step_plan['id'],
                'step_type': step_plan['type']
            })
            
            execute_step(
                task_id=self.task_id,
                step=step_plan,
                events=self.events,
                context=self.context
            )
            
            await self.emit_event('step_finished', {
                'step_id': step_plan['id'],
                'step_type': step_plan['type'],
                'output': step_plan.get('output', {})
            })
            
            # ========== 步骤 3: 编写代码 ==========
            step_write = {
                'id': 'step_3',
                'type': 'write',
                'status': 'pending',
                'input': {'plan': step_plan['output']}
            }
            
            await self.emit_event('step_started', {
                'step_id': step_write['id'],
                'step_type': step_write['type']
            })
            
            # 模拟流式输出
            await self.emit_streaming_output(step_write)
            
            execute_step(
                task_id=self.task_id,
                step=step_write,
                events=self.events,
                context=self.context
            )
            
            await self.emit_event('step_finished', {
                'step_id': step_write['id'],
                'step_type': step_write['type'],
                'output': step_write.get('output', {})
            })
            
            # ========== 步骤 4: 测试验证 ==========
            step_test = {
                'id': 'step_4',
                'type': 'test',
                'status': 'pending',
                'input': {'code': step_write['output']}
            }
            
            await self.emit_event('step_started', {
                'step_id': step_test['id'],
                'step_type': step_test['type']
            })
            
            execute_step(
                task_id=self.task_id,
                step=step_test,
                events=self.events,
                context=self.context
            )
            
            await self.emit_event('step_finished', {
                'step_id': step_test['id'],
                'step_type': step_test['type'],
                'output': step_test.get('output', {})
            })
            
            # ========== 任务完成 ==========
            await self.emit_event('task_completed', {
                'result': {
                    'code': step_write['output'],
                    'tests': step_test['output'],
                    'steps_completed': 4
                }
            })
            
        except Exception as e:
            # 任务失败
            await self.emit_event('task_failed', {
                'error': str(e)
            })
    
    async def emit_streaming_output(self, step: dict):
        """模拟流式输出"""
        await self.emit_event('stream_start', {
            'title': '✏️ 正在编写代码...'
        })
        
        # 假设代码是分块生成的
        code_chunks = [
            "def fibonacci(n):\n",
            "    \"\"\"计算斐波那契数列\"\"\"\n",
            "    if n <= 0:\n",
            "        return []\n",
            "    elif n == 1:\n",
            "        return [0]\n",
            "    \n",
            "    result = [0, 1]\n",
            "    for i in range(2, n):\n",
            "        result.append(result[i-1] + result[i-2])\n",
            "    \n",
            "    return result\n"
        ]
        
        for chunk in code_chunks:
            await self.emit_event('stream_chunk', {
                'chunk': chunk
            })
            await asyncio.sleep(0.1)  # 模拟延迟
        
        await self.emit_event('stream_end', {})


# WebSocket 服务器集成
import websockets

async def handle_client(websocket, path):
    """处理客户端连接"""
    task_id = None
    
    async for message in websocket:
        data = json.loads(message)
        
        if data.get('event') == 'subscribe_task':
            task_id = data['task_id']
            print(f'📡 客户端订阅任务：{task_id}')
            
            # 创建任务执行器并开始执行
            orchestrator = TaskOrchestrator(task_id, websocket)
            asyncio.create_task(orchestrator.execute_task(
                prompt="帮我写一个斐波那契数列函数"
            ))

# 启动服务器
start_server = websockets.serve(handle_client, 'localhost', 3000)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
```

---

## 📤 前端接收事件格式

### 标准事件结构

```typescript
interface Event {
  event: string;        // 事件类型
  task_id: string;      // 任务 ID
  step_id?: string;     // 步骤 ID（可选）
  timestamp: string;    // ISO 8601 时间戳
  data?: any;          // 事件数据
}
```

### 事件类型详解

#### 1. 任务生命周期事件

```javascript
// 任务开始
{
  event: 'task_started',
  task_id: 'task_123',
  timestamp: '2026-03-26T10:30:00Z'
}

// 任务完成
{
  event: 'task_completed',
  task_id: 'task_123',
  timestamp: '2026-03-26T10:35:00Z',
  result: {
    code: '...',
    tests: {...},
    steps_completed: 4
  }
}

// 任务失败
{
  event: 'task_failed',
  task_id: 'task_123',
  timestamp: '2026-03-26T10:32:00Z',
  error: 'API 调用超时'
}

// 任务取消
{
  event: 'task_cancelled',
  task_id: 'task_123',
  timestamp: '2026-03-26T10:33:00Z',
  reason: '用户主动取消'
}
```

#### 2. 步骤事件

```javascript
// 步骤开始
{
  event: 'step_started',
  task_id: 'task_123',
  step_id: 'step_1',
  step_type: 'analyze',
  timestamp: '2026-03-26T10:30:05Z'
}

// 步骤完成
{
  event: 'step_finished',
  task_id: 'task_123',
  step_id: 'step_1',
  step_type: 'analyze',
  timestamp: '2026-03-26T10:30:15Z',
  output: {
    analysis: '用户需要一个排序算法...',
    complexity: 'O(n log n)',
    recommendations: ['使用快速排序', '考虑稳定性']
  }
}

// 步骤失败
{
  event: 'step_failed',
  task_id: 'task_123',
  step_id: 'step_2',
  step_type: 'plan',
  timestamp: '2026-03-26T10:31:00Z',
  error: '无法解析依赖关系'
}
```

#### 3. 流式输出事件

```javascript
// 流式输出开始
{
  event: 'stream_start',
  task_id: 'task_123',
  title: '✏️ 正在编写代码...',
  timestamp: '2026-03-26T10:32:00Z'
}

// 流式数据块
{
  event: 'stream_chunk',
  task_id: 'task_123',
  chunk: 'def fibonacci(n):\n',
  timestamp: '2026-03-26T10:32:01Z'
}

// 流式输出结束
{
  event: 'stream_end',
  task_id: 'task_123',
  timestamp: '2026-03-26T10:32:10Z'
}

// 流式错误
{
  event: 'stream_error',
  task_id: 'task_123',
  message: '生成中断',
  timestamp: '2026-03-26T10:32:05Z'
}
```

---

## 🎨 前端 UI 渲染策略

### 步骤树渲染

```javascript
// 在 Webview 中渲染步骤树
function renderStepTree(steps) {
  const container = document.getElementById('step-tree');
  
  steps.forEach((step, index) => {
    const stepEl = createStepElement(step, index);
    container.appendChild(stepEl);
  });
}

function createStepElement(step, index) {
  const config = STEP_CONFIG[step.type];
  
  const el = document.createElement('div');
  el.className = `step-item step-${step.status}`;
  el.id = `step-${step.id}`;
  
  const icon = getStepIcon(step.status);
  const time = formatDuration(step.startTime, step.endTime);
  
  el.innerHTML = `
    <div class="step-header">
      <span class="step-icon">${icon}</span>
      <span class="step-name">${index + 1}. ${config.name}</span>
      <span class="step-time">${time}</span>
    </div>
    <div class="step-content">
      <div class="step-description">${config.description}</div>
      ${step.output ? `<pre>${JSON.stringify(step.output, null, 2)}</pre>` : ''}
    </div>
    <div class="progress-bar">
      <div class="progress-fill" style="width: ${getProgress(step)}%"></div>
    </div>
  `;
  
  return el;
}

function getStepIcon(status) {
  switch(status) {
    case 'pending': return '◯';
    case 'running': return '▶️';
    case 'completed': return '✓';
    case 'failed': return '✕';
    case 'skipped': return '⊘';
  }
}
```

### 流式输出渲染

```javascript
// 流式输出组件
class StreamRenderer {
  constructor(outputElement) {
    this.outputEl = outputElement;
    this.charCount = 0;
    this.isPaused = false;
    this.buffer = [];
  }
  
  start() {
    this.outputEl.textContent = '';
    this.charCount = 0;
    this.isPaused = false;
    this.updateStatus('🔄 流式输出中...');
  }
  
  append(chunk) {
    if (this.isPaused) {
      this.buffer.push(chunk);
      return;
    }
    
    this.outputEl.textContent += chunk;
    this.charCount += chunk.length;
    this.autoScroll();
    this.updateStatus(`📝 ${this.charCount} 字`);
  }
  
  pause() {
    this.isPaused = true;
    this.updateStatus('⏸️ 已暂停');
  }
  
  resume() {
    this.isPaused = false;
    this.updateStatus('▶️ 继续输出');
    
    // 消费缓冲区
    while (this.buffer.length > 0) {
      this.append(this.buffer.shift());
    }
  }
  
  end() {
    this.updateStatus(`✨ 完成 | ${this.charCount} 字`);
  }
  
  autoScroll() {
    this.outputEl.parentElement.scrollTop = this.outputEl.parentElement.scrollHeight;
  }
  
  updateStatus(text) {
    document.getElementById('status').textContent = text;
  }
}
```

---

## 🔄 完整数据流示例

### 场景：用户请求生成排序算法

```
1. 用户在 VS Code 输入框输入:
   "帮我写一个快速排序算法"
   
2. Extension 提交任务:
   POST http://localhost:3000/task/submit
   Body: { type: "qwen_generate", payload: { prompt: "..." } }
   
3. Node API 返回:
   { task_id: "task_abc123" }
   
4. Extension 打开面板并订阅:
   panel.setTaskId("task_abc123")
   websocket.subscribeTask("task_abc123")
   
5. Python Worker 开始执行:
   
   a) 发送 task_started 事件
      → 前端显示 "🚀 任务已开始"
   
   b) 执行 analyze 步骤
      → 发送 step_started (analyze)
      → 前端步骤树高亮 "🔍 需求分析"
      → 执行完成
      → 发送 step_finished
      → 前端标记步骤完成 ✓
   
   c) 执行 plan 步骤
      → 发送 step_started (plan)
      → 前端高亮 "📋 步骤规划"
      → 执行完成
      → 发送 step_finished
   
   d) 执行 write 步骤
      → 发送 step_started (write)
      → 前端高亮 "✏️ 代码编写"
      → 发送 stream_start
      → 前端清空输出区，显示 "🔄 流式输出中..."
      → 循环发送 stream_chunk
      → 前端逐字显示代码
      → 发送 stream_end
      → 前端显示 "✨ 完成 | 256 字"
      → 发送 step_finished
   
   e) 执行 test 步骤
      → 发送 step_started (test)
      → 前端高亮 "✅ 测试验证"
      → 执行测试
      → 发送 step_finished
      → 显示测试结果
   
   f) 发送 task_completed
      → 前端显示 "🎉 任务已完成"
      → 展示最终代码和测试结果

6. 用户看到完整的执行过程和结果
```

---

## ⚠️ 注意事项

### 1. 错误处理

```python
try:
    execute_step(...)
except Exception as e:
    await websocket.send(json.dumps({
        'event': 'step_failed',
        'error': str(e),
        'traceback': traceback.format_exc()
    }))
```

### 2. 超时控制

```python
import asyncio

async def execute_with_timeout(step, timeout=300):
    try:
        await asyncio.wait_for(
            execute_step_async(step),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f'步骤执行超时 ({timeout}s)')
```

### 3. 资源清理

```python
async def cleanup(task_id):
    # 清理临时文件
    # 释放内存
    # 关闭连接
    pass
```

---

## 📊 性能优化建议

### 1. 批量发送事件

```python
# ❌ 避免频繁发送
for chunk in chunks:
    await websocket.send(json.dumps({'event': 'stream_chunk', 'chunk': chunk}))

# ✅ 批量发送
batch_size = 10
batch = []
for i, chunk in enumerate(chunks):
    batch.append(chunk)
    if (i + 1) % batch_size == 0:
        await websocket.send(json.dumps({
            'event': 'stream_chunk',
            'chunk': ''.join(batch)
        }))
        batch = []
```

### 2. 压缩大数据

```python
import gzip
import json

# 对于大输出，使用 gzip 压缩
output_data = json.dumps(large_output).encode('utf-8')
compressed = gzip.compress(output_data)

await websocket.send(json.dumps({
    'event': 'step_finished',
    'output_compressed': True,
    'output': compressed.decode('latin-1')
}))
```

---

## 🎯 总结

通过本文档，你应该已经了解:

1. ✅ step_executor 的 8 种步骤类型及其用途
2. ✅ 前后端通信协议和事件格式
3. ✅ 如何在 Python 中集成 step_executor
4. ✅ 如何在前端渲染步骤树和流式输出
5. ✅ 完整的任务执行数据流
6. ✅ 错误处理和性能优化技巧

现在你可以开始实现了！🚀

---

## 📚 参考资源

- [FRONTEND_ARCHITECTURE_v2.md](./FRONTEND_ARCHITECTURE_v2.md) - 前端架构设计
- [COMPONENT_GUIDE.md](./COMPONENT_GUIDE.md) - 组件使用指南
- [step_executor/__init__.py](../../python-worker/step_executor/__init__.py) - step_executor 源码
