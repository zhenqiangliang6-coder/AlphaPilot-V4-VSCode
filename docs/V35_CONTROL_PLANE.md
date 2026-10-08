# 自动任务路由与 V3.5 控制平面 / Automatic Task Routing and V3.5 Control Plane

本文记录 Worker 自动识别任务、选择执行链及当前授权边界。意图到规范执行链的映射统一维护在 `python_worker/intent_router.py`；各 Worker 根据自身能力适配该链。协作模式是内部行为策略，不是用户必须选择的人格，也不应成为第二个执行链决策源。

This document describes Worker-owned intent classification, execution-chain selection, and the current authorization boundary. The canonical intent-to-chain mapping lives in `python_worker/intent_router.py`; each Worker adapts it to its available capabilities. Collaboration modes are internal behavior policies, not a persona the user must select or a second source of execution-chain decisions.

## 路由行为 / Routing Behavior

Worker 根据请求选择任务意图，并据此推导内部协作策略和最小执行链。已覆盖的意图包括：

The Worker classifies each request, derives an internal collaboration policy, and selects the corresponding minimal execution chain. Covered intents include:

| 请求类型 / Request type | Intent | Qwen 执行链 / Qwen chain | 行为边界 / Behavior |
| --- | --- | --- | --- |
| 普通问答 / General conversation | `chat` | `analyze -> plan -> respond` | 不产生文件操作提案 / No file-operation proposals |
| 项目使用说明 / Project usage guidance | `mentor_explain` | `analyze -> plan -> respond` | 只读收集允许范围内的项目上下文 / Read allowlisted project context |
| 代码说明 / Code explanation | `explain_code` | `analyze -> plan -> respond` | 说明已有代码，不修改文件 / Explain existing code without file changes |
| 代码审查 / Code review | `code_review` | `analyze -> plan -> respond` | 只报告审查结果 / Report findings only |
| 创作 / Creative writing | `creative_writing` | `analyze -> plan -> write -> refine` | 输出文本，不写入工作区 / Produce text without workspace writes |
| 代码修复 / Code repair | `fix_code` | `analyze -> fix -> test` | 修复以 FileOps 提案形式返回；测试步骤须等待授权 / Return proposed FileOps; testing waits for authorization |
| 解释并修复 / Explain and repair | `explain_and_fix` | `analyze -> plan -> fix -> test -> respond` | 先解释再修复；测试未经授权不运行 / Explain and repair; do not run tests before authorization |
| 项目维护 / Workspace maintenance | `workspace_maintenance` | `analyze -> fix -> workspace` | 按请求扫描 Python 文件，并可创建虚拟环境或安装依赖 / Scan Python files and perform explicitly requested environment or dependency operations |
| 代码生成 / Code generation | `write_code` | `analyze -> plan -> write -> refine -> test` | 变更作为提案返回；测试未经授权不运行 / Return changes as proposals; testing waits for authorization |

未知请求安全降级到只读问答，而不是默认进入代码生成链。Qwen、Gemini、MaaS、ModelScope 和 Local LLM 现在通过共享请求准备器使用同一规范路由，并注册只读响应、工作区维护和 docstring 步骤；各 Worker 的模型调用仍由各自的 Provider API 执行。共享工作区工具当前只扫描 Python 项目，因此这表示执行框架与步骤能力对齐，不代表不同模型的回答质量相同，也不代表已完成真实 API 或端到端验证。任何未接通的工具能力仍不得声称已执行。

Unrecognized requests safely fall back to read-only conversation rather than code generation. Qwen, Gemini, MaaS, ModelScope, and Local LLM now use the same canonical routing through a shared request preparer and register read-only response, workspace-maintenance, and docstring steps; model calls remain provider-specific. The shared workspace tools currently scan Python projects only. This aligns execution framework and step capabilities; it does not mean the models produce identical answer quality or that live API/end-to-end validation has been performed. Workers must not claim any tool operation that is not connected and executed.

## 执行计划契约 / Execution Plan Contract

`execution_plan` 保存在 `context.meta` 中，包含：

`execution_plan` is stored in `context.meta` and contains:

- `mode`、`intent` 和 `persona`：Worker 推导出的执行策略、任务类型和行为人格。
  `mode`, `intent`, and `persona`: the Worker-derived execution policy, task type, and behavior persona.
- `context_requirements`：规划前需要收集的项目事实。
  `context_requirements`: project evidence to gather before planning.
- `capabilities`：计划所需能力及当前执行路径是否支持这些能力。
  `capabilities`: required capabilities and whether the current path provides them.
- `execution_chain`：经 Worker 能力适配后的步骤顺序。
  `execution_chain`: the step sequence adapted to the Worker’s capabilities.
- `side_effects` 和 `approval`：可能产生的副作用及授权要求。
  `side_effects` and `approval`: possible side effects and their authorization requirements.
- `validation` 和 `recovery`：验证要求和无法完成时的处理方式。
  `validation` and `recovery`: validation requirements and failure handling.

能力标记不可用时，Worker 必须明确说明限制，不能把计划中的能力描述成已经执行。

When a capability is marked unavailable, the Worker must report the limitation and must not describe a planned capability as completed.

## 只读策略与授权 / Read-only Policy and Authorization

- Webview 不要求用户选择协作模式；缺少模式时由 Worker 根据意图推导 `teacher`、`reviewer`、`creative` 或 `engineer` 等内部策略。
- `teacher`、`reviewer` 和 `creative` 策略会禁止文件修改；Worker 结果和步骤事件中的 FileOps 会受策略约束。
- VS Code 扩展在将 FileOps 写入工作区前要求用户确认。拒绝或关闭确认框均不应用提案。
- 需要运行测试的执行计划在 Worker 侧将 `test` 步骤延后并标记为等待授权；当前没有在确认文件变更后恢复 Worker 并执行项目测试的完整流程。
- 工作区维护工具的虚拟环境和依赖操作只应由明确提出该操作的请求触发。请求安装依赖时，扫描器会从 Python AST 导入中提取第三方模块，过滤标准库和项目内模块，并将已知别名映射到发行包名（例如 `sklearn -> scikit-learn`）；无清单时安装可确认的候选包。有歧义或无可靠映射的导入会报告且不擅自安装。语法错误文件无法解析导入；完整包裹在 Markdown 代码围栏中的源文件只在依赖分析时去除外层围栏。此静态分析不能发现动态导入或非 Python 依赖，候选导入也不保证都是运行时必需项。
- 自动意图判断本身不能授权删除文件、高风险命令或超出请求范围的操作。
- Git 修改、确认后恢复执行、自动重试和自愈编排尚未形成完整的请求/授权/结果协议；能力不可用时必须停止并如实报告。

- The Webview does not require a collaboration-mode selection. When no mode is supplied, the Worker derives an internal policy such as `teacher`, `reviewer`, `creative`, or `engineer` from the intent.
- `teacher`, `reviewer`, and `creative` policies prohibit file changes; FileOps in Worker results and step events are constrained by these policies.
- The VS Code extension requests confirmation before applying FileOps to the workspace. Refusing or closing the prompt does not apply the proposal.
- Plans that include test execution defer the `test` step and mark it as awaiting authorization in the Worker. There is not yet a complete flow to resume the Worker and run project tests after file changes are approved.
- Workspace environment and dependency operations should be triggered only by a request that explicitly asks for them. For an explicit dependency-install request, the scanner extracts third-party imports from Python AST, excludes standard-library and project-local modules, and maps known aliases to distribution names (for example, `sklearn -> scikit-learn`). When no manifest exists, safely identified candidates are installed. Ambiguous or unmapped imports are reported, not guessed. Files with syntax errors cannot be parsed for imports; a source file wrapped entirely in a Markdown code fence is unwrapped for dependency analysis only. Static analysis cannot find dynamic imports or non-Python dependencies, and an import is not necessarily a runtime requirement.
- Automatic intent classification does not authorize file deletion, high-risk commands, or actions outside the requested scope.
- Git mutations, post-approval resumption, automatic retries, and self-healing do not yet have a complete request/approval/result protocol. Stop and report the limitation when a capability is unavailable.

## 验证范围 / Validation

