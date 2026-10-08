# 自愈系统更新总结 — v3.2 事件驱动多层自愈引擎

## 更新日期
2026-10-08

## 更新目标
将"单次 LLM 修复"升级为**事件驱动多层自愈引擎**，实现规则引擎优先、停滞检测、上下文精简、环境自愈四大核心能力，并织入现有 fix_step 流水线。

---

## 三层自愈架构

```
┌──────────────────────────────────────────────┐
│  Layer 1: 语法层 (Syntax)                     │
│  ├─ 括号闭合 → 规则引擎直接补括号              │
│  ├─ 缺冒号   → 规则引擎正则补冒号              │
│  └─ 引号/缩进 → LLM fallback                  │
├──────────────────────────────────────────────┤
│  Layer 2: 逻辑层 (Logic)                      │
│  ├─ import 路径 → 符号索引 + 精简 LLM prompt   │
│  ├─ fixture 缺失 → 规则引擎加 @pytest.fixture  │
│  └─ 断言失败   → 多文件上下文 LLM 修复         │
├──────────────────────────────────────────────┤
│  Layer 3: 环境层 (Environment)                │
│  ├─ venv 不存在  → python -m venv 自动创建    │
│  ├─ 依赖缺失     → 扫描 + pip install          │
│  └─ Python 版本 → 检测 + 报告                  │
└──────────────────────────────────────────────┘
```

---

## 修改文件清单

### 新增文件

| 文件 | 用途 | 大小 |
|------|------|------|
| `self_healing_adapter.py` | 自愈引擎适配器，生产级封装所有能力 | ~310 行 |

### 修改文件

| 文件 | 修改内容 | 版本 |
|------|---------|------|
| `agents/qwen/step_executor/fix_step.py` | 检测测试错误 → 触发自愈引擎；传统路径作为 fallback | v3.1 → v3.2 |

### 验证文件（测试用，开发阶段）

| 文件 | 用途 |
|------|------|
| `test_autonomous.py` | 全自动端到端自愈测试（注入 5 个错误 + 删除 venv） |
| `test_env_healing.py` | 环境层独立测试 |
| `test_final_demo.py` | 环境层 + 代码层集成测试 |

---

## 核心能力详解

### 1. 规则引擎优先（零 LLM 调用）

对于确定性语法错误，正则直接修复，不调 LLM：

| 错误类型 | 检测模式 | 修复方式 | LLM 调用 |
|----------|---------|---------|----------|
| 缺少冒号 | `expected ':'` | 正则补 `:` | 0 |
| 括号未闭合 | `was never closed` | 统计括号数补 `)` | 0 |
| fixture 缺装饰器 | `fixture 'X' not found` | 函数定义前加 `@pytest.fixture` | 0 |

### 2. 事件驱动路由

错误自动分类 → 按优先级路由 → 对应修复函数：

```
SyntaxError → 规则引擎 (优先) / LLM fallback
ModuleNotFoundError → 环境层 (pip install)
NameError → 符号索引 → 精简 LLM prompt
fixture_not_found → 规则引擎
assertion_error → 多文件上下文 LLM
```

### 3. 上下文分层（解决 prompt 超限）

| 层级 | 内容 | 大小 | 使用场景 |
|------|------|------|----------|
| 零上下文 | 无 | 0 | 规则引擎修复 |
| 精确上下文 | 单行导入路径 | ~500 字符 | import 修复 |
| 中度上下文 | 相关文件 + 错误栈 | ~5000 字符 | 多文件逻辑修复 |
| 坠安全截断 | 硬限制 + 截断警告 | 28000 字符 | 兜底保护 |

### 4. 停滞检测

连续 3 轮出相同错误类型且无新修复 → 终止重试，不再死循环。

### 5. 逗号保护

LLM 修复后检查逗号数量，要求保留 ≥ 80%，防止 LLM 误删 import 和参数中的逗号。

### 6. 文件备份/恢复

修代码前备份原文件，防止 LLM 永久破坏源文件（测试验证阶段使用）。

---

## 错误分类与优先级

