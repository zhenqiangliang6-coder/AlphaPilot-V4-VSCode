# DeepSeek Worker v2 - 标准化智能体执行引擎

## 📋 概述

DeepSeek Worker v2 是基于火山引擎 Ark 平台的 DeepSeek 大模型构建的标准化智能体执行引擎，遵循 AlphaPilot 的统一架构规范。

## 🎯 核心特性

- **强推理能力**：充分发挥 DeepSeek 模型的逻辑推理优势
- **标准化流程**：遵循 analyze → plan → write → refine → test → fix → profile → doc 的标准执行链
- **流式输出支持**：实时展示推理过程和生成内容
- **任务取消机制**：支持分布式任务取消标记
- **错误恢复**：自动重试和死信队列处理
- **步骤状态管理**：pending → running → success/error 的完整状态跟踪

## 🏗️ 架构组成

```
deepeek/
├── deepseek_api.py          # API 调用封装（支持流式）
├── deepseek_prompts.py      # Agent 级 Prompt 模板
├── deepseek_worker_v2.py    # Worker 主入口
└── step_executor/           # 标准步骤执行器
    ├── __init__.py
    ├── execute_step.py      # 统一调度器
    ├── analyze_step.py
    ├── plan_step.py
    ├── write_step.py
    ├── refine_step.py
    ├── test_step.py
    ├── fix_step.py
    ├── profile_step.py
    └── doc_step.py
```

## 🚀 快速开始

### 1. 环境配置

在 `.env` 文件中配置：

```bash
# DeepSeek API Key（火山引擎 Ark 平台）
VOLC_DEEPSEEK_API_KEY=your_api_key_here

# 可选：指定模型版本
VOLC_DEEPSEEK_MODEL=deepseek-v3-250324

# Redis 配置（Upstash）
UPSTASH_REDIS_REST_URL=https://your-redis-url
UPSTASH_REDIS_REST_TOKEN=your_redis_token

# Node API 地址
NODE_API_URL=http://localhost:3000
```

### 2. 启动 Worker

```bash
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.deepeek.deepseek_worker_v2
```

### 3. 提交任务

通过 Redis 队列提交任务：

```python
import redis
import json
from TaskModel_v2 import TaskModel

r = redis.Redis(...)

# 创建任务
task = TaskModel.create_task_submit(
    task_id="task-123",
    task_type="deepseek_generate",
    payload={
        "prompt": "创建一个计算斐波那契数列的函数"
    }
)

# 推送到队列
r.lpush("task_queue", json.dumps(task))
```

## 📊 执行流程

### 标准步骤序列

1. **analyze** - 需求分析与风险识别
   - 深入理解问题本质
   - 识别已知条件和约束
   - 分析潜在风险点

2. **plan** - 方案设计与伪代码规划
   - 设计最优解决方案
   - 考虑多种可能性
   - 提供伪代码规划

3. **write** - 代码实现
   - 生成高质量、可维护的代码
   - 遵循最佳实践
   - 考虑边界情况

4. **refine** - 代码优化
   - 执行生成的代码
   - 根据执行结果优化
   - 改进代码质量

5. **test** - 测试验证
   - 自动生成单元测试
   - 覆盖边界情况
   - 验证功能正确性

6. **fix** - 错误修复（如需要）
   - 检测执行错误
   - 自动修复问题
   - 验证修复效果

7. **profile** - 性能分析（如需要）
   - 分析时间/空间复杂度
   - 提供优化建议
   - 基准测试

8. **doc** - 文档生成（如需要）
   - 生成 Markdown 文档
   - 添加代码注释
   - 提供使用说明

## 🔧 自定义 API 调用

DeepSeek Worker 支持灵活的 API 调用方式：

```python
from .deepseek_api import call_deepseek

# 非流式调用
result = call_deepseek(prompt, stream=False)

# 流式调用
result = call_deepseek(prompt, stream=True)
```

## 📝 Prompt 特色

DeepSeek Worker 的 Prompt 设计充分体现了模型特色：

- **深度思考框架**：引导模型逐步分析问题
- **代码审查提示**：从多个维度检查代码质量
- **结构化输出**：确保输出可被程序解析
- **能力边界明确**：避免模型越界或幻觉

## 🛠️ 故障排查

### 常见问题

1. **API Key 未设置**
   - 检查 `.env` 文件是否存在
   - 确认环境变量名称正确
   - 验证 API Key 有效性

2. **Redis 连接失败**
   - 检查 Upstash URL 和 Token
   - 确认网络连接正常
   - 验证 Redis 服务状态

3. **任务执行超时**
   - 增加 timeout 参数值
   - 检查模型响应速度
   - 考虑使用流式输出

## 📈 性能优化

- 使用流式输出提升用户体验
- 合理设置重试次数和延迟
- 利用 Redis 缓存中间结果
- 分布式场景下注意取消标记同步

## 🔮 未来扩展

- 支持 Tool Calling（搜索、代码解释器等）
- 多 Agent 协作能力
- 更复杂的任务规划策略
- 增强的错误恢复机制

## 📚 参考文档

- [Qwen Worker v2 架构](../qwen/ARCHITECTURE_REFACTOR.md)
- [Task Model v2 规范](../../TASK_MODEL_SPECIFICATION.md)
- [Worker 配置说明](../../worker_config.py)

## 👥 作者

DavidLiang - 2026-03-31
