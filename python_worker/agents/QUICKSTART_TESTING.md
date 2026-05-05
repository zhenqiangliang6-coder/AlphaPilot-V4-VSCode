# 多模型 Worker v2 快速测试指南

## 📋 测试前准备

### 1. 确认环境配置

检查 `.env` 文件是否包含所有必需的 API Key：

```bash
# Qwen (DashScope)
DASHSCOPE_API_KEY=your_dashscope_key

# DeepSeek (火山引擎)
VOLC_DEEPSEEK_API_KEY=your_volc_key
# 或
VOLC_API_KEY=your_volc_key

# Doubao (火山引擎)
VOLC_API_KEY=your_volc_key

# Redis (Upstash)
UPSTASH_REDIS_REST_URL=https://your-redis-url
UPSTASH_REDIS_REST_TOKEN=your_redis_token

# Node API
NODE_API_URL=http://localhost:3000
```

### 2. 安装依赖

确保已安装所有必需的依赖：

```bash
pip install requests python-dotenv upstash-redis
```

## 🚀 测试步骤

### 步骤 1：启动 Redis（可选）

如果使用 Upstash Redis，跳过此步骤。

如果使用本地 Redis：

```bash
redis-server
```

### 步骤 2：启动 Node API

在另一个终端窗口启动 Node API：

```bash
cd node-api
npm start
```

### 步骤 3：启动 Worker

#### 选项 A：启动 Qwen Worker

```bash
cd C:\Users\DavidLiang\Desktop\Copilot_Alphapilot
python -m python_worker.agents.qwen.qwen_worker_v2.py
```

#### 选项 B：启动 DeepSeek Worker

```bash
cd C:\Users\DavidLiang\Desktop\Copilot_Alphapilot
python -m python_worker.agents.deepeek.deepseek_worker_v2.py
```

#### 选项 C：启动 Doubao Worker

```bash
cd C:\Users\DavidLiang\Desktop\Copilot_Alphapilot
python -m python_worker.agents.Volcengine.doubao_worker_v2.py
```

### 步骤 4：提交测试任务

创建测试脚本 `test_workers.py`：

```python
import redis
import json
import time
from TaskModel_v2 import TaskModel

# 连接 Redis
r = redis.Redis(
    host='localhost',  # 或 Upstash URL
    port=6379,
    password='your_password'  # 或 Upstash Token
)

def test_qwen():
    """测试 Qwen Worker"""
    print("\n=== 测试 Qwen Worker ===")
    
    task = TaskModel.create_task_submit(
        task_id="qwen-test-" + str(int(time.time())),
        task_type="qwen_generate",
        payload={
            "prompt": "创建一个计算斐波那契数列的函数，要求支持 n 从 0 到 100"
        }
    )
    
    r.lpush("task_queue", json.dumps(task))
    print(f"✅ 任务已提交：{task['task_id']}")
    return task['task_id']

def test_deepseek():
    """测试 DeepSeek Worker"""
    print("\n=== 测试 DeepSeek Worker ===")
    
    task = TaskModel.create_task_submit(
        task_id="deepseek-test-" + str(int(time.time())),
        task_type="deepseek_generate",
        payload={
            "prompt": "实现一个快速排序算法，并分析时间复杂度"
        }
    )
    
    r.lpush("task_queue", json.dumps(task))
    print(f"✅ 任务已提交：{task['task_id']}")
    return task['task_id']

def test_doubao_text():
    """测试 Doubao Worker（纯文本）"""
    print("\n=== 测试 Doubao Worker（文本）===")
    
    task = TaskModel.create_task_submit(
        task_id="doubao-text-" + str(int(time.time())),
        task_type="doubao_generate",
        payload={
            "prompt": "用 Python 写一个装饰器，用于缓存函数结果"
        }
    )
    
    r.lpush("task_queue", json.dumps(task))
    print(f"✅ 任务已提交：{task['task_id']}")
    return task['task_id']

def test_doubao_multimodal():
    """测试 Doubao Worker（多模态）"""
    print("\n=== 测试 Doubao Worker（多模态）===")
    
    task = TaskModel.create_task_submit(
        task_id="doubao-multimodal-" + str(int(time.time())),
        task_type="doubao_multimodal",
        payload={
            "prompt": "请描述这张图片的内容",
            "image_url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png"
        }
    )
    
    r.lpush("task_queue", json.dumps(task))
    print(f"✅ 任务已提交：{task['task_id']}")
    return task['task_id']

def check_result(task_id):
    """检查结果"""
    result_key = f"task_result:{task_id}"
    result = r.get(result_key)
    
    if result:
        data = json.loads(result)
        print(f"\n✅ 任务完成:")
        print(f"状态：{data['status']}")
        if data['status'] == 'done':
            print(f"结果：{data['result'][:200]}...")
        elif data['status'] == 'error':
            print(f"错误：{data['error']['message']}")
        return data
    else:
        print(f"⏳ 任务仍在处理中...")
        return None

if __name__ == "__main__":
    print("🚀 开始测试多模型 Worker v2")
    print("=" * 60)
    
    # 选择要测试的 Worker
    # task_id = test_qwen()
    # task_id = test_deepseek()
    # task_id = test_doubao_text()
    # task_id = test_doubao_multimodal()
    
    # 等待结果
    # time.sleep(5)
    # check_result(task_id)
```

