# CHANGELOG

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