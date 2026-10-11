# 工作记录（Worklog）

记录项目中的重要变更与里程碑，便于回溯与审计。

## 2026-10-09 🎯 工业级稳定性里程碑

> **"今天我们把 AlphaPilot 从能跑推到了跑不错"**
> 
> 今天的工作是一次系统级的"免疫系统"建设——不只是修 bug，而是让 AlphaPilot 具备了自我纠错和自我清理的能力。

### 发现与诊断过程

1. **端到端测试失败**：运行测试任务后，文件内容被 JSON 包裹污染（`auth.py` 里是 JSON dump、`test_api.py` 里是 `{"test_api.py": {"content": "..."}}`）
2. **逐级排查**：Worker 生产 → Redis 存储 → Node.js 推送 → VSCode 扩展 → Node.js `/fileops/execute` → FileOpsHandler 写盘
3. **定位根因**：管道没有 bug，但 `parse_fileops_v3` 不会检测 LLM 输出的 JSON 包裹格式，导致 JSON 协议被当成文件内容写入

### 实施的四个修复（P0-P3）

| 优先级 | 修复 | 影响 |
|--------|------|------|
| 🔴 P0 | `_unwrap_json_content()` 自动检测并提取 JSON 包裹中的纯代码 | 终结 JSON 污染文件 |
| 🟡 P1 | `intent_router` 去 Python 化 | 解除语言绑定的第一步 |
| 🟡 P2 | 工作区扫描扩展到 20+ 文件类型 | 为多语言项目做准备 |
| 🟡 P3 | Redis 缓存追踪 + 自动垃圾清理 | 防止错误积累，自愈式清理 |

### 关键洞察

- **AlphaPilot 从 Python 起步 ≠ 只能处理 Python**：`# FILE:` 协议是语言无关的，LLM 能写任何语言。瓶颈在 prompts 设计。
- **自清理 = 智能体的基本能力**：一个真正的 Agent 应该能清理自己的错误输出，而不是依赖人工介入。
- **管道比想象中干净**：Worker → Redis → Node.js → VSCode 扩展 的 FileOps 链路没有 bug，污染只来自解析层。

### 提交

```
f822e60 v3.2: JSON unwrap in FileOps parser, language-agnostic architecture, self-cleanup
89a6c0d Merge conflicts resolved
→ 推送到 GitHub main + feature/gemini-worker-and-memory-hub
```

### 文件清单

| 文件 | 改动 |
|------|------|
| `python_worker/file_ops.py` | P0: JSON 解包; P3: 清理/追踪 |
| `python_worker/intent_router.py` | P1: 去 Python 化 |
| `python_worker/context_builder.py` | P2: 多文件类型扫描 |
| `python_worker/agents/qwen/qwen_worker_v2.py` | P3: 集成自清理 |
| `python_worker/CHANGELOG.md` | v3.3 条目 |
| `docs/WORKLOG.md` | 本条记录 |

---

## 2026-10-10 🔧 运行时修复日 — 打通前后端全链路

> **"问题不在于代码写得不对，而在于运行时环境总会背叛你"**
>
> 今天的工作集中在发现并修复潜伏已久的配置错误和协议不一致，让系统从"能启动"到"能真正跑通任务"。

### 🐛 Bug 修复

#### ① `@prisma/client` 缺失导致 Node API 启动崩溃

- **现象**：`Cannot find module '@prisma/client'`
- **根因**：`@prisma/client` 从 5 月就错放在 `devDependencies`，之前因 `npm install` 默认安装 dev 依赖而侥幸运行。近期的部分安装/清理操作触发了 `production` 模式，导致运行时依赖被跳过。
- **修复**：
  - 将 `@prisma/client` 从 `devDependencies` 移到 `dependencies`（`node-api/package.json`）
  - 执行 `npm install` + `npx prisma generate`

#### ② Node API 队列路由错误 — 任务发到错误队列

- **现象**：前端发送 `qwen-turbo` 类型任务，Qwen Worker 收不到
- **根因**：Node API 用 `getWorkerQueueByType("qwen-turbo")` 做精确匹配 → 查不到 → 兜底到通用队列 `task_queue`；而 Qwen Worker 监听 `task_queue:qwen`
- **修复**：`node-api/index.js` — `getWorkerQueueByType(type)` → `getWorkerQueue(type)`，后者智能提取前缀：`qwen-turbo` → `qwen` → `task_queue:qwen`

