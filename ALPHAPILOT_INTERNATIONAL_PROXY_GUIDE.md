# AlphaPilot International Proxy - 使用指南（D:\Copilot_Alphapilot 项目专用）

本文档说明如何在 **D:\Copilot_Alphapilot** 项目中使用 AlphaPilot International Proxy 代理服务。

---

## 📌 快速开始

### 1. 启动代理服务

#### 方法一：使用批处理脚本（推荐）

双击运行：
```
d:\alphapilot-international-proxy\start_proxy.bat
```

#### 方法二：使用 PowerShell 脚本（更高级）

右键选择 "使用 PowerShell 运行"：
```
d:\alphapilot-international-proxy\start_proxy.ps1
```

#### 方法三：手动启动

```powershell
cd d:\alphapilot-international-proxy
uvicorn main:app --host 0.0.0.0 --port 8000
```

**启动成功后**：
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

### 2. 验证代理服务

在浏览器中访问：
- **健康检查**: http://localhost:8000/
- **模型列表**: http://localhost:8000/v1/models
- **原生模型列表**: http://localhost:8000/gemini/v1beta/models

**预期响应**：
```json
{
  "status": "ok",
  "message": "AlphaPilot Proxy is running. Version 2.0.0",
  "default_model": "gemini-2.5-flash",
  "models": [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-pro-image"
  ],
  "auth_required": false
}
```

---

### 3. 在 D:\Copilot_Alphapilot 项目中调用

#### 方式一：OpenAI 兼容格式（推荐）

**适用场景**：使用第三方工具（如 Qwen Code、LangChain 等）

**API 端点**：
```
POST http://localhost:8000/v1/chat/completions
```

**请求示例**（Python）：
```python
import requests

url = "http://localhost:8000/v1/chat/completions"
headers = {
    "Content-Type": "application/json"
}
data = {
    "model": "gemini-3.6-flash",
    "messages": [
        {"role": "user", "content": "你好，请介绍一下自己"}
    ],
    "temperature": 0.7,
    "max_tokens": 500
}

response = requests.post(url, json=data, headers=headers)
result = response.json()

print(result["choices"][0]["message"]["content"])
```

**流式请求示例**：
```python
import requests
import json

url = "http://localhost:8000/v1/chat/completions"
headers = {
    "Content-Type": "application/json"
}
data = {
    "model": "gemini-3.6-flash",
    "messages": [
        {"role": "user", "content": "请用三句话介绍人工智能"}
    ],
    "stream": True
}

response = requests.post(url, json=data, headers=headers, stream=True)

for line in response.iter_lines():
    if line:
        line_str = line.decode("utf-8")
        if line_str.startswith("data: ") and line_str != "data: [DONE]":
            chunk = json.loads(line_str[6:])
            content = chunk["choices"][0]["delta"].get("content", "")
            print(content, end="", flush=True)
```

---

#### 方式二：原生 Gemini 格式

**适用场景**：自研项目（Copilot_Alphapilot）直接使用 Gemini 原生功能

**API 端点**：
```
POST http://localhost:8000/gemini/v1beta/models/{model}:generateContent
POST http://localhost:8000/gemini/v1beta/models/{model}:streamGenerateContent
```

**请求示例**（Python）：
```python
import requests

url = "http://localhost:8000/gemini/v1beta/models/gemini-3.6-flash:generateContent"
headers = {
    "Content-Type": "application/json"
}
data = {
    "contents": [
        {
            "role": "user",
            "parts": [
                {"text": "你好，请介绍一下自己"}
            ]
        }
    ],
    "generationConfig": {
        "temperature": 0.7,
        "maxOutputTokens": 500
    }
}

response = requests.post(url, json=data, headers=headers)
result = response.json()

print(result["candidates"][0]["content"]["parts"][0]["text"])
```

---

## 🔧 配置说明

### 环境变量配置（.env 文件）

在 `d:\alphapilot-international-proxy` 目录下创建 `.env` 文件：

```env
# Google Gemini API Key（必须）
GOOGLE_API_KEY=AIzaSy...

# 代理服务认证密钥（可选，生产环境建议设置）
PROXY_API_KEY=your-secure-api-key

# 默认模型
PROXY_DEFAULT_MODEL=gemini-3.6-flash

# 模型列表（逗号分隔）
PROXY_MODEL_LIST=gemini-3.6-flash,gemini-3.5-flash,gemini-3.1-flash-lite,gemini-3-pro-image

# VPN 代理配置（中国大陆必须）
HTTP_PROXY=http://127.0.0.1:22307
HTTPS_PROXY=http://127.0.0.1:22307

# 请求超时（秒）
PROXY_TIMEOUT=300

# 最大输出 token 数
PROXY_MAX_OUTPUT_TOKENS=8192

# 温度参数
PROXY_TEMPERATURE=0.7
```

