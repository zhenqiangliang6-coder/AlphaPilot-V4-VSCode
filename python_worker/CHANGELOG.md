# CHANGELOG

## [v4.1] — 2026-10-11 🔧 工程稳固与架构优化

> **"代码写得再好，工程做不扎实，一切都是空中楼阁"**

---

### 🔴 DeepSeek Worker v3.0 完全重写

**问题**: DeepSeek Worker 自 v2 创建后从未升级，与 Qwen Worker v3.0 严重脱节，缺少记忆集成、意图识别、工作区扫描、Post-analyze 重决策、自清理、协议验证、死信队列等所有关键功能。

**方案**: 以 Qwen Worker v3.0 为蓝本完全重写

| 模块 | 文件 | 变更 |
|------|------|------|
| Worker 主入口 | `agents/deepeek/deepseek_worker_v3.py` | 完全重写，+记忆中枢 +意图路由 +工作区扫描 +Post-analyze 重决策 +自清理 +协议验证 +死信队列 |
| API 封装 | `agents/deepeek/deepseek_api.py` | 完全重写，三级降级链 |

**三级 API 降级链**:
```
deepseek-v4-pro-0813 (阿里云 MAAS 主模型)
  └─ 失败 → deepseek-v4-pro (降级模型)
       └─ 失败 → 火山引擎 Ark (备用源)
```

**环境变量** (`.env`):
```bash
DEEPSEEK_MAAS_API_KEY=xxx
DEEPSEEK_MAAS_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DEEPSEEK_MAAS_MODEL=deepseek-v4-pro-0813
DEEPSEEK_MAAS_FALLBACK_MODEL=deepseek-v4-pro
```

### 🟡 全部 9 个 Worker write_step plan 回退修复

**问题**: `creative_writing` 等意图的执行链是 `analyze → write`（无 plan 步骤），但所有 write_step 硬要求 `plan_output`。LLM 报错 "未找到 plan 步骤的规划内容"。

**修复**: 在全部 9 个 Worker 的 `write_step.py` 中添加 plan 缺失时的智能回退：
```python
plan_content = steps.get("plan", {}).get("output", "")
if not plan_content:
    plan_content = steps.get("analyze", {}).get("output", "") + "\n---\n" + user_request
```

| Worker | 文件 |
|--------|------|
| Qwen | `agents/qwen/step_executor/write_step.py` |
| DeepSeek | `agents/deepeek/step_executor/write_step.py` |
| Gemini | `agents/gemini/step_executor/write_step.py` |
| MAAS | `agents/maas/step_executor/write_step.py` |
| Volcengine | `agents/Volcengine/step_executor/write_step.py` |
| OpenAI | `agents/openai/step_executor/write_step.py` |
| Claude | `agents/claude/step_executor/write_step.py` |
| Multi-Agent | `agents/multi_agent/step_executor/write_step.py` |
| Local LLM | `agents/local_llm/step_executor/write_step.py` |

### 🟡 创意意图 Token 浪费优化

**问题**: L1 层 `write_prompt()` 是静态函数，无视 intent 永远强制输出多文件协议格式（FILE/TEST/DOC），导致 `creative_writing`/`translate`/`chat` 等创意意图浪费大量 token 生成无用结构。

**修复**: 为 4 个核心 Worker 新增 `creative_write_prompt()`，创意意图路由到该函数直接输出纯文本：

| Worker | 文件 | 变更 |
|--------|------|------|
| Qwen | `step_executor/write_step.py` | +`_creative_intents` +`creative_write_prompt()` |
| DeepSeek | `step_executor/write_step.py` | 同上 |
| Local LLM | `step_executor/write_step.py` | 同上 |
| ModelScope | `step_executor/write_step.py` | 同上 |

```python
_creative_intents = {"creative_writing", "translate", "chat", "mentor_explain"}
if intent in self._creative_intents:
    prompt = creative_write_prompt(plan_content, f"{persona.profile}\n{persona.business_rules}")
else:
    prompt = write_prompt(plan_content, f"{persona.profile}\n{persona.business_rules}")
```

### 🟡 DeepSeek → 本地 Redis 切换

**问题**: DeepSeek Worker 旧版使用失效的阿里云 Tair Redis，报 `socket.gaierror: [Errno 11001] getaddrinfo failed`。

**修复**:
- `.env` 中 DeepSeek 加入本地 Redis 列表: `LOCAL_REDIS_MODELS=maas,modelscope,deepseek`
- 删除无效的 `Base URL (OpenAI兼容)=...` 行（导致 .env 解析错误）
- Worker 通过 `worker_config` 统一获取 Redis 配置

### 🏗️ intent_router.py 拆分为 intent_router/ 包

**问题**: `intent_router.py` 1216 行单体文件，包含静态配置表、LLM 分类引擎、主路由类 3 大功能域，过长难于理解和维护。

**拆分结果**:

```
之前: intent_router.py (1216 行单体)

之后: intent_router/
      ├── __init__.py           (  3 行) — 向后兼容入口
      ├── _data.py              (460 行) — 静态配置表
      ├── _classification.py    (170 行) — LLM 语义分类引擎
      └── _router.py            (370 行) — IntentRouter 主类
```