#### ③ 9 个 Worker 的类型校验全部失败 — 任务循环放回队列

- **现象**：任务到达正确队列后，Worker 识别为"不匹配的类型"又把任务放回队列，造成死循环
- **根因**：前端传 `qwen-turbo` / `deepseek-chat`（`-` 分隔），Worker 校验 `startswith("qwen_")` / `startswith("deepseek_")`（`_` 分隔），永远不匹配
- **修复**：统一将 9 个 Worker 的验证改为 `startswith("qwen")` / `startswith("deepseek")` 等（去掉分隔符）
  - `qwen_worker_v2.py`、`maas_worker_v3.py`、`modelscope_worker_v3.py`
  - `local_worker_v3.py`、`doubao_worker_v3.py`、`doubao_worker_v2.py`
  - `gemini_worker_v2.py`、`deepseek_worker_v3.py`、`deepseek_worker_v2.py`

#### ④ `analyze_prompt()` 不接受 `context` 参数

- **现象**：`LLM 调用失败: analyze_prompt() got an unexpected keyword argument 'context'`
- **根因**：`analyze_step.py` 传了 `context=context` 但 `prompts.py` 的函数签名只有 `(user_input)`
- **修复**：`python_worker/agents/qwen/step_executor/prompts.py` — 添加 `context: dict = None` 参数，并注入上下文记忆到分析 prompt 中

#### ⑤ 前端模型选择器缺少 3 个 Worker

- **现象**：VSCode 插件下拉框看不到 Gemini、MaaS、ModelScope
- **根因**：源码 `ModelSelector.tsx` 已有全部 7 个模型，但 `webview-dist` 构建产物是旧版
- **修复**：重新 `npm run build` webview 并 Reload Window

### 📁 文件清单

| 文件 | 改动 |
|------|------|
| `node-api/package.json` | `@prisma/client` devDeps → deps |
| `node-api/index.js` | 队列路由函数修正 |
| `python_worker/agents/*/worker*.py` (x9) | 类型前缀校验去分隔符 |
| `python_worker/agents/qwen/step_executor/prompts.py` | analyze_prompt 添加 context 参数 |
| `vscode-extension/webview-dist/` | 重新打包 |

### 关键洞察

- **`devDependencies` vs `dependencies`**：运行时需要 `require()` 的包必须在 `dependencies`，否则 `NODE_ENV=production` 就炸
- **前后端协议对齐是最大坑**：`qwen-turbo` vs `qwen_generate` 这类命名不一致会在链路多个节点分别卡死，每个节点的日志看起来都"正常"
- **构建产物 ≠ 源码**：改了源码后没有 rebuild，表象就是"我已经加了但这个功能怎么没有"

---

## 2026-10-10 🚀 V4.0 执行引擎 — 动态链组装与 LLM 驱动重决策

> **"宁可多花 1000 token 让 LLM 决策怎么做，也不要用 1 行 if/else 把路堵死"**
>
> V4.0 执行引擎核心架构升级：从静态 INTENT_TO_CHAIN 硬编码映射 → 三维动态决策矩阵 → LLM analyze 输出驱动链重新路由。分 4 个 Phase 执行。

### Phase 2: Skill 升级 — Output Profile 优先级体系

**背景**：v3.x 中 Skill 仅提供 guidance 文本注入，不参与执行链决策。

**实现**：
- 为所有 Skill 赋予 `output_profile` 能力合约字段，描述该 Skill 的输出模式
- `route_skill()` 匹配结果传递到 `plan_request()` → `_resolve_chain()`，Skill profile 优先于意图默认 profile
- 优先级规则：`Skill.output_profile > 意图默认 profile > 兜底 code 模式`
- `worker_runtime.py` 中 `route_skill()` 调用提前到 `plan_request()` 之前，确保 matched_skill 变量被真正传入执行链构建流程
- 新增 4 个 v4.0 Skill：`creative.pure-text`、`creative.document-proposal`、`creative.brand-content`、`vision.image-analysis`
- 修复 Skill dataclass 字段顺序：`guidance` 移到 `output_profile`（有默认值）之前，消除 TypeError

