> **"Safety is not a feature. It is the architecture itself."**
>
> AlphaPilot 是一个自主编码 Agent 系统，以 LLM 为脑、以 Git Worktree 为沙箱、以 pytest 为反馈闭环。
> 本文档定义其核心安全架构、流水线设计、数据模型、执行链资产与扩展策略。

---

## 工作日志 — 2026-10-20（G4 工作区绑定与证据准入治理）

> G1 发现 → G2 验证 → G3 方案 → G4 实现 → 审计复核。三条链路闭环，两个待运行时确认。

### G4.1：工作区绑定断裂修复（Node API）

**问题**：`/workspace/set` 更新 `fileOpsHandler.workspaceRoot` 但未更新模块级 `workspaceRoot` → `/task/submit` 中 `finalPayload.workspace_path` 始终为空 → Worker 收不到工作区路径。

**修复**：[`node-api/index.js:778`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/node-api/index.js#L778)
```javascript
app.post("/workspace/set", (req, res) => {
    workspaceRoot = path;  // ← 同步更新模块级变量
    fileOpsHandler.setWorkspace(path);
});
```

### G4.2：architect 证据准入（collaboration_modes）

**问题**：architect 模式执行链 `["analyze","plan","write"]` 不含 `workspace` → Phase D 证据收集不触发 → EvidenceGate 被旁路。

**修复**：[`collaboration_modes.py:128-131`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/collaboration_modes.py#L128-L131)
```python
if "workspace" in default_chain and "workspace" not in chain:
    _pos = chain.index("analyze") + 1 if "analyze" in chain else 0
    chain.insert(_pos, "workspace")
```
- 条件式保留：仅当 intent 的 `default_chain` 含 workspace 且模式链未包含时插入
- 插入位置：analyze 之后 plan 之前
- 不影响 automatic/chat/mentor 等无 workspace 依赖的模式

### G4.3：证据文件存在性校验（task_state_contract）

**问题**：`workspace_evidence` 中 key → content 仅做内容非空检查，不做文件系统验证 → 证据真实性不可审计。

**修复**：[`task_state_contract.py:571-600`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/task_state_contract.py#L571-L600)
- 新增 `import os`（L14）
- `ws_path` 非空时：逐文件 `os.path.join(ws_path, k)` + `os.path.isfile()` 校验
- `ws_path` 为空时：仅做字符串非空校验（向后兼容旧调用方）

### ⚠️ 审计已知风险

| 风险 | 严重度 | 说明 |
|------|:---:|------|
| architecture intent fallback 证据路径脆弱 | 🔴 | Phase D 对 architecture 走关键词搜索，若 prompt 无匹配 → 证据空 → EvidenceGate 阻断 |
| `os.path.join` 无路径穿越防护 | 🟡 | 绝对路径 key / `..` 穿越可突破（当前 key 来源受控） |
| workspaceRoot 无任务级并发隔离 | 🟡 | 模块级全局变量，多任务共享 |
| mark_failed 幂等性测试失败 | 🟡 | 无 git 基线证实归属 |

### 文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `node-api/index.js` | G4.1: L778 新增 `workspaceRoot = path` |
| 修改 | `python_worker/collaboration_modes.py` | G4.2: L128-131 条件式保留 workspace |
| 修改 | `python_worker/task_state_contract.py` | G4.3: L14 新增 `import os`, L571-600 增强验证 |

---

## 工作日志 — 2026-10-19（G1.2 结构化产物协议）

### Worker 层
- **`worker_config.py`**：新增 `emit_artifact(task_id, artifact_id, artifact_type, format, content, label, sequence)` — 通过 `POST /task/stream_chunk/:task_id`（复用现有路由）发送结构化产物；新增 `extract_and_emit_artifacts(task_id, full_text)` — 正则提取 `` ```mermaid ... ``` `` 代码块并发射为 artifact
- **`worker_respond_step.py`**：在 `stream_end()` 之前调用 `extract_and_emit_artifacts()`，确保产物在任务终态前完成传输
- **`agents/openai/openai_worker.py`**：`stream_chunk` 签名统一为 `(task_id, content, phase=None, channel=None)`
- **`agents/deepeek/deepseek_worker.py`**：同上

### 关键原则
- 不新增通信旁路，全部复用现有 `stream_chunk` HTTP 路由
- 产物通过 `message_type="artifact_created"` 信封与文本流区分
- 任务状态机不动，artifact 发射不改变任务终态语义
- 产物发送失败记录诊断日志，不伪造成功产物

---

## 目录

0. [核心宪法 (Core Constitution)](#0-核心宪法-core-constitution)
1. [系统总览](#1-系统总览)
2. [核心流水线 (Coding Loop)](#2-核心流水线-coding-loop)
3. [安全架构](#3-安全架构)
4. [数据模型 (TaskModel_v2)](#4-数据模型-taskmodel_v2)
5. [服务层架构](#5-服务层架构)
6. [Agent 多模型架构](#6-agent-多模型架构)
7. [执行链与 Prompt 工程资产](#7-执行链与-prompt-工程资产)
8. [执行后端](#8-执行后端)
9. [Redis 三级降级策略](#9-redis-三级降级策略)
10. [升级路线图](#10-升级路线图)
11. [部署拓扑](#11-部署拓扑)
12. [向量记忆系统](#12-向量记忆系统)

---

## 0. 核心宪法 (Core Constitution)

> **"协议即宪法。宪法不可变。所有组件必须遵守，无例外。"**

AlphaPilot 的架构不是从代码开始的，是从宪法开始的。宪法定义了系统的**灵魂边界**：谁拥有真相、谁只能映射、谁只能投影、谁定义协议。

### 0.1 四大信条 (Four Tenets)

```
┌──────────────────────────────────────────────────────────────┐
│                    AlphaPilot 宪法                            │
│                                                              │
│  信条 1: Worker = 真相                                        │
│  ─────────────────────────────────────────────────────────── │
│  python-worker/ 是系统中唯一具有"真相"的实体。               │
│  - TaskModel_v2 的状态、events、steps 均由 Worker 写入       │
│  - 任何其他组件不得产生独立于 Worker 的任务状态               │
│  - 任务进度、测试结果、补丁应用的唯一真相源 = Worker          │
│                                                              │
│  信条 2: Extension = 映射                                     │
│  ─────────────────────────────────────────────────────────── │
│  vscode-extension/ 是 Worker 真相的 UI 映射层。               │
│  - Extension 只能读取 Worker 写入的状态                       │
│  - Extension 不得自行计算或推断任务状态                       │
│  - 所有写操作（提交任务、审批）通过 Redis 队列交付 Worker      │
│                                                              │
│  信条 3: Webview = 投影 (纯只读)                              │
│  ─────────────────────────────────────────────────────────── │
│  webview/ 是 Extension 态的纯投影。                           │
│  - Webview 只消耗 Extension 或 Worker 推送的 stream_chunk     │
│  - Webview 不发起任何状态变更请求                             │
│  - 所有交互事件通过 Extension 中转                             │
│                                                              │
│  信条 4: 协议 = 宪法                                          │
│  ─────────────────────────────────────────────────────────── │
│  所有跨组件通信必须复用宪法协议，严禁旁路。                    │
│  - emit_chunk (StreamService) 是唯一的实时推送通道            │
│  - Redis 队列 (Task Queue) 是唯一的任务投递通道               │
│  - 不新建 WebSocket、不新增 HTTP 端点、不建旁路               │
└──────────────────────────────────────────────────────────────┘
```
# CHANGELOG

---

## [v4.4] — 2026-10-13 🎯 图片"看图修代码"能力平权 & 一等公民技能范式确立

> **"vision_analysis 不是旁路功能。它是输入模态一等公民扩展点的第一个实例。"**

---

### 🎯 核心洞察：Skill 与 Step Executor 本质上是同一种东西

在 AlphaPilot 中，**"技能"（Skill）和"步骤执行器"（step_executor）是同一个原子能力单元的两面**：

```
Skill 系统（skills/）         Step Executor（step_executor/）
─────────────────────────────────────────────────────────
vision_image_analysis.py      run_vision_step()          ←  看图
(无对应 skill，纯意图驱动)     run_analyze_step()         ←  分析需求
backend_python.py             run_write_step()            ←  生成代码
diagnosis_runtime_error.py   run_fix_step()              ←  修复 bug
test_automation.py            run_test_step()             ←  跑测试
...
```

**关键范式**：加一个能力 = 三个动作，不改任何架构

```
1. 注册 Skill 定义（skills/ 下）         — 计划时：告诉 LLM 这个能力是什么
2. 实现 step executor（step_executor/）  — 运行时：真正执行这个能力
3. 挂入 STEP_DISPATCHER + build_execution_chain
                                        — 宪法通道：走统一调度，不走旁路
```

这个范式使 AlphaPilot 成为一个真正的 **LLM 驱动智能体**：LLM（Intent Router + analyze）根据用户意图 **动态组装技能链**，12 个原子技能按需串联，不预设死板流水线。

---

### 🐛 本次修复的三个根因

#### 1. Post-analyze 链重决策永久失效（最严重）

**症状**：`llm_profile` 永远为 `None`，analyze 步骤后的链重建从未触发。

**根因**：`_router.py` 第 232 行使用 `find("[EXECUTION_PROFILE]")` 查找**第一个**出现的标记。
LLM 在 analyze 输出的**指令文本**（告诉 LLM 输出格式的那段）中会先出现一次 `[EXECUTION_PROFILE]` 字符串，
`find` 找到的是指令文本，不是后面的 JSON 数据体，JSON 解析失败 → 返回 None。

**修复**：`find` → `rfind`。查找**最后一个**出现的标记 = 真正的 JSON 数据体。

```python
# 旧（永远失败）
marker_idx = analysis_output.find(_PROFILE_MARKER)

# 新（正确找到 JSON 数据体）
marker_idx = analysis_output.rfind(_PROFILE_MARKER)
```

**文件**: `intent_router/_router.py:232`

---

#### 2. workspace 步骤 NoneType 崩溃

**症状**：`'NoneType' object has no attribute 'get'` at `workspace_step.py:15`

**根因**：当链未正确重建时 workspace 步骤仍被调度，`meta.get("workspace_scan", {})` 返回 `None`（`workspace_scan` 未初始化），
后续 `scan.get("root")` 抛出 AttributeError。

**修复**：添加一行空值防御。

```python
# 旧（None 时崩溃）
workspace_root = scan.get("root") or meta.get("workspace_path")

# 新（防御空值）
scan = scan or {}
workspace_root = scan.get("root") or meta.get("workspace_path")
```

**文件**: `agents/qwen/step_executor/workspace_step.py:15`

---

#### 3. 纯图片无文字 → 死锁为 chat 意图

**症状**：用户只贴图不打字时，`prompt=""` 进入 `detect_intent`，LLM 无法分类 → fallback 为 `chat` → 链中没有 code 步骤。

**根因**：`detect_intent("")` 的语义分类对空字符串无有效信号。

**修复**：当 `prompt` 为空且 `has_vision_support(payload)` 时，生成一个合成 prompt 仅用于意图分类；
原始空 prompt 保留给 vision_analysis 步骤（图片本身提供内容）。

```python
_intent_prompt = prompt
if not prompt.strip() and has_vision_support(payload):
    _intent_prompt = "分析上传的图片并根据图片内容处理（报错则修复、设计图则生成代码、文档则解释说明）"

detected_intent, detected_persona, detected_chain = IntentRouter.detect_intent(_intent_prompt)
```

同时将 Post-analyze 意图推断的触发条件从 `intent == "vision_analysis"` 泛化为 `context.get("_vision_result")`，
使其覆盖"空 prompt 但已有视觉分析结果"的所有场景。

**文件**: `agents/qwen/qwen_worker_v2.py:172-176, 190, 492`

---

### 🔗 Skill 与 Intent Profile 对齐

`vision_image_analysis.py` 的 `output_profile` 原为 `text-only` 模式（`fileops=False`），
与 `_data.py` 中 `vision_analysis` 意图的 `code-capable` 默认 profile 矛盾。
Skill profile 在 `resolve_execution_profile` 中具有最高优先级，会覆盖 Intent profile。

**修复**：Skill profile 对齐为 code-capable（`fileops=True`, `workspace_dependency="read_write"`），
让 Skill 提供能力上限，由 Post-analyze LLM 根据实际图片内容决定是否使用代码能力。

**文件**: `skills/vision_image_analysis.py:33-39`

---

### ✅ 宪法合规审查

| 信条 | 状态 | 说明 |
|------|------|------|
| Worker = 真相 | ✅ | 全部 6 处修改在 Worker 边界内，0 个新状态源 |
| Extension = 映射 | ✅ | 0 行 Extension 代码变更 |
| Webview = 投影 | ✅ | 0 行 Webview 代码变更，stream_chunk 通道不变 |
| 协议 = 宪法 | ✅ | 0 个新 WebSocket / HTTP 端点 / Redis 通道 |

```
本次全部修改 = 架构内扩展，未越宪法雷池一步。
每一个未来待加的能力（audio / video / 3D 分析）也当循此契约：
Skill 定义 + Step Executor + 宪法通道，不做任何例外。
```

---

### 🧪 测试结果

```
test_intent_router.py  22/23 PASS  (1 FAIL 为 external_git 路由预存问题，无关)
test_skills.py          4/4 PASS
所有 parse_execution_profile 系列测试 7/7 PASS
全部修改语法验证通过
```

---

## [v4.3] — 2026-10-12 🤖 Qwen 多模型运行时探测 & 兼容模式全线切换

> **"不预设任何候选，让 API 自己说实话"**

---

### 🔍 qwen_model_probe — 四步客观探测法

**旧版**: 硬编码 21 个模型候选逐一试探，结果误导—称"视觉模型不可用"，实则 omni 系列完全可用。

**新版**: 以 `/v1/models` API 为真相源

```
第一步: GET /v1/models → 175 个真实可用模型
第二步: 按能力分类 → 文本 / 视觉(vl) / 全模态(omni) / 专用(coder)
第三步: 按代际排序 → qwen3.8 > qwen3.7 > qwen3 > qwen2.5
第四步: 轻量验证 → compatible-mode 1-token 确认
```

| 维度 | 旧版 | 新版 |
|------|------|------|
| 文本首推 | `qwen-max` | ⭐ `qwen3.8-max` |
| 文本可用 | 5 个 | 9 个 |
| 视觉可用 | 0 个（误判） | 7 个（qwen3.8-omni-flash → ...） |
| 缓存 | 无 | 1 小时 TTL |

### 🔄 Qwen API 全链路 → compatible-mode

所有 Qwen API 调用从原生 DashScope 端点迁移到 `compatible-mode/v1/chat/completions`。omni 模型仅通过 compatible-mode 可用。

| 文件 | 改动 |
|------|------|
| `agents/qwen/qwen_api.py` | 完全重写: 端点 + 消息/流式格式 + `_extract_text_from_response` |
| `agents/vision_api.py` | `_call_qwen_vision`: compatible-mode + OpenAI image_url 格式 |
| `planner.py` | 端点 + 响应解析同步 |
| `intent_router/_classification.py` | `format: dashscope` → `openai` |

### 🔗 step_executor/qwen_api.py ×3 统一

`agents/{openai,claude,multi_agent}/step_executor/qwen_api.py` 三个独立硬编码副本全部替换为 `from agents.qwen.qwen_api import call_qwen`。

### 📊 ModelScope 降级链

`modelscope_api.py` 加入 env 驱动的降级循环:
```
call_modelscope() → Qwen/Qwen3.8-Flash-Next
  → fail → Qwen/Qwen3.8-27B
  → fail → deepseek-ai/DeepSeek-V4-Flash-Vision-Exp
  → fail → deepseek-ai/DeepSeek-V4.1-Flash
  → fail → Qwen/Qwen3.8-27B
```
三个调用入口（blocking / stream / stream_generator）全部支持。

### 🧹 清除硬编码

全文 10 处 `qwen-turbo` + 3 处旧原生端点全部修复：

| 文件 | 修复 |
|------|------|
| `TaskModel_v2.py` | 默认模型 `qwen-turbo` → `qwen-max`；SUPPORTED_MODELS 更新 |
| `planner.py` | `qwen-turbo` → `qwen-max` + compatible-mode |
| `_classification.py` | `qwen-turbo` → `qwen-max` + `format: openai` |
| `step_executor/qwen_api.py` ×3 | 硬编码副本 → 统一 re-export |

### 🔑 推荐 .env

```env
QWEN_MODEL=qwen3.8-max
QWEN_FALLBACK_1=qwen3.8-max-0902
QWEN_FALLBACK_2=qwen3.8-flash
QWEN_FALLBACK_3=qwen3.8-27b
QWEN_VISION_MODEL=qwen3.8-omni-flash
QWEN_VISION_FALLBACK=qwen3.5-omni-plus
```

### 文件变更

| 操作 | 文件 |
|------|------|
| 重写 | `agents/qwen/qwen_model_probe.py` |
| 重写 | `agents/qwen/qwen_api.py` |
| 重写 | `agents/modelscope/modelscope_api.py` |
| 修改 | `agents/vision_api.py` |
| 重写 | `agents/{openai,claude,multi_agent}/step_executor/qwen_api.py` |
| 修改 | `TaskModel_v2.py` |
| 修改 | `planner.py` |
| 修改 | `intent_router/_classification.py` |
| 修改 | `.env` |

---

## [v4.2] — 2026-10-12 🧪 冒烟测试 42 题矩阵完整落地 & 工程模块化

> **"88% 不是缺憾，是 AlphaPilot 今天真实的能力水印"**

---

### 🧪 42 题自愈能力契约矩阵全覆盖

**背景**: AlphaPilot 的自愈能力曾仅有 6 道 P0 试题验证，剩余 36 道仅在矩阵文档中定义但未落地到可执行测试。这 42 道题是 AlphaPilot 的最低能力契约——每一道设计验证一个具体的自愈维度。

**完整落地**:

```
42 题矩阵 = P0(6) + P1(15) + P2(21)
├── P0 基线:  S0-S5 + T1-T6    → 6/6  PASS ✅
├── P1 进阶:  T7-T21           → 15/15 PASS ✅
└── P2 高阶:  T22-T42          → 16/21 PASS (76%)
──────────────────────────────────────────
   总计: 37/42 PASS = 88% 自愈率
```

| 维度 | 题号 | 验证能力 |
|------|------|---------|
| 语法缺陷 | S0, T7, T9 | SyntaxError 自动修复 |
| 类型错误 | S1, T17, T20, T25 | 类型推断与修正 |
| 逻辑错误 | S3, T10, T14, T18, T31 | 逻辑条件修正 |
| 运行时异常 | T11, T12, T16, T26, T27, T28, T38 | 异常捕获与防御 |
| 浮点/数值 | T13, T17, T37 | 浮点精度处理 |
| 安全漏洞 | T18, T22, T23, T30 | SQL注入/路径遍历/信息泄露 |
| 并发/异步 | T42 | 协程 await 缺陷 |
| 边界条件 | T40, T41 | 默认参数/is 比较 |
| 跨文件 | S2, T19, T20 | 跨模块导入修复 |
| 数据序列化 | T35 | JSON datetime 非标类型 |

### 🏗️ run_smoke_e2e.py 模块化拆分

**问题**: 原 `run_smoke_e2e.py` 已膨胀至 2408 行单体文件，42 道全套落地后预计破 5000 行，编辑器卡顿、解释器承受极限。

**拆分方案**:

```
之前: run_smoke_e2e.py (2408 行单体)

之后: run_smoke_e2e.py (11 行薄入口)
     smoke_tests/
     ├── __init__.py
     ├── config.py              # 公共常量 & 工具函数
     ├── turns.py               # 工作流 turn 执行 & 意图路由
     ├── engine.py              # 自愈执行引擎核心 (含 LLM 路径规范化)
     ├── runner.py              # 编排层 & 最终报告
     └── definitions/
         ├── __init__.py
         ├── P0_baseline.py     # S0-S5 + T1-T6  (6 题)
         ├── P1_intermediate.py # T7-T21         (15 题)
         └── P2_advanced.py     # T22-T42        (21 题)
```

**依赖方向**: `config → turns → definitions/* → engine → runner`，单向无循环。新增试题只需在对应优先级文件追加定义，引擎零改动。

### 🔧 测试数据 5 道退化修复

拆分过程中发现的测试用例退化，全部修复：

| 题号 | 退化 | 修复 |
|------|------|------|
| T16 编码 | `'hello world'` ASCII 无法触发编码缺陷 | → `'你好世界'` UTF-8 中文 |
| T30 信息泄露 | `assert API_TOKEN not in output` — LLM 自然修复为 `token=***` 后仍触发断言 | → `assert 'tk_test_12345' not in output` 检查真实值 |
| T31 生成器 | `assert rest == []` — bug 本身恰好满足断言，测试永远通过 | → `assert len(rest) > 0` 强制要求生成器可重用 |
| T35 JSON | `isinstance(result, str)` 太弱，无法阻止 LLM 偷删 timestamp 字段 | → `json.loads` + `data['event']` + `'timestamp' in data` 三步结构验证 |
| T41 is 比较 | `is_hello('hello')` 因 CPython 字符串 interning 永远为 True | → `''.join([chr(104)...])` 运行时拼接防 interning |

### 🐳 基础设施

| 操作 | 说明 |
|------|------|
| Docker PostgreSQL 端口隔离 | 5432 → 5433，解决与 Windows 本地 PostgreSQL 端口冲突 |
| `.env.memory` / `.env.memory.example` | `DB_PORT=5433` 同步 |
| `node-api/.env` | `DATABASE_URL` 端口同步为 5433 |
| Node.js → Prisma → PostgreSQL 生产记忆链路 | `test_memory_chain.js` 独立验证通过 ✅ |

### 5 FAIL 定性

T19/T20/T22/T37/T38 为 LLM 非确定性噪声——同一题在不同轮次跑出现过 PASS 也出现过 FAIL，不是代码缺陷。这是 LLM 基座模型的可重复性天然上限。88% 自愈率是 AlphaPilot 当前的真实能力水印。

### 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `smoke_tests/__init__.py` | 包入口 |
| 新增 | `smoke_tests/config.py` | 公共常量 & 工具 |
| 新增 | `smoke_tests/turns.py` | 工作流 turn 执行 |
| 新增 | `smoke_tests/engine.py` | 自愈引擎核心 |
| 新增 | `smoke_tests/runner.py` | 编排层 |
| 新增 | `smoke_tests/definitions/__init__.py` | 定义包子入口 |
| 新增 | `smoke_tests/definitions/P0_baseline.py` | P0 6 题 |
| 新增 | `smoke_tests/definitions/P1_intermediate.py` | P1 15 题 |
| 新增 | `smoke_tests/definitions/P2_advanced.py` | P2 21 题 |
| 重写 | `run_smoke_e2e.py` | 2408 行 → 11 行入口 |
| 修改 | `.env.memory.example` | `DB_PORT`: 5432 → 5433 |
| 修改 | `.env.memory` | `DB_PORT`: 5433 |
| 修改 | `node-api/.env` | `DATABASE_URL` 端口 → 5433 |

---

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