**向后兼容**: 所有 15 个现有 `from intent_router import ...` 导入点零改动。23 个单元测试全部通过。

---

### 修改文件总览

| 操作 | 文件 | 说明 |
|------|------|------|
| 重写 | `agents/deepeek/deepseek_worker_v3.py` | Worker v3.0 完全重写 |
| 重写 | `agents/deepeek/deepseek_api.py` | 三级降级链 |
| 修改 | `.env` | 清理无效变量，添加 MAAS 配置，DeepSeek → 本地 Redis |
| 修改 | `start_all.ps1` | DeepSeek Worker 加入启动管线 |
| 修改 | `agents/*/step_executor/write_step.py` ×9 | plan 回退修复 |
| 修改 | `agents/{qwen,deepeek,local_llm,modelscope}/step_executor/write_step.py` ×4 | 创意意图优化 |
| 删除 | `intent_router.py` | 拆分为包 |
| 新增 | `intent_router/__init__.py` | 向后兼容入口 |
| 新增 | `intent_router/_data.py` | 静态配置表 |
| 新增 | `intent_router/_classification.py` | LLM 分类引擎 |
| 新增 | `intent_router/_router.py` | IntentRouter 主类 |

### 验证

- intent_router 拆分: 23/23 测试通过 ✅
- DeepSeek Worker: 导入验证通过 ✅
- .env 解析: 无语法错误 ✅

---

## [v4.0] — 2026-10-10 🚀 动态执行引擎

> **"宁可多花 1000 token 让 LLM 决策怎么做，也不要用 1 行 if/else 把路堵死"**

### 🏗️ 核心架构: 三维动态决策矩阵

V4.0 执行引擎从静态 INTENT_TO_CHAIN 硬编码映射完全升级为动态决策系统:

```
Intent(what) + Skill Match(context) + analyze_step(how → LLM) → Execution Profile → Dynamic Chain
```

### Phase 2: Skill Output Profile 优先级

- Skill 新增 `output_profile` 字段作为能力合约
- 优先级: `Skill.output_profile > 意图默认 profile > 兜底`
- 新增 4 个 v4.0 Skill: creative.pure-text, creative.document-proposal, creative.brand-content, vision.image-analysis
- `route_skill()` → `plan_request()` 全链路 Skill 传递

### Phase 3: 彻底去静态化

- 🗑️ 删除 `INTENT_TO_CHAIN` 静态字典（15 条硬编码映射）
- 100% 动态: `build_execution_chain(profile)` 7 维度规则驱动
- `execution_chain_for()` 转为 `_resolve_chain()` 兼容包装

### Phase 4: LLM 分析重决策

- `analyze_prompt()` 要求 LLM 输出 `[EXECUTION_PROFILE]` JSON
- `parse_execution_profile_from_analysis()`: JSON + 正则容错双路径提取
- Post-analyze 链重新路由: analyze 执行后 rebuild 剩余步骤
- 仅链不同时替换; 异常时零破坏性回退

### Phase 5: diagnosis.runtime-error Skill

- 新增运行时错误诊断 Skill (priority=90)
- `requires_test: False` — 端口/配置/权限错误不跑无效测试
- `diagnosis.log` 新 capability 维度
- guidance 精确约束: "MINIMUM-VIABLE fix. DO NOT modify unrelated business logic"

### 测试

- 全量: 136 passed (8 个已有环境问题)
- Phase 4: +6 profile 解析测试; Phase 5: +4 Skill 测试
- 零回归, 所有链路向后兼容

---

## [v3.3] — 2026-10-09 🎯 工业级稳定性里程碑

### 今天我们把 AlphaPilot 从"能跑"推到了"跑不错"

---

### 🔴 P0 — FileOps 解析器 JSON 陷阱修复

**问题**：LLM 偶尔输出 `{"file.py": {"content": "..."}}` 这种 JSON 包裹格式，`parse_fileops_v3` 直接当成文件内容写入磁盘，导致 `.py` 文件里全是 JSON 而不是 Python 代码。这是端到端测试全部失败的根因。

**修复**：新增 `_unwrap_json_content()` 函数
- 检测内容是否以 `{` 开头
- 尝试 `json.loads` 解析
- 提取 `{"filename": {"content": "..."}}` 中的 `content` 字段
- 路径不匹配时拒绝解包（防止误判）
- 在 `# FILE:` / `# TEST:` / `# DOC:` 三种协议标记后自动调用

```python
# 之前写盘:
{"requirements.txt": {"content": "fastapi\npytest\nuvicorn"}}

# 现在写盘:
fastapi
pytest
uvicorn
```

### 🟡 P1 — 语言无关架构

**之前**：`intent_router` 的 `workspace_maintenance` 上下文限定为 "Python source inventory"、"workspace.python_environment"

**现在**：
- "Python source inventory" → "Project source inventory"
- "workspace.python_environment" → "workspace.environment"
- "workspace.python_syntax" → "workspace.syntax"
- 验证从 "Compile repaired Python files" → "Compile the language payload and report results"

