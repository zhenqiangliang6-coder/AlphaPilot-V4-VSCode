# DeepSeek Worker v3.0 — 阿里云 MAAS + 本地 Redis 架构

## 📋 概述

DeepSeek Worker v3.0 是基于阿里云 MAAS (Model-as-a-Service) 平台的 DeepSeek 大模型构建的标准化智能体执行引擎，已与 Qwen Worker v3.0 完全对齐。

## 🎯 核心特性

- **三级 API 降级链**: `deepseek-v4-pro-0813` → `deepseek-v4-pro` → 火山引擎 Ark，确保高可用
- **记忆中枢集成**: 任务前注入历史记忆，任务后自动保存
- **意图识别与动态路由**: LLM + Regex 联合路由，v4.0 Execution Profile 动态决策
- **Post-analyze 链重决策**: analyze 完成后重新评估执行链
- **自清理机制**: 上次生成文件自动清理
- **协议验证**: Multi-Agent JSON 输出格式验证
- **死信队列**: 失败任务不丢失，可重试
- **工作区扫描**: 多语言项目文件自动索引

## 🏗️ 架构组成

```
deepeek/
├── deepseek_api.py          # API 调用封装（三级降级链）
├── deepseek_prompts.py      # Agent 级 Prompt 模板
├── deepseek_worker_v3.py    # Worker 主入口（v3.0 完全重写）
├── README.md                # 本文档
└── step_executor/           # 标准步骤执行器
    ├── __init__.py
    ├── execute_step.py      # 统一调度器
    ├── analyze_step.py
    ├── workspace_step.py    # 工作区扫描
    ├── plan_step.py
    ├── write_step.py        # 含 creative_write_prompt 创意意图支持
    ├── refine_step.py
    ├── test_step.py
    ├── fix_step.py
    ├── doc_step.py
    └── docstring_step.py
```

## 🚀 快速开始

### 1. 环境配置

在 `.env` 文件中配置：

```bash
# DeepSeek MAAS API Key（阿里云）
DEEPSEEK_MAAS_API_KEY=your_maas_api_key_here

# DeepSeek MAAS Base URL
DEEPSEEK_MAAS_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 主模型
DEEPSEEK_MAAS_MODEL=deepseek-v4-pro-0813

# 降级模型
DEEPSEEK_MAAS_FALLBACK_MODEL=deepseek-v4-pro

# 本地 Redis（与 Qwen/ModelScope 共享）
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
LOCAL_REDIS_MODELS=maas,modelscope,deepseek
```

### 2. 启动 Worker

```bash
# 独立启动
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.deepeek.deepseek_worker_v3

# 或通过 start_all.ps1 统一启动
.\start_all.ps1
```

## 🔄 API 降级链

```
主模型: deepseek-v4-pro-0813 (阿里云 MAAS)
  │
  ├─ 成功 → 返回结果
  │
  └─ 失败 (网络/配额/限流)
       │
       └─ 降级: deepseek-v4-pro (阿里云 MAAS)
            │
            ├─ 成功 → 返回结果
            │
            └─ 失败
                 │
                 └─ 回退: 火山引擎 Ark (VOLC_DEEPSEEK_API_KEY)
```

## 📊 执行流程

### v4.0 动态执行链

执行链由 `IntentRouter.build_execution_chain()` 动态组装，不再使用静态映射：

```
analyze → workspace → plan → write → refine → test → fix → doc → docstring
```

创意意图（creative_writing/translate/chat）自动裁剪链：
```
analyze → plan → respond
```

## 🔧 与 Qwen Worker v3.0 对齐清单

| 功能 | Qwen | DeepSeek |
|------|------|----------|
| 意图识别 | ✅ | ✅ |
| 记忆中枢 | ✅ | ✅ |
| 工作区扫描 | ✅ | ✅ |
| Post-analyze 重决策 | ✅ | ✅ |
| Execution Profile | ✅ | ✅ |
| 自清理机制 | ✅ | ✅ |
| 协议验证 | ✅ | ✅ |
| 死信队列 | ✅ | ✅ |
| 创意意图优化 | ✅ | ✅ |
| 本地 Redis | ✅ | ✅ |
| start_all.ps1 | ✅ | ✅ |

## 🛠️ 故障排查

### 常见问题

1. **MAAS API Key 未设置**
   - 检查 `.env` 中 `DEEPSEEK_MAAS_API_KEY` 是否正确
   - 验证 Key 是否在阿里云 DashScope 控制台有效

2. **Redis 连接失败**
   - 确认本地 Redis 已启动: `redis-cli ping`
   - 检查 `.env` 中 `LOCAL_REDIS_MODELS` 是否包含 `deepseek`

3. **API 降级触发**
   - 正常行为，检查主模型是否需要续费/扩容
   - 查看日志确认降级原因（网络超时/配额不足/限流）

## 📈 性能特性

- 主模型 `deepseek-v4-pro-0813` 为最新 Pro 版本，编程能力最强
- 降级模型 `deepseek-v4-pro` 为稳定版本，作为容错保障
- 火山引擎 Ark 作为最后一层兜底
- 本地 Redis 零网络延迟

## 🔮 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-03 | 初始版本，火山引擎 Ark |
| v2.0 | 2026-03 | 标准化 step executor |
| v3.0 | 2026-10 | 完全重写：MAAS 三级降级 + 本地 Redis + Qwen 对齐 |

## 👥 维护者

DavidLiang — 2026-10-11