### 步骤 5：运行测试

取消注释要测试的 Worker：

```python
# 测试 Qwen
task_id = test_qwen()

# 或测试 DeepSeek
# task_id = test_deepseek()

# 或测试 Doubao 文本
# task_id = test_doubao_text()

# 或测试 Doubao 多模态
# task_id = test_doubao_multimodal()
```

然后运行：

```bash
python test_workers.py
```

## 📊 验证结果

### 1. 查看 Worker 输出

Worker 终端应该显示：

```
============================================================
收到任务:
{
  "version": "2.0",
  "task_id": "task-123",
  "type": "model_generate",
  ...
}
============================================================

🔄 [Model] 尝试执行任务 (第 1/3 次)...
✅ 第 1 次尝试成功，结果：xxx

============================================================
任务完成，结果已写入 Redis:
{
  "version": "2.0",
  "status": "done",
  ...
}
============================================================
```

### 2. 检查 Redis 结果

使用 Redis 客户端查看结果：

```bash
# 获取任务结果
GET task_result:task-123

# 查看队列长度
LLEN task_queue

# 查看死信队列
LRANGE dlq 0 -1
```

### 3. 验证步骤执行

检查结果中的 `steps` 数组，应该包含：

```json
{
  "steps": [
    {
      "id": "step-1",
      "type": "analyze",
      "status": "success",
      "output": {"text": "..."}
    },
    {
      "id": "step-2",
      "type": "plan",
      "status": "success",
      "output": {"text": "..."}
    },
    {
      "id": "step-3",
      "type": "write",
      "status": "success",
      "output": {
        "text": "...",
        "code": "..."
      }
    }
  ]
}
```

## 🛠️ 故障排查

### Worker 未响应

1. **检查 Redis 连接**
   ```bash
   redis-cli ping
   ```

2. **检查队列是否有任务**
   ```bash
   LLEN task_queue
   ```

3. **确认 Worker 正在运行**
   - 查看 Worker 终端输出
   - 确认没有报错

### 任务失败

1. **查看错误信息**
   ```bash
   GET task_result:task-123
   ```

2. **检查死信队列**
   ```bash
   LRANGE dlq 0 -1
   ```

3. **常见错误**
   - API Key 无效 → 检查 `.env` 配置
   - 网络连接问题 → 检查网络连通性
   - 模型返回格式错误 → 查看 Worker 日志

### 多模态任务失败

1. **检查图片 URL**
   - 确保 URL 可访问
   - 图片格式正确

2. **验证模型支持**
   - 确认使用的是 doubao-seed-2-0-lite-260215

## 📈 性能测试

### 并发测试

同时提交多个任务：

```python
for i in range(5):
    task_id = test_qwen()
    time.sleep(0.5)
```

### 压力测试

连续提交大量任务：

```python
for i in range(100):
    task_id = test_deepseek()
```

## ✅ 测试清单

- [ ] Qwen Worker 正常启动
- [ ] DeepSeek Worker 正常启动
- [ ] Doubao Worker 正常启动
- [ ] Qwen 文本任务成功执行
- [ ] DeepSeek 文本任务成功执行
- [ ] Doubao 文本任务成功执行
- [ ] Doubao 多模态任务成功执行
- [ ] 步骤状态正确（pending → running → success）
- [ ] 结果正确写入 Redis
- [ ] 错误任务正确写入 DLQ
- [ ] 任务取消功能正常

## 📚 下一步

测试通过后，可以：

1. 集成到 VSCode Extension
2. 添加更多模型支持
3. 实现多 Agent 协作
4. 优化性能

## 👥 作者

DavidLiang - 2026-03-31