`# FILE:` 协议本身是语言无关的，LLM (Qwen) 也能写任何语言——只是 prompts 之前被限死在 Python 世界观里。

### 🟡 P2 — 工作区扫描扩展至 20+ 文件类型

**之前**：`inspect_python_project` 只扫描 `.py` 文件

**现在**：新增 `_INSPECT_EXTENSIONS` 常量，支持：

| 类别 | 扩展名 |
|------|--------|
| Python | `.py` |
| JavaScript/TS | `.js` `.jsx` `.ts` `.tsx` `.mjs` `.cjs` |
| Java/Kotlin | `.java` `.kt` `.kts` |
| C/C++ | `.cpp` `.c` `.h` `.hpp` `.cc` `.cxx` |
| Rust/Go | `.rs` `.go` |
| 配置 | `.json` `.yaml` `.yml` `.toml` `.ini` `.cfg` |
| 文档 | `.md` `.mdx` `.rst` |
| 前端 | `.html` `.css` `.scss` `.less` |
| Shell | `.sh` `.bash` `.ps1` `.bat` `.cmd` |
| 环境 | `.env` `.env.example` |

返回新增字段：`total_file_count`、`language_counts`
Python 语法检查和导入分析仅对 `.py` 执行。

### 🟡 P3 — 自清理机制

**问题**：`write_code` 每次运行积累垃圾文件（JSON 污染的 `requirements.txt`、JSON dump 的 `auth.py`...），上次的错文件不会被清理。

**方案**：Redis 缓存追踪 + 自动清理
- `cleanup_previous_generated()` — 从 Redis 缓存读取上次 AlphaPilot 生成的文件列表，生成 `delete` file_ops
- `track_generated_files()` — 任务完成后将本次生成的文件路径写入 Redis
- 新增 `.alphapilot_generated.mark` 文件可见清单
- 触发条件：`write_code` / `fix_code` / `refactor` / `workspace_maintenance` 意图

```
流程:
  任务开始 → 读 Redis 缓存 → DELETE 旧垃圾文件
  任务执行 → write_step 生成新 file_ops
  任务结束 → 写 Redis 缓存 + .alphapilot_generated.mark
```

---

### 修改文件

| 操作 | 文件 | 改动 |
|------|------|------|
| 修改 | `python_worker/file_ops.py` | P0: `_unwrap_json_content()` + `parse_fileops_v3` 调用; P3: `cleanup_previous_generated()` + `track_generated_files()` |
| 修改 | `python_worker/intent_router.py` | P1: `workspace_maintenance` 上下文去 Python 化 |
| 修改 | `python_worker/context_builder.py` | P2: `inspect_python_project` 扩展到 20+ 文件类型; 新增 `_INSPECT_EXTENSIONS` |
| 修改 | `python_worker/agents/qwen/qwen_worker_v2.py` | P3: 导入清理/追踪函数; 任务前后插入清理逻辑 |

### 验证

- 所有文件 `py_compile` 通过 ✅
- `_unwrap_json_content` 4 个场景单元测试通过 ✅
- GitHub 推送成功 ✅

---

## [v3.2] — 2026-10-08

### 新增 — 事件驱动多层自愈引擎

**核心模块**: `self_healing_adapter.py`

- **规则引擎优先修复**：语法错误（缺冒号、括号未闭合）和 fixture 缺失用正则直接修复，零 LLM 调用
- **错误自动分类**：6 种错误类型（syntax / fixture_not_found / name_error / module_not_found / assertion_error / attribute_error）按优先级路由
- **符号索引**：AST 扫描源文件构建 {符号 → 文件:行号} 映射，import 修复只用 ~500 字符而非全量项目地图
- **停滞检测**：连续 3 轮同类型错误且无新修复 → 终止，避免无效循环
- **逗号保护**：LLM 修复后检查前后逗号数量 ≥ 80%，防止 LLM 误删
- **上下文分层**：零上下文（规则引擎）→ 精确上下文（import）→ 中度上下文（多文件）→ 安全截断（28000 字符）

### 修改

- **fix_step.py** (v3.1 → v3.2)：检测测试错误时自动触发 `run_healing_fix`，传统单次 LLM 修复作为 fallback

### 验证

- 已有单元测试 6/6 通过
- 端到端测试：5 个注入错误修复 4 个（第 5 个 assertion_error 为架构级路径问题，需多步推理链解决）
- 环境层：venv 删除 → 自动创建 → pip install → 测试通过
- 错误分类：6 种错误类型全部正确识别

### 文件

| 操作 | 文件 |
|------|------|
| 新增 | `python_worker/self_healing_adapter.py` |
| 修改 | `python_worker/agents/qwen/step_executor/fix_step.py` |
| 新增 | `python_worker/test_autonomous.py` (验证脚本) |
| 新增 | `python_worker/test_env_healing.py` (验证脚本) |
| 新增 | `python_worker/test_final_demo.py` (验证脚本) |

---

## [v3.1] — 2026-03-28 (历史)

### Qwen Worker 架构重构

- Step Executor 模块化拆分
- Prompt 集中管理
- 跨包导入规范（`..` 相对导入）
- `__init__.py` 包结构完善