---

### 中国大陆网络适配

在中国大陆环境下，必须配置 VPN 代理才能访问 Google Gemini 等外部 API。

**配置步骤**：

1. **启动本地 VPN 代理**（假设监听 22307 端口）

2. **在 .env 文件中配置**：
```env
HTTP_PROXY=http://127.0.0.1:22307
HTTPS_PROXY=http://127.0.0.1:22307
```

3. **或临时设置环境变量**（PowerShell）：
```powershell
$env:HTTP_PROXY = "http://127.0.0.1:22307"
$env:HTTPS_PROXY = "http://127.0.0.1:22307"
```

---

## 📊 可用模型列表

| 模型名称 | 状态 | 说明 | 适用场景 |
|---------|------|------|---------|
| `gemini-3.6-flash` | ✅ 推荐 | 最新稳定版，支持工具调用 | 通用对话、编程助手 |
| `gemini-3.5-flash` | ✅ 可用 | 稳定版本 | 通用对话 |
| `gemini-3.1-flash-lite` | ✅ 可用 | 轻量版本 | 低延迟场景 |
| `gemini-3-pro-image` | ✅ 可用 | 支持图像生成 | 多模态任务 |

**动态更新模型列表**：

修改 `.env` 文件：
```env
PROXY_MODEL_LIST=gemini-3.6-flash,gemini-3.5-flash,你的新模型
```

重启代理服务即可生效。

---

## 🤖 Gemini Worker v3.0 — Google Gemini 原生接口集成

### 架构概述

Gemini Worker v3.0 是 AlphaPilot OS 的世界级执行链架构版本，使用 **Google Gemini 原生接口**（通过 AlphaPilot International Proxy）驱动。

**核心特性**：
- ✅ **Intent Router**：智能意图识别
- ✅ **Persona Engine**：执行链人格（engineer/creator/conversational）
- ✅ **Execution Chain**：analyze → plan → write → refine → test → fix → doc → docstring → profile
- ✅ **FileOps**：多文件协议 v3.0
- ✅ **Memory Integration**：记忆中枢集成
- ✅ **Streaming Output**：流式输出支持
- ✅ **Error Degradation**：非核心步骤异常降级

### 文件结构

```
python_worker/agents/gemini/
├── __init__.py                    # Gemini 模块初始化
├── gemini_api.py                  # ⭐ Google Gemini 原生 API 客户端
├── gemini_worker_v2.py            # ⭐ Gemini Worker 主程序（v3.0 架构）
├── personas.py                    # 执行链人格配置
├── gemini_prompts.py              # Agent 级别 Prompt 模板
└── step_executor/                 # 步骤执行器
    ├── __init__.py
    ├── execute_step.py            # 统一步骤调度器
    ├── analyze_step.py            # 分析步骤（流式 + 人格）
    ├── plan_step.py               # 规划步骤（流式 + 人格）
    ├── write_step.py              # 代码生成步骤（流式 + 人格）
    ├── refine_step.py             # 代码优化步骤（流式 + 人格）
    ├── test_step.py               # 测试步骤
    ├── fix_step.py                # 修复步骤（流式 + 人格）
    ├── doc_step.py                # 文档步骤（非核心，异常降级）
    ├── profile_step.py            # 性能分析步骤（非核心，异常降级）
    ├── prompts.py                 # 步骤 Prompt 模板
    ├── qwen_api.py                # 向后兼容桥接层（内部调用 Gemini）
    └── utils.py                   # 工具函数
```

### API 调用架构

```
用户任务 → Redis 队列 → Gemini Worker v3.0
                              ↓
                        Intent Router（意图识别）
                              ↓
                        Persona Engine（人格选择）
                              ↓
                        Execution Chain（执行链构建）
                              ↓
                        Step Executor（步骤执行）
                              ↓
                        ┌─────────────────────┐
                        │  analyze_step.py    │
                        │  plan_step.py       │
                        │  write_step.py      │
                        │  refine_step.py     │
                        │  test_step.py       │
                        │  fix_step.py        │
                        │  doc_step.py        │
                        │  profile_step.py    │
                        └─────────────────────┘
                              ↓
                        gemini_api.py（Google Gemini 原生接口）
                              ↓
                        AlphaPilot International Proxy
                              ↓
                        Google Gemini API
```

### 配置说明

在 `python_worker/.env` 文件中配置：

