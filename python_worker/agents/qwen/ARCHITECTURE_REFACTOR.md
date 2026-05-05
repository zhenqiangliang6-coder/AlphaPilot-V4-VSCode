# Qwen Agent 架构重构文档

## 📋 更新概述

**更新日期**: 2026-03-28  
**版本**: v2.0  
**主要变更**: Prompt 规范化、模块化、可复用架构重构

---

## 🎯 重构目标

本次重构旨在将 Qwen Worker 的架构从单体式改进为模块化、可扩展的架构，具体目标包括：

1. **Prompt 规范化**: 将所有步骤的 Prompt 模板统一管理，提高可维护性
2. **模块化设计**: 每个步骤独立成模块，职责清晰，易于测试和扩展
3. **可复用架构**: 支持快速添加新的步骤类型，支持多 Agent 协作

---

## 📁 新架构目录结构

```
python-worker/agents/qwen/
├── step_executor/              # 步骤执行器模块（核心）
│   ├── __init__.py            # 统一导出所有公共 API
│   ├── execute_step.py        # 统一步骤调度器（Worker 调用入口）
│   ├── analyze_step.py        # analyze 步骤：需求分析
│   ├── plan_step.py           # plan 步骤：代码规划
│   ├── write_step.py          # write 步骤：代码生成
│   ├── refine_step.py         # refine 步骤：代码优化
│   ├── test_step.py           # test 步骤：单元测试生成
│   ├── fix_step.py            # fix 步骤：自动修复
│   ├── profile_step.py        # profile 步骤：性能分析
│   ├── doc_step.py            # doc 步骤：文档生成
│   ├── prompts.py             # ⭐ Prompt 模板集中管理
│   ├── qwen_api.py            # Qwen API 调用封装
│   └── utils.py               # 工具函数
├── qwen_prompts.py            # Agent 级别 Prompt（学校级）
├── qwen_api.py                # ⭐ 已迁移到 step_executor/
└── qwen_worker_v2.py          # ⭐ Worker 主入口（v2）
```

---

## 🔧 核心改进点

### 1. Prompt 规范化管理

#### 之前的问题
- Prompt 散落在各个 step 文件中
- 格式不统一，难以维护
- 修改 Prompt 需要遍历多个文件

#### 现在的解决方案

**文件**: `step_executor/prompts.py`

所有步骤的 Prompt 模板集中管理，统一格式：

```python
def analyze_prompt(user_input: str) -> str:
    """analyze 步骤的 prompt：分析用户需求"""
    return f"""
请分析下面的任务描述，并提取关键需求点：

【用户任务描述】：
{user_input}

请输出：
1. 任务的核心目标
2. 需要实现的功能点
...
"""

def plan_prompt(analysis: str) -> str:
    """plan 步骤的 prompt：根据分析结果生成代码结构规划"""
    return f"""
下面是对任务的分析结果，请根据这些内容生成代码结构规划：

【分析结果】：
{analysis}
...
"""

# ... 其他 8 个 Prompt 模板
```

**优势**:
- ✅ 一处修改，全局生效
- ✅ 格式统一，易于审查
- ✅ 支持快速添加新的 Prompt 模板

---

### 2. 模块化 Step Executor

#### 之前的问题
- 步骤执行逻辑耦合在 Worker 中
- 新增步骤类型需要修改 Worker 代码
- 难以单独测试某个步骤

#### 现在的解决方案

**架构**:
```
每个步骤 = 独立的 Python 模块
├── 输入：context + events
├── 处理：调用 LLM + 工具
└── 输出：写入 context + events
```

**示例**: `analyze_step.py`

```python
from .qwen_api import call_qwen
from .prompts import analyze_prompt
from worker_config import create_event

def run_analyze_step(step, context, events):
    # 1) 获取用户输入
    user_input = step["input"].get("prompt", "")
    
    # 2) 调用 LLM 生成分析结果
    result = call_qwen(analyze_prompt(user_input))
    
    # 3) 写入输出
    step["output"] = {"text": result}
    
    # 4) 写入上下文（供后续步骤使用）
    context["intermediate_results"].append({
        "type": "analyze",
        "analysis": result
    })
    
    # 5) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("analyze_output", {
        "analysis": result
    }))
```

