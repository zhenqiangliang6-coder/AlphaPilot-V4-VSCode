# CHANGELOG

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