```env
# Google Gemini API Key
# 注意：此处为占位符，真实密钥只写在本地 python_worker/.env 中，
#       .env 已被 .gitignore 忽略，切勿把真实 Key 提交到任何文档或代码里
GEMINI_API_KEY=your-gemini-api-key-here

# =========================
# Google Gemini 代理配置（AlphaPilot International Proxy）
# =========================
GEMINI_PROXY_URL=http://localhost:8000
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TIMEOUT=300
GEMINI_MAX_OUTPUT_TOKENS=8192
GEMINI_TEMPERATURE=0.7
```

### 启动 Gemini Worker

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.gemini.gemini_worker_v2
```

**预期输出**：
```
🚀 Gemini Worker v3.0 已启动（Google Gemini 原生接口）
   · Worker ID: gemini-worker-1
   · Node API: 已连接
   · API 接口: Google Gemini 原生 (via AlphaPilot Proxy)
   · 正在监听任务队列...

📡 Gemini Worker v3.0 监听队列: task_queue:gemini
```

### 任务提交示例

```python
import json
from python_worker.worker_config import redis

task = {
    "task_id": "test-gemini-001",
    "task_type": "gemini_generate",
    "payload": {
        "prompt": "创建一个 Python 函数，计算斐波那契数列的第 n 项",
        "user_id": "test_user",
        "language": "Python"
    },
    "meta": {
        "retry_count": 0,
        "started_at": int(time.time() * 1000)
    }
}

redis.lpush("task_queue:gemini", json.dumps(task))
print("✅ 任务已提交到 Gemini 队列")
```

### 执行链详解

#### 1. analyze（分析）
- **输入**：用户任务描述
- **输出**：需求分析（结构化自然语言）
- **特性**：流式输出 + 人格配置

#### 2. plan（规划）
- **输入**：analyze 步骤的分析结果
- **输出**：代码结构规划（自然语言 + 伪代码）
- **特性**：流式输出 + 人格配置

#### 3. write（生成）
- **输入**：plan 步骤的规划
- **输出**：完整的 Python 代码
- **特性**：流式输出 + 人格配置 + 多文件协议 v3.0

#### 4. refine（优化）
- **输入**：write 步骤的代码 + 执行结果
- **输出**：优化后的代码
- **特性**：流式输出 + 人格配置

#### 5. test（测试）
- **输入**：write 步骤的代码
- **输出**：pytest 风格测试代码 + 测试结果
- **特性**：自动生成测试 + 执行测试

#### 6. fix（修复）
- **输入**：write 步骤的代码 + 执行错误
- **输出**：修复后的代码 + 验证结果
- **特性**：流式输出 + 人格配置

#### 7. doc（文档）— 非核心步骤
- **输入**：write 步骤的代码
- **输出**：Markdown 文档 + 带 docstring 的代码
- **特性**：异常降级（失败不中断任务）

#### 8. profile（性能分析）— 非核心步骤
- **输入**：write 步骤的代码
- **输出**：性能分析报告 + 基准测试结果
- **特性**：异常降级（失败不中断任务）

### 人格配置

Gemini Worker 支持三种执行链人格：

| 人格类型 | 名称 | 图标 | 适用场景 |
|---------|------|------|---------|
| `engineer` | 工程师人格 | 👨‍💻 | 编程任务、技术文档 |
| `creator` | 创作者人格 | 🎨 | 创意写作、内容生成 |
| `conversational` | 对话人格 | 💬 | 问答、对话交互 |

人格由 Intent Router 根据用户意图自动选择。

### 错误处理机制

#### 非核心步骤降级
- `doc`、`docstring`、`profile` 等非核心步骤异常时，任务继续执行
- 降级步骤状态标记为 `warning` 而非 `failed`
- 确保核心步骤（write、refine、test、fix）的成果不被覆盖

#### 任务取消
- 支持通过 Redis 标记取消正在执行的任务
- 取消后任务状态标记为 `failed`，错误码为 `TASK_CANCELLED`

#### 死信队列（DLQ）
- 任务失败后自动写入死信队列
- 支持重试机制

---

## 🤖 接入 Qwen Code

详见主 README.md 文档的"接入 Qwen Code"章节。

**快速配置**：

编辑 `~/.qwen/settings.json`：
```json
{
  "modelProviders": {
    "openai": [
      {
        "id": "gemini-3.6-flash",
        "name": "Gemini 3.6 Flash via AlphaPilot Proxy",
        "baseUrl": "http://localhost:8000/v1",
        "envKey": "ALPHAPILOT_PROXY_API_KEY"
      }
    ]
  },
  "model": {
    "name": "gemini-3.6-flash"
  }
}
```

启动 Qwen Code：
```powershell
$env:ALPHAPILOT_PROXY_API_KEY = "your-proxy-api-key"
qwen
```

---

## 🧪 测试验证

### 1. 单元测试（17 个测试用例）

```powershell
cd d:\alphapilot-international-proxy
python test_proxy.py
```

**预期输出**：
```
PASS  test_auth_enforced_when_configured
PASS  test_default_max_output_tokens_is_large_enough
...
17/17 通过
```

### 2. 真实环境测试

```powershell
cd d:\alphapilot-international-proxy
python real_test.py
```

**预期输出**：
```
============================================================
📊 测试结果汇总
============================================================
健康检查: ✅ 通过
模型列表: ✅ 通过
真实对话: ✅ 通过
流式输出: ✅ 通过
============================================================
🎉 所有测试通过! 代理接口工作正常!
============================================================
```

### 3. 双协议测试

```powershell
cd d:\alphapilot-international-proxy
python test_dual_protocol.py
```

### 4. Gemini Worker 测试

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot

# 测试 Gemini API 连接
python -c "from python_worker.agents.gemini.gemini_api import call_gemini; print(call_gemini('你好，请介绍一下自己'))"

# 测试 Gemini Worker 启动
python -m python_worker.agents.gemini.gemini_worker_v2
```