**优势**:
- ✅ 每个步骤职责单一，易于理解
- ✅ 可独立测试每个步骤
- ✅ 新增步骤只需添加新文件

---

### 3. 统一调度器（Step Dispatcher）

**文件**: `step_executor/execute_step.py`

```python
STEP_DISPATCHER = {
    "analyze": run_analyze_step,
    "plan": run_plan_step,
    "write": run_write_step,
    "refine": run_refine_step,
    "test": run_test_step,
    "fix": run_fix_step,
    "profile": run_profile_step,
    "doc": run_doc_step,
}

def execute_step(task_id: str, step: dict, events: list, context: dict):
    """
    统一步骤执行入口：
    - Worker 调用本函数，而不是直接调用 run_xxx_step
    - 根据 step["type"] 自动路由到对应的执行器
    """
    step_type = step.get("type")
    handler = STEP_DISPATCHER[step_type]
    handler(step, context, events)
    
    # 记录步骤完成事件
    events.append({
        "event": "step_finished",
        "task_id": task_id,
        "step_id": step.get("id"),
        "step_type": step_type,
        "output": step.get("output", {})
    })
```

**优势**:
- ✅ Worker 不需要知道每个步骤的细节
- ✅ 新增步骤只需在字典中注册
- ✅ 支持动态扩展

---

### 4. 相对导入规范

**问题**: 之前使用绝对导入，导致在不同目录下执行时报错

**解决方案**: 严格遵循 Python 包内导入规范

```python
# ✅ 正确：相对导入（step_executor 包内）
from .qwen_api import call_qwen
from .prompts import analyze_prompt
from .utils import extract_code

# ✅ 正确：导入根目录模块（使用绝对导入）
from worker_config import create_event
from code_executor import run_python
```

---

### 5. qwen_api.py 位置调整

**之前**: `python-worker/agents/qwen/qwen_api.py`

**现在**: 
- 保留 `python-worker/agents/qwen/qwen_api.py` （兼容旧代码）
- 新增 `python-worker/agents/qwen/step_executor/qwen_api.py` （包内使用）

**修改**:
```python
# step_executor/qwen_api.py
import sys
import os

# 添加父目录到路径，以便导入 worker_config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from worker_config import DASHSCOPE_API_KEY

def call_qwen(prompt: str) -> str:
    # ... Qwen API 调用逻辑
```

---

## 🚀 qwen_worker_v2.py 核心特性

### 1. 统一任务入口

```python
def execute_task(task_type: str, payload: dict, task_id: str, steps: list, events: list, context: dict):
    if task_type == "qwen_generate":
        # 1) 调用 Planner：让 Qwen 拆解任务
        plan_steps = llm_decompose_task(prompt)
        steps.extend(plan_steps)
        
        # 2) 依次执行每个步骤（新增：步骤状态管理 + 取消检查）
        for step in steps:
            # 检查是否被取消
            if check_stop_flag(task_id):
                step["status"] = "cancelled"
                raise Exception("任务已被用户取消")
            
            # 状态：pending → running
            step["status"] = "running"
            
            # 执行步骤
            execute_step(task_id, step, events, context)
            
            # 状态：running → success
            step["status"] = "success"
```

### 2. 步骤状态管理

```python
# 步骤状态机
step["status"] = "pending"     # 待执行
step["status"] = "running"     # 执行中
step["status"] = "success"     # 执行成功
step["status"] = "error"       # 执行失败
step["status"] = "cancelled"   # 已取消
```

### 3. 取消机制（线程安全）

