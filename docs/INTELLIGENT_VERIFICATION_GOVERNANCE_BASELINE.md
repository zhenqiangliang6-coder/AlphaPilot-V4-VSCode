# Intelligent Verification Governance — P1 验收基线

> 版本: v1.0 | 日期: 2026-11-10 | 状态: 已冻结 P1 安全验收门禁
>
> 核心原则: AlphaPilot 不应该因为测试没有报错，就认为自己已经验证成功；它必须知道哪些事情实际验证了，哪些事情没有验证，以及为什么。

---

## 1. P1 安全验收结果（2026-11-10）

本次验收严格遵循「先基线后实现」原则，**零生产代码修改**，通过 Eval Harness 完整验证了当前工程边界状态。

### 1.1 验收状态汇总

| 类别 | 数量 | 状态 | 说明 |
|------|:----:|------|------|
| 现状探测 PASS | 7/7 | ✅ 全部通过 | 已有行为经过实际运行验证，无假阳性 |
| 生产边界探测实际执行 | 3/3 | ✅ 全部完成 | 不依赖目标模块，直接验证现存生产代码的真实边界行为 |
| 目标模块契约 SKIP | 25 | ⏭ 严格未实现跳过 | 全部因 `conversation_context` 模块尚未创建而跳过，无异常跳过、无测试错误 |
| 六项阻断修复 | 6/6 | ✅ 全部完成 | P0 级安全契约缺陷已全部锁定 |
| 生产代码修改 | 0 | 🔒 零修改 | 本次验收未触碰任何生产代码 |
| Eval Harness | — | ❄️ 已冻结 | 作为 P1 安全验收门禁，不再随意变更 |

### 1.2 三类验证状态的严格定义

本次验收明确区分三种结果，不得混淆：

| 状态 | 语义 | 判定规则 |
|------|------|----------|
| **PASS** | 已有行为经过实际验证 | 测试代码真实运行，断言通过，观察到实际发生的生产行为 |
| **SKIP** | 目标模块尚未实现，契约未执行 | 仅因模块导入失败触发 skip，其他任何原因不得标记 SKIP；不是验证失败，也不是功能通过 |
| **BLOCKED** | 本应执行验证，但环境/依赖限制无法完成 | 不属于本次基线范围，需单独登记原因 |

> 重要澄清: 本次报告中的 25 条 SKIP **不能** 理解为 25 项功能已经通过验收，也不能理解为验证失败。它们是严格的「目标模块未实现，等待未来接入后执行」状态占位。

---

## 2. 六项阻断修复及其工程意义

这六项修复从根本上改变了测试的可信度，是 AlphaPilot 的长期工程规范：

### 2.1 M1 — Thread.join() 并发测试修复

**原问题**: `assert t1.join(timeout=60)` — Python `threading.Thread.join()` 恒返回 `None`，断言必然失败，并发测试永远无法可靠证明线程完成状态。

**修复**:
```python
t1.join(timeout=60)
t2.join(timeout=60)
t3.join(timeout=60)
assert not t1.is_alive(), "Writer A 超时未结束（可能死锁）"
```

**工程意义**: 保证并发测试观察的是线程实际完成后的真实状态，而不是检查 API 返回值恒为 None 的无意义断言。

### 2.2 C3-B — 生产边界探测解耦

**原问题**: C3-B 现存 `worker_runtime.py` 硬编码污染点探测被 `cc` fixture 整体跳过，无法在目标模块未实现时验证现存生产问题。

**修复**: 将 `test_existing_worker_runtime_save_hardcodes_success_status` 从 Section C 移至 Section A，直接导入 `worker_runtime`，用 monkeypatch 捕获 `save_task_memories` 参数，完全不依赖 `conversation_context` 模块。

**工程意义**: 防止生产边界探测依赖目标模块 Fixture，确保现存生产代码的已知问题在任何阶段都能被独立验证。

### 2.3 M2 — 真实 call_llm() 参数捕获

**原问题**: 测试自行构造 `final_worker_prompt` 变量自检，没有真正捕获流入 `call_llm()` 的实际 Prompt 参数。测试观察的是测试代码自己构造出来的预期行为，不是真实调用链。

