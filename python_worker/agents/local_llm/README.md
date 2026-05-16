# Local LLM Worker v3.0 - 快速开始指南

## 📋 概述

Local LLM Worker v3.0 是 AlphaPilot OS 的本地模型执行引擎，支持 Ollama 等本地 LLM 服务。它完全遵循 AlphaPilot v3.1 架构信条，与 Doubao/Qwen/DeepSeek Worker 保持一致的架构模式。

### ✨ 核心特性

- **Intent Router**：智能意图识别（write_code/explain_code/fix_code 等）
- **Persona Engine**：三种人格模式（工程师/创作者/对话）
- **Execution Chain**：动态执行链（analyze → plan → write → refine → test → fix → doc）
- **FileOps v3.0**：多文件协议支持
- **流式输出**：实时推送生成内容到前端
- **任务取消**：支持运行时取消任务

---

## 🚀 前置要求

### 1. 安装 Ollama

```powershell
# Windows (winget)
winget install Ollama.Ollama

# 或者从官网下载
# https://ollama.com/download
```

### 2. 下载模型

```powershell
# 推荐模型（轻量级，适合本地运行）
ollama pull gemma2:2b

# 其他可选模型
ollama pull llama3.2:1b    # 更轻量
ollama pull qwen2.5:1.5b   # 中文优化
ollama pull mistral:7b     # 更强性能
```

### 3. 启动 Ollama 服务

```powershell
# Ollama 会自动在后台运行
# 验证服务是否启动
ollama list
```

---

## ⚙️ 配置

### 环境变量（可选）

在项目根目录的 `.env` 文件中添加：

```env
# Local LLM 配置
LOCAL_MODEL_NAME=gemma2:2b
LOCAL_OLLAMA_URL=http://localhost:11434

# Worker 配置
WORKER_ID=local-worker-1
NODE_API_URL=http://localhost:3000

# Redis 配置（根据模型类型自动选择）
REDIS_TYPE=auto  # auto/upstash/tair/memory
```

---

## 🧪 测试

### 1. 测试 Ollama 连接

```powershell
cd python_worker
python test_local_llm.py
```

预期输出：
```
============================================================
🧪 Local LLM Worker v3.0 - 连接测试
============================================================

📡 步骤 1: 测试 Ollama 连接...
✅ Ollama 连接成功，可用模型: ['gemma2:2b']

💬 步骤 2: 测试基本对话...
✅ 响应成功:
你好！我是 Gemma，一个由 Google DeepMind 开发的大型语言模型...

💻 步骤 3: 测试代码生成...
✅ 代码生成成功:
def fibonacci(n):
    if n <= 0:
        return []
    ...

============================================================
✅ 所有测试通过！Local LLM Worker 可以正常使用。
============================================================
```

### 2. 启动 Worker

```powershell
# 设置环境变量
$env:WORKER_ID="local-worker-1"
$env:NODE_API_URL="http://localhost:3000"

# 启动 Worker
cd python_worker
python -m agents.local_llm.local_worker_v3
```

---

## 📦 架构说明

### 文件结构

```
python_worker/agents/local_llm/
├── local_api.py              # Ollama API 封装（支持流式）
├── local_worker_v3.py        # Worker 主文件（v3.0 架构）
├── personas.py               # 人格引擎配置
└── step_executor/            # 步骤执行器
    ├── __init__.py           # 模块导出
    ├── execute_step.py       # 统一步骤调度器
    ├── analyze_step.py       # 需求分析步骤
    ├── plan_step.py          # 计划生成步骤
    ├── write_step.py         # 代码生成步骤
    ├── refine_step.py        # 代码优化步骤
    ├── test_step.py          # 单元测试步骤
    ├── fix_step.py           # 错误修复步骤
    ├── profile_step.py       # 性能分析步骤
    ├── doc_step.py           # 文档生成步骤
    ├── prompts.py            # Prompt 模板
    ├── utils.py              # 工具函数
    └── qwen_api.py           # Qwen API（向后兼容）
```

### 执行流程

```
用户请求 → Intent Router → Persona Engine → Execution Chain
                                    ↓
                    analyze → plan → write → refine → test → fix → doc
                                    ↓
                            Local LLM (Ollama)
                                    ↓
                        Node API → VSCode Extension
```

---

## 🔧 故障排查

### 问题 1：无法连接到 Ollama

**症状**：
```
ConnectionError: 无法连接到 Ollama 服务 (http://localhost:11434)
```

**解决方案**：
```powershell
# 检查 Ollama 是否运行
ollama list

# 如果没有运行，启动 Ollama
ollama serve

# 验证端口
netstat -ano | findstr "11434"
```

### 问题 2：模型未找到

**症状**：
```
RuntimeError: Local LLM API 调用失败: model "gemma2:2b" not found
```

**解决方案**：
```powershell
# 下载模型
ollama pull gemma2:2b

# 或修改 LOCAL_MODEL_NAME 为已安装的模型
```

### 问题 3：Redis 连接失败

**症状**：
```
ValueError: UPSTASH_REDIS_REST_URL 和 UPSTASH_REDIS_REST_TOKEN 必须设置
```

**解决方案**：
```powershell
# 使用内存模式（仅用于调试）
$env:USE_MEMORY_REDIS="true"

# 或配置正确的 Redis 凭据
```

---

## 📊 性能对比

| 模型 | 参数量 | 显存需求 | 推理速度 | 适用场景 |
|------|--------|----------|----------|----------|
| gemma2:2b | 2B | ~2GB | ⚡⚡⚡ 快 | 日常对话、简单代码 |
| llama3.2:1b | 1B | ~1GB | ⚡⚡⚡⚡ 很快 | 轻量任务、边缘设备 |
| qwen2.5:1.5b | 1.5B | ~1.5GB | ⚡⚡⚡ 快 | 中文任务 |
| mistral:7b | 7B | ~4GB | ⚡⚡ 中等 | 复杂推理、高质量代码 |

---

## 🎯 下一步

1. **集成到 AlphaPilot**：在 VSCode Extension 中添加 "local_generate" 任务类型
2. **自定义 Prompt**：根据需求调整 `prompts.py` 中的模板
3. **扩展步骤**：添加新的执行步骤（如 security_audit、code_review）
4. **多模型切换**：实现动态模型选择机制

---

## 📝 参考文档

- [AlphaPilot v3.1 Worker 升级架构方案](../../ARCHITECTURE_MANIFESTO.md)
- [Doubao Worker v3.0 实现](../Volcengine/doubao_worker_v3.py)
- [Qwen Worker v3.0 实现](../qwen/qwen_worker_v3.py)
- [TaskModel v2 规范](../../TASK_MODEL_SPECIFICATION.md)

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**最后更新**: 2026-05-15  
**版本**: v3.0  
**维护者**: AlphaPilot Team