### Phase 3: 彻底去静态化 — INTENT_TO_CHAIN 字典删除

**背景**：v3.x 中 15 条意图到执行链的映射全部硬编码在 `INTENT_TO_CHAIN` 字典中。

**实现**：
- 🗑️ 删除 `INTENT_TO_CHAIN` 静态字典（15 条意图→链映射），保留历史注释
- 🔄 `build_execution_chain()` 移除静态降级逻辑，profile 为 None 时自动调用 `resolve_execution_profile()`
- 🔄 `execution_chain_for()` 兼容方法内部转调 `_resolve_chain()`，不再依赖静态字典
- 动态链组装规则（7 维度驱动）：

```
chain = ["analyze"]
if workspace_dependency != "none": chain.append("workspace")
if output_mode != "text": chain.append("plan")
chain.append("write")
if output_mode in ("code", "document"): chain.append("refine")
if output_mode == "code" and requires_test: chain.append("test")
if output_mode == "code": chain.extend(["fix", "doc", "docstring"])
```

- chat/mentor 意图强制覆盖为 `["analyze", "plan", "respond"]`
- external_git worker 过滤掉 write/refine/test/fix/doc 步骤

### Phase 4: LLM 驱动 analyze_step → 执行链重新决策

**核心洞察**：v3.x 中执行链在 analyze 步骤执行前就已确定，但 LLM 在 analyze 阶段对任务有更深刻的理解，应该允许它重新决定后续步骤。

**实现**：
1. **`analyze_prompt()` 升级**（`prompts.py`）：要求 LLM 在分析末尾输出 `[EXECUTION_PROFILE]` JSON 块，包含 7 个执行维度
2. **`parse_execution_profile_from_analysis()`**（`intent_router.py`）：从 LLM 输出中提取 profile JSON
   - 主路径：精确 JSON 解析
   - 容错路径：逐字段正则提取（畸形 JSON 也能恢复）
   - 完全失败时返回 None（调用方保持原始链不变）
3. **Post-analyze 链重路由**（`qwen_worker_v2.py::execute_task()`）：
   - analyze 步骤从 steps 列表分离，单独先执行
   - 从输出中提取 profile，调用 `build_execution_chain()` 重建剩余步骤
   - 仅当新链与旧链不同时才替换（避免无意义重建）
   - 异常时回退到原始 steps（零破坏性容错）

### Phase 5: diagnosis.runtime-error Skill — LLM 行为约束合约

**背景**：当用户报"端口被占用 Errno 10048"时，LLM 在 `engineer` 人格下可能过度修改业务代码，而不是去改端口号。系统缺少精确的行为约束机制。

**新增 Skill**：`diagnosis.runtime-error`（`skills/diagnosis_runtime_error.py`）
```python
Skill(
    id="diagnosis.runtime-error",
    priority=90,  # 覆盖默认 backend.python (60)
    triggers=("端口被占用", "Address already in use", "ConnectionRefused",
              "Errno 10048", "Errno 13", "Permission denied", ...),
    capabilities=("workspace.read", "workspace.write", "diagnosis.log"),
    output_profile=dict(requires_test=False),  # 运行时错误不需要跑测试
    guidance="MINIMUM-VIABLE fix. DO NOT modify unrelated business logic..."
)
```

**三个关键价值**：
- 🎯 `requires_test: False` — 端口/配置/权限问题不需要 test→doc 链路，Skill 覆盖了 `fix_code` 的默认 `requires_test: True`
- 🔒 `guidance` 行为约束 — "严禁修改无关业务逻辑，最小化修复"，这是当前系统最缺少的能力
- 🏷️ `diagnosis.log` 新 capability 维度 — 供 authorization/policy 组件做差异化处理

### V4.0 架构完整性

| 层级 | 机制 | 状态 |
|---|---|---|
| 意图分类 | LLM + Regex 联合路由 | v3.5 ✅ |
| Skill 匹配 | capability 合约 + output_profile 优先级 | Phase 2 ✅ |
| 执行链组装 | `build_execution_chain()` 7 维度纯规则 | Phase 3 ✅ |
| LLM 分析重决策 | analyze → profile → rebuild chain | Phase 4 ✅ |
| 行为约束 | Skill guidance 精确注入 | Phase 5 ✅ |