| 错误类型 | 优先级 | 模式 | 路由目标 |
|----------|--------|------|----------|
| module_not_found | 10 | `ModuleNotFoundError: No module named 'X'` | 环境层 |
| no_tests | 9 | `collected 0 items` | 测试生成 |
| syntax | 8 | `SyntaxError: expected ':'` / `was never closed` | 规则引擎 → LLM |
| import_error | 7 | `ImportError: cannot import name 'X'` | 符号索引 + LLM |
| fixture_not_found | 6 | `fixture 'X' not found` | 规则引擎 |
| file_not_found | 5 | `FileNotFoundError: 'X'` | 路径分析 |
| name_error | 4 | `NameError: name 'X' is not defined` | 符号索引 + LLM |
| attribute_error | 3 | `AttributeError: 'X' object has no attribute` | 多文件 LLM |
| assertion_error | 3 | `AssertionError` | 多文件 LLM |

---

## 流水线集成

```
start_all.ps1
  → python_worker.agents.qwen.qwen_worker_v2
    → write_step → test_step → fix_step
                                │
                    [检测到测试错误?]
                     ├─ YES → self_healing_adapter.run_healing_fix
                     │         ├─ classify_top_error (错误分类)
                     │         ├─ 规则引擎 (语法 + fixture)
                     │         ├─ LLM 按需调用 (import + 逻辑)
                     │         └─ 停滞检测 (3轮无进展 → 终止)
                     │
                     └─ NO  → 传统单次 LLM 修复 (向后兼容)
```

---

## 验证结果

| 检查项 | 结果 |
|--------|------|
| 已有单元测试 | 6/6 通过 |
| 适配器 import 链 | python_worker → fix_step 完整 |
| 错误分类 6 种 | 全部正确识别 |
| 符号索引构建 | 正确索引类/函数/模块路径 |
| 规则引擎优先 | fixture 修复 0 次 LLM 调用 |
| 端到端自愈测试 | 5 个注入错误修复 4 个（第 5 个为架构级路径问题）|
| 环境层自愈 | venv 删除 → 自动创建 + pip install → 测试通过 |
| 停滞检测 | 连续 3 轮 assertion_error → 正确终止 |

---

## 上下文分层策略（记住什么 vs 放弃什么）

### 记住
- 错误位置和类型
- 目标符号的精确导入路径（如 `from src.api.vote_router import VoteRequest`）
- 当前修复文件的代码
- 项目符号索引（类/函数 → 文件:行号 映射）

### 放弃
- 全量项目地图文本（150 万字符 → 不进 prompt）
- 不相关文件的代码
- 已经修过的历史上下文
- 前几轮的 LLM 响应

### 原则
> 能用规则引擎绝不调 LLM，必须调 LLM 时先问"这轮最少需要多少信息就能让 LLM 做出正确决策"。

---

## 下一步规划

### Phase 1 (已完成)
- [x] 三层自愈架构 (语法/逻辑/环境)
- [x] 事件驱动引擎 + 错误路由
- [x] 规则引擎优先 + LLM fallback
- [x] 停滞检测 + prompt 截断保护
- [x] 备份/恢复机制
- [x] 项目符号索引 + 精简上下文
- [x] 织入实际 fix_step 流水线

### Phase 2 (下一步)
- [ ] 多步推理链 (_fix_logic: 分析 → 决策 → 验证 → 回退)
- [ ] 路径匹配修复 (monkeypatch / 依赖注入识别)
- [ ] 金字塔单元测试覆盖核心函数
- [ ] 上下文策略配置化 (不同 API 不同 max_chars)

### Phase 3 (远期)
- [ ] 修复策略学习 (记录成功模式，避免重复 LLM 调用)
- [ ] 多 API 适配器 (qwen / gpt / claude 自动切换)
- [ ] 修复回归测试 (修完后跑全量测试，不只看当前)

---

## 关键技术决策

| 决策 | 原因 |
|------|------|
| 规则引擎优先于 LLM | LLM 会误删逗号、引入新 bug；规则引擎零副作用 |
| 只修测试文件不碰源码 | LLM 错误修改被测源文件导致级联故障 |
| 符号索引替代全量项目地图 | 150 万字符 → API 400 错误；精简到 ~500 字符 |
| 3 轮停滞检测 | 避免 7-10 轮无效循环浪费资源 |
| prompt 28000 字符硬限制 | qwen-max 30720 限制，留 2720 余量 |

---

**更新完成时间**: 2026-10-08
**执行人**: AI Assistant
**关键文件**:
- [self_healing_adapter.py](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/self_healing_adapter.py) — 生产级自愈适配器
- [fix_step.py](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/qwen/step_executor/fix_step.py) — 织入点 (v3.2)
- [test_autonomous.py](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/test_autonomous.py) — 端到端验证脚本