**修复**: monkeypatch 真实 `python_worker.agents.qwen.qwen_api.call_llm`，捕获实际传入模型层的 Prompt 对象，断言失败/危险标记不存在于该对象上。

**工程意义**: 建立核心原则 — **测试必须观察实际发生的行为，而不是观察测试代码自己构造出来的预期行为**。

### 2.4 C6B — 三级命名空间完整验证

**原问题**: 仅用宽松的 `has_user or has_project` 检查签名，没有真正锁定 user_id → project_id → conversation_id 的三级隔离契约。

**修复**: 不再做宽松签名检查，要求模块暴露 `make_namespace_key(user_id, project_id, conversation_id)` 辅助函数，真实验证：
- 三个维度任一不同 → 生成的键必须不同；
- 跨用户、跨项目、跨会话双向读写隔离。

**工程意义**: 明确锁定 Store 三级命名空间契约，防止不同用户/项目/会话之间发生数据串线。

### 2.5 outcome — 非法值拒绝测试

**原问题**: 仅检查 `success/failed/abandoned` 三个合法值，没有防止非法状态被静默归一化为 `success`。

**修复**: 明确遍历 `"unknown"`, `"pending"`, `""`, `"invalid"`, `"PARTIAL"`, `123` 等非法值，断言绝对不得被静默转换为 `"success"` — 必须抛出异常、拒绝写入、或保留原始非法值以便上层校验。

**工程意义**: 这是状态完整性和安全边界问题，不是普通的输入校验问题。防止整个系统用「默认 success」掩盖所有失败状态。

### 2.6 M3 — 完整因果链锁定

**原问题**: 仅在 Prompt 文本层检查字符串位置，没有建立从历史内容到真实执行边界的因果链。

**修复**: 逐段锁定因果链路：
```
恶意历史（授权声明 + 危险计划）
   ↓ build_conversation_context
上下文过滤：危险内容不作为当前可注入依据
   ↓ inject_conversation_context
注入产物：危险内容绝不进入「当前用户请求」段
   ↓ 由当前上下文推导的执行计划
执行计划：approval 为空（历史授权不得被继承）
   ↓ requires_authorization_before_step（真实硬边界）
授权检查拒绝（空 approval 下不得通过）
```

**工程意义**: 这已经具有了 IVG 要求的「影响分析与证据链思维」，不再是孤立的断言点。

---

## 3. Eval Harness 冻结边界

### 3.1 受保护资产定义

以下内容已冻结为 P1 安全验收门禁，IVG 作为治理系统可以调用、读取结果、将其作为证据，但**不得随意修改已经冻结的 P1 规则**：

| 冻结项 | 路径 | 保护级别 |
|--------|------|:--------:|
| 7 条现状探测 | `test_conversation_context.py` Section A | 🔒 只读，不可变更 |
| 6 项阻断修复 | 同上 | 🔒 只读，不可变更 |
| 25 条目标模块契约 SKIP | `test_conversation_context.py` Section B/C | 🔒 规则不可变更，仅可修改 SKIP 条件为 PASS 当目标模块实现 |
| 函数契约文档头 | 文件头部 docstring | 🔒 只读 |

### 3.2 冻结原则

1. 不因为 IVG 的引入而改写已通过的现状探测结果；
2. 不把 SKIP 的 25 条伪装成 PASS；
3. 不允许新代码直接合并导致原安全门禁静默失效。

---

## 4. 25 项未实现契约的状态管理原则

| 原则 | 规则 |
|------|------|
| 显式登记 | 每项 SKIP 必须在 skip 消息中明确说明原因（`P1 未实现：python_worker.conversation_context 模块尚未创建`） |
| 仅一条跳过路径 | 唯一合法的跳过触发条件：导入目标模块失败（`import_module("python_worker.conversation_context")` 抛出 ImportError） |
| 不得提前通过 | 目标模块未实现时，不得用 mock、stub 或其他方式让契约测试显示 PASS |
| 接入审计 | 未来实现 `conversation_context.py` 后，必须重新运行全部 25 条，每条 PASS 都要有对应的源码变更审计记录 |

---

## 5. Intelligent Verification Governance (IVG) 架构

### 5.1 IVG 与现有 Eval Harness 的关系