### 测试验证

- 全量 Python Worker 测试：**136 passed**（8 个已有环境问题：6× EMBEDDING_PROVIDER + 2× qwen_fix_step）
- Phase 4 新增 6 个 profile 解析测试：有效 JSON、无标记、空输入、部分字段、链差异、chat 覆盖
- Phase 5 新增 4 个 Skill 测试：注册验证、路由验证、profile 验证、guidance 验证
- `test_workspace_task_flow.py` 3 个测试适配 v4.0 动态链预期

### 文件变更

| 文件 | 改动 |
|------|------|
| `intent_router.py` | Phase 2-4: `ExecutionProfile`、动态链构建、profile 解析 |
| `qwen_worker_v2.py` | Phase 4: Post-analyze 链重路由 |
| `prompts.py` | Phase 4: analyze prompt + EXECUTION_PROFILE JSON |
| `skills/base.py` | Phase 2: 字段顺序修复 |
| `worker_runtime.py` | Phase 2: Skill 传递衔接 |
| `skills/diagnosis_runtime_error.py` | Phase 5: 新增 |
| `skills/creative_*.py` + `vision_*.py` | Phase 2: 新增 4 个 v4.0 Skill |
| `tests/test_intent_router.py` | Phase 2-4: 动态链验证 + 6 个 Phase 4 测试 |
| `tests/test_skills.py` | Phase 2+5: v4.0 Skill 注册 + diagnosis 测试 |
| `tests/test_v35_control_plane.py` | Phase 2: LLM 路由不确定性兼容 |
| `tests/test_workspace_task_flow.py` | Phase 3: v4.0 链预期适配 |

---

## 2026-04-02

- 增强 `planner` 的 JSON 修复器（`python_worker/planner.py`）
  - 解决 LLM 返回非严格 JSON（单引号、尾随逗号、缺失分隔符、冗余括号等）导致解析失败的问题。
  - 实现策略：快速 regex 清理 -> 插入缺失逗号 -> 单引号替换 -> ast.literal_eval 回退 -> 基于括号计数提取顶层对象并逐一解析。
  - 相关文件：`python_worker/planner.py`（更新）

- 添加单元测试以覆盖坏 JSON 场景
  - 文件：`python_worker/test_planner_repair.py`
  - 覆盖示例：多余右大括号、对象间缺少逗号、单引号 + 尾随逗号
  - 本地运行结果：3 tests passed（修复器通过代表性场景验证）

- 为 Step Executor 添加受控测试套件
  - 文件：`python_worker/test_step_executor_agents.py`
  - 覆盖 agent：`qwen`、`Volcengine`、`deepeek`
  - 覆盖步骤类型：`analyze`、`plan`、`write`、`refine`、`test`
  - 测试策略：使用 `monkeypatch` 替换 LLM/运行器为安全 stub，避免网络/执行副作用
  - 本地运行结果：15 tests passed

- 在 `Copilot_Alphapilot/Copilot_Alphapilot` 目录初始化本地 git 并提交以上变更（commit message："增强：planner JSON 修复器并添加单元测试"）。

---

后续建议：
- 将新增测试加入 CI（GitHub Actions），以防回归。
- 在生产/部署说明中记录哪些步骤需要 API Key 才能运行（避免在 CI 中误触）。
- 考虑在 `planner` 中记录（或以 debug 级别日志输出）原始 LLM 输出与修复候选，便于线下诊断异常样本。

## 2026-10-02

> 本条根据当前工作区的未提交改动整理；仓库没有发现 2026-10-02 的提交记录。以下测试为新增或更新的测试覆盖范围，不代表本日已运行并通过。

- 统一任务请求协议
  - 增加 Node API 与 Python Worker 共用的任务协议定义，并在 VS Code 扩展中补充对应的类型和适配器。
  - 对协议版本、任务类型、必填 prompt、context、workspace 路径和 trace ID 等字段增加校验，便于跨进程追踪请求并及早拒绝格式错误的任务。
  - 新增任务协议相关测试。