---

## ❓ 常见问题

### 1. 服务启动失败

**错误**：`ModuleNotFoundError: No module named 'fastapi'`

**解决**：
```powershell
cd d:\alphapilot-international-proxy
pip install -r requirements.txt
```

---

### 2. 无法连接到 Google Gemini

**错误**：`Connection refused` 或 `Timeout`

**解决**：
- 检查 VPN 代理是否启动
- 检查 `.env` 文件中 `HTTP_PROXY` 和 `HTTPS_PROXY` 是否配置
- 检查 `GOOGLE_API_KEY` 是否正确（必须以 `AIzaSy` 开头）
- 检查 AlphaPilot Proxy 是否启动（`http://localhost:8000`）

---

### 3. 模型返回 404

**错误**：`Model 'gemini-xxx' is not supported`

**解决**：
- 访问 http://localhost:8000/v1/models 查看当前可用模型列表
- 使用返回列表中的模型名称

---

### 4. 模型返回 503

**错误**：`503 Service Unavailable`

**解决**：
- 这是上游 Google Gemini 的高负载问题
- 代理服务会自动尝试其他可用模型
- 如持续出现，稍后重试或切换备用代理（Vercel）

---

### 5. 流式输出中断

**错误**：流式响应突然停止

**解决**：
- 检查网络连接稳定性
- 增加 `PROXY_TIMEOUT` 值（默认 300 秒）
- 检查 VPN 代理是否正常工作

---

### 6. Gemini Worker 未收到任务

**错误**：Worker 启动后一直等待

**解决**：
- 检查任务类型是否为 `gemini_generate`
- 检查 Redis 队列名称是否为 `task_queue:gemini`
- 检查 AlphaPilot Proxy 是否启动

---

### 7. Gemini API 响应格式异常

**错误**：`Gemini API 响应格式异常: 'candidates'`

**解决**：
- 检查 AlphaPilot Proxy 是否正确转发响应
- 检查模型名称是否正确
- 查看代理日志以获取详细信息

---

## 🔄 更新与维护

### 更新代码

```powershell
cd d:\alphapilot-international-proxy
git pull origin main
pip install -r requirements.txt -U
```

### 查看日志

代理服务会在终端输出实时日志，包括：
- 请求信息
- 模型调用详情
- 错误信息

---

## 📞 技术支持

如遇到问题，请按以下步骤排查：

1. **运行单元测试**：`python test_proxy.py`
2. **运行真实测试**：`python real_test.py`
3. **检查日志输出**：查看 Uvicorn 启动日志
4. **检查环境变量**：确认 `.env` 文件配置正确
5. **检查网络连接**：确认 VPN 代理正常工作
6. **检查 Gemini Worker 日志**：查看 Worker 启动和执行日志

---

## 📊 架构对比：Qwen Worker vs Gemini Worker

| 特性 | Qwen Worker v3.0 | Gemini Worker v3.0 |
|------|------------------|-------------------|
| API 接口 | 阿里云 DashScope | Google Gemini 原生 |
| 代理方式 | 直连阿里云 | AlphaPilot International Proxy |
| 流式输出 | ✅ SSE | ✅ SSE / JSON Stream |
| 人格配置 | ✅ 3 种 | ✅ 3 种 |
| 执行链 | ✅ 9 步骤 | ✅ 9 步骤 |
| 记忆集成 | ✅ | ✅ |
| 非核心步骤降级 | ✅ | ✅ |
| 任务取消 | ✅ | ✅ |
| 死信队列 | ✅ | ✅ |
| Redis 类型 | Upstash（国际） | Upstash（国际） |

---

**© 2026 AlphaPilot OS. All rights reserved.**