```
现有 Eval Harness（已冻结 P1 安全验收门禁）
    ▲
    │ 可调用 / 可读取结果 / 作为安全验收证据
    │ 但 IVG 不得随意修改已冻结规则
    │
Intelligent Verification Governance
    ├─ Analyze   → 变更与影响分析
    ├─ Select    → 验证策略选择
    ├─ Execute   → 验证执行
    ├─ Evidence  → 证据与审计链
    └─ Engineering Verification Gate → 决定是否具备交付条件
```

**关键设计约束**: IVG 是治理系统，Eval Harness 是其中一个**受保护的验证执行与验收资产**。两者不能混同。

### 5.2 IVG 目标架构四层模型

| 层级 | 能力 | 当前状态 |
|------|------|----------|
| Analyze | 变更影响范围自动分析，定位哪些测试需要重跑 | 架构设计阶段 |
| Select | 根据影响分析结果智能选择验证子集，而非全量重跑 | 尚未证明实现 |
| Execute | 调度受保护的 Eval Harness 和其他验证资产 | P1 Eval Harness 已就绪 |
| Evidence | 自动汇总 PASS/SKIP/BLOCKED 状态，生成审计链 | 已有验收实践（本次 P1 报告），尚未通用化 |

---

## 6. AlphaPilot 当前阶段定位（2026-11-10）

| 能力维度 | 当前判断 |
|----------|----------|
| P1 安全边界探测 | ✅ 已通过本次报告验收 |
| Eval Harness | ❄️ 已冻结为 P1 安全门禁 |
| 真实生产行为探测 | ✅ 已执行 3/3 条独立探测 |
| 目标模块契约 | 25 项仍待实现（conversation_context 模块尚未创建） |
| 全项目真实调用链验证 | ⚠️ 尚不能据此认定完成 |
| Intelligent Verification Governance | 📐 架构设计阶段 |
| 自动验证策略选择 | ⏳ 尚未证明实现 |
| 证据化跳过治理 | ✅ 已有验收实践，尚未证明具备通用机制 |

---

## 7. Round 1～Round 10 历史验证定位（审计保护）

本次 P1 验收基线是在多轮迭代基础上形成的。历史工作记录（`g54_audit_log.md`、`phase2-gate-decisions.md`、`WORKLOG.md` 等）全部保留，IVG 架构设计阶段必须审计完整项目和 Round 1～Round 10 记录，避免与已有成果重复建设。

### 审计保护原则
1. 所有历史验证结论保留原始文件，不覆盖、不移除；
2. 新基线仅叠加新状态，不推翻历史；
3. 如发现重复建设风险，立即在 IVG 架构中标记重用路径。

---

## 8. 后续规划

### 8.1 近期（P1 生产实现前）
- 不立即启动 Round 11；
- 完成 IVG 架构审计，识别可重用资产；
- 保持 Eval Harness 冻结状态，不做任何生产代码修改。

### 8.2 中期（P1 Conversation Context 模块实现）
- 实现 `python_worker/conversation_context.py`；
- 重新运行 `python -m pytest python_worker/tests/test_conversation_context.py -q -rs`；
- 25 条 SKIP 逐条转为 PASS，每条 PASS 对应源码变更审计记录。

### 8.3 远期（IVG 落地）
- 实现 Analyze → Select → Execute → Evidence 全链路；
- 将 P1 Eval Harness 接入 IVG 作为首个受保护验证资产；
- 建立全项目的证据化跳过治理通用机制。

---

## 9. IVG 验收标准与交付门禁

IVG 自身必须通过以下门禁，才能正式接管全项目验证治理：

| # | IVG 验收标准 | 状态 |
|---|-------------|:----:|
| 1 | 能准确区分 PASS/SKIP/BLOCKED 三类状态，不混淆 | 部分验证（本次 P1 基线已演示） |
| 2 | 变更影响分析至少覆盖 80% 的已知测试依赖关系 | 待实现 |
| 3 | 不随意修改已冻结的 Eval Harness 规则 | —（架构约束） |
| 4 | 自动生成带时间戳的审计证据链 | 待实现 |
| 5 | Engineering Verification Gate 输出可解释的交付/不交付结论 | 待实现 |