- 增加协作模式与读写策略
  - 增加导师、结对编程、工程师、审查者、创作者和导航员模式，并把模式选择接入 Webview 和任务提交流程。
  - 在 Worker 侧为模式配置提示词和执行步骤；对只读模式清理文件操作，在扩展侧阻止只读结果进入文件写入接口。
  - 新增协作模式策略测试。

- 建设 Qwen V3.5 控制平面
  - 增加意图、Persona、上下文需求、能力声明、执行链、副作用、授权、验证和恢复信息组成的执行计划。
  - 增加受限的项目上下文读取和用户指定 Python 文件读取能力，并为控制平面、上下文构建及 Qwen 步骤处理补充测试。
  - 明确授权边界：文件操作需要扩展侧确认；尚未接通的 Git 修改、测试恢复及重试能力不得报告为已执行。

- 接入 MaaS、ModelScope 和本地 Redis 运行路径
  - 增加 MaaS、ModelScope Worker 及相应的模型配置、任务路由和启动流程，并更新 `.env.example` 与 Docker Compose 配置。
  - 更新 `start_all.ps1`，支持启动本地 Redis 和新增 Worker；新增 API Key 连通性检查脚本及本地 Redis / 模型配置说明。

- 完善多模型任务执行及 VS Code 扩展衔接
  - 更新 Qwen、DeepSeek、Doubao、Gemini 和本地模型 Worker 的 Persona、步骤提示词、FileOps 或执行逻辑。
  - 调整 Node API、VS Code 扩展任务分发、协议类型、WebSocket / 结果处理及任务面板，并更新 React Webview 的协作模式、聊天输入和模型选择界面。
  - 更新扩展编译产物及 Webview 构建资源，以配合源码改动。

- 新增或扩展测试覆盖
  - 覆盖任务协议、协作模式、上下文构建、控制平面、FileOps 代码围栏、Qwen 文档生成 / 修复步骤及文件操作等场景。
  - 本条日志整理时未执行这些测试；合并前仍需运行相应的 Python、Node.js 和扩展构建验证，并进行多模型端到端检查。

- 当前已知验证边界
  - 现有文档指出，Qwen 文件操作确认后的 Worker 恢复、项目测试执行以及 Git 操作流程尚未完整接通；这些能力仍需后续实现和验证。

## 2026-10-03

- 完成自动任务路由与控制平面文档更新
  - 更新 `docs/V35_CONTROL_PLANE.md`，将文档从 Qwen 专属控制平面说明扩展为跨 Worker 自动任务路由说明，记录统一路由来源、意图与 Qwen 步骤链、能力适配、只读策略和授权限制。
  - 明确协作模式是 Worker 根据请求推导的内部策略，不是前端必选的人格；未知请求安全回落到只读问答。
  - 记录当前仍未接通的确认后测试恢复、Git 操作、重试及自愈流程，并区分自动化测试与真实端到端验证。

- 验证自动路由及工作区维护回归
  - 在 Python Worker 环境运行 `python -m pytest tests -q`：**51 passed**。
  - 对修改过的路由、Worker 和测试文件运行 `py_compile`：通过。
  - 运行 `git diff --check`：通过；Git 输出的 LF/CRLF 转换提示不属于空白错误。
  - 测试覆盖中文创作、项目使用说明、代码审查、代码修复及“解释并修复”请求，并检查步骤选择、只读 FileOps、文件范围、测试授权等待以及工作区工具进度和命令结果报告。
  - 本次未进行实时模型 API、VS Code 界面或确认后真实写入的端到端验证。
  - 后续补充依赖发现：用户明确请求安装依赖时，从 Python AST 导入分析中排除标准库和项目本地模块，将常见导入别名映射到发行包名（例如 `sklearn` → `scikit-learn`）；无清单时安装可靠识别的包，无法映射的导入会报告且不猜测。完整 Markdown 代码围栏会在依赖分析时解包，但扫描仍报告源文件语法错误。
  - 依赖扫描、环境安装和工作区任务流的定向测试通过；依赖发现改动后的完整 Python Worker 测试套件 `python -m pytest tests -q`：**54 passed**。
  - 用户在 `D:\src` 完成实际工作区验证：扫描 8 个 Python 文件，结果为 0 个语法/缩进问题；复用项目 `.venv`，源码导入识别出 `joblib`、`numpy`、`pandas`、`scikit-learn`，pip 安装命令退出码为 0，并安装了其传递依赖。
  - 后续在 `D:\src\.venv` 验证 `joblib`、`numpy`、`pandas`、`sklearn`、`scipy` 均可导入，`pip check` 输出 `No broken requirements found`。用户反馈此前已确认并应用修复提案，复扫无语法/缩进错误；此文件修改结果按用户实测反馈记录，不将其误写成自动化测试覆盖。
  - 这是依赖扫描功能首次得到真实项目安装成功的用户反馈：成功日志包含实际命令、退出码和包安装输出。无法映射的项目模块名被列出而未尝试安装，保留了“不猜包名”的安全行为。