```python
# 在每个步骤执行前检查取消标记
if check_stop_flag(task_id):
    step["status"] = "cancelled"
    step["output"] = {"text": "任务已被用户取消"}
    raise Exception("任务已被用户取消")
```

---

## 📊 数据流图

```
┌─────────────┐
│ VSCode      │
│ Extension   │
└──────┬──────┘
       │
       │ HTTP POST
       │ task_queue (Redis)
       ▼
┌─────────────────────────────┐
│ qwen_worker_v2.py           │
│  1. rpop(task_queue)        │
│  2. llm_decompose_task()    │
│  3. for step in steps:      │
│     execute_step()          │
└──────┬──────────────────────┘
       │
       │ Redis SET
       │ task_result:{task_id}
       ▼
┌─────────────┐
│ VSCode      │
│ Polling     │
└─────────────┘
```

---

## 🧪 测试指南

### 1. 测试脚本

运行测试脚本验证完整流程：

```bash
cd python-worker
python test_qwen_worker_v2.py
```

### 2. 手动测试步骤

**步骤 1**: 启动 Worker
```bash
cd python-worker/agents/qwen
python qwen_worker_v2.py
```

**步骤 2**: 提交测试任务
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
```

**步骤 3**: 查看执行结果
```python
result = redis.get("task_result:test-001")
print(result)
```

---

## 📝 迁移指南

### 从旧版迁移到新版

如果你之前使用的是旧版 `qwen_worker.py`，请按以下步骤迁移：

1. **更新前端配置**: 确保 VSCode Extension 连接到 `qwen_worker_v2.py`
2. **更新环境变量**: 确认 `WORKER_ID` 设置为 `qwen-worker-v2`
3. **测试兼容性**: 使用测试脚本验证任务执行正常
4. **监控日志**: 观察 Worker 日志，确保没有错误

---

## 🔮 未来扩展方向

### 1. 多 Agent 协作

当前架构已为多 Agent 协作做好准备：

```python
# agents/
# ├── qwen/           # Qwen Agent
# ├── claude/         # Claude Agent (未来)
# ├── openai/         # OpenAI Agent (未来)
# └── multi_agent/    # 多 Agent 协调器 (未来)
```

### 2. Tool Calling 支持

在 `qwen_prompts.py` 中已预留工具描述：

```python
QWEN_TOOLS = [
    {
        "name": "search",
        "description": "执行互联网搜索",
        "parameters": {...}
    }
]
```

### 3. 自定义步骤类型

添加新的步骤类型非常简单：

1. 创建 `step_executor/new_step.py`
2. 实现 `run_new_step(step, context, events)`
3. 在 `execute_step.py` 的 `STEP_DISPATCHER` 中注册
4. 在 `__init__.py` 中导出

---

## 📚 相关文件

- `python-worker/agents/qwen/qwen_prompts.py`: Agent 级别 Prompt
- `python-worker/agents/qwen/qwen_worker_v2.py`: Worker 主入口
- `python-worker/step_executor/`: 通用步骤执行器（根目录版本）
- `python-worker/planner.py`: 任务拆解器
- `python-worker/TaskModel_v2.py`: 任务数据模型 v2

---

## ✅ 检查清单

- [x] 所有 step 文件使用相对导入
- [x] Prompt 模板集中到 `prompts.py`
- [x] `execute_step.py` 统一调度
- [x] `qwen_api.py` 支持包内外导入
- [x] 步骤状态管理实现
- [x] 取消机制集成
- [x] 测试脚本编写
- [x] 文档完善

---

## 🎉 总结

本次重构完成了以下目标：

1. ✅ **Prompt 规范化**: 所有 Prompt 模板集中管理，统一格式
2. ✅ **模块化**: 每个步骤独立，职责清晰
3. ✅ **可复用**: 支持快速添加新步骤，支持多 Agent 协作
4. ✅ **易测试**: 每个步骤可独立测试
5. ✅ **易扩展**: 新增功能无需修改核心逻辑

新架构为未来的功能扩展奠定了坚实基础！🚀
