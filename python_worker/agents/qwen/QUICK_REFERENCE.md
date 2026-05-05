# Qwen Worker v2 快速参考指南

## ⚠️ 重要前提：包结构

在运行 Worker 之前，请确保以下文件存在（可以为空）：

```
python-worker/
    __init__.py          ← 必须存在！
    worker_config.py
    agents/
        __init__.py      ← 必须存在！
        qwen/
            __init__.py  ← 必须存在！
            qwen_worker_v2.py
```

如果缺少任何 `__init__.py` 文件，会导致 `ModuleNotFoundError`。

---

## 🚀 启动 Worker

```bash
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.qwen.qwen_worker_v2
```

或者从根目录：

```bash
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.qwen.qwen_worker_v2
```

---

## 📦 核心文件清单

| 文件 | 作用 | 修改频率 |
|------|------|----------|
| `qwen_worker_v2.py` | Worker 主入口 | ⭐⭐ (偶尔) |
| `step_executor/__init__.py` | API 导出 | ⭐ (很少) |
| `step_executor/execute_step.py` | 步骤调度器 | ⭐⭐ (添加新步骤时) |
| `step_executor/prompts.py` | Prompt 模板 | ⭐⭐⭐ (经常优化) |
| `step_executor/qwen_api.py` | API 调用 | ⭐ (很少) |
| `step_executor/*_step.py` | 各步骤实现 | ⭐⭐ (按需修改) |
| `qwen_prompts.py` | Agent 人格 | ⭐ (很少) |
| **`__init__.py`** (多个) | **包标识文件** | ⭐ (创建后不变) |

---

## 🔧 常用操作

### 1. 添加新的步骤类型

**步骤 1**: 创建 `step_executor/new_step.py`

```python
from .qwen_api import call_qwen
from .prompts import new_prompt
from worker_config import create_event

def run_new_step(step, context, events):
    # 实现你的步骤逻辑
    result = call_qwen(new_prompt(...))
    step["output"] = {"text": result}
    context["intermediate_results"].append({...})
    events.append(create_event("new_output", {...}))
```

**步骤 2**: 在 `execute_step.py` 中注册

```python
STEP_DISPATCHER = {
    "analyze": run_analyze_step,
    # ... 其他步骤
    "new": run_new_step,  # ← 添加这里
}
```

**步骤 3**: 在 `__init__.py` 中导出

```python
from .new_step import run_new_step

__all__ = [
    # ... 其他导出
    "run_new_step",
]
```

---

### 2. 修改 Prompt 模板

直接在 `step_executor/prompts.py` 中修改对应的函数：

```python
def analyze_prompt(user_input: str) -> str:
    return f"""
请分析下面的任务描述：

【用户任务描述】：
{user_input}

请输出结构化分析结果。
"""
```

---

### 3. 调试单个步骤

创建测试脚本：

```python
from step_executor.analyze_step import run_analyze_step

step = {
    "id": "test-1",
    "type": "analyze",
    "input": {"prompt": "写一个计算器"},
    "status": "pending"
}

context = {"intermediate_results": []}
events = []

run_analyze_step(step, context, events)

print(step["output"])
```

---

## 🧪 测试命令

### 完整流程测试

```bash
cd python-worker
python test_qwen_worker_v2.py
```

### 手动提交任务

```python
from worker_config import redis
from TaskModel_v2 import TaskModel
import json

task = TaskModel.create_task_submit(
    task_id="test-001",
    task_type="qwen_generate",
    payload={"prompt": "写一个函数，计算两个数的和"}
)

redis.lpush("task_queue", json.dumps(task))
print("✅ 任务已提交")
```

### 查看执行结果

```python
result = redis.get("task_result:test-001")
print(result)
```

---

## 🐛 常见问题

### Q1: ModuleNotFoundError: No module named 'xxx'

**原因**: 导入路径不正确 或 缺少 `__init__.py`

**解决**: 
1. 检查是否使用了正确的导入方式：
   - step_executor 包内使用相对导入：`from .qwen_api import ...`
   - 导入根目录模块使用绝对导入：`from worker_config import ...`
2. **确认以下文件存在**：
   ```
   python-worker/__init__.py
   python-worker/agents/__init__.py
   python-worker/agents/qwen/__init__.py
   ```

---

### Q2: 步骤状态一直是 pending

**原因**: Worker 没有运行或队列中没有任务

**检查**:
1. Worker 是否启动：`ps aux | grep qwen_worker_v2.py`
2. 队列中是否有任务：`redis.lrange("task_queue", 0, -1)`
3. `__init__.py` 文件是否存在

---

### Q3: 任务执行失败，错误信息 "LLM 调用失败"

**原因**: Qwen API Key 配置问题

**解决**:
1. 检查 `.env` 文件中是否有 `DASHSCOPE_API_KEY`
2. 确认 API Key 有效且未过期
3. 检查网络连接

---

## 📊 步骤状态机

```
pending → running → success
              ↓
            error / cancelled
```

- **pending**: 步骤已创建，等待执行
- **running**: 步骤正在执行
- **success**: 步骤执行成功
- **error**: 步骤执行出错
- **cancelled**: 步骤被用户取消

---

## 🔍 监控和日志

### 查看 Worker 日志

Worker 会自动打印：
- 收到的任务
- 每个步骤的执行情况
- 最终结果

### 查看 Redis 数据

```bash
# 查看队列中的任务
redis-cli LRANGE task_queue 0 -1

# 查看任务结果
redis-cli GET task_result:test-001

# 查看取消标记
redis-cli GET stop:test-001
```

---

## 📝 最佳实践

### 1. 保持步骤幂等性

每个步骤应该可以重复执行，不会产生副作用。

### 2. 写入详细的事件流

```python
events.append(create_event("step_progress", {
    "message": "正在分析需求...",
    "progress": 0.3
}))
```

### 3. 处理异常情况

```python
try:
    result = call_qwen(prompt(...))
except Exception as e:
    step["output"] = {"text": f"执行失败：{e}"}
    step["status"] = "error"
    return
```

### 4. 定期检查取消标记

```python
if check_stop_flag(task_id):
    step["status"] = "cancelled"
    raise Exception("任务已被取消")
```

---

## 🎯 下一步

- [ ] 阅读 `ARCHITECTURE_REFACTOR.md` 了解架构细节
- [ ] 尝试添加自定义的步骤类型
- [ ] 实现多 Agent 协作功能
- [ ] 集成 Tool Calling 支持

---

**最后更新**: 2026-03-28  
**维护者**: AlphaPilot Team
