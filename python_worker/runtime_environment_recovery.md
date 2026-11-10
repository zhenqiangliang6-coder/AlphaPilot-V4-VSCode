# 差距与路线图 — runtime_environment_recovery（P0）架构依据

> 归档日期：2026-11-10
> 用途：本文档是 AlphaPilot「运行期环境自愈（P0）」的设计依据与实施边界，替代追加到 CHANGELOG.md 的方案。后续 P0 的实现、测试、验收均以本文档为准。

## 一、背景与现状

### 1.1 已具备的能力（分层）

| 层 | 能力 | 成熟度 |
| --- | --- | --- |
| 意图/人格路由 | 意图识别 + 人格路由 + 执行链规划 | ✅ 稳定 |
| 执行层 | 动态多步骤 + 人格流式调用 | 🟡 动态好但缺收敛门 |
| 安全/授权 | R6 四步授权、路径守卫、授权测试命令 | ✅ 稳定 |
| 自愈层 | test-fix 循环、venv + 依赖安装 | 🟡 缺运行期命令探测自愈 |
| 记忆层 | 长期项目记忆（MEMORY） | 🟡 缺短期会话工作记忆 |
| 治理层 | R10 四层语义门禁 + 隔离 + 回滚 + 证据链 | ✅ 强（FAIL-CLOSED） |
| 契约层 | 协议 1.0 三端对齐 + 契约向量测试 | ✅ 强 |

### 1.2 三个核心差距

1. **命令执行自愈缺失**：已有 `setup_python_environment` / `install_dependencies` / venv 创建等基础设施，但缺「运行期探测 → 自动补装 → 降级」这条受授权约束的闭环。pytest 缺失时走的是「test 失败 → fix 循环」，而非自愈路径。
2. **短期工作记忆未接线**：`conversation_id` 已全链路透传（Node 注入 → Worker meta 保留 → 前端持久化），但 Worker 的 prompt 增强只有长期记忆（MEMORY，按项目路径 hash 生成 user_id）＋只读源码＋工作区扫描，**没有按 `conversation_id` 拉取历史轮次注入**。长期记忆 ≠ 短期会话工作记忆。
3. **动态执行链缺收敛门**：`IntentRouter.plan_request` + `detected_chain` 已实现 LLM 重定向的动态链，但缺 step budget、环路检测、收敛门，存在无限重定向风险。

## 二、P0 定义与边界

### 2.1 命名与范围

- **命名**：`runtime_environment_recovery`
- **第一版严格限定**：Python 测试命令自愈（不做其它语言的运行时环境恢复）

### 2.2 目标执行链（7 步）

1. **Probe（运行环境探测）**：检查 Python 解释器、pytest 是否可用、项目依赖声明、虚拟环境状态。
2. **Diagnose（故障分类）**：区分「命令不存在 / 依赖缺失 / 依赖冲突 / 测试代码失败 / 环境配置错误」。
3. **Authorize（授权检查）**：安装动作必须经过 R6 授权门，自动修复不得绕过用户授权。
4. **Recover（隔离修复）**：优先复用已有 `setup_python_environment`，在项目隔离环境中安装必要依赖。
5. **Retry（有限重试）**：使用修复后的解释器重新执行原测试命令，设置明确重试上限。
6. **Degrade（安全降级）**：无法恢复时停止自动安装，记录失败原因，将真实失败交还现有 test → fix 链路。
7. **Evidence（证据记录）**：将探测、授权、安装、重试、降级记录写入 `context.meta`。

### 2.3 降级决策表（权威口径）

| 情况 | 处理方式 |
| --- | --- |
| pytest 不存在 | 授权后隔离安装 |
| pytest 依赖缺失 | 根据项目依赖声明修复 |
| pytest 安装失败 | 保留证据，停止自动安装 |
| pytest 测试失败 | 进入现有 fix 流程 |
| pytest 无法运行，但 unittest 测试存在 | 可作为辅助诊断，不替代原测试结果 |
| 没有可执行测试 | 标记验证未完成，不得判定通过 |

**核心原则**：自愈层绝不能把「无法验证」错误地变成「验证通过」。unittest 或手动执行目标函数**不能**作为 pytest 验收的等价替代。

## 三、授权约束（复用 R6）

- 安装动作（`pip install`）必须经 R6 授权门，与 `authorized_test_command` 同源。
- 授权失败 → 进入 Degrade，不得静默安装。
- 证据保留 best-effort，但工作区安全 mandatory（与 R10 治理一脉相承）。