## 2026-10-04

- 按用户要求更新 `start_all.ps1`：启动列表和服务状态摘要中移除 DeepSeek Worker 与 Doubao Worker；用户反馈这两个 Worker 的 API Key 已无效。
- `start_all.ps1` 仍会尝试启动记忆中枢（Docker PostgreSQL/pgvector）、本地 Redis、Node API、AlphaPilot Proxy，以及 Qwen、Gemini、MaaS、ModelScope 和 Local LLM Worker。脚本不会编译 VS Code 扩展，也不会自动启动 VS Code 调试会话；E2E 测试由用户自行运行并反馈问题。
- 本次未运行启动脚本或 E2E 测试，避免启动 Docker 容器、服务和多个 Worker；仅静态检查了脚本配置和说明。

- 对齐 Gemini、MaaS、ModelScope 和 Local LLM Worker 的共享能力入口
  - 四个 Worker 改用与 Qwen 相同的规范意图链、项目上下文/记忆/技能准备流程，并接入只读响应、Python 工作区维护和 docstring 步骤；LLM API 调用仍保留 Provider 专属实现。
  - 补充任务协议校验及 trace 元数据传递，授权等待状态不写入成功记忆；Local LLM 不再向步骤暴露可直接写磁盘的旧占位能力。
  - 新增 `python_worker/tests/test_worker_capability_parity.py`，覆盖四个 Worker 的步骤注册、协议感知入口及无 Provider 网络调用的只读执行链。
  - 经用户确认，使用仓库根目录 `.venv_worker` 执行 6 个定向测试文件：**30 passed**。项目子目录 `.venv_worker` 缺少 pytest，安装工具未能将其安装到该解释器；未在该环境中执行测试。
  - 本次未运行实时模型 API、Worker 服务或端到端对话测试；共享工作区扫描仍仅覆盖 Python 项目。

- 精简工作区检查结果并重做实时工具进度呈现
  - 用户端最终答复仅保留 Python 扫描/问题/修改提案摘要及新增安装包数量；pip 命令、安装日志、依赖猜测与无法映射模块不再拼入聊天文本。
  - Worker 仍保留命令 stdout/stderr 供结构化诊断，并从 pip 的 `Successfully installed` 输出统计本次新增安装的唯一包数。
  - 工作区状态改为独立、短暂的工具进度提示；修正 Node API 与 Extension 对流式 `phase` / `channel` 的传递，使工具状态不再混入持久化的 AI 思考文本。
  - 新增/更新定向测试，覆盖成功包数与精简输出、tool 通道状态事件；经用户确认，定向 Python 测试 **9 passed**、Webview production build 和 VS Code Extension TypeScript compile 均通过。
  - 未进行真实模型 API 或前端端到端交互验证。

- 修复记忆服务未加载 PostgreSQL 本地凭据的问题
  - `memory_service.py` 在读取配置前加载仓库根目录 `.env.memory`，并保留进程环境变量优先级；凭据文件仍被 `.gitignore` 排除。
  - 安全核对本地配置密码与 Docker Desktop 中运行的 `alphapilot-memory-hub` 一致，未输出或改写密码。
  - 经用户确认执行只读连接检查：成功连接 `alphapilot_memory`，且 `user_profiles`、`memory_items` 表存在。

