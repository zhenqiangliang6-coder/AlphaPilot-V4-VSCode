# Volcengine Worker v2 - 豆包大模型智能体执行引擎

## 📋 概述

Volcengine Worker v2 是基于火山引擎 Ark 平台的豆包大模型（Doubao）构建的标准化智能体执行引擎，遵循 AlphaPilot 的统一架构规范。

## 🎯 核心特性

- **多模态理解能力**：支持图文结合的任务处理
- **视觉分析能力强**：擅长图片内容识别和描述
- **标准化流程**：遵循 analyze → plan → write → refine → test 的标准执行链
- **任务取消机制**：支持分布式任务取消标记
- **错误恢复**：自动重试和死信队列处理
- **步骤状态管理**：pending → running → success/error 的完整状态跟踪

## 🏗️ 架构组成

```
Volcengine/
├── doubao_api.py          # API 调用封装（支持多模态）
├── doubao_prompts.py      # Agent 级 Prompt 模板
├── doubao_worker_v2.py    # Worker 主入口
└── step_executor/         # 标准步骤执行器
    ├── __init__.py
    ├── execute_step.py    # 统一调度器
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
# 火山引擎 API Key
VOLC_API_KEY=your_api_key_here

# 可选：指定豆包模型版本
DOUBAO_MODEL=doubao-seed-2-0-lite-260215

# Redis 配置（Upstash）
UPSTASH_REDIS_REST_URL=https://your-redis-url
UPSTASH_REDIS_REST_TOKEN=your_redis_token

# Node API 地址
NODE_API_URL=http://localhost:3000
```

### 2. 启动 Worker

```bash
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.Volcengine.doubao_worker_v2
```

### 3. 提交任务

#### 3.1 文本任务

通过 Redis 队列提交纯文本任务：

```python
import redis
import json
from TaskModel_v2 import TaskModel

r = redis.Redis(...)

# 创建任务
task = TaskModel.create_task_submit(
    task_id="task-123",
    task_type="doubao_generate",
    payload={
        "prompt": "创建一个计算斐波那契数列的函数"
    }
)

# 推送到队列
r.lpush("task_queue", json.dumps(task))
```

#### 3.2 多模态任务

提交包含图片的多模态任务：

```python
task = TaskModel.create_task_submit(
    task_id="task-456",
    task_type="doubao_multimodal",
    payload={
        "prompt": "请分析这张图片的内容",
        "image_url": "https://example.com/image.png"
    }
)

r.lpush("task_queue", json.dumps(task))
```

## 📊 执行流程

### 标准步骤序列

1. **analyze** - 需求分析与风险识别
   - 深入理解问题本质
   - 识别已知条件和约束
   - 分析潜在风险点
   - （多模态任务）综合分析图文信息

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

## 🔧 多模态 API 调用

豆包 Worker 支持灵活的多模态调用方式：

```python
from .doubao_api import call_doubao

# 纯文本输入
result = call_doubao("请描述一下春天的景象")

# 图文结合输入
result = call_doubao(
    prompt="这张图片里有什么？",
    image_url="https://example.com/image.png"
)

# 流式调用（如果支持）
for chunk in call_doubao_stream(prompt, image_url):
    print(chunk, end='')
```

## 📝 Prompt 特色

豆包 Worker 的 Prompt 设计充分体现了模型特色：

- **多模态融合**：引导模型综合考虑图文信息
- **视觉分析框架**：从基础描述到深层分析的完整框架
- **图像问答提示**：基于可见信息，不臆测
- **结构化输出**：确保输出可被程序解析
- **能力边界明确**：避免模型越界或幻觉

## 🛠️ 故障排查

### 常见问题

1. **API Key 未设置**
   - 检查 `.env` 文件是否存在
   - 确认环境变量名称正确（VOLC_API_KEY）
   - 验证 API Key 有效性

2. **Redis 连接失败**
   - 检查 Upstash URL 和 Token
   - 确认网络连接正常
   - 验证 Redis 服务状态

3. **多模态任务失败**
   - 确认 image_url 可访问
   - 检查图片格式是否支持
   - 验证模型是否支持多模态

4. **任务执行超时**
   - 增加 timeout 参数值
   - 检查模型响应速度
   - 图片较大时处理时间较长

## 📈 性能优化

- 合理设置图片尺寸（避免过大）
- 使用流式输出提升用户体验
- 合理设置重试次数和延迟
- 利用 Redis 缓存中间结果
- 分布式场景下注意取消标记同步

## 🔮 未来扩展

- 支持更多火山引擎模型（如 DeepSeek 等）
- 增强的多模态处理能力
- 支持 Tool Calling（搜索、图像分析等）
- 多 Agent 协作能力
- 更复杂的任务规划策略

## 📚 参考文档

- [Qwen Worker v2 架构](../qwen/ARCHITECTURE_REFACTOR.md)
- [Task Model v2 规范](../../TASK_MODEL_SPECIFICATION.md)
- [Worker 配置说明](../../worker_config.py)
- [DeepSeek Worker v2](../deepeek/README.md)

## 👥 作者

DavidLiang - 2026-03-31