2026-10-03 在 Python Worker 环境运行 `python -m pytest tests -q`：**51 passed**。修改过的路由、Worker 和测试文件通过 `py_compile`；`git diff --check` 通过（Git 对部分文件提示 LF/CRLF 转换，不是空白错误）。测试覆盖真实中文请求的意图与步骤、只读结果、文件读取范围、修复提案范围、测试步骤延后，以及工作区工具进度和真实命令结果的报告。

On 2026-10-03, `python -m pytest tests -q` completed in the Python Worker environment: **51 passed**. The modified router, Workers, and tests passed `py_compile`; `git diff --check` passed (Git emitted LF/CRLF conversion notices for some files, not whitespace errors). Tests cover Chinese request routing and step selection, read-only results, file-read scope, repair proposal scope, deferred test steps, and workspace-tool progress and command-result reporting.

这些是 Worker 层的自动化测试，不等同于实时模型 API 调用、VS Code 界面交互、用户确认后的真实文件写入或服务端到端验证。

These are Worker-level automated tests. They do not constitute live model API calls, VS Code UI interaction, real file writes after user confirmation, or end-to-end service validation.

依赖扫描测试验证：无依赖清单时从 `pandas`、`sklearn` 等源码导入推断并生成 pip 安装命令；标准库和项目本地模块不会作为 pip 依赖；未知包名不进行猜测安装；围栏包裹的 Python 源可参与导入分析，同时仍报告其磁盘内容存在语法错误。

Dependency-scan tests verify that imports such as `pandas` and `sklearn` produce pip install commands without a manifest; standard-library and project-local modules are excluded; unknown package names are not guessed; and fenced Python source is considered for import analysis while its on-disk syntax issue remains reported.

2026-10-03 依赖发现与安装器接线完成后，完整 Python Worker 测试套件为 **54 passed**。

After wiring source-based dependency discovery to the installer on 2026-10-03, the full Python Worker test suite completed with **54 passed**.

## 用户实测案例 / User-Reported End-to-End Example

2026-10-03，用户在 `D:\src` 实际运行项目维护请求。Worker 扫描 8 个 Python 文件，报告 0 个语法/缩进问题；复用现有 `D:\src\.venv`，从导入推断出 `joblib`、`numpy`、`pandas` 和 `scikit-learn`，并以退出码 0 执行 pip 安装。安装日志还显示 `scipy`、`python-dateutil`、`cloudpickle`、`threadpoolctl`、`six`、`tzdata`、`narwhals` 等依赖一并安装。随后在该虚拟环境中验证核心包可导入，`pip check` 报告 `No broken requirements found`。

用户反馈此前已确认并应用代码修复提案，后续扫描未发现语法/缩进问题。上述结论记录为用户提供的实际使用反馈；自动化 Worker 测试本身不验证用户工作区的文件写入过程。实际安装成功由 pip 日志及后续虚拟环境导入检查支持。

未能映射的导入（包括日志中的项目内模块名）被单独报告，没有被当作已安装依赖。静态导入分析仍可能包含条件/可选导入，也无法发现动态导入；需要由开发者确认实际运行时依赖。

On 2026-10-03, the user ran a workspace-maintenance request against `D:\src`. The Worker scanned 8 Python files and reported no syntax/indentation issues; it reused `D:\src\.venv`, inferred `joblib`, `numpy`, `pandas`, and `scikit-learn` from imports, and ran pip with exit code 0. The installation log also showed transitive packages such as `scipy`, `python-dateutil`, `cloudpickle`, `threadpoolctl`, `six`, `tzdata`, and `narwhals`. A subsequent check in that venv successfully imported the core packages, and `pip check` reported `No broken requirements found`.

The user reports that an earlier repair proposal was confirmed and applied, and a later scan found no remaining syntax/indentation issues. This is recorded as user-reported real-world usage; the automated Worker tests do not themselves validate writes to the user's workspace. Successful dependency installation is supported by the pip log and subsequent venv import check.

Unmapped imports, including project-local module names from the log, were reported separately and were not represented as installed dependencies. Static import analysis may include conditional/optional imports and cannot discover dynamic imports; developers should confirm runtime requirements.