- 修复多轮记忆因 Embedding 服务失败及旧数据库结构不兼容而未写入的问题
  - 用户提供的两轮真实日志确认：第一轮因 Embedding 服务请求失败而保存失败；真实数据库验证又发现旧版表缺少 `updated_at`，且唯一索引与当前 upsert 冲突目标不同。
  - Embedding 服务不可用时告警并将记忆写入 `NULL` 向量；近期高价值记忆层仍可召回。向量语义检索需有效的 Embedding API 配置。
  - 原始用户请求与任务结果摘要一起保存；闲聊过滤改为整句匹配，避免“好的，请……”请求被误判。
  - 通过只读 schema 检测，兼容有/无 `updated_at` 列的现有数据库；使用 `ON CONFLICT DO NOTHING` 后按用户、类型和内容更新，兼容旧唯一索引。未在数据库执行 DDL。
  - 经用户确认，定向测试 **12 passed**；真实 PostgreSQL 随机探针写入后由独立连接从近期记忆层读回成功，并已删除探针数据（残留计数为 0）。

- 隔离 AlphaPilot 项目记忆数据库
  - 对比两个项目的 `.env.memory` 和记忆服务代码，确认它们此前都连接 `localhost:5432/alphapilot_memory`，使用同一个 `public.memory_items` / `public.user_profiles`；这导致共享物理表，但不是本次写入失败的唯一原因，embedding 配置失败和旧表结构差异才是已复现的直接故障。
  - 经用户确认，在同一 Docker PostgreSQL 容器和持久化卷中创建独立数据库 `alphapilot_copilot_memory`，使用 `init_memory_schema.sql` 初始化 4 张记忆表及 2 个检索函数。
  - 只更新本项目被忽略的 `.env.memory` 中 `DB_NAME`；`D:\Copilot_Alphapilot_new` 仍使用 `alphapilot_memory`。旧数据库数据不迁移、不删除；新库初始为空。
  - 验证新库的真实写入及另一连接近期记忆召回成功，探针数据已清理；启动本项目默认配置可连接新库。旧库仍保留 7 条 memory_items，两个数据库物理隔离。

- 修复"按上一轮对话执行"仍路由到导师人格的问题
  - 为"按照上面的对话执行项目编写"等明确承接式实现请求增加高优先级工程意图识别；自动协作模式因此选择 `engineer`，进入 `analyze → plan → write → refine → test`，测试仍遵循用户确认策略。
  - 为记忆上下文增加历史资料优先级说明：旧回答中的只读限制不自动覆盖用户当前明确的实现请求；当前安全授权规则仍然有效。
  - 增加精确复现用例，确认该 follow-up 路由为 `write_code` / `ENGINEER_EXECUTE` / `engineer`，并检查历史记忆不会覆盖当前请求。
  - 经用户确认运行 `test_intent_router.py` 与 `test_memory_scope.py`：**27 passed**。

## 2026-10-05

> 核心里程碑：Intent Router 从纯 Regex 规则引擎升级为 **LLM+Regex 联合路由架构**，正式具备语义级意图识别能力。

### LLM+Regex 联合路由架构

- 架构设计：LLM 作为第一层语义分类器，Regex 作为第二层兜底验证器
  - 第一层：调用 Qwen-turbo（免费）进行轻量意图分类，3 秒超时，输出 JSON `{intent, target_type, confidence, reasoning}`
  - 第二层：Regex 50+ 模式匹配兜底，覆盖 LLM 不可用/低置信/边界碰撞等场景
  - 决策策略：`confidence ≥ 0.75` 直接采用 LLM 结果；低于阈值或 API 调用失败则降级 Regex

- 新增意图与目标类型体系（`intent_router.py`）
  - **15 种意图**：`chat`、`mentor_explain`、`code_review`、`delete_files`、`workspace_maintenance`、`write_code`、`fix_code`、`explain_and_fix`、`explain_code`、`creative_writing`、`analysis`、`architecture`、`refactor`、`generate_doc`、`search_code`
  - **7 种目标类型**：`code`（源代码）、`test`（测试代码）、`config`（配置文件）、`infra`（基础设施 Docker/k8s/CI）、`file`（纯文本文档）、`dep`（依赖管理）、`none`（无目标—对话/解释/审查）
  - 分类提示词 `LITE_CLASSIFY_PROMPT`：temperature=0、max_tokens=120、result_format="message"

