# 多模型 Worker v2 统一架构指南

## 📋 概述

本项目已成功实现基于三种不同大模型的标准化智能体执行引擎，标志着系统从"手工作坊"正式升级为"自动化工厂"架构。

## 🎯 支持的模型

### 1. Qwen Worker v2（通义千问）
- **位置**: `python_worker/agents/qwen/`
- **API**: DashScope API
- **特点**: 中文理解能力强、长上下文处理、逻辑稳定
- **状态**: ✅ 已完成并验证

### 2. DeepSeek Worker v2（深度求索）
- **位置**: `python_worker/agents/deepeek/`
- **API**: 火山引擎 Ark 平台 - Chat Completions API
- **特点**: 强推理、强数学、强代码、强中文表达
- **状态**: ✅ 已完成并验证

### 3. Doubao Worker v2（豆包大模型）
- **位置**: `python_worker/agents/Volcengine/`
- **API**: 火山引擎 Ark 平台 - Responses API
- **特点**: 多模态理解、视觉分析、中文友好
- **状态**: ✅ 已完成并验证

## 🏗️ 统一架构规范

所有 Worker 均遵循以下统一架构：

### 核心组成

```
model_worker/
├── model_api.py          # API 调用封装
├── model_prompts.py      # Agent 级 Prompt 模板
├── model_worker_v2.py    # Worker 主入口
└── step_executor/        # 标准步骤执行器
    ├── __init__.py
    ├── execute_step.py   # 统一调度器
    ├── analyze_step.py
    ├── plan_step.py
    ├── write_step.py
    ├── refine_step.py
    ├── test_step.py
    ├── fix_step.py
    ├── profile_step.py
    └── doc_step.py
```

### 标准执行流程

所有模型 Worker 必须遵循以下固定步骤序列：

1. **analyze** - 需求分析与风险识别
2. **plan** - 方案设计与伪代码规划
3. **write** - 代码实现
4. **refine** - 代码优化（可选）
5. **test** - 自动生成测试并验证
6. **fix** - 错误修复（如需要）
7. **profile** - 性能分析（如需要）
8. **doc** - 文档生成（如需要）

### 通用数据协议

所有 Worker 使用相同的数据交互协议：

```python
# 任务提交格式
task = {
    "version": "2.0",
    "task_id": "task-123",
    "type": "model_generate",
    "status": "pending",
    "payload": {"prompt": "..."},
    "steps": [],
    "events": [],
    "context": {...},
    "meta": {...}
}

# 成功结果格式
result = {
    "version": "2.0",
    "task_id": "task-123",
    "type": "model_generate",
    "status": "done",
    "result": "生成的内容",
    "steps": [...],
    "events": [...],
    "context": {...},
    "meta": {...}
}
```

## 🚀 快速开始

### 环境配置

在 `.env` 文件中配置所有模型的 API Key：

```bash
# Qwen (DashScope)
DASHSCOPE_API_KEY=your_dashscope_key

# DeepSeek (火山引擎)
VOLC_DEEPSEEK_API_KEY=your_volc_key
VOLC_DEEPSEEK_MODEL=deepseek-v3-250324

# Doubao (火山引擎)
VOLC_API_KEY=your_volc_key
DOUBAO_MODEL=doubao-seed-2-0-lite-260215

# Redis (Upstash)
UPSTASH_REDIS_REST_URL=https://your-redis-url
UPSTASH_REDIS_REST_TOKEN=your_redis_token

# Node API
NODE_API_URL=http://localhost:3000
```

### 启动 Worker

#### 启动 Qwen Worker

```bash
# Qwen
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.qwen.qwen_worker_v2

# DeepSeek
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.deepeek.deepseek_worker_v2

# Doubao
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.Volcengine.doubao_worker_v2
```


## 🔧 扩展新模型

接入新模型（如 OpenAI, Gemini）时，仅需以下步骤：

### 1. 创建目录结构

```bash
mkdir -p python_worker/agents/openai/step_executor
```

### 2. 实现 API 封装

创建 `openai_api.py`：

```python
import requests
import os

def call_openai(prompt: str) -> str:
    """调用 OpenAI API"""
    api_key = os.getenv("OPENAI_API_KEY")
    url = "https://api.openai.com/v1/chat/completions"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": prompt}]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    
    return response.json()["choices"][0]["message"]["content"]
```

### 3. 创建 Prompt 模板

创建 `openai_prompts.py`（复制并根据模型特色调整）：

```python
OPENAI_SYSTEM_PROMPT = """
你是 AlphaPilot 的 OpenAI Agent...
"""
```

### 4. 复制 step_executor

```bash
cp -r python_worker/agents/qwen/step_executor/* python_worker/agents/openai/step_executor/
```

然后修改导入路径：
- 将 `from ..qwen_api import call_qwen` 改为 `from ..openai_api import call_openai`

### 5. 创建 Worker 主文件

创建 `openai_worker_v2.py`（复制 `qwen_worker_v2.py` 并修改）：

```python
from .step_executor import execute_step
from ...TaskModel_v2 import TaskModel

def call_openai_wrapper(prompt: str) -> str:
    from .openai_api import call_openai
    return call_openai(prompt)

# 主循环与 qwen_worker_v2.py 保持一致
```

### 6. 更新导出配置

修改 `step_executor/__init__.py`：

```python
from ..openai_api import call_openai

__all__ = [
    # ...
    "call_openai",
    # ...
]
```

### 7. 添加 README

创建 `README.md` 说明使用方法。

## 📊 模型特性对比

| 特性 | Qwen | DeepSeek | Doubao |
|------|------|----------|--------|
| 中文理解 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 逻辑推理 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 代码能力 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 多模态 | ❌ | ❌ | ⭐⭐⭐⭐⭐ |
| 长上下文 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 流式输出 | ✅ | ✅ | ✅ |

## 🛠️ 故障排查

### 常见问题

1. **ModuleNotFoundError**
   - 检查 `__init__.py` 是否存在
   - 确认相对导入路径正确
   - 使用 `python -m` 方式运行

2. **API Key 未设置**
   - 检查 `.env` 文件
   - 确认环境变量名称
   - 验证 API Key 有效性

3. **Redis 连接失败**
   - 检查 Upstash 配置
   - 验证网络连接
   - 确认 SSL 设置

## 📈 最佳实践

1. **统一的代码风格**：所有 Worker 保持一致的代码结构
2. **相对导入原则**：严格遵循 Python 模块导入规范
3. **错误处理**：每个步骤都要有完善的异常处理
4. **日志记录**：关键操作都要记录到 events 和 context
5. **可取消性**：支持分布式任务取消机制

## 🔮 未来规划

- [ ] 支持更多模型（OpenAI, Gemini, Claude 等）
- [ ] 多 Agent 协作能力
- [ ] Tool Calling 支持
- [ ] 增强的任务规划策略
- [ ] 更好的错误恢复机制
- [ ] 性能监控和优化

## 📚 参考文档

- [Qwen Worker v2](qwen/README.md)
- [DeepSeek Worker v2](deepeek/README.md)
- [Doubao Worker v2](Volcengine/README.md)
- [Task Model v2 规范](../TASK_MODEL_SPECIFICATION.md)
- [Worker 配置说明](../worker_config.py)

## 👥 作者

DavidLiang - 2026-03-31
