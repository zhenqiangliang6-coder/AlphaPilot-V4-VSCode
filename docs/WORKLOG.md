# 工作记录（Worklog）

记录项目中的重要变更与里程碑，便于回溯与审计。

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