- 实现 LLM 分类核心方法
  - `_llm_classify(prompt)`：调用 Qwen API 做语义分类，解析 JSON 响应（处理 ```json 代码块包裹），异常时返回 None 触发降级
  - `_call_qwen_blocking(prompt, max_timeout)`：同步 HTTP 调用，支持 `choices[0].message.content` 和 `output.text` 两种响应格式
  - API Key 从 `worker_config.DASHSCOPE_API_KEY` 加载（支持 `.env` 文件），fallback 到 `os.environ`

- 修改 `detect_intent` 主逻辑
  - 最前端插入 ⓪ LLM 语义路由层，高置信结果直接返回 `(intent, persona, chain)`
  - LLM 失败或低置信时打印降级日志，无缝进入原有 ①-⑥ Regex 硬规则链路
  - 保持 `target_type` 信息透传，为后续 FileOps Parser 根据目标类型优化文件解析策略预留接口

- 扩展 Regex 兜底模式覆盖专业术语
  - 新增 50+ 专业工程术语正则：`FORCE_WRITE_CODE_PATTERNS` 增加"抽取为独立类"、"迁移至 Zustand"、"编写集成测试"等
  - `INTENT_PATTERNS` 增加 `refactor` 对"拆分组件"、"替换为环境变量"、"清掉 console.log"等操作的识别
  - 解决"清 console.log"在 `delete_files` 和 `refactor` 之间的 Regex 碰撞问题

### 测试验证

- **LLM 语义热点验证**（10 条歧义/专业 case）：8/8 均命中，LLM 正确区分了 `refactor` vs `write_code`、`fix_code` vs `write_code`、`delete_files` vs `refactor` 等 Regex 无法处理的语义边界
  - 关键差异案例：
    | prompt | Regex 旧判定 | LLM 新判定 | 分析 |
    |--------|:-----------:|:---------:|------|
    | 按钮颜色换成主题色 | `write_code` | `refactor` | LLM 正确识别 UI 修改 = 重构 |
    | API 整理成 Markdown | `write_code` | `generate_doc` | LLM 正确识别文档生成 |
    | 引入 Repository 模式 | `write_code` | `refactor` | LLM 正确识别设计模式引入 = 重构 |
    | SSR 水合不匹配修复 | `write_code` | `fix_code` | LLM 正确识别修复任务 |
    | 排查内存泄漏 | `explain_code` | `analysis` | LLM 正确识别诊断分析任务 |

- **全量 41 用例联合路由测试**（9 大类：模糊动作/非代码生成/破坏性操作/上下文指代/高阶上下文/架构重构/配置工程/测试保障/调试优化）
  - 纯 Regex 模式：41/41 PASS（宽松语义基准——许多"对"实际上是 Regex 把 `refactor` 都判成 `write_code`）
  - LLM+Regex 模式：**39/41 PASS (95.1%)**，耗时 38.1 秒（免费 Qwen-turbo）
  - 仅 2 个语义边缘差异：
    - "能不能搞个分页懒加载啥的" → LLM 被"能不能"疑问句误导为 `architecture` 讨论（实际意图是 write_code）
    - "诊断 CORS OPTIONS 返回 405" → LLM 判定为 `fix_code`（因"返回错误"暗示需修复），预期为 `explain_and_fix`

- 降级链路验证：未设置 `DASHSCOPE_API_KEY` 时，`_call_qwen_blocking` 返回空字符串 → `_llm_classify` 返回 None → `detect_intent` 打印"LLM不可用，降级Regex" → 原有 Regex 链路全量通过（零破坏性）

### 架构对比

| 维度 | 纯 Regex (旧) | LLM+Regex (新) |
|------|:---:|:---:|
| 意图分类 | 基于关键词正则匹配 | LLM 语义理解 + Regex 兜底 |
| 语义精度 | 低—"换成主题色" = write_code | 高—"换成主题色" = refactor |
| 歧义消解 | 无—依赖人工调正则冲突 | 有—"清console.log" 正确选 refactor 而非 delete_files |
| target_type | 无—无法区分 code/file/config/infra | 有—"生成.env.example"=file, "Dockerfile"=infra |
| API 依赖 | 无—离线可用 | 弱—无 API Key 时自动降级 Regex，功能不降级 |
| 扩展成本 | 高—每次新增需要手写正则 | 低—LLM 自然理解新术语，Regex 仅补边界 |