## 四、优先级路线图

| 优先级 | 工作 | 验收目标 |
| --- | --- | --- |
| P0 | 运行期环境自愈 | 缺失 pytest 时可受控恢复 |
| P1 | Conversation Context | 多轮任务真正共享短期工作记忆 |
| P2 | 动态执行链收敛 | 防止环路、无限重定向 |
| P3 | 测试分级与治理可视化 | 建立更完整的质量反馈体系 |
| 基础设施 | Eval Harness | 每轮升级都有可比较的质量基线 |

**Eval Harness 前移**：不得等到 P3。P0 实施前必须建立最小评估基线，否则无法判断自愈功能改善的是「成功率」还是「重试次数」。

## 五、验收标准

- 缺失 pytest 时可受控恢复（Probe → Diagnose → Authorize → Recover → Retry → Degrade → Evidence 全链路可走通）。
- 安装动作始终经过授权门，无授权不安装。
- 任何情况下「无法验证」不会误报为「验证通过」。
- 全过程证据可追溯（写入 `context.meta`）。

## 六、P0 实施验收报告

> 验收日期：2026-11-10
> 验收结论：**P0 验收通过**，安全契约达标，达到进入下一阶段（P1 Conversation Context 架构审查）的条件。

### 6.1 Eval Harness 红线基线

`pytest tests/test_eval_baseline.py -v` → **9 passed in 0.21s**，无 SKIP。

- S1–S3：恢复成功 3/3（`status=recovered` + `verification=passed`）
- S4：断言失败禁止自愈，`verification=failed`，无安装动作
- S5：unittest 仅辅助诊断，`verification=not_verified`
- S6：无可执行测试，`verification=not_verified`
- S7：安装超时终止，`install_calls ≤ 1`，有界重试
- S8：授权拒绝，`install_calls=0`、`install_actions=[]`
- 授权违规校验：跨全场景 `authorized=True`，违规次数恒为 0

### 6.2 四项核心指标

| 指标 | 结果 |
| --- | --- |
| Recovery Success（恢复成功率） | 3/3 |
| Recovery Cost（恢复成本） | 有界（安装恰 1 次，超时不无限重试） |
| False Positive（误报率） | 0（S4 `failed` / S5 S6 `not_verified`，无「无法验证→通过」） |
| Authorization Violation（授权违规） | 0（S8 零安装，全部安装动作已授权） |

### 6.3 Integration Regression（真实链路回归）

| 测试集 | 结果 |
| --- | --- |
| `test_project_test_routing.py` | PASS |
| `test_real_pytest_and_retry.py` | PASS |
| `test_self_healing_fix_with_di.py` | 3/4 |
| `test_intent_router.py` | 33/34 |

### 6.4 Known Flaky Tests（待隔离复现的失败项）

以下两个失败项**保留在整体回归报告中**，判定为「疑似既有、与 P0 修改范围无关」，但**尚未通过隔离复现证明其完全独立**，需作为独立待处理事项跟进。

1. `test_self_healing_fix_with_di.py::test_full_integration_with_dependency_injection`（IndexError）
   - 触发条件：`fix_step` 检测到测试错误后进入「自愈引擎路径」，该路径直接调用真实 LLM，忽略注入的 `fix_llm` mock。
   - 调用链：`run_test_step`(write_code) → `run_fix_step` → `run_healing_fix`（真实 LLM）。
   - 现象：外部 LLM 429/400 → `fix_llm.prompts` 为空 → `IndexError: list index out of range`。
   - 与 P0 关系：P0 改动仅落在 `run_test_step_for_intent`（`run_tests` 意图分支）及两个辅助函数，不涉及该路径。

2. `test_intent_router.py::test_fix_code_detection`（AssertionError: explain_and_fix ≠ fix_code）
   - 触发条件：依赖真实 LLM 语义分类。
   - 调用链：`IntentRouter._llm_classify` → 真实 LLM。
   - 现象：模型波动，返回 `explain_and_fix` 而非期望 `fix_code`/`analysis`。
   - 与 P0 关系：`intent_router.py` 未被改动。

### 6.5 Acceptance Decision

P0 达到安全契约与功能验收标准：可恢复场景 3/3、基线测试 9/9、误报 0、授权违规 0、安装重试有界，且原 test→fix→retest 闭环保持正常。

两个非全绿回归项（见 6.4）保留为独立待处理事项，不阻塞 P0 验收。