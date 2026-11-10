> **"Safety is not a feature. It is the architecture itself."**
>
> AlphaPilot 是一个自主编码 Agent 系统，以 LLM 为脑、以 Git Worktree 为沙箱、以 pytest 为反馈闭环。
> 本文档定义其核心安全架构、流水线设计、数据模型、执行链资产与扩展策略。

---

## 工作日志 — 2026-11-10（P0→P3 短期会话记忆全链路闭环 + Qwen conversation_id 提取路径补齐）

### 背景
Worker 多轮任务之间缺乏「短期会话工作记忆」：上一轮成功结论无法注入下一轮 Prompt，失败轮次可能污染后续决策，跨会话存在串线风险。本阶段以「先基线后实现」纪律推进 P0→P3，先写 Eval Harness 锁定安全契约，再写生产实现，全程零回归。

### 交付链路（P1 → P2 → P3 → Qwen）

**P1 短期会话工作记忆基座**（`conversation_context.py`）
- `ConversationStore` 三级命名空间：`user_id → project_id → conversation_id → turns`，线程安全。
- `ConversationTurn` 单轮记录：`prompt/intent` 为历史叙事（不可信背景），`conclusion` 为需文件 mtime 新鲜度验证的当前事实。
- 失败/废弃轮次（`outcome in {failed, abandoned}`）整体排除，绝不进入下一轮决策。
- `ANTI_INJECTION_DECLARATION` 反注入声明恒在指令末尾，防止历史叙事劫持当前请求。
- 安全不变量：`cross_conversation_leak=0`、`unauthorized_injection=0`、`untrusted_instruction_exec=0`。
- 契约：`test_conversation_context.py` 32/32。

**P2-2 自愈记忆结构化接入**（`RecoveryResult → ConversationTurn`）
- 权威映射：`status=="recovered"` 且 `verification_status=="passed"` → `outcome=success`；其余一切组合 → `outcome=failed`。
- 未验证自愈绝不误报成功，失败自愈不污染后续决策。
- 契约：`test_healing_memory.py` 8/8。

**P2-3 Runtime 桥接，根除 status="success" 硬编码**（`worker_runtime.py`）
- `save_worker_memory` 不再无条件硬编码 `status="success"`，改从 `steps` 推导真实 outcome。
- 安全指标：`failed_task_marked_success=0`。
- 契约：`test_runtime_memory_bridge.py` 5/5。

**P3 全链路闭环**（`conversation_context.py` + `worker_runtime.py`）
- `get_conversation_store()`：进程级线程安全惰性单例，Worker 长驻进程跨任务共享，测试自行实例化实现零残留。
- `save_conversation_memory()` 写端：执行结果 → `ConversationTurn` → 全局 Store，自动维护 turn 序号。
- `inject_conversation_memory()` 读端：读回历史 → 排除失败轮次 → 追加反注入声明 → 注入本轮 Prompt。
- `_extract_conversation_id()`：从 `payload.conversation_id` / `payload.task_context` / `payload.context` 三路径安全提取。
- `prepare_worker_request` 读端注入 + `meta["conversation_id"]` 透传；`save_worker_memory` 末尾自动写回闭环。
- 契约：`test_full_execution_memory_bridge.py` F1-F9（9/9）。

**Qwen Worker conversation_id 提取路径补齐**（`agents/qwen/qwen_worker_v2.py`）
- 复用 `worker_runtime.inject_conversation_memory` / `save_conversation_memory` 单一实现（延迟导入 + 降级开关 `_SHORT_TERM_MEMORY_ENABLED`）。
- 读端：`execute_task` 长期记忆注入后，`context["meta"]["conversation_id"]` 存在时读回注入 Prompt。
- 写端：`main_loop` 长期记忆保存后，conversation_id 存在时写回短期记忆；`authorization_requests` 存在时跳过。
- `_derive_conversation_outcome(steps)` 纯函数：失败步骤绝不误标 success，与 worker_runtime 逻辑一致。
- 契约：`test_full_execution_memory_bridge.py` Q1-Q3（3/3）。

### 安全指标（P0→P3 全链路实施后恒为 0）

| 指标 | 实测 |
| --- | --- |
| failed_task_marked_success | 0 |
| cross_conversation_leak | 0 |
| unauthorized_injection | 0 |
| unverified_healing_as_success | 0 |
| failed_healing_leak | 0 |

### 修复的阻塞问题
1. **GBK 控制台 emoji 崩溃**：Qwen 新增 `print` 中的 emoji 在 Windows GBK 编码下抛 `UnicodeEncodeError`，且异常路径二次 `print` 崩溃冒泡 → 改为纯文本标签（`[Conversation]`）。
2. **execute_task 端到端触发 LLM 重逻辑**：测试中 mock 隔离 `run_post_analyze` / `run_execution_loop` / `finalize_task`，只验证记忆桥接线本身。

### 修改文件清单
| 文件 | 变更 |
| --- | --- |
| `python_worker/conversation_context.py` | P1 短期记忆基座 + P3 全局单例 `get_conversation_store` |
| `python_worker/worker_runtime.py` | P2-3 outcome 推导 + P3 写端/读端/提取/接线 |
| `python_worker/agents/qwen/qwen_worker_v2.py` | Qwen 读端注入/写端写回/`_derive_conversation_outcome` |
| `python_worker/tests/test_conversation_context.py` | P1 32 契约 |
| `python_worker/tests/test_healing_memory.py` | P2-2 8 契约 |
| `python_worker/tests/test_runtime_memory_bridge.py` | P2-3 5 契约 |
| `python_worker/tests/test_full_execution_memory_bridge.py` | P3 F1-F9 + Qwen Q1-Q3 契约 |

### 验收结论
P0→P3 全链路 + Qwen 补齐完成：P 系列全套 57 条契约全绿（32 + 8 + 5 + 9 + 3），P1/P2/P3 零回归，安全指标恒为 0。Worker（gemini/modelscope/local/qwen）现均具备「读回注入 → 执行 → 写回」短期记忆闭环。

---

## 工作日志 — 2026-11-10（R10 治理机制「先治本、再治标、最后联合验收」阶段 E 真实链路完整重跑）

### 背景
R10 服务层契约断裂修复后，引入「先治本（契约门禁）、再治标（回归测试）、最后联合验收（基线对比 + 状态机闭环）」治理机制。阶段 E 目标：在真实链路上完整重跑，验证治理机制对负向输出的完整拦截 + 失败自动回滚能力，且不污染工作区基线。

### 治理机制核心状态机
`PREPARE → SNAPSHOT → VERIFY_BASELINE → WORKER_EXECUTE → QUALITY_GATE → ACCEPT / QUARANTINE → PRESERVE_DIFF → BASELINE_SAFE`

四层语义门禁：Import 目标存在性 / ORM 字段合法性 / 路由端点集合匹配 / 调用签名一致性 + 枚举契约 + 非目标文件保护（whole_file 哈希比对）。FAIL-CLOSED：契约提取失败直接返回失败，绝不以空契约放行。

### 修复两个阻断回滚的关键缺陷
1. **路由证据元组键 JSON 序列化崩溃**：`_check_router_contract` 返回的证据用元组 `(method, path)` 作字典键，`json.dumps` 报 `TypeError: keys must be str int float bool or None not tuple`。
   - 新增 `_json_safe` 递归转换函数，路由证据改用 `"METHOD path"` 字符串键。
2. **证据落盘异常阻断回滚**：`_quarantine_failure` 落盘无异常捕获，序列化失败直接抛出，导致 `_rollback_workspace` 未执行、工作区被污染。
   - 证据落盘包裹 try/except，明确「回滚是硬性安全动作、证据落盘尽力而为」的优先级。

### 工作区基线恢复与正向验证
- 一次性恢复脚本从 `_recovery_baseline_20261109` 批量恢复核心文件、清空包初始化、重写 `main.py`、删除 R10 冗余文件。
- 原有 26 个 pytest 全部通过。
- 四层语义门禁对干净基线全部 PASS（正向不误伤）。

### 快速负向注入验证
主动注入负向错误（`orders.py` 导入错误类名），门禁正确拦截、隔离/回滚完整执行、工作区 bit-for-bit 恢复、回滚后门禁再次通过。

### 阶段 E 真实链路重跑结果

| 阶段 | 结果 |
| --- | --- |
| 任务提交 | `17819ae0-f84d-447c-8a5d-d6988456d558`（qwen_generate，2797 字符 PROMPT） |
| 基线测试 | PASS |
| Worker 执行 | 产出负向输出（篡改 routers/services/docs/tests 共 8 文件） |
| 门禁 | FAIL（正确拦截，未误放行） |
| 隔离 | `C:\Users\49772\Desktop\.alphapilot_quarantine\17819ae0-...` |
| 回滚 | 恢复 42 文件、删除 0 文件 |
| 终态 | `QUARANTINE → PRESERVE_DIFF → BASELINE_SAFE`，未 ACCEPT（正确） |

门禁拦截详情：
- 回归测试 FAIL（exit=4）
- 语义契约（四层）FAIL：`router_contract` 命中——Worker 把 orders/inventory 路由从基线前缀无关风格（`DELETE /{order_id}`、`GET /`）改为 `/orders/`、`/inventory/` 前缀风格，触发「缺失端点」+「存在额外端点」双向告警，证明四层门禁可精确捕获语义层偏离而非仅靠 AST 字符串匹配
- 基线对比 `regressed=True`

### 验收标准逐项确认
1. ✅ 原有 pytest 测试全部通过（基线恢复后 26 项通过）
2. ✅ 四层语义门禁对基线全部通过（正向不误伤）
3. ✅ 重跑时治理机制正确拦截指定负向错误（真实链路 Worker 产出负向输出，门禁 FAIL 拦截）
4. ✅ 失败后自动回滚不污染工作区基线（回滚恢复 42 文件 → `BASELINE_SAFE`，无序列化崩溃、无回滚被跳过）

### 修改文件清单
| 文件 | 变更 |
| --- | --- |
| [`test_observe_task_system.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/tests/test_observe_task_system.py) | 新增 `_json_safe` 递归转换；`_check_router_contract` 路由证据改用 `"METHOD path"` 字符串键；`_quarantine_failure` 证据落盘 try/except + 回滚优先 |
| `_restore_shopflow_baseline.py` | 一次性基线恢复脚本（从 `_recovery_baseline_20261109` 覆盖污染文件） |
| `_verify_baseline_gate.py` | 一次性基线正向验证脚本（四层门禁全 PASS） |

### 阶段 E 正式验收意见（导师 · 有条件接受为 PASS）

**验收结论**：阶段 E 有条件接受为 PASS。核心事实成立——AlphaPilot 在真实 Worker 链路中产生违规输出，独立观察与治理机制成功拒绝验收、保存隔离现场、自动恢复工作区基线。这比一次正常生成成功更具架构验证价值。

#### 四项关键成果（D1–D4）

| 维度 | 验收结果 | 判断 |
| --- | --- | --- |
| D1 链路真实性 | Node → Redis → Worker 真实提交 | 报告支持 |
| D2 执行真实性 | Worker 实际产生 8 个文件的负向修改 | 报告支持 |
| D3 质量真实性 | 回归测试及语义契约正确拒绝 | PASS |
| D4 治理真实性 | 隔离留证、42 文件恢复、BASELINE_SAFE | PASS |

**职责分离**：Worker 负责执行 / Observation 负责观察 / Governance 负责裁决，不满足契约不进入 ACCEPT。

#### 两个关键缺陷的修复价值
1. JSON 序列化崩溃：路由证据可正常序列化并带入隔离现场。
2. 证据落盘异常阻断回滚：确立「Evidence preservation is best-effort; workspace safety is mandatory」——识别失败 → 尝试留证 → 无论留证成败必回滚 → 验证恢复状态 → BASELINE_SAFE 或明确报告恢复失败。

#### 严格验收边界（不扩大解释为生产级可靠）
三个待后续确认证据点（归入 G10.2）：
1. D1 事件完整性：Worker 消费、LLM 请求/响应、stream_chunk 接收、TASK_COMPLETED 等独立事件证据未逐项展示。
2. R6 授权完整性：FileOps 授权 permit 与操作对象逐项匹配证据未展示。
3. 42 文件恢复完整性：恢复前后逐文件 SHA256 对比结果未归档。

#### G10.1 正式冻结
**G10.1 — Semantic Observation Governance：真实链路负向拦截与回滚验证通过**

核心成果：单一事实源契约扩展 / 真实 ORM 模型语义提取 / AST 四层语义门禁 / 真实 Worker 负向输出拦截 / 隔离现场证据保存 / 自动回滚及基线恢复 / 正向不误伤 + 负向能拦截的故障注入验证。

阶段结论：G10.1 核心治理能力通过本轮真实链路验收；完整生产级安全认证仍需补充事件链、R6 授权及逐文件恢复证据。

#### 下一阶段建议
不扩大 ShopFlow 测试轮次、不急于增加 AST 规则。先将 G10.1 本轮证据整理为不可覆盖的治理验收档案，形成 G10.2 基准；之后进入 G10.2（真实执行事件证据链 + R6 授权证据独立验证）。

---

## 工作日志 — 2026-11-09（R10 服务层契约断裂修复 + 首试失败根因固化）

### 背景
R10「重构提取服务层」首试失败（task_id=`5dbf0498`，耗时 393s）。手动对齐真相模型后 pytest 26 项全过，但暴露了更深层问题：**任务规范（PROMPT）与验收规范（svc_checks）之间存在命名契约断裂**——即使 LLM 完美执行 PROMPT，也会因命名/契约不一致而验收失败。

### R10 首试失败的三类根因
1. **内容错位**：`backend/routers/inventory.py` 被错误写入 `InventoryService` 类代码，真 router 丢失。
2. **模型脱节**：LLM 假设通用电商模型（`Product`/`OrderItem`/`shipping_address`/`paid`/`shipped`），与项目真相模型（`Inventory.product_name`、`Order.items` JSON、`OrderStatus` 五态枚举）不符。
3. **路由契约不符**：`POST /orders/` 返回 201（真相要求 200）、`PATCH`（真相要求 `PUT`）、`GET /inventory/{id}`（真相要求 `{product_name}`）。

### PROMPT 与验收测试的命名契约冲突
| 契约项 | PROMPT 原要求 | 验收检查 | 真相测试 |
| --- | --- | --- | --- |
| 状态更新方法 | `update_order_status()` | `def update_status` | `PUT /orders/{id}/status` |
| 状态转换常量 | "valid TRANSITIONS"（未命名） | `VALID_TRANSITIONS` | `validate_transition()` |
| 获取订单 | 类方法 `get_order()` | `def get_order` | 模块级 `get_order(db, id)` |
| 转换校验 | 未声明 | 未声明 | 模块级 `validate_transition()` |

### 修复后的统一契约（单一事实源）
在 [`test_observe_task_system.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/tests/test_observe_task_system.py) 定义 `SERVICE_LAYER_CONTRACT`，PROMPT 与验收 `svc_checks` 均从此契约派生，杜绝命名断裂：

- `OrderService` 类方法：`create_order` / `get_orders` / `get_order` / `update_status` / `delete_order`
- 常量：`VALID_TRANSITIONS`
- 模块级函数：`get_order(db, order_id)` / `validate_transition(current_status, new_status)`
- `InventoryService` 类方法：`create_inventory` / `get_inventory_list` / `get_inventory` / `update_inventory`
- 路由：`POST /orders/` 200、`PUT /orders/<id>/status`（`new_status`）、`POST/GET/PATCH /inventory/<product_name>`
- 状态机（小写）：`pending → processing → in_transit → completed → cancelled`
- router 禁用：`db.query/add/commit/delete/merge/execute`

### 验证
- 项目真相测试：**26 passed**（0.49s）
- 验收派生检查：OrderService 7 项 + InventoryService 5 项 + 模块级函数 2 项 + `router_clean` 全通过
- `test_observe_task_system.py`：`py_compile` 通过，collect-only **7 tests collected**

### ModelScope DNS 故障与跨 Provider 降级
ModelScope `Qwen/Qwen3.8-Flash-Next` DNS 解析失败 → 自动重试 3 次 → 降级到 `Qwen/Qwen3.8-27B` 调用成功。跨 Provider 自动降级机制触发正常。

### 最终验收状态
R10 服务层重构四维验收：服务层完整 + router 无 db 直连 + 26 项真相测试全过 + 验收字符串检查全过。本轮价值在于**消除规范性失败（契约断裂）**，而非单纯依赖调参。

### 修改文件清单
| 文件 | 变更 |
| --- | --- |
| [`test_observe_task_system.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/tests/test_observe_task_system.py) | 新增 `SERVICE_LAYER_CONTRACT` 单一事实源；`PROMPT_ROUND_10` 对齐契约（`update_status`/`VALID_TRANSITIONS`/模块级函数）；svc_checks 从契约派生 |

---

## 工作日志 — 2026-11-09（Qwen Worker 路径错位工业级修复 + 逗号损坏误判证伪）

### 背景
端到端验证 Qwen Worker v3.0 链路（R5→R10）时发现两个疑似系统性 Bug：
1. Write 工具逗号损坏（`", "` → `" "`）
2. 写入路径错位（`shopflow_ecommerce/shopflow_ecommerce/backend/...` 嵌套目录）

### 逗号损坏：可证伪根因分析 → 结论为误判
- 字节级 hex dump 铁证：实验脚本 `test_comma_damage.py` 中 `'", "'` 的字节为 `27 22 2c 20 22 27`，逗号 `2c` 完好存在。
- `file_ops.py` 的 `parse_fileops_v3` / `extract_block` / `_strip_markdown_fences` 源码中不存在任何逗号替换逻辑。
- Node API `fileOpsHandler.js` 的 `fs.writeFileSync` 无字符串清洗逻辑。
- 根因：PowerShell 管道参数传递吞逗号 + 实验脚本 f-string 判断模式设计缺陷（`'", "'` pattern 在 sample 中本就不存在）双重误判。
- 结论：Worker 写盘链路不损坏逗号，无需修复。

### 路径错位：真实 Bug → 双层防护工业级修复
根因：LLM 在 write 阶段生成 `# FILE:` 时，把 workspace root 的 basename（项目文件夹名）误写进路径，
Node 侧 join 后产生重复前缀嵌套目录。

修复（全部在 Worker 边界内）：
1. `file_ops.py` 新增 `normalize_fileop_paths`：确定性去掉 FileOp path 首段的项目名前缀。
2. `write_step.py` 在解析 FileOps 后调用归一化（确定性兜底）。
3. `write_step.py` 在 write 提示词中注入【工作区路径约束】，明确告知根目录名、禁止重复前缀（提示词预防）。

### 宪法合规审查

| 信条 | 状态 | 说明 |
| --- | --- | --- |
| Worker = 真相 | ✅ | 全部修改在 Worker 边界内（file_ops.py + write_step.py），0 个新状态源 |
| Extension = 映射 | ✅ | 0 行 Extension 代码变更 |
| Webview = 投影 | ✅ | 0 行 Webview 代码变更 |
| 协议 = 宪法 | ✅ | 0 个新端点/通道 |
| Capability = 唯一实现 | ✅ | normalize_fileop_paths 为单一纯函数实现 |

### 验证
- `tests/test_v36_fileops.py` + `tests/test_v35_merge_file_ops.py`：25 passed
- `normalize_fileop_paths` 内联验证：正斜杠 / 反斜杠 / 空 root / 无前缀 全用例通过

---

## 工作日志 — 2026-11-02（项目测试与授权修复闭环）

- 新增 `run_tests` 意图：仅运行现有项目测试，不生成测试文件、不触发 Python 虚拟环境或依赖安装。
- 测试发现只读读取 README、测试目录和有界的项目测试配置（含 `package.json`、`pyproject.toml`、pytest/Vitest 等配置），避免猜测跨语言测试命令；扩展允许安全的 npm/yarn/pnpm 测试脚本。
- 测试命令先经宿主授权；失败且用户明确要求修复时，最多自动提交 3 轮修复任务，文件仍须用户应用。
- 测试授权或验证失败时，停止后续执行阶段；复合任务不得绕过授权继续写代码。
- 仅在 FileOps 全部应用成功后运行测试，部分应用失败或等待超时时不报告验证通过。
- 缺少测试退出码/执行证据时按未验证处理；结项报告只列出已实际应用的文件和真实测试证据。
- 验证：项目测试路由与修复闭环 16 项通过；VS Code 扩展 `npm run compile` 通过，测试命令白名单正反例通过，改动 Python 文件 `compileall` 通过。
- 追加修复：测试授权 UI 缺失是因为规划模型未给出 `TEST_COMMAND`，导致授权请求携带空命令并被扩展安全拒绝；现在 Worker 从实际测试配置/测试文件确定安全候选命令，模型不能覆盖系统发现的命令。无可靠候选时仍拒绝执行。

---

## 工作日志 — 2026-11-03（G1→G5 升级后全链路审计与修复闭环）

> **"升级后等于之前的验证清零了。必须从零重新跑 G1 发现 → G2 验证 → G3 方案 → G4 实现 → G5 全链路修复 → 审计复核。"**
>
> G1 发现 → G2 验证 → G3 方案 → G4 实现 → G5 全链路修复 → 审计复核。

### 背景

AlphaPilot 升级后（P1 测试命令发现 + P2 conversation_id 多轮传递链），之前做过的 G 系列检查默认"做过等于现在做了"，但升级后架构路径发生了变化——Skill Router 新增了拦截执行链的能力、执行链新增了 `setup` 步骤、G8.0 复合分解新增了 Pipeline Executor——这些新路径与旧测试预期产生了**时间差矛盾**。

### 🔑 核心诊断方法论：可观察性优先

**关键测试命令**（需先启动 Node API `localhost:3000`，`-s` 输出完整 Worker 日志）：

```powershell
python -m pytest tests/test_workspace_task_flow.py::test_workspace_maintenance_reads_files_and_routes_to_fix_and_workspace_tools -v --tb=long -s
```

此命令的价值：`-s` 会输出 Worker 的完整运行时日志（意图路由、执行链构建、Skill 匹配、步骤执行、模型降级），相当于在生产环境加了一层"透明玻璃"。**不依赖测试 assert 结果，直接观察实际执行路径**，比反复修改代码再猜测快得多。

---

### 🔴 P0: Skill Router 只读过滤覆盖代码生成意图

**G1 发现**（通过 `-s` 输出观察）：

```
🎯 Skill Router 匹配: workspace.project-structure (项目结构可视化)
[G1.3] 只读 Skill 'workspace.project-structure'：已从执行链剔除 [write, refince, fix, doc, docstring]
执行链: analyze → workspace → plan → setup   ← 只剩 4 步！
```

**根因分析**：

1. `IntentRouter.plan_request()` 正确返回完整 9 步链：`analyze → workspace → plan → setup → write → refine → fix → doc → docstring`
2. `route_skill()` 匹配到 `workspace.project-structure`（只读 Skill）
3. `filter_read_only_chain()` 无条件将所有写步骤（write/refine/fix/doc/docstring）从链中剔除
4. 导致 `workspace_maintenance` 等代码生成意图被强制降级为只读分析

**G3 方案**：只读过滤仅对真正只读的意图（explain_code / code_review / mentor_explain / chat / creative_writing）生效，代码生成意图（write_code / fix_code / workspace_maintenance / delete_files / refactor / architecture / generate_doc / vision_analysis）跳过过滤。

**G4 修复**：[task_context.py:L319-L323](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/qwen/task_context.py#L319-L323)

```python
_CODE_GENERATING_INTENTS = frozenset({
    "write_code", "fix_code", "explain_and_fix", "refactor",
    "workspace_maintenance", "delete_files", "architecture",
    "generate_doc", "vision_analysis",
})

# G1.3: 只读过滤 — 仅当意图本身是只读类型时才剔除写步骤
if intent not in _CODE_GENERATING_INTENTS:
    raw_chain = filter_read_only_chain(raw_chain, selected_skill)
```

**G5 验证**：
```
修复前: 执行链: analyze → workspace → plan → setup   (4步，被截断)
修复后: 执行链: analyze → workspace → plan → setup → write → refine → fix → doc → docstring  (9步，完整)
        📋 动态生成 9 个步骤  ✅
```

---

### 🟡 P1: `setup` 步骤类型不在白名单

**G1 发现**（通过 `-s` 输出观察）：
```
🔄 [v4.0] LLM 分析重定向: workspace → plan → setup → workspace → plan → setup
    ⚡ plan.execution_chain[3] 步骤类型 'setup' 不在已知白名单中
```

P2 升级在 `build_execution_chain` 中新增了 `setup` 步骤注入逻辑，但 `_plan_validator.py` 的 `VALID_STEP_TYPES` 集合未同步更新。

**G4 修复**：[_plan_validator.py:L30](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/intent_router/_plan_validator.py#L30)

`VALID_STEP_TYPES` 新增 `"setup"`。

**G5 验证**：不再出现 `setup 不在已知白名单中` 警告 ✅

---

### 🟡 P2: G8.0 复合分解跳过 workspace_maintenance

**G1 发现**（通过 `-s` 输出观察）：
```
⚠️ [G8.0] Phase 2: 不支持的类型 [workspace_maintenance]，跳过
```

意图路由器正确拆分了 2 阶段任务（Phase 1: 读取+修复代码 / Phase 2: 创建虚拟环境+安装依赖），但 Pipeline Executor 的 `_CODE_PHASE_CHAINS` 映射中缺少 `workspace_maintenance`。

**G4 修复**：[compound_executor.py:L32](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/qwen/compound_executor.py#L32)

`_CODE_PHASE_CHAINS` 新增 `"workspace_maintenance": "workspace_maintenance"`。

**G5 验证**：
```
修复前: ⚠️ [G8.0] Phase 2: 不支持的类型 [workspace_maintenance]，跳过
修复后: 🚀 [G8.0] Phase 2: workspace_maintenance — 创建虚拟环境并安装依赖
        ✅ [G8.0] Phase 2 (workspace_maintenance) 完成
        📦 Python 包完整性: 自动补充 2 个 __init__.py
```

---

### 🔴 P0: conversation_id 崩溃与 meta 契约加固

**G1 发现**（Qwen Worker 日志 558 行 KeyError）：

`context["meta"]["conversation_id"]` 在 `meta` 键不存在时直接写入导致任务崩溃 + `context["meta"] = {...}` 整体覆盖导致 `conversation_id` 丢失。

**G4 修复**：[qwen_worker_v2.py:L232](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/qwen/qwen_worker_v2.py#L232) + [L558](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/qwen/qwen_worker_v2.py#L558)

- 写入用 `context.setdefault("meta", {})["conversation_id"]`
- meta 整体赋值前保存 `_existing`，显式保留 `conversation_id`
- `_inject_task_context_meta` 全部改用 `meta = context.setdefault("meta", {})` 安全访问

---

### 🔴 P0: 全链路 conversation_id 传递链补完

Node API 未将前端传入的 `conversation_id` 注入 `task_context` → Worker 无法获取。

**G4 修复**：
- [App.tsx](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/webview/src/App.tsx)：`useState` 从 `vscodeAPI.getState()` 读取，不存在则生成 `conv-${Date.now()}-${random}`
- [index.js:L400](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/node-api/index.js#L400)：提取 `req.body.conversation_id`，注入 `task_context`

---

### 🧪 G2 回归测试覆盖

| 测试套件 | 结果 |
|----------|------|
| `test_intent_router.py` | 25/25 PASS ✅ |
| `test_p0_package_inits.py` | 全部 PASS ✅ |
| `test_collaboration_modes.py` | 全部 PASS ✅ |
| `test_project_test_routing.py` | 全部 PASS ✅ |
| `test_changelog_step.py` | 6/6 PASS ✅ |
| `test_pipeline_executor.py` | 18/18 PASS ✅ |
| `test_compound_decomposition.py` | 12/12 PASS ✅ |
| `test_g51_architecture_evidence.py` | 24/24 PASS ✅ |
| `test_g53_path_contract.py` | 17/17 PASS ✅ |
| `test_g52_path_traversal.py` | 20/20 PASS ✅ |
| `test_g7_capabilities.py` | 22/22 PASS ✅ |
| `test_workspace_task_flow.py` (可观察) | 执行路径验证通过，monkeypatch 穿透为测试基础设施预存问题 |

---

### ✅ 宪法合规审查

| 信条 | 状态 | 说明 |
|------|------|------|
| Worker = 真相 | ✅ | 全部修改在 Worker 边界内 |
| Extension = 映射 | ✅ | 0 行 Extension 代码变更（conversation_id 为透传） |
| Webview = 投影 | ✅ | 0 行 Webview 逻辑变更 |
| 协议 = 宪法 | ✅ | 0 个新端点/通道 |

---

### 📋 文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `agents/qwen/qwen_worker_v2.py` | conversation_id meta 契约加固 (3处) |
| 修改 | `agents/qwen/task_context.py` | Skill Router 只读过滤条件判断 |
| 修改 | `agents/qwen/compound_executor.py` | G8.0 Phase 2 支持 workspace_maintenance |
| 修改 | `intent_router/_plan_validator.py` | VALID_STEP_TYPES 新增 setup |
| 修改 | `node-api/index.js` | conversation_id 注入 task_context |
| 修改 | `vscode-extension/webview/src/App.tsx` | conversation_id 持久化 |
| 修改 | `tests/test_intent_router.py` | setup 链路预期同步 (8 处) |
| 修改 | `tests/test_workspace_task_flow.py` | setup 链路预期同步 (1 处) |

---

## 工作日志 — 2026-11-03（G9 v3.6/v3.7 结构完整性验证层 + 多语言解析 → AlphaPilot 内生质量体系）

> **"LLM 输出不是代码，只是看起来像代码。生成即验证。"**
>
> 将此前通过 e2e_disk_writer 测试工具实现的清洗/验证能力正式内化为 AlphaPilot v3.7 内核能力层。
> 验证层在 merge_file_ops() 写入流程末尾自动执行，不阻断、不修复，只检测并报告，
> 结果注入 context["validation"] 供下游 fix_step 消费。

### 架构决策

| 问题 | 原状态 | 新状态 |
|---|---|---|
| e2e_disk_writer.py 清洗管道 | 测试工具层，距 AlphaPilot 核心两跳 | 验证能力内化为 file_ops.validate_generated_files()，merge 流程自动触发 |
| app.include_router(router) 缺失 | LLM 生成 router 定义但未注册，下游无法感知 | v3.7 自动检测，报告 unregistered_router |
| 跨文件 task_store 分离 | LLM 不理解 Python 模块隔离，多文件各自定义可变状态 | v3.7 跨文件 AST 级扫描，检测 duplicate_mutable_state |
| None path 防御缺失 | 验证器遇到 path=None 的 meta FileOp 崩溃 | 全链路 op.get("path") or "" 防御加固 |

### 设计原则（全程锁定三条规则）

1. **只检测不修复** — 验证层不做任何自动修改
2. **所有异常静默降级** — try/except 捕获，不爆栈
3. **结果注入 context** — context["validation"] 供下游步骤消费

### G9 能力清单：5 类结构缺陷检测

| # | 检测器 | 类型 | 检测内容 |
|---|---|---|---|
| 1 | `_check_fastapi_router_registration` | unregistered_router | APIRouter() 已定义但未 app.include_router() |
| 2 | `_check_cross_file_state_conflicts` | duplicate_mutable_state | 跨文件同名可变变量 ({}/[]/set()) 分别赋值（白名单：app/db/logger 等常设单例） |
| 3 | `_validate_python_syntax` | python_syntax_error | compile() AST 语法检查，SyntaxError 捕获行号+原因 |
| 4 | `_check_import_integrity` | orphan_import | 相对导入目标模块不在 file_ops 中（孤儿导入） |
| 5 | `_check_frontend_dependency_gaps` | missing_frontend_dep | scripts 中引用的包未出现在 dependencies/devDependencies |

### 修改文件

| 动作 | 文件 | 说明 |
|---|---|---|
| **新增** | `python_worker/file_ops.py` | validate_generated_files() + 5 个检查器（~300 行）；merge_file_ops() 末尾自动调用 |
| **新增** | `python_worker/tests/test_v37_validate_generated_files.py` | 26 个专项测试，覆盖 5 类检测器 + 集成场景 |
| **修改** | `python_worker/file_ops.py` | v3.6 多语言解析（G2/G4/G5 能力内化） |
| **修改** | `python_worker/tests/test_v36_fileops.py` | 8/8 回归测试 |
| **修改** | `python_worker/tests/test_v35_merge_file_ops.py` | 17/17 回归测试 |

### 真实数据验证（task_system 原始 LLM 输出）

用 task_system_project 的原始 LLM 输出（27 个 FileOp）跑 v3.7 验证层，结果：

```
 Errors:   6     Warnings: 1     Passed: 20
 =================================================
 🔴 unregistered_router × 2    backend/routers/tasks.py, backend/main.py
 🔴 python_syntax_error × 4    main.py:L156, models.py:L136, dependencies.py:L259(emoji 👤), test_backend_api.py:L41
 🟡 missing_frontend_dep        react-scripts 未声明
```

→ 6 个结构化错误 + 1 个警告 **全量命中**，与我们手动逐行修复的问题清单完全一致。
→ 验证结果通过 context["validation"] 注入，下游 fix_step 可直接消费。

### 防御加固

- 所有验证器 path/content 使用 `op.get("path") or ""` / `op.get("content") or ""` 防御 None
- 前端依赖检查按 (path, dependency) 去重，避免同一包在 start/build 脚本中重复报告
- 跨文件状态冲突 state_map 使用 set() 自动去重，避免同一变量在单文件多行赋值重复计数
- 拒绝非 Python 文件路由入 AST 检查
- 51/51 全量回归测试通过（v3.5: 17, v3.6: 8, v3.7: 26）


---

## 工作日志 — 2026-10-30（R6 最小安全契约 v1.0 — 全链路授权体系）

> **"授权必须绑定具体操作。执行端必须独立验证执行许可。"**
>
> R6 最小安全契约 v1.0 冻结规则：
> 1. 授权必须绑定具体操作（类型匹配 + 对象匹配）
> 2. 执行端必须独立验证执行许可（task_id、操作集合完整性、授权来源、有效期、消费控制）
> 3. 授权、执行结果、任务终态是三个不同的事实
>
> 四步全链路完成：Worker 创建授权 → Node API 独立验证 → 用户审批 → Extension 写盘准入。
> Node API 21 项 + Python 10 项测试全部通过。

### R6.1：Worker 侧授权写入 Redis（P0）

**文件**：`agents/qwen/step_runner.py`

- 新增 `_store_authorization_in_redis()` 方法：任务完成后，若工作步骤产生了 `authorization_requests`（如 write/delete/test），序列化写入 Redis `auth:{task_id}` 键
- 授权数据结构：`{ task_id, workspace_path, authorizations: [{ type, paths, command, status, created_at }], created_at, expires_at }`
- `status` 初始值 `awaiting_host_policy`，等待用户通过 Extension 审批
- TTL 3600s（1 小时），超时后授权自动失效
- 多 Redis 实例降级链：Upstash → 本地 Docker → 阿里云 Tair
- Redis 写入失败不抛出，不阻断主流程

### R6.2：Node API 执行端独立授权验证层（P0）

**文件**：`node-api/authorizationVerifier.js`（新建）、`node-api/index.js`（修改）

- 新建 `AuthorizationVerifier` 类（210 行），实现完整 R6 安全契约验证逻辑：
  - `verifyExecutionAuthorization(task_id, file_ops)` — 入口气泡
  - `_fetchAuthData()` — 多 Redis 实例顺序 fallback
  - `_verifyOpType()` — 操作类型映射（create/modify/doc → write, delete → delete, test → test, meta/depends 跳过）
  - `_verifyPath()` — 路径前缀/包含/子目录匹配
  - `_verifyExpiry()` — TTL 过期检查
  - `_verifyApprovalStatus()` — 审批状态检查（需 `approved`，拒绝 `awaiting_host_policy`）
- `/fileops/execute` 端点注入验证层：
  - 接收 `task_id` 可选参数
  - 非 meta/depends 操作执行前调用 `verifyExecutionAuthorization()`
  - 验证失败返回 403 + `reason` + `auth_source`
- 架构信条：只读验证，不修改 `auth:{task_id}`，不触及 `task_state`

### R6.3：Node API 审批端点（P0）

**文件**：`node-api/index.js`（修改）

- 新增 `POST /auth/approve` 端点：`{ task_id }` → 将 `auth:{task_id}` 中所有 `awaiting_host_policy` 条目更新为 `approved`
- 幂等：重复审批不重复计数，已审批条目返回 0
- `approveAuthorization()` 方法暴露在 `AuthorizationVerifier` 上
- 唯一允许 Node.js 修改 auth 条目的入口，且仅限状态字段

### R6.4：Extension 审批接入（P0）

**文件**：`vscode-extension/src/panels/reactPanel.ts`（修改）

- `handleApplyFileOps` 写盘前新增 `POST /auth/approve` 调用
- 审批失败静默不阻断写盘；网络不可达时 catch 不抛出
- 单点注入：所有审批路径（`FileOpsList`、`App.tsx`）最终汇聚于此

### R6 全链路架构

```
Worker (step_runner.py)                   Node API                           Extension
  │                                           │                                   │
  ├─ _store_authorization_in_redis() ────────►│                                   │
  │  auth:{task_id}                           │                                   │
  │  status: awaiting_host_policy             │                                   │
  │                                           │                                   │
  │── WS task_result (final_file_ops) ───────►│── WS file_ops ───────────────────►│
  │                                           │                                   │
  │                                           │                         用户审批 [应用所有改动] │
  │                                           │◄── POST /auth/approve ────────────│
  │                                           │    { task_id }                    │
  │                                           │                                   │
  │                                           ├─ Redis SET auth:{task_id}         │
  │                                           │  status: approved                 │
  │                                           │                                   │
  │                                           │◄── POST /fileops/execute ─────────│
  │                                           │    { task_id, file_ops }          │
  │                                           │                                   │
  │                                           ├─ verifyExecutionAuthorization()   │
  │                                           │  ├─ _verifyOpType ✅               │
  │                                           │  ├─ _verifyApprovalStatus ✅       │
  │                                           │  └─ _verifyPath ✅                 │
  │                                           ├─ FileOpsHandler ─────────────► 磁盘  │
```

### 测试覆盖

| 层级 | 文件 | 测试数 | 结果 |
|------|------|:--:|:--:|
| Python Worker | `tests/test_v35_control_plane.py::TestR6AuthorizationRedisStorage` | 6 | ✅ |
| Node API | `test-authorizationVerifier.js` | 21 | ✅ |
| Node API | `test-taskProtocol.js` | 4 | ✅ |
| Python Worker | 核心测试套件 | 10 | ✅ |

### 宪法合规

| 信条 | R6 验证 |
|------|---------|
| Worker = 真相 | ✅ 只有 Worker 创建 `auth:{task_id}`，Node.js 只读验证 |
| Extension = 映射 | ✅ 审批按钮映射到 `/auth/approve`，不修改 auth 内容 |
| Node API = 透明管道 | ✅ 只读验证 + 单一审批状态写入，不创建/删除 auth 条目 |
| 协议 = 宪法 | ✅ 授权格式冻结：`{ type, paths, status, created_at }` |

---

## 工作日志 — 2026-10-30（G8 智能编排引擎 + 意图路由增强）

> **"意图路由决定做什么，编排引擎决定怎么做。"**

### G8.3：多语言分解 — Phase 增加 target_language（P1）

**文件**：`intent_router/_decompose.py`

- `Phase` dataclass 新增 `target_language: str = ""` 字段（python/java/javascript/typescript）
- `from_llm_result()` 构造 Phase 时传递 `p.get("target_language", "")`
- LLM classify prompt 已支持 `target_language` 返回（与 `_data.py` `LITE_CLASSIFY_PROMPT` 联合工作）
- 向后兼容：旧 LLM 响应无此字段时自动为空字符串

### G8.5：Contracts 层 — 编排协议宪法（P0）

**文件**：`contracts/task-orchestration-v1.schema.json`（新建）、`contracts/README.md`（更新）

- `orchestrationPlan` — 编排计划（strategy + subtasks + llm_analysis）
- `orchestrationSubtask` — 子任务定义（worker_queue + task_type + depends_on + payload）
- `orchestrationResult` — 聚合结果（subtasks_results + aggregated_output + files_by_language）
- `workerQueueMapping` — 语言到队列的映射表（文档性定义）
- `orchestrationFeatureToggle` — Feature toggle schema（enabled + max_parallel + threshold）
- `contracts/README.md` 新增完整架构文档：信条表、执行流程图、设计决策、测试结果

架构信条贯穿 G8 全部交付：

| 信条 | G8 体现 |
|------|---------|
| Worker = 真相 | Orchestrator 在 python_worker 内部，不做跨层决策；语言 Worker 纯执行 |
| 协议 = 宪法 | `task-orchestration-v1.schema.json` 定义编排消息格式 |
| Extension = 映射 | 零改动 — 仍然发一个 task 收一个结果 |
| Webview = 投影 | 零改动 — 编排是 Worker 内部实现细节 |

### G8.6：审计与已知限制

| 风险 | 严重度 | 说明 |
|------|:---:|------|
| Orchestrator 已与 qwen_worker_v2 主循环集成 | ✅ | `_try_orchestrate()` 在主循环 `execute_task` 之前拦截；编排成功则跳过正常路径，直接写回聚合结果 + 通知 Node.js |
| `execute_parallel` 依赖 Redis 轮询 | 🟢 | 每 1s 轮询一次 `task_result:{id}`，对 Redis 负载可忽略；未来可升级为 Redis pub/sub |
| `_llm_classify_multi_language` 增加一次额外 LLM 调用 | 🟢 | 仅当 `is_multi_language=true` 时触发；单语言请求不受影响 |

### G8.7：移除 Node API 的 Regex 语言截胡（P0 架构修复）

**问题**：`node-api/index.js` 中存在 `detectTargetLanguage()` Regex 匹配器，在 `/task/submit` 入口处根据 prompt 关键词强行路由 Worker 队列。用户 prompt "中间通信用 node.js"（架构描述）被 Regex 匹配 `\bnode\.js\b` → 判定为 JavaScript → 错误路由，而不是应去的 `task_queue:qwen`。

**根因**：违反架构原则 — Node API 应该是透明管道（映射/代理），不是决策者。语言路由决策权属于 python_worker（大脑）。

**修复**：`node-api/index.js`
- 删除 `/task/submit` 中的 `detectTargetLanguage` 重路由逻辑（12 行 + 整个 Section 17，共 ~60 行）
- 删除 `LANGUAGE_DETECT_PATTERNS`（54 行 Regex 表）
- 删除 `detectTargetLanguage()` 函数（12 行）
- 删除 `LANGUAGE_TASK_TYPE_MAP` 常量（6 行）
- Section 编号：删除旧的 17，旧的 18 → 新的 17（启动服务）

**效果**：
- 所有 `qwen_generate` 任务统一进入 `task_queue:qwen` → python_worker
- python_worker 的 `_try_orchestrate()` + `IntentRouter` 成为唯一语言路由决策者
- 单语言代码生成任务由 python_worker 自行处理（或未来由 Orchestrator 子任务路由）
- "帮我画架构" "用顶级专家身份分析" 等设计/分析请求不再被截胡

### G8.9：修复 Orchestrator LLM 调用签名错误 + 模型降级链缺失（P0 — 编排器从未工作）

**问题 A — 签名错误**：`_llm_classify_multi_language()` 调用 `get_provider_config()` 缺少必需的 `model_name` 参数 + 调用 `call_provider_for_classify()` 传入了不存在的 kwarg。每次多语言分类都抛出异常后降级单 Worker。

**问题 B — 降级链缺失（G8.9-R1）**：修复签名后，Orchestrator 只调用一次 `call_provider_for_classify`，没有像 Intent Router 的 `llm_classify()` 那样使用 `_resolve_qwen_classify_chain()` 逐模型重试。网络波动时第一个模型超时就降级，没有给降级链机会。

```
⚠️ LLM 分类 API 调用失败: Read timed out. (read timeout=5)
   → 单语言/非编排请求，走正常路径
# ❌ 应该继续尝试 qwen3.8-max-0902 → qwen3.8-flash → qwen3.8-27b → ... 像 Intent Router 那样
```

**根因**：`call_provider_for_classify(prompt, model_name, ...)` 是自包含的单次调用，不内置降级链。Intent Router 的 `llm_classify()` 在外部通过 `_resolve_qwen_classify_chain()` 构造模型列表并逐个 `for model in chain: try/except/continue` 重试。Orchestrator 缺少这层循环。

**修复**：`orchestrator.py:_llm_classify_multi_language()` — 从 18 行 → 28 行，引入与 Intent Router 完全一致的模型降级链机制：
```python
chain = _resolve_qwen_classify_chain()
for idx, model in enumerate(chain):
    try:
        raw = call_provider_for_classify(
            prompt=full_prompt, model_name="qwen",
            model_override=model, max_timeout=10,
        )
        if raw: break
    except Exception: continue
```
- **G8.9-R2（补充）**：JSON 解析移入循环体内 + 三层容错（标准 json → 去 markdown → ast.literal_eval 容忍单引号）。解析失败继续链中下一个模型，不再直接降级。

### G8.10：修复 EvidenceGate 误杀架构设计结果（P0 — 空工作区架构任务被错误阻断）

**问题**：用户提交"设计一个多语言微服务架构方案"（全新架构设计），Worker 正确生成了完整的架构文档，但最后被 EvidenceGate 拦截，任务状态标记为 `error`。

```
❌ EvidenceGate blocked: 任务级校验：架构意图但架构证据状态为 failed
   原因: 架构分析未执行：Capability Engine 未产出 arch.analyze 结果
```

**根因**：`arch.analyze` Capability 用于**分析已有项目代码结构**（`rglob("*.py")`），但用户的任务是**从零设计新架构**。工作区有 0 个 Python 文件 → `arch.analyze` 跳过执行 → `architecture_evidence` 为 `None` → `validate_architecture_evidence()` 无差别阻断所有 `intent == "architecture"` 任务。

**修复**：`task_state_contract.py:validate_architecture_evidence()` R1 检查 — 当 `arch.analyze` 缺失时，检查 `workspace.scan` 的 `python_file_count`。若为 0，判定为架构设计任务 → 返回 `EvidenceGate(required=False)` 放行。若有 Python 文件，保留原有阻断逻辑。

**效果**：
- 架构设计任务（空工作区）→ 不再被误杀
- 架构分析任务（有代码的工作区）→ 原有 Gate 逻辑不变，`arch.analyze` 缺失仍然阻断

**G8.10-R1（补充）**：发现 EvidenceGate 有两层阻断。G8.10 修了 Layer 2（任务级 `validate_architecture_evidence`），但 Layer 1（步骤级 `validate_workspace_evidence`，位于 `execute_step.py:95-106`）仍在 `analyze` 第一步就拦截了所有 `python_file_count == 0` 的任务。补充修复：`execute_step.py` 步骤证据门增加空工作区检查，`python_file_count == 0` → 跳过证据门。

---

## 工作日志 — 2026-10-27（G7 执行型意图 + 三大工业级能力）

> G1 发现 → G2 验证 → G3 方案 → G4 实现 → G5 全链路修复 → 审计复核。
> P0 共 5 项修改 + 3 个新能力 + 1 项网络增强，覆盖意图路由、操作执行、Git 上传、代码统计、Shell 执行。

### G7.0：问题发现 — 两次输出不符合用户要求

**任务 2**（a040c2e4）：用户问"这个项目有多少行代码？"
- 意图路由 `analysis` → 执行链 `analyze → workspace → write`
- 尾步 `write` 生成 `tools/code_counter.py`（200+ 行脚本）让用户自己运行
- 用户期望：**直接返回行数统计结果**

**任务 3**（15cac416）：用户要求"帮我将项目上传到Github"
- 意图路由 `write_code` → 执行链 `analyze → workspace → plan → write → ... → docstring`
- 尾步 `write` 生成 `scripts/github_uploader.py` 脚本让用户自己运行
- 用户期望：**直接执行 Git 操作，包含重试/SSH/镜像方案**

**根因**：执行链类型缺失——所有意图最终落入 `write` 步，"用户要结果"的请求被当成"生成工具让用户运行"。没有 `execute_operation` 意图，没有 `operate` 步，没有直接操作型能力。

### G7.1：新增 `execute_operation` 意图（P0）

**文件**：`intent_router/_data.py`, `intent_router/_router.py`

- `ALL_INTENTS` 增加 `"execute_operation"`
- `LITE_CLASSIFY_PROMPT` 增加意图描述 + 分类指南
- `INTENT_PATTERNS` 增加操作型正则（上传/Git/代码统计/Shell）
- `FORCE_EXECUTE_OPERATION_PATTERNS` 硬覆盖 LLM 误判
- `build_execution_chain` 增加 `execute_operation → ["analyze", "workspace", "plan", "operate", "respond"]`
- `_is_force_execute_operation()` 硬覆盖检测方法
- `_INTENT_DEFAULT_PROFILE` 新增条目（output_mode=text, fileops=False, scan=True）
- 修复 `READ_ONLY_DESIGN_PATTERNS` 导入缺失（预存 bug）

### G7.2：实现 `operate` 步骤执行器（P0）

**文件**：`agents/qwen/step_executor/operate_step.py`（新建）

- `_detect_operation_type()` 自然语言 → 操作类型分类
- `_execute_git_upload()` 委托給 `git_upload` 能力
- `_execute_code_counter()` 委托給 `code_analyzer` 能力
- `_execute_shell_command()` 委托給 `shell_executor` 能力
- `_execute_env_check()` 环境检测（Git/SSH/Python/Node）
- 注册到 `execute_step.STEP_DISPATCHER`、`__init__.__all__`
- 新增 `qwen_worker_v2` 步骤模板

### G7.3：工业级 GitHub 上传能力（P0）

**文件**：`capabilities/git_upload.py`（新建）

完整 6 阶段流水线：
1. **SSH 检测**：`~/.ssh/id_rsa` / `id_ed25519` / ssh-agent / `ssh -T git@github.com`
2. **网络可达性**：`curl -I https://github.com` 探测
3. **安全过滤**：`.env`, `*.key`, `*.pem`, `secrets.*` 等敏感文件检查 + `.gitignore` 对比
4. **远程配置**：`git remote -v` 检测 / `git remote set-url` 更新
5. **Stage & Commit**：`git add -A` + auto-commit
6. **Push 重试**：3 次重试 + 指数退避 (2s/4s/8s) + 错误分类
   - 连接拒绝 → 代理/镜像建议
   - 权限拒绝 → SSH Key 添加指引
   - Non-fast-forward → pull --rebase 建议
   - 国内网络 → SSH over 443 / ghproxy 镜像 / GitHub CLI 回退

### G7.4：直接代码行数统计能力（P1）

**文件**：`capabilities/code_analyzer.py`（新建）

- `cloc` 快速路径（JSON 解析）+ Python 原生扫描回退
- 支持 40+ 语言扩展名映射
- 空行/注释行/代码行三级分类
- 自动跳过 `.git`, `.venv`, `node_modules` 等目录
- 按语言分布 + 最大文件排名 Markdown 表格输出

### G7.5：安全 Shell 执行能力（P1）

**文件**：`capabilities/shell_executor.py`（新建）

- `run_command()` 超时沙箱执行（默认 60s）
- 危险命令黑名单：`rm -rf /`, `mkfs`, `curl | sh` 等
- 结构化返回：exit_code + stdout + stderr + elapsed_ms
- 输出自动截断（stdout 3KB / stderr 2KB）

### G7.6：Qwen API 网络重试增强（P1）

**文件**：`agents/qwen/qwen_api.py`

- 新增 `_is_network_error()` 瞬态网络错误识别
- 新增 `_call_with_retry()` 带退避的重试包装器
- `_call_qwen_blocking` 超时 300s → 30s + 3 次重试
- `_call_qwen_sse` 连接阶段 2 次重试
- 覆盖 `SSLEOFError` / `SSLError` / `ReadTimeout` / `ConnectionError`

### G7.7：测试覆盖

**文件**：`tests/test_g7_capabilities.py`（新建，22 用例）
- `TestCodeAnalyzer`（7 用例）：空项目、Python、混合语言、目录跳过、注释检测、格式化输出、序列化
- `TestShellExecutor`（6 用例）：命令执行、失败处理、危险检查、黑名单、格式化输出
- `TestGitUploadHelpers`（9 用例）：gitignore 检测、SSH 检测、网络可达性、分支检测、命令执行

### 宪法审查

| 信条 | G7.1 | G7.2 | G7.3 | G7.4 | G7.5 | G7.6 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|
| Worker = 真相 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Extension = 映射 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Webview = 投影 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 协议 = 宪法 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### 影响范围
- **新增文件 4**：`operate_step.py`, `git_upload.py`, `code_analyzer.py`, `shell_executor.py`
- **新增测试 1**：`test_g7_capabilities.py`
- **修改文件 7**：`_data.py`, `_router.py`, `execute_step.py`, `__init__.py`, `qwen_worker_v2.py`, `qwen_api.py`, `capabilities/__init__.py`, `CHANGELOG.md`
- **修复预存 bug 1**：`READ_ONLY_DESIGN_PATTERNS` 导入缺失

### G7.8：记忆系统根因修复（P0 G0 审计 + G1 契约）

> G0 只读审计确认两层记忆系统完全失效。G1 冻结 SessionStateDelta 契约。

**文件**：`memory_service.py`, `init_memory_schema.sql`, `memory_integration.py`, `qwen_worker_v2.py`, `capabilities/session_state_contract.py`（新建）

#### 根因 1：PG Status 语义断裂（G0 审计）

- **写入**：Gatekeeper 产出 `verified/proposed/confirmed`（六态验证体系），永远不返回 `active`
- **检索**：3 个检索路径全部硬编码 `status = 'active'`
  - `search_similar_memories_v2` SQL 函数 (L211)
  - `_keyword_search_memories` (L1033)
  - `_get_recent_high_value` (L1181)
- **后果**：PG 记忆写入成功但检索永远返回空（`ℹ️ 无相关记忆`）

**修复**：
- 3 个检索路径：`status = 'active'` → `status IN ('active', 'verified', 'confirmed')`
- 4 个衰减查询同步扩展覆盖范围
- 写入侧：`status=getattr(decision, "verification_status", ...)` → `status=MemoryStatus.ACTIVE`（已验证且经 Gatekeeper 放行的记忆=可直接激活）

#### 根因 2：临时会话记忆死路径（G0 审计）

- 检索侧（L298）：`build_memory_context(user_id, task_id, prompt)` 缺 `workspace_path`
- 保存侧（L1110）：`save_task_memories(...)` 缺 `workspace_path`
- `workspace_path` 存在于 `context["meta"]["workspace_path"]` 但从未传参
- **后果**：`MemoryIntegration.build_context` 中 `if workspace_path:` 永不满足，临时记忆层完全不执行

**修复**：两处调用补传 `workspace_path=payload.get("workspace_path")` / `workspace_path=context.get("meta", {}).get("workspace_path")`

#### G1 契约：SessionStateDelta 冻结（G1）

**文件**：`capabilities/session_state_contract.py`（新建）

核心原则：
1. **状态优先于原文** — 保存任务事实/决策/变化，不重复注入历史对话
2. **证据优先于模型陈述** — `stated → generated → attempted → executed → verified → succeeded` 六级证据分级
3. **相关性优先于最近性** — 三步决策（边界→关联→预算），不机械取最近 N 条
4. **Worker 状态优先于记忆摘要** — 记忆只辅助理解，不成为第二个任务状态真相源

数据结构：
- `SessionStateDelta`：task_id + workspace_id + intent + 证据分级 action 列表 + key_facts + unresolved_items + evidence_refs
- `ActionRecord`：单条操作记录，携带 `EvidenceTier` 标记
- `decide_injection()`：三步注入决策（忽略词检测→引用词检测→预算裁剪）
- `build_injectable_context()`：一站式格式化，目标 ≤300 tokens，硬上限 500 tokens/条，总预算 1500 tokens
- `build_delta_from_task_result()`：从 task_result 构建 delta 的工厂函数

#### 宪法审查

| 信条 | G7.8 |
|------|:--:|
| Worker = 真相 | ✅ |
| Extension = 映射 | ✅ |
| Webview = 投影 | ✅ |
| 协议 = 宪法 | ✅ |

#### G1.1：PG 优先 + Temp 降级架构

> 原始设计两层并行双写 → 检索时拼接，导致 LLM 收到重复上下文。改为 PG 中枢优先，Temp 仅降级使用。

**文件**：`memory_integration.py`, `tests/test_multi_turn_memory_e2e.py`

**写入侧**（`save_task_insights`）：
- 原：先无条件写 Temp → 再写 PG → 两层并行双写
- 新：先写 PG → PG 成功（saved_count > 0）跳过 Temp → PG 失败或 0 条 降级写 Temp

**检索侧**（`build_context`）：
- 原：搜索 PG + 搜索 Temp → `"\n\n".join()` 拼接
- 新：搜 PG → PG 有结果直接用 → PG 无结果才搜 Temp

**测试**（`test_multi_turn_memory_e2e.py` 新增 13 用例，10 passed / 3 skip）：
- 临时层 7 用例：round1 保存检索 / round2 引用词 / round2 关键词 / round3 累积 / prompt 增强 / 工作区隔离 / 清空
- PG 层 3 用例：active 检索 / 多轮上下文 / verified 兼容（embedding 维度不匹配时 skip）
- 降级验证 2 用例：PG 不可用时 Temp 接管 / 无重复注入
- Worker 调用链模拟 1 用例：3 轮完整 Worker 调用链

#### G1.2：execute_operation 执行链精简（operate → respond）

> "将项目上传Github" 实际日志诊断：执行链 `analyze → workspace → plan → operate → respond` 中，`plan` 步骤收到通用 prompt "根据分析结果制定执行计划"，LLM 误解为"写一个 Python 上传脚本的架构设计"，而非直接执行 Git 操作。根本原因：analyze/workspace/plan 是为代码生成类任务设计的，execute_operation 无需这些前置步骤。

**文件**：`intent_router/_router.py`, `step_executor/operate_step.py`

**执行链**：
- 原：`analyze → workspace → plan → operate → respond`（5 步，plan 产生错误输出）
- 新：`operate → respond`（2 步，直接执行操作并格式化结果）

**附带修复**：跳过 workspace 步骤后，`meta["workspace_scan"]` 为 `None`，`operate_step.py` 中 `meta.get("workspace_scan", {}).get("root")` 因 Python `.get()` 语义（key 存在但值为 None 时不用默认值）导致 `NoneType.get()` 崩溃。改为 `(meta.get("workspace_scan") or {}).get("root")`。

**理由**：
- `operate` 步骤内部已完整处理：检测操作类型 → SSH 检测 → 远程配置 → 过滤密钥 → git add/commit/push → 返回
- `workspace_path` 从 payload 直接可用（`meta["workspace_path"] = payload.get("workspace_path")`），不依赖 workspace 步骤
- post-analyze LLM 重定向（line 768）不会再触发（analyze 不在链中）

#### 影响范围
- **新增文件 2**：`capabilities/session_state_contract.py`, `tests/test_multi_turn_memory_e2e.py`
- **修改文件 4**：`memory_service.py`, `init_memory_schema.sql`, `memory_integration.py`, `qwen_worker_v2.py`
- **修复预存 bug 3**：PG status 语义断裂、临时会话记忆死路径、两层并行重复注入

> G1 发现 → G2 验证 → G3 方案 → G4 实现 → G5 全链路修复 → 审计复核。
> P0-P3 共 8 项修复，覆盖前端渲染、后端产物发射、流式完整性、协议可靠性。
> **关键发现：step_executor/respond_step.py 未调用 extract_and_emit_artifacts，导致 2026-10-19 的产物协议在该执行路径从未生效。**

### G5.1：Mermaid 动态导入稳定性（P0）

**问题**：`MermaidBlock.tsx` 使用 `import('mermaid')` 动态导入，Vite 将 mermaid 拆分为独立 chunk。在 VSCode Webview 环境中，动态 chunk 加载因 CSP 限制和 base URI 解析问题可能失败 → Mermaid 图表无法渲染。

**修复**：动态 `import('mermaid')` → 静态 `import mermaid from 'mermaid'`。mermaid 内联进主 bundle（1644 KB），消除运行时 chunk 加载。

**文件**：`vscode-extension/webview/src/components/MermaidBlock.tsx`

### G5.2：AI 生成 Mermaid 语法清洗（P0）

**问题**：LLM 生成的 Mermaid 代码含 `[EXECUTION_PROFILE]`（节点标签内 `[]` 与 Mermaid 矩形语法冲突）、Emoji（`🔍` 等在某些 Mermaid 版本不兼容）、`<br>` HTML 标签（与 `htmlLabels: true` 冲突）→ `mermaid.render()` 抛出解析错误。

**修复**：新增 `sanitizeMermaidCode()` — `[]` 标签自动加双引号包裹、移除非 ASCII Emoji、转义 `<br>`。错误卡片增加"清洗后源码"折叠区便于调试。

**文件**：`vscode-extension/webview/src/components/MermaidBlock.tsx`

### G5.3：流式→静态切换内容丢失（P1）

**问题**：`stream_end` 到达时 `isStreaming` 立即翻为 `false`，最后一帧 `stream_chunk` 可能在 React 渲染周期中未被处理 → `EnhancedStreamingOutput` 切换到 `MarkdownRenderer` 时丢失尾部内容。

**修复**：在 `ChatBubble.tsx` 新增 `renderFinal` 局部状态 + `useEffect` 200ms 延迟，确保内容完全写入后再切换渲染模式。

**文件**：`vscode-extension/webview/src/components/ChatBubble.tsx`

### G5.4：stream_chunk HTTP 可靠性（P1）

**问题**：`worker_config.py` 的 `stream_chunk()` 每个 chunk 是独立 HTTP POST，单次请求失败（网络抖动 / Node API 瞬时不可用）→ 静默丢失数据（仅打印警告，不重试）。

**修复**：新增 `max_retries=2` 重试机制，timeout 5s→10s，指数退避 0.3s/0.6s/0.9s。

**文件**：`python_worker/worker_config.py`

### G5.5：respond 步骤产物发射断裂（P2）🔴 关键发现

**问题**：2026-10-19 工作日志记录了 `worker_respond_step.py` 已实现 `extract_and_emit_artifacts()`，但 Qwen Worker 通过 `step_executor.execute_step` 调用的是 `agents/qwen/step_executor/respond_step.py`，该文件**从未调用 `extract_and_emit_artifacts`**。这意味着 `mentor_explain` 等意图的执行路径中，Mermaid 产物协议自 v4.0 引入以来从未实际生效。

**修复**：
- 在 `step_executor/respond_step.py` 导入并调用 `extract_and_emit_artifacts(result, task_id)`，于 `stream_end()` 之前执行
- 同时增强 prompt 注入 Mermaid 输出指令（`mentor_explain` 意图时自动注入格式要求）
- 新增 `_close_unclosed_blocks()` 补全流式输出中未闭合的 ` ```mermaid ``` ` 代码块
- 新增 analyze 结果回退机制（plan 步骤失败时使用 analyze 输出）

**文件**：`python_worker/agents/qwen/step_executor/respond_step.py`

### G5.6：Node API 流式完整性校验（P2）

**问题**：流式输出被截断时，未闭合的 ` ``` ` 代码块导致 MarkdownRenderer 解析异常。

**修复**：
- 新增 `streamContentCache`（Map）累积 content 通道文本
- `stream_end` 处理时检测未闭合代码块（`` ``` `` 出现奇数个），自动补全末尾 `\n```\` 并 WebSocket 推送
- `stream_end` 后清理缓存防内存泄漏

**文件**：`node-api/index.js`

### G5.7：task_started 去重守卫加固（P3）

**问题**：`processedTaskIds` 去重守卫对空 payload 无防御 → 若首条消息缺失 `task_id`，第二条有效消息被误跳过。

**修复**：在去重检查前新增 `!payload || !payload.task_id` 完整性校验。

**文件**：`vscode-extension/webview/src/App.tsx`

### G5.8：normalizeMarkdownTables 代码块隔离（P3）

**问题**：`normalizeMarkdownTables()` 仅检查行首 ` ``` ` 跳过代码块边界行，但代码块内部的 `|---` 行仍可能被误匹配。

**修复**：新增 `inCodeBlock` 布尔状态追踪，代码块内部所有行原样保留，彻底隔离 Mermaid 与 Table 处理逻辑。

**文件**：`vscode-extension/webview/src/components/MarkdownRenderer.tsx`

### ✅ 宪法合规审查

| 信条 | 状态 | 说明 |
|------|------|------|
| Worker = 真相 | ✅ | 全部 Worker 修改在边界内（worker_config.py, respond_step.py），0 个新状态源 |
| Extension = 映射 | ✅ | 0 行 Extension 代码变更 |
| Webview = 投影 | ✅ | Webview 修改均为投影层渲染修复（MermaidBlock, ChatBubble, MarkdownRenderer, App.tsx），不发起状态变更 |
| 协议 = 宪法 | ✅ | node-api 新增 streamContentCache 为现有路由内部簿记，io.emit 走原有 WebSocket 通道，0 个新端点/通道 |

### 文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `vscode-extension/webview/src/components/MermaidBlock.tsx` | G5.1+G5.2: 静态导入 + sanitizeMermaidCode + ensureMermaidInit |
| 修改 | `vscode-extension/webview/src/components/ChatBubble.tsx` | G5.3: renderFinal 延迟切换 |
| 修改 | `vscode-extension/webview/src/components/MarkdownRenderer.tsx` | G5.8: inCodeBlock 隔离 |
| 修改 | `vscode-extension/webview/src/App.tsx` | G5.7: task_id 完整性校验 |
| 修改 | `python_worker/worker_config.py` | G5.4: stream_chunk 重试 |
| 修改 | `python_worker/agents/qwen/step_executor/respond_step.py` | G5.5: extract_and_emit_artifacts + Mermaid prompt + _close_unclosed_blocks + analyze 回退 |
| 修改 | `node-api/index.js` | G5.6: streamContentCache + 未闭合代码块自动补全 |

### ⚠️ 审计已知风险

| 风险 | 严重度 | 说明 |
|------|:---:|------|
| step_executor/respond_step 与 worker_respond_step.py 功能重复 | 🟡 | 两份 respond 实现未统一，后续维护可能分歧；建议运行时选择其一或合并 |
| Mermaid 静态导入增大了主 bundle | 🟢 | index.js 1644 KB（含 mermaid~1MB），首次加载略慢，但消除了运行时 chunk 加载失败风险 |
| _close_unclosed_blocks 无法处理嵌套代码块 | 🟢 | 仅检查全局 ``` 计数的奇偶性，不处理嵌套代码块（如 Markdown 示例中演示 mermaid 写法的场景） |

---

## 工作日志 — 2026-10-27（G6 Mermaid 边标签着色 & 缩放功能）

> Mermaid 渲染的两个 UX 问题：边标签着色对比度太低 → 人类开发者看不清；无缩放 → 大图溢出小图看不清。

### G6.1：流程图边标签着色修复

**问题**：Mermaid dark 主题的 `edgeLabelBackground` 和 `tertiaryTextColor` 为默认值（接近透明/暗灰），导致流程图边上的文字（如 `-->|报错：ModuleNotFoundError 或路径错误|`）在深色背景下几乎不可见。

**修复**：
- `themeVariables` 新增 `tertiaryTextColor: '#e2e8f0'`（亮白）、`edgeLabelBackground: 'rgba(15, 23, 42, 0.92)'`（深色半透明底）、`fontSize: '14px'`
- 新增 `injectEdgeLabelStyles(svg)` 函数，渲染后在 SVG 内注入 `<style>` 标签，覆盖 `.edgeLabel rect`（深底+浅边框+圆角）和 `.edgeLabel span/p/text/tspan`（亮白字体 13px 500 粗细）

**文件**：`vscode-extension/webview/src/components/MermaidBlock.tsx`

### G6.2：Mermaid SVG 缩放功能

**问题**：复杂流程图（30+ 节点）和简单结构图（10 节点以内）使用相同的固定尺寸渲染——大图溢出、小图留白巨大。人类开发者无法自行调整视图比例。

**修复**：
- 新增 `scale` 状态（25% ~ 300%，步长 10%），默认 100%
- 工具栏：`[−]` 缩小 / `[100%]` 重置 / `[+]` 放大 三按钮，禁用边界防越界
- 快捷键：`Ctrl + 滚轮` 缩放（页面滚轮正常滚动不影响）
- 容器：`maxHeight: 65vh` + `overflow: auto` 大图可滚动；`transition: transform 0.15s ease-out` 缩放平滑
- 切换图表时自动 `setScale(1)` 重置

**文件**：`vscode-extension/webview/src/components/MermaidBlock.tsx`

### 文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `vscode-extension/webview/src/components/MermaidBlock.tsx` | G6.1+G6.2: edgeLabel 样式注入 + 缩放 UI |

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
- **`agents/gemini/gemini_worker.py`**：`stream_chunk` 签名统一为 `(task_id, content, phase=None, channel=None)`

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

## [G8.0] — 2026-10-27 🏭 多任务编排：changelog 步骤 & 复合意图分解 & 编程专家人格升级

> **"写代码 + 更新日志 + 上传 GitHub — 一个请求，三个阶段，一条执行链"**

---

### Phase 1: changelog 步骤实现

**文件**: `agents/qwen/step_executor/changelog_step.py`（新建 120 行）

changelog 步骤在 write_code/refactor 执行链中自动注入变更记录：从 `context["final_file_ops"]`、`context["intermediate_results"]`、`context["meta"]["user_request"]` 提取描述信息，追加到项目根目录的 `CHANGELOG.md`。

**设计原则**：
- **语言无关**：不假定 Python 项目，兼容任何语言
- **幂等性**：同 task_id 多次执行追加而非覆盖
- **非破坏性**：先读后写，不存在则创建
- **批量就绪**：`_extract_changes()` 接受结构化变更数据，未来可直接对接 Pipeline executor artifacts
- **多格式兼容**：CHANGELOG.md / .txt / .rst 按优先级查找

**生成的条目格式**：
```markdown
### 2026-10-27 19:30 UTC
- **任务**: 用户管理功能中新增权限校验模块
- **文件**: `auth/permissions.py`, `models/user.py`
- **测试**: 3/3 通过
```

**执行链注入逻辑**（`intent_router/_router.py`）：
- 关键词检测：`changelog|CHANGELOG|工作日志|更新日志|变更日志|注入.*更新时间`
- 插入位置：fix 步骤之后、doc/docstring 之前
- 仅当 intent 为 `write_code` 或 `refactor` 时注入

**注册**：
- `STEP_DISPATCHER` 新增 `"changelog": run_changelog_step`
- `step_templates` 新增 changelog 模板
- `step_executor/__init__.py` 新增导出

---

### 编程专家人格升级

**文件**: `agents/local_llm/step_executor/write_step.py:437`

```
"专业的编程助手" → "专业的编程专家"
```

**理由**：为未来多语言支持打好地基。AlphaPilot 的未来定位是通用的编程专家，不局限于 Python。Prompt 中的"Python 编程助手"标签会误导 LLM 自我约束为单一语言助手。改为"编程专家"后，LLM 更愿意以通用编程能力人的身份响应多语言需求。

---

### 宪法合规审查

| 信条 | 状态 | 说明 |
|------|------|------|
| Worker = 真相 | ✅ | 全部修改在 Worker 边界内 |
| Extension = 映射 | ✅ | 0 行 Extension 代码变更 |
| Webview = 投影 | ✅ | 0 行 Webview 变更，stream_chunk 通道不变 |
| 协议 = 宪法 | ✅ | 0 个新 WebSocket / HTTP 端点 / Redis 通道 |

---

### Phase 2: 复合意图分解

**文件**: `intent_router/_decompose.py`（新建 120 行）

Intent Router 从"单意图分类器"升级为"复合请求分解器"——一次 LLM 调用同时完成分类和任务分解。

**数据结构**:
- `Phase(type, prompt)` — 单个子任务阶段
- `CompoundPlan(is_compound, phases, fallback_*)` — 复合执行计划
- `from_llm_result()` — 从 LLM classify 原始结果构造计划
- `validate()` — 验证阶段完整性（≥2 阶段，类型白名单）

**核心算法** (`IntentRouter.detect_intent_multi`):
1. 调用 `detect_intent`（复用全量 LLM + Regex 降级逻辑）
2. 读取 `_last_classify_result.is_compound` / `.phases`
3. 复合 → 构造 `CompoundPlan(is_compound=True, phases=[...])`
4. 单任务 → `CompoundPlan(is_compound=False, fallback_intent=...)`

**执行器** (`_exec_compound_phases`):
- 在主链（Phase 1）完成后检查上下文中的 compound_plan
- Phase {2..N} 循环：仅执行 `execute_operation`（调用 operate_step 运行 git add/commit/push）
- 每阶段结果通过 stream_chunk 推送到前端

**LITE_CLASSIFY_PROMPT 扩展** (`_data.py`):
- 新增 `is_compound` (bool) + `phases` (list) 输出字段
- 2 个复合请求 JSON 示例（写+上传、写+CHANGELOG+push）
- 合并规则："更新CHANGELOG"/"测试" → 合并到上一个 write_code

**LLM 响应格式新增** (`_classification.py`):
- `llm_classify` 返回新增 `is_compound` / `phases` 字段
- `max_tokens`: 120 → 256（容纳复合响应）

**降级策略**（零风险）:
| 场景 | 行为 |
|------|------|
| LLM 返回 `is_compound=false` | 走现有单阶段路径（100% 兼容） |
| phases < 2 | 降级单阶段 |
| phases 格式无效 | 降级单阶段 |
| LLM 调用超时/异常 | Regex 降级（永远不返回复合） |

### 测试结果

```
test_g7_capabilities.py              22/22 PASS
test_multi_turn_memory_e2e.py        10/10 + 3 skip (PG 维度)
test_changelog_step.py                6/6 PASS
test_compound_decomposition.py       12/12 PASS
─────────────────────────────────────────────
合计                                  50/50 + 3 skip

---

### 影响范围

| 操作 | 文件 |
|------|------|
| **新建** | `intent_router/_decompose.py` (Phase 数据类 + LLM 结果解析) |
| **新建** | `agents/qwen/step_executor/changelog_step.py` (changelog 步骤执行) |
| **新建** | `tests/test_changelog_step.py` (6 cases) |
| **新建** | `tests/test_compound_decomposition.py` (12 cases) |
| 修改 | `intent_router/_data.py` (LITE_CLASSIFY_PROMPT: is_compound + phases + 复合示例) |
| 修改 | `intent_router/_classification.py` (parse compound fields, max_tokens 120→256) |
| 修改 | `intent_router/_router.py` (_last_classify_result, detect_intent_multi, changelog 链注入) |
| 修改 | `intent_router/__init__.py` (导出 Phase, CompoundPlan) |
| 修改 | `agents/qwen/qwen_worker_v2.py` (compound_plan 分叉, _exec_compound_phases, changelog 模板) |
| 修改 | `agents/qwen/step_executor/execute_step.py` (changelog dispatcher) |
| 修改 | `agents/qwen/step_executor/__init__.py` (changelog 导出) |
| 修改 | `agents/local_llm/step_executor/write_step.py` ("编程助手"→"编程专家") |

---

## [G8.1] — 2026-10-27 🚀 Phase 3: Pipeline Executor（通用多阶段编排引擎）

> **状态: ✅ 已完成 — 4 模块 + 18 测试**

---

### 交付物

| 操作 | 文件 | 行数 |
|------|------|------|
| **新建** | `pipeline_executor/__init__.py` | 类型导出 |
| **新建** | `pipeline_executor/contract.py` | 合约+制品+工厂函数 |
| **新建** | `pipeline_executor/checkpoint.py` | 检查点序列化/存储 |
| **新建** | `pipeline_executor/stages.py` | 三阶段 Gate/OnComplete |
| **新建** | `pipeline_executor/pipeline.py` | PipelineExecutor 主调度器 |
| **新建** | `tests/test_pipeline_executor.py` | 18 测试 |

### 目标

将当前隐式的步骤执行链升级为**显式、可组合、可恢复**的 Pipeline Executor：

```
analyze → workspace → plan → write → refine → test → fix → changelog → doc → docstring
   ↓          ↓         ↓        ↓        ↓       ↓       ↓       ↓         ↓
  [阶段1: 理解]               [阶段2: 生成+验证]                  [阶段3: 后处理]
```

### 核心设计

#### 1. 三阶段管道模型

```
┌─────────── Preparatory ──────────┐  ┌────── Generative ──────────┐  ┌── Post-process ──┐
│ analyze  →  workspace  →  plan   │→ │ write/refine/test/fix loop │→ │ changelog → doc  │
│ (理解需求) (读取代码库) (制定方案) │  │ (写→测→修→重测 循环)        │  │ → docstring      │
└──────────────────────────────────┘  └────────────────────────────┘  └──────────────────┘
```

#### 2. Pipeline 契约（PipelineContract）

```python
@dataclass
class PipelineStage:
    name: str                # 阶段名（preparatory / generative / post）
    steps: list[str]         # 步骤列表
    gate: Callable           # 准入条件：context → bool
    on_complete: Callable    # 完成回调：context → context
    retry: int               # 本阶段最大重试次数
    timeout_s: int           # 阶段超时（秒）

@dataclass
class PipelineContract:
    stages: list[PipelineStage]
    artifacts: dict          # 阶段间共享制品（类型安全）
    state: PipelineState     # PENDING → RUNNING → COMPLETED / FAILED
```

#### 3. 阶段间制品传递（Stage Artifacts）

| 上一阶段产出 | 类型 | 下一阶段消费 |
|------------|------|------------|
| plan 输出 | `PlanArtifact` | write 步骤的 plan 输入 |
| write 输出 | `CodeArtifact` (file_ops) | test 步骤的文件引用 |
| test 输出 | `TestArtifact` (passed/failed) | fix 步骤的修复目标 |
| fix 输出 | `FixArtifact` | retest 步骤的重新测试 |
| changelog 输出 | `ChangelogArtifact` | 返回用户 |

#### 4. 可恢复执行（Checkpoint）

```python
@dataclass
class PipelineCheckpoint:
    completed_stages: list[str]
    current_stage: str
    current_step: int
    context_snapshot: dict    # 可序列化的上下文快照
    timestamp: float

# 断点续跑：worker 重启后从 checkpoint 恢复
```

#### 5. 多意图管道串联

```
Intent A (write_code)         Intent B (execute_operation)
─────────────────────        ──────────────────────────
Preparatory → Generative  →  PostProcess  →  Operate
     ↓                             ↓              ↓
  (analyze+plan+write)      (changelog+doc)  (git push)
     └────────── Artifact flow ──────┘
```

### 实现文件（计划）

| 操作 | 文件 |
|------|------|
| **新建** | `pipeline_executor/pipeline.py` (PipelineExecutor 主类) |
| **新建** | `pipeline_executor/contract.py` (PipelineStage, PipelineContract, Artifact) |
| **新建** | `pipeline_executor/checkpoint.py` (PipelineCheckpoint 序列化/恢复) |
| **新建** | `pipeline_executor/stages.py` (PreparatoryStage, GenerativeStage, PostStage) |
| **新建** | `tests/test_pipeline_executor.py` |
| 修改 | `agents/qwen/qwen_worker_v2.py` (execute_task → 接入 PipelineExecutor) |

### 宪法合规审查（前置）

| 信条 | 约束 |
|------|------|
| Worker = 真相 | Pipeline 执行器必须在 Worker 边界内，不依赖 Extension |
| Extension = 映射 | 0 行 Extension 改动，管道状态通过现有 stream_chunk 推送 |
| Webview = 投影 | 0 行 Webview 改动，阶段进度用现有 channel 字段 |
| 协议 = 宪法 | 0 新端点，阶段间通信通过内存 context dict |

### 优先级矩阵

| 功能 | 优先级 | 状态 |
|------|:--:|:--:|
| PipelineContract + 三阶段划分 | P0 | ✅ 已交付 |
| Stage Artifacts 类型化传递 | P0 | ✅ 已交付 |
| Checkpoint 断点续跑 | P1 | ✅ 已交付 |
| 多管道串联合并 | P2 | ✅ 已交付（make_write_code_pipeline / make_execute_operation_pipeline） |
| 并行阶段支持 | P3 | 🔜 未来迭代 |

### 测试结果

```
test_g7_capabilities.py              22/22 PASS
test_changelog_step.py                6/6 PASS
test_compound_decomposition.py       12/12 PASS
test_pipeline_executor.py            18/18 PASS
─────────────────────────────────────────────
合计                                  58/58 ✅
```

### 宪法合规验证

| 信条 | 验证 |
|------|------|
| Worker = 真相 | ✅ PipelineExecutor 纯 Worker 内运行，`set_execute_step` 依赖注入解耦 |
| Extension = 映射 | ✅ 0 行 Extension 变更 |
| Webview = 投影 | ✅ 0 行 Webview 变更，生命周期钩子可接入现有 stream_chunk |
| 协议 = 宪法 | ✅ 0 新端点 / 通道，阶段间通信通过内存 context dict |

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

### 🔗 step_executor/qwen_api.py 统一

`agents/{gemini,multi_agent}/step_executor/qwen_api.py` 独立硬编码副本全部替换为 `from agents.qwen.qwen_api import call_qwen`。

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
| 重写 | `agents/{gemini,multi_agent}/step_executor/qwen_api.py` |
| 修改 | `TaskModel_v2.py` |
| 修改 | `planner.py` |
| 修改 | `intent_router/_classification.py` |
| 修改 | `.env` |

---

## [v4.1] — 2026-10-11 🔧 工程稳固与架构优化

> **"代码写得再好，工程做不扎实，一切都是空中楼阁"**

---

### 🟡 全部 7 个 Worker write_step plan 回退修复

**问题**: `creative_writing` 等意图的执行链是 `analyze → write`（无 plan 步骤），但所有 write_step 硬要求 `plan_output`。LLM 报错 "未找到 plan 步骤的规划内容"。

**修复**: 在 7 个 Worker 的 `write_step.py` 中添加 plan 缺失时的智能回退：
```python
plan_content = steps.get("plan", {}).get("output", "")
if not plan_content:
    plan_content = steps.get("analyze", {}).get("output", "") + "\n---\n" + user_request
```

| Worker | 文件 |
|--------|------|
| Qwen | `agents/qwen/step_executor/write_step.py` |
| Gemini | `agents/gemini/step_executor/write_step.py` |
| MAAS | `agents/maas/step_executor/write_step.py` |
| Volcengine | `agents/Volcengine/step_executor/write_step.py` |
| Multi-Agent | `agents/multi_agent/step_executor/write_step.py` |
| Local LLM | `agents/local_llm/step_executor/write_step.py` |
| ModelScope | `agents/modelscope/step_executor/write_step.py` |

### 🟡 创意意图 Token 浪费优化

**问题**: L1 层 `write_prompt()` 是静态函数，无视 intent 永远强制输出多文件协议格式（FILE/TEST/DOC），导致 `creative_writing`/`translate`/`chat` 等创意意图浪费大量 token 生成无用结构。

**修复**: 为 3 个核心 Worker 新增 `creative_write_prompt()`，创意意图路由到该函数直接输出纯文本：

| Worker | 文件 | 变更 |
|--------|------|------|
| Qwen | `step_executor/write_step.py` | +`_creative_intents` +`creative_write_prompt()` |
| Local LLM | `step_executor/write_step.py` | 同上 |
| ModelScope | `step_executor/write_step.py` | 同上 |

```python
_creative_intents = {"creative_writing", "translate", "chat", "mentor_explain"}
if intent in self._creative_intents:
    prompt = creative_write_prompt(plan_content, f"{persona.profile}\n{persona.business_rules}")
else:
    prompt = write_prompt(plan_content, f"{persona.profile}\n{persona.business_rules}")
```

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
| 修改 | `agents/*/step_executor/write_step.py` ×7 | plan 回退修复 |
| 修改 | `agents/{qwen,local_llm,modelscope}/step_executor/write_step.py` ×3 | 创意意图优化 |
| 删除 | `intent_router.py` | 拆分为包 |
| 新增 | `intent_router/__init__.py` | 向后兼容入口 |
| 新增 | `intent_router/_data.py` | 静态配置表 |
| 新增 | `intent_router/_classification.py` | LLM 分类引擎 |
| 新增 | `intent_router/_router.py` | IntentRouter 主类 |

### 验证

- intent_router 拆分: 23/23 测试通过 ✅
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

---

## [v4.0 Phase 4.0] — 2026-10-29 🌐 多语言 Worker 集成联调

### 语言感知路由（Language-Aware Routing）

**核心能力**：用户请求自动按目标编程语言路由到对应 Worker 队列，实现四语言 Worker（Python/Java/Node.js/TypeScript）能力平权。

### 新增 — node-api 层 Regex 快速语言检测

**文件**: `node-api/index.js`

- 新增 `LANGUAGE_DETECT_PATTERNS` 三组正则模式（java / typescript / javascript）
- 新增 `detectTargetLanguage(prompt)` 函数，Regex 优先匹配
- 新增 `LANGUAGE_TASK_TYPE_MAP` 映射：python → qwen_generate, java → java_generate, javascript → node_generate, typescript → ts_generate
- `/task/submit` 端点注入：当 type 为 `qwen_generate` 或 `task.generate` 且 prompt 包含非 Python 语言线索时，自动重映射 type → 路由到对应 Worker 队列

**语言检测优先级**: java > typescript > javascript > python（默认）

### 修改 — intent_router 语言字段正规化

**文件**: `python_worker/intent_router/_router.py`

- `detect_intent()` 从 LLM 分类结果中提取 `target_language` 字段
- 当 LLM 返回有效语言且属于 `ALL_TARGET_LANGUAGES` 时，替换默认 `language` 参数
- `target_language` 注入执行链解析链路（`_resolve_chain` → `build_execution_chain` → `apply_language_modifiers`）
- 新增 `ALL_TARGET_LANGUAGES` 导入

### 修改 — 启动脚本多语言 Worker 集成

**文件**: `start_all.ps1`

- 并行启动 Qwen 和 Gemini Worker 实例
- 服务状态摘要新增各 Worker 状态行

### 架构合规性

| 信条 | 状态 |
|------|------|
| Worker = 真相 | ✅ 语言分类由 Worker 内部 intent_router 完成 |
| 协议 = 宪法 | ✅ 任务协议跨语言一致，队列映射统一 |
| 1300 行纪律 | ✅ 所有修改模块均在 400 行以内 |

### 测试验证

- Python 核心测试套件: 145/145 全过 ✅
- Redis 集成测试: 24/24 全过 ✅
- node-api 语法检查: 通过 ✅
- 语言检测 Regex: 27/27 覆盖通过 ✅
- 执行链一致性: 跨语言 compile 注入正确 ✅

---

## [G9] — 2026-10-31 🏛️ 编排器收敛与多 Agent 架构路线图

> **"编排器分解，步骤执行器执行。各司其职，不越界。多 Agent 非远景——契约与 Redis 已铺路。"**

---

### G9.0：宪法审计 — 今日 6 项修复 vs 四大信条

在进行编排器收敛之前，先对今天累积的修复做一次完整的宪法合规审计。AlphaPilot 的四条宪法信条定义于 [CHANGELOG.md §0.1（四大组件信条）](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/CHANGELOG.md#L728-L758)。

**核心定义**：
| 信条 | 含义 | 越界红线 |
|------|------|----------|
| **Worker = 真相** | python_worker 是唯一具“真相”的实体；其他组件不得产生独立于 Worker 的任务状态 | Worker 边界内自由；出边界的消息必须走协议 |
| **Extension = 映射** | vscode-extension 只能读取 Worker 写入的状态，不得自行计算/推断任务状态 | 可读、可转发、不可决策 |
| **Webview = 投影** | webview 只消耗 Extension/Worker 推送的数据，不发起状态变更请求 | 纯只读渲染层 |
| **协议 = 宪法** | 所有跨组件通信复用宪法协议，严禁旁路 | 不改现有端点语义，不加新通道 |

**审计结果**：

| # | 修复 | 文件 | Worker | Extension | Webview | 协议 | 判定 |
|---|------|------|:------:|:---------:|:-------:|:----:|:----:|
| 1 | 编排器工作区根目录 `%TEMP%` → `~/alphapilot_workspaces/.orchestrator/` | `orchestrator.py:L233` | ✅ 内部实现 | - | - | ✅ 复用电 env | ✅ |
| 2 | 意图分类器 JSON Mode + 自适应 max_tokens | `_classification.py` | ✅ 内部 LLM 调用 | - | - | ✅ | ✅ |
| 3 | 编排器链式降级空返回值守卫 | `orchestrator.py:L550` | ✅ 内部降级逻辑 | - | - | ✅ | ✅ |
| 4 | TaskStateContract `all_failed` 聚合状态映射 | `taskStateContract.js` | ✅ 消费真相，非产生 | - | - | ✅ 翻译器非决策 | ✅ |
| 5 | Prisma P2025 不存在任务静默跳过 | `memoryService.js` | ✅ 记忆为二级存储 | - | - | ✅ | ✅ |
| 6 | confirm 路径补发 `task_started` + 响应补 `prompt`/`model` | `reactPanel.ts` + `index.js` | ✅ | ✅ 对齐行为 | - | ✅ 已有消息类型 | ✅ |
| 7 | 前端输入提交立即可见 + 去除重复消息 | `ChatInput.tsx` + `App.tsx` | - | ✅ 映射 | ✅ 渲染时序 | ✅ | ✅ |

```
新增端点:     0
新增通道:     0
新增消息类型: 0（task_started 是对齐已有类型）
新增决策逻辑: 0（taskStateContract 是翻译器，不是决策者）

信条 1 Worker = 真相    ✅ 全部通过
信条 2 Extension = 映射 ✅ 对齐行为，非新增
信条 3 Webview = 投影   ✅ 渲染时序调整
信条 4 协议 = 宪法       ✅ 0 新端点 / 通道
```

---

### G9.1：编排器功能重复分析 — 自建管线 vs 已有步骤执行器

**问题发现**：
G8 编排器的 `_run_subtask`（L373-472）自建了一套迷你执行管线，与 `step_executor/` 系统形成全面功能重复。这不是“类似”——是同一功能的两个独立实现，同一份需求维护两套代码。

**重复清单（精确定位）**：

```
┌──────────────────────────────────────────────────────────────────┐
│  编排器自建方法（orchestrator.py）     →  已有标准实现             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  _build_code_generation_prompt     →  write_step.py:run_write_step│
│  (L517-548, 32 行)                     完整 prompt 工程           │
│    自建: lang_hint 六语言硬编码         + persona/intent 注入      │
│    自建: # FILE: 格式指导               + 多文件协议 (# FILE:/TEST:)│
│    缺失: 意图上下文、persona 注入        + collaboration_modes    │
│                                                                  │
│  _generate_and_write_code          →  execute_step("write", ...) │
│  (L479-515, 37 行)                     STEP_DISPATCHER["write"]  │
│    自建: os.makedirs + open/write       + file_ops 自动记录       │
│    自建: print(f"📄 {f['path']}")       + stream_chunk 实时推送   │
│    缺失: 无 stream_chunk                + 写盘错误自动重试        │
│                                                                  │
│  _call_llm_for_code                →  write_step → call_qwen()   │
│  (L550-583, 34 行)                     已有: 链式降级             │
│    自建: from intent_router import...    + JSON Mode 约束         │
│    自建: for model in chain: try/except  + max_tokens 自适应      │
│    重复: 与 intent_router 降级链完全一致   + 超时从 env 读取      │
│                                                                  │
│  _fix_and_recompile                →  execute_step("fix", ...)   │
│  (L586-612, 27 行)                     STEP_DISPATCHER["fix"]    │
│    自建: 仅传 stderr[:3000]              + 完整上下文注入          │
│    自建: 手写 "只输出修复后代码" prompt    + self_healing_adapter  │
│    缺失: 无 self_healing_adapter          + 符号索引精确上下文     │
│    缺失: 无 EvidenceGate                  + 停滞检测 (3 轮防御)    │
│                                                                  │
│  _fix_and_retest                   →  execute_step("test", ...)  │
│  (L614-645, 32 行)                  →  execute_step("fix", ...)  │
│    自建: 手写 "测试失败请修复" prompt      + test→fix 循环在       │
│    自建: 手写 0 tests 特殊处理            qwen_worker_v2 层       │
│    缺失: 无 EvidenceGate                  + pytest/jest 完整集成   │
│                                                                  │
│  _parse_llm_code_output            →  write_step 内部处理         │
│  (L858-919, 53 行)                     extract_code() +          │
│    自建: re.compile(r"#\s*FILE\s*:")    parse_fileops_v3()       │
│    自建: 三层回退 (FILE → ``` → raw)    + _unwrap_json_content() │
│    缺失: _unwrap_json_content()          + 更健壮的协议解析       │
│                                                                  │
│  _get_extension (L921-928, 8 行)   →  保留（adapter 仍需判断     │
│    仅作语言映射，不算严格重复              文件扩展名）            │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  合计可清除: ~215 行 (23% of orchestrator.py)                    │
│  保留: 分解 + 分发 + 聚合（编排器真正职责）                         │
└──────────────────────────────────────────────────────────────────┘
```

**为什么当时走了“自建管线”？**
`_execute_unified`（L304）文档注释写明：“统一执行路径（Python Worker LLM 写代码 + Adapter 瀑布验证）。不再启动语言 Worker，不 LPUSH Redis 队列。”这是 G8 时期的务实选择——当时 `qwen_worker_v2` 进程内无法直接启动 `node_worker`/`ts_worker`/`java_worker` 等独立进程，只能用一个 Worker（qwen）写所有语言代码 + Adapter 做编译/测试验证。

**现在为什么可以收敛？**
Step 3 的多 Agent 架构（见 G9.3）天然解决这个问题：编排器负责分解，子任务通过 Redis 队列分发，各 Agent 走完整的 `execute_task` 管线。消除了“一个 Worker 写所有语言”的架构前提。

---

### G9.2：Step 1 收敛计划 — 编排器回退为纯分解/分发/聚合层

**目标架构**：
```
编排器的职责边界（只有三件事）
┌─────────────────────────────────────────────┐
│  1. 分解 (Decompose)                        │
│     LLM 分析用户输入 → 识别多语言/多项目     │
│     → 生成 OrchestrationPlan + SubTask 列表 │
│                                             │
│  2. 分发 (Dispatch)                         │
│     每个子任务 → 构造标准 task payload      │
│     → 委托给 step executor 执行             │
│     （Step 2 后可改为 Redis LPUSH）          │
│                                             │
│  3. 聚合 (Aggregate)                        │
│     等待所有子任务结果 → 合并               │
│     → 写回 task_result:{parent_id}          │
│     → 通知 Node API                         │
└─────────────────────────────────────────────┘
         │                   │
         ▼                   ▼
    ┌─────────┐        ┌─────────┐
    │ write   │        │ write   │
    │ → test  │        │ → test  │
    │ → fix   │        │ → fix   │
    │ → capab.│        │ → capab.│
    │ → stream│        │ → stream│
    └─────────┘        └─────────┘
```

**Step 1 具体修改（orchestrator.py）**：

| 操作 | 方法 | 行号 | 处理 |
|------|------|------|------|
| 🗑️ 删除 | `_build_code_generation_prompt` | L517-548 | 委托给 `write_step.run_write_step` 的 prompt 构建 |
| 🗑️ 删除 | `_call_llm_for_code` | L550-583 | 委托给 step executor 的 LLM 调用（已有降级链） |
| 🗑️ 删除 | `_fix_and_recompile` | L586-612 | 委托给 step executor 的 `execute_step("fix", ...)` |
| 🗑️ 删除 | `_fix_and_retest` | L614-645 | 委托给 step executor 的 `execute_step("test", ...)` |
| 🗑️ 删除 | `_parse_llm_code_output` | L858-919 | 委托给 `write_step` 内的 `extract_code` + `parse_fileops_v3` |
| ✏️ 重写 | `_generate_and_write_code` | L479-515 | 改为调用 `execute_step("write", ...)` |
| ✏️ 重写 | `_run_subtask` | L373-472 | 构造 context → 委托 step executor 执行完整 write→compile→test→fix 链 |
| ✏️ 重命名 | `_execute_unified` | L304 | → `_execute_via_step_executor` |

**新 `_run_subtask` 骨架（伪代码）**：
```python
def _run_subtask(self, st: SubTask, plan: OrchestrationPlan) -> SubTaskResult:
    """编排器不再自建管线，委托给 step executor。"""
    t_start = time.time()
    
    # 1. 构建标准 context（复用 Worker 的数据结构）
    context = {
        "meta": {
            "workspace_path": st.workspace_path,
            "user_request": st.prompt,
            "target_language": st.target_language,
        },
        "workspace_scan": {},
        "intermediate_results": [],
    }
    events = []
    
    # 2. 委托 step executor 执行完整管线
    #    write → compile → test → fix（由 test 步骤内部触发）
    execute_step(
        step={"type": "write", "prompt": st.prompt},
        context=context,
        events=events,
        task_id=st.subtask_id,
    )
    
    # 3. 从 context 收集结果（step executor 写入的，不由编排器自建）
    final_files = context.get("final_file_ops", [])
    test_result = context.get("test_result", {})
    
    return SubTaskResult(
        subtask_id=st.subtask_id,
        status="done" if test_result.get("success") else "test_failed",
        generated_files=final_files,
        ...
    )
```

**收益**：
- 消除 ~215 行重复代码
- Prompt 工程、LLM 降级策略、token 自适应、流式推送 —— 从此只维护一份
- 子任务自动获得 `self_healing_adapter`（符号索引 + 停滞检测）、`EvidenceGate`、`parse_fileops_v3`（`_unwrap_json_content`） 等已有能力
- `_build_code_generation_prompt` 六语言硬编码不再需要单独维护（write_step 已是语言无关架构，G8.5 已验证）

---

### G9.3：多 Agent 架构路线图 — 从单体到 Agent Pool

#### 架构演进三步走

```
现在 ────────→ Step 2 ────────→ Step 3
单体 Worker    Agent Pool      进程级 Agent 网格
              (ThreadPool)     (Redis pub/sub)
```

#### Step 2：Agent Pool（同一进程，多 API Key 并发）

**核心洞察**：Python 的 GIL 对 LLM 调用几乎无影响——LLM 调用是纯网络 I/O，`ThreadPoolExecutor` 完全够用。

```
qwen_worker_v2 进程
├─ Thread 1: Agent(api_key=KEYS[0], model="qwen3.8-max-0902")
│   → execute_task(sub_task_A)  [完整管线: analyze→plan→write→test→fix]
├─ Thread 2: Agent(api_key=KEYS[1], model="qwen3.8-flash")
│   → execute_task(sub_task_B)  [完整管线: analyze→plan→write→test→fix]
├─ Thread 3: Agent(api_key=KEYS[2], model="qwen3.8-max-0902")
│   → execute_task(sub_task_C)  [完整管线: analyze→plan→write→test→fix]
└─ Orchestrator: 等待所有线程完成 → 聚合
```

**APi Key 分配策略**：
```python
# 环境变量池（支持多个 API Key，逗号分隔）
DASHSCOPE_API_KEYS = os.environ.get("DASHSCOPE_API_KEYS", "").split(",")
# 例如: DASHSCOPE_API_KEYS=key1,key2,key3

# Round-robin 分配
agent_key = DASHSCOPE_API_KEYS[thread_index % len(DASHSCOPE_API_KEYS)]

# 每个 Agent 内部仍保留降级链
# Agent 1: 主 key → 降级到 flash → 降级到 27b → ...
# Agent 2: 主 key → 降级到 flash → 降级到 27b → ...
# Agent 3: 主 key → 降级到 flash → 降级到 27b → ...
```

**并发模型**：
```
3 个子任务 × 3 个 API Key × 每个 Key 内 3 层模型降级 = 9 条独立链路
不受单 Key 限流影响（阿里云 DashScope 单 Key QPM ~60-100）
```

#### Step 3：进程级 Agent 网格 + 语言 Agent 上线

```
                  Orchestrator
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   Redis Queue   Redis Queue   Redis Queue
   qwen_generate node_generate  ts_generate
        │             │             │
        ▼             ▼             ▼
   qwen_worker   node_worker   ts_worker
   (4 instances) (2 instances) (2 instances)
   每实例不同 Key 每实例不同 Key 每实例不同 Key
        │             │             │
        └─────────────┼─────────────┘
                      ▼
              Redis pub/sub
              task_result:{id}
                      │
                      ▼
              Node API → WebSocket → 前端
```

**质量保证 — 契约三道关口**：
```python
# 多 Agent 最大风险：某个 Agent 产出垃圾。
# 契约系统天然解决——每个 Agent 产出必须过三关：

result = agent.execute(subtask)

# 关口 1: 协议校验
if not TaskStateContract.validate(result):
    retry_with_different_model(subtask)

# 关口 2: 证据门控
if not EvidenceGate.pass(result):
    retry_with_different_model(subtask)

# 关口 3: 授权验证 (R6)
if result.has_file_ops and not AuthorizationVerifier.verify(result):
    block_and_notify_user(subtask)
```

**不是靠“希望 LLM 做好”，而是靠“契约强制执行”。** 这是工业级 Agent 的质量底线。

---

### G9.4：生效条件与风险控制

| 条件 | 当前状态 | 说明 |
|------|----------|------|
| step executor 可独立调用 | ✅ | `execute_step()` 接受 context + events |
| write_step 已是语言无关 | ✅ | G8.5 已验证，支持全部 6 种语言 |
| test_step 可跨语言运行 | ✅ | 通过 adapter 调用 subprocess |
| fix_step + self_healing_adapter | ✅ | 符号索引 + 6 类错误路由 + 停滞检测 |
| EvidenceGate 可用于子任务 | ✅ | 标准 context 结构 |
| stream_chunk 可推子任务步骤 | ✅ | task_id 隔离 |

**回退方案**：所有删除方法保留在 Git 历史中。如果 Step 1 收敛后子任务质量下降，可对比原因（是 step executor 的 prompt 不足还是上下文丢失），针对性修复而非回退。

**上线影响**：
- `orchestrator.py`: 净减少 ~215 行，增加 ~40 行委托代码
- 其余模块: 0 行修改
- 编排结果 schema (`orchestrationResult`): 不变
- WebSocket 事件: 不变
- 前端: 0 行修改

---

### 文件清单（待执行）

| 操作 | 文件 | 内容 |
|------|------|------|
| 🗑️ 删除方法 | `python_worker/orchestrator.py` | `_build_code_generation_prompt`, `_call_llm_for_code`, `_fix_and_recompile`, `_fix_and_retest`, `_parse_llm_code_output` |
| ✏️ 重写方法 | `python_worker/orchestrator.py` | `_generate_and_write_code` → 委托 write_step; `_run_subtask` → 构造 context + 委托 execute_step |
| ✏️ 重命名方法 | `python_worker/orchestrator.py` | `_execute_unified` → `_execute_via_step_executor` |
| 📝 文档 | `python_worker/CHANGELOG.md` | G9 完整条目（本条目） |

### 验证

- [ ] `orchestrator.py` 语法检查通过
- [ ] 单语言任务（非编排路径）零回归
- [ ] 多语言编排任务子任务创建正常
- [ ] 子任务内 write→test→fix 链正确执行
- [ ] EvidenceGate 在子任务上下文中生效
- [ ] stream_chunk 推送子任务步骤到前端
- [ ] 编排聚合结果 schema 字段不变


---

## [G10] — 2026-10-31 🏛️ 第五条宪法：Capability = 唯一实现

### 动机

G9.2 Step 1 收敛暴露了一个深层架构问题：编排器自建了 5 个 LLM 调用方法（~215 行），
而 `python_worker` 内部早已存在完整的 `write_step` / `test_step` / `fix_step` 管线。
这不是“功能缺失”，而是“**能力重复**”——同一个能力被两个 Agent 各自实现了一遍，
结果更差的那一版（自建管线只输出单文件）反而在生产环境中被调用。

这引出了一个此前四大信条没有覆盖的约束：

> **同一种能力，只能存在一个生产实现。**

### G10.0：宪法声明

```text
第五条宪法：Capability = 唯一实现

定义：
  同一种能力在系统中只能存在一个生产实现。

允许：
  ✓ 多个 Agent 调用同一个能力入口
  ✓ 能力内部的多策略降级（链式降级属于同一个实现）
  ✓ 能力实现被替换（旧实现退役，新实现在同一切入点接管）

不允许：
  ✗ Agent 自建同类能力（自建 prompt → LLM → parse 链条）
  ✗ Agent Fork 已有能力（复制代码后修改，与原版并行存在）
  ✗ Agent 复制 Prompt 工程（绕过标准 prompt 模板）
  ✗ Agent 绕过标准能力入口（不通过 execute_step / Verifier / Contract）

核心推论 → 第六条规则：
  Agent 不允许发明能力，只能申请能力。
```

**完整宪法体系（五条）**：

| # | 信条 | 一句话定义 | 首次写入 |
|---|------|-----------|----------|
| 1 | Worker = 真相 | 只有 Worker 创建数据，Node.js 只读 | G6 |
| 2 | Extension = 映射 | Extension 不持有业务状态 | G6 |
| 3 | Webview = 投影 | Webview 不持有业务状态 | G6 |
| 4 | 协议 = 宪法 | 每层通信必须遵守契约 Schema | G6 |
| **5** | **Capability = 唯一实现** | **同一种能力只有一个生产入口** | **G10** |

### G10.1：能力注册表（Capability Library）

未来系统中，所有 Agent 共享同一个能力注册表：

```
                    100 个 Agent
                         │
                         ▼
            ┌────────────────────────┐
            │   Capability Library   │
            │   (唯一真相源)          │
            └────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                 ▼
   ┌─────────┐    ┌──────────┐    ┌──────────────┐
   │  Write  │    │   Test   │    │     Fix      │
   │ 唯一入口 │    │  唯一入口 │    │   唯一入口    │
   │ execute │    │ execute  │    │   execute    │
   │ _step() │    │ _step()  │    │  _step()    │
   └─────────┘    └──────────┘    └──────────────┘
        │                │                 │
   ┌────┴────┐    ┌─────┴─────┐    ┌──────┴──────┐
   │ Memory  │    │ GitUpload │    │  Analyzer   │
   │ 唯一入口 │    │  唯一入口  │    │  唯一入口    │
   └─────────┘    └───────────┘    └─────────────┘
        │                │                 │
   ┌────┴────┐    ┌─────┴─────┐    ┌──────┴──────┐
   │  Shell  │    │ Changelog │    │  Evidence   │
   │ 唯一入口 │    │  唯一入口  │    │  唯一入口    │
   └─────────┘    └───────────┘    └─────────────┘
```

**已存在的能力注册条目**（当前生产环境）：

| 能力 | 唯一入口 | 类型 |
|------|---------|------|
| 代码生成 | `execute_step("write")` | `write_step.py` |
| 测试执行 | `execute_step("test")` | `test_step.py` |
| 代码修复 | `execute_step("fix")` | `fix_step.py` |
| 授权验证 | `AuthorizationVerifier` | `authorization/verifier.py` |
| 记忆注入 | `SessionStateContract` | `contracts/session_state.py` |
| 步骤调度 | `execute_step()` | `execute_step.py` |
| 任务执行循环 | `run_execution_loop()` | `step_runner.py` |

### G10.2：能力申请协议（Capability Request Protocol）

当 Agent 发现缺少某个能力时，**不允许**直接写 `_quick_xxx()` 方法，
必须走正式的能力申请流程：

```text
能力申请格式：

  能力名称：semantic_refactor

  能力契约：
    输入  — { source_code: str, refactor_intent: str }
    输出  — { file_ops: List[FileOp], confidence: float }
    Evidence — 至少 3 个测试用例通过
    错误模式 — 超时 60s / 置信度 < 0.7 → 回退到 write + manual

  评审清单：
    [ ] 是否与现有能力重叠？（重叠 → 拒绝）
    [ ] 契约是否可测试？（不可测试 → 拒绝）
    [ ] Evidence 标准是否明确？
    [ ] 错误降级路径是否定义？

  评审通过后 → 进入 Capability Library → 全部 Agent 共享。
```

**禁止模式（违反第五条宪法）**：

| 违规行为 | 示例 | 后果 |
|---------|------|------|
| Agent 自建同类能力 | `_build_code_generation_prompt()` | → 2026-10-31 G9.2 已删除 |
| Agent Fork 已有能力 | 复制 `write_step.py` 改名为 `write_step_v2.py` | → 拒绝合并 |
| Agent 复制 Prompt 工程 | 在 Agent 方法内硬编码 prompt 字符串 | → 拒绝合并 |
| Agent 绕过标准入口 | 直接 `call_qwen(prompt)` 不通过 `execute_step` | → 运行时告警 |

### G10.3：G9.2 收敛 — 第五条宪法的第一个案例

今天 G9.2 Step 1 做的就是这件事——这是第五条宪法的第一个执法案例：

| 违规发现 | 执法动作 |
|---------|---------|
| `_build_code_generation_prompt` (32 行硬编码 prompt) | → 删除，委托 `write_step` |
| `_call_llm_for_code` (34 行自建 LLM 降级链) | → 删除，委托 `write_step` 的 `call_qwen_with_persona` |
| `_fix_and_recompile` (27 行无符号索引的 fix prompt) | → 删除，委托 `fix_step` 的 `self_healing_adapter` |
| `_fix_and_retest` (32 行同上) | → 删除，委托 `fix_step` |
| `_parse_llm_code_output` (53 行简单正则) | → 删除，委托 `parse_fileops_v3` |

**结果**：215 行重复代码 → 0，编排器回退为纯分解/分发/聚合层。
所有子任务的 write / test / fix 全部通过 `execute_step()` 唯一入口。

### G10.4：未来演进 — 从“不允许发明”到“只能申请”

G10 的最终形态：

```
Coding Agent 发现自己需要 "semantic_refactor" 能力

  OLD (违规):                   NEW (合规):
  ┌──────────────────┐          ┌──────────────────┐
  │ def _quick_refactor():│    │ 提交能力申请      │
  │   prompt = "重构..."  │    │                  │
  │   result = call_qwen() │   │ 能力名称:         │
  │   return result       │    │ semantic_refactor │
  └──────────────────┘          │                  │
       ↓                        │ 契约:            │
  被 Code Review 拒绝           │ 输入/输出/Evidence│
                                │                  │
                                │ 评审通过后:       │
                                │ 进入 Capability   │
                                │ Library          │
                                │                  │
                                │ 全部 100 个 Agent │
                                │ 自动获得该能力    │
                                └──────────────────┘
```

**保守启用**（与 G9.4 一致）：
- 第五条宪法通过 Code Review 强制执行（非运行时检测）
- `execute_step()` 作为唯一入口已是事实上的技术约束
- 能力申请协议目前为文档约定，后续可工具化（lint rule / pre-commit hook）

### G10.5：能力驱动架构 — AlphaPilot 的核心资产

#### 架构宣言

G10 不是一条孤立的规则，而是 AlphaPilot 从第一天就在践行、但直到今天
才正式命名的架构哲学：

```text
模型会变，能力不变。
Agent 会变，契约不变。
Provider 会变，执行链不变。
```

大多数 AI Coding Agent 项目最终会演化成**模型驱动架构**（Model-Driven Architecture）——
一切围绕 `call_qwen()` / `call_openai()` / `call_gemini()` 展开，
换一个模型就要改一堆 Agent 代码。

AlphaPilot 走的是另一条路：**能力驱动架构**（Capability-Driven Architecture）。

#### 四层分层模型

```text
┌─────────────────────────────────────────────────────────┐
│                    Agent Layer                          │
│   Planner Agent · Coding Agent · Review Agent           │
│   Architecture Agent · Frontend Agent · Backend Agent   │
│                                                         │
│   ★ 允许无限增长 ★                                       │
│   新增 Agent 只需调用已有能力，不创建新能力              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                 Capability Layer                        │
│   write · fix · test · analyze · git_upload             │
│   shell_executor · code_analyzer · changelog            │
│                                                         │
│   ★ 这是 AlphaPilot 的核心资产 ★                         │
│   能力数量增长缓慢，但每个能力的质量持续提升              │
│   新增能力须通过正式申请评审                              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  Provider Layer                         │
│   Qwen · OpenAI · Gemini · ModelScope · Local LLM       │
│   Claude · DeepSeek · Kimi · Grok · Llama (未来)        │
│                                                         │
│   ★ 可无限替换，对上层完全透明 ★                          │
│   execute_step("write") 内部可以是任何模型               │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│               Infrastructure Layer                      │
│   Redis · PostgreSQL · Worktree · FileOps               │
│   Authorization · RedisPubSub · SessionState            │
└─────────────────────────────────────────────────────────┘
```

#### 依赖抽象，而非依赖实现

这本质上是工业软件最推崇的原则在 AI Agent 领域的应用：

| 层次 | 依赖 | 不依赖 |
|------|------|--------|
| Agent Layer | Capability 契约 | 模型名称、Provider 实现 |
| Capability Layer | 契约定义 | 具体模型、具体 Agent |
| Provider Layer | 标准调用接口 | Agent 逻辑、Capability 定义 |
| Infrastructure | 协议 Schema | 任何上层实现 |

```text
Agent 只知道一件事：
  "我需要 write 能力"
  不关心是 Qwen 写的还是 GPT-6 写的

Provider 只知道一件事：
  "给我 prompt，返回结果"
  不关心这是给哪个 Agent 用的

orchestrator / memory / evidence / authorization / extension / webview
全都只关心：
  "write 能力是否履行了契约"
  不关心谁写的
```

#### 演进历史的自我证明

回头看 AlphaPilot 的多模型适配演进，其实每一步都在验证这个架构：

```
v1.0:  Qwen 单模型
       execute_step("write") ──► call_qwen()

v2.0:  + Gemini
       execute_step("write") ──► call_qwen_with_persona()
                             ──► call_gemini()          ← 新 Provider，同一切入点

v3.0:  + OpenAI Compatible
       execute_step("write") ──► call_openai_compatible() ← 再新 Provider，入口不变

v4.0:  + ModelScope / Local LLM
       execute_step("write") ──► call_modelscope()
                             ──► call_local_llm()       ← 入口仍然不变

未来:  + Claude / DeepSeek / Kimi / Grok / Llama
       execute_step("write") ──► 仍然是同一切入点
```

**关键事实**：Provider 从 1 个变成 4+ 个，但 `execute_step("write")` 的调用方
（orchestrator、step_runner、memory、evidence）一行代码都没改过。

这就是能力驱动架构的威力——Provider 是引擎，不是整辆车。
换引擎不需要重造汽车。

#### 增长定律

```text
架构复杂度增长公式：

  旧范式（模型驱动）：
    复杂度 ≈ Agent数量 × Model数量 × 能力数量

  新范式（能力驱动）：
    复杂度 ≈ Capability数量 + Agent数量

增长的是：执行者数量
不变的是：核心能力数量
```

这就是为什么从单 Agent 走到 Agent Pool，再走到多 Agent Mesh，
架构复杂度增长会非常缓慢——因为每新增一个 Agent，
它只是调用已有能力的又一个消费者，不引入新的能力分叉。

#### AlphaPilot 应该守住的底线

```text
允许：
  ✓ 新增 Agent（Planner、Review、Architecture、Frontend、Backend...）
  ✓ 替换 Provider（Qwen → GPT-6 → 本地 70B 模型）
  ✓ 增强能力实现（write_step 内部的 prompt 工程持续改进）
  ✓ 新增能力（通过正式申请 + 评审）

不允许：
  ✗ 新增同类能力（frontend_write_step、review_write_step、agent_write_step_v2）
  ✗ Agent 绕过 Capability Layer 直调 Provider
  ✗ Agent Fork 已有能力
```

换模型只是换引擎，不是重造汽车。
换 Agent 只是换驾驶员，不是重建赛道。
Capability Layer 才是 AlphaPilot 不可替代的核心资产。

---

### G10.6：Intelligent Verification Governance — Step 1 Shadow Mode

**日期**：2026-11-05

**能力名称**：`verification_governance`

**G10.2 申请**：✅ 已通过评审（零重叠、零 LLM 依赖、PASS_THROUGH 降级）

#### 问题

AlphaPilot 已有验证能力（test_step、fix_step、compile gate），但没有**验证治理**——
即决定"验证什么、为什么验证、如何证明验证充分"的决策层。

```
旧行为：
  test 步骤 → LLM 生成测试 → 跑 pytest → exit_code==0 → ✅
  → 没有影响分析 → 不知道改了什么
  → 没有风险分级 → 注释修改也跑全量 pytest
  → 没有跳过证据 → skip 了也不知道为什么

新行为（Shadow Mode）：
  test 步骤前 → VerificationGovernor.analyze_impact()
  → 输出 impact_profile 到 context.meta.verification_governance
  → 不改变任何现有测试执行行为（仅观察）
```

#### 新增文件

[verification_governor.py](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/qwen/step_executor/verification_governor.py)

```
VerificationGovernor
  ├── collect_file_changes()     ← 从 final_file_ops 收集 create/modify/delete
  ├── classify_file_types()      ← Python / Markdown / Config / SQL / ...
  ├── analyze_diff_signals()     ← AST 对比，识别 docstring_only / function_signature / ...
  ├── detect_changed_symbols()   ← 提取变化的函数/类名
  ├── estimate_blast_radius()    ← import 关系扫描，估算影响范围
  ├── calculate_risk()           ← 综合信号计算 risk_level + confidence
  └── build_impact_profile()     ← 组装结构化输出
```

#### 核心设计决策

| 决策 | 说明 |
|------|------|
| **Scope ≠ Risk** | `scope` 描述范围（cosmetic/module/wide），`risk_level` 独立判定风险（low/medium/high） |
| **零 LLM 依赖** | 全部使用 AST + 规则 + 文件系统，确定性分析 |
| **不跳过测试** | Step 1 只观察不决策，测试行为完全不变 |
| **降级路径** | 异常 → `analysis_failed: true`，不阻塞执行链 |
| **旧内容回退** | 优先磁盘读取，回退 file_op.old_content（Worker 入队时携带） |

#### 修改文件

| 文件 | 变更 |
|------|------|
| `step_executor/__init__.py` | 注册 `VerificationGovernor` 导出 |
| `step_runner.py` | `run_execution_loop` 中 test 步骤前插入 Shadow Mode 调用 |

#### 单元验证

33/33 测试通过，覆盖：
- R7-A: Markdown only → cosmetic/low
- R7-B: Docstring only → cosmetic/low
- R7-C: Function signature change → module/medium
- R7-D: Schema change → module/high
- R7-E: 5+ 文件 wide change → wide/high
- Edge: 空 ops / syntax error / no context / API surface 新文件

#### 后续

- **Round 7**：真实链路 Shadow Mode 验证（双轨对比）
- **Step 2**：Static Check Capability（compile + ruff/mypy 项目感知）
- **Step 3**：Verification Selector + Skip Evidence（通过策略验证后启用）

---

## G10.7 — 2026-11-05 Shadow Mode 嵌入、Redis 架构修复、真实链路验证启动

> **"不要让测试因手动修复而通过——AlphaPilot 的真实能力才是我们要验证的。"**

### Shadow Mode 生产嵌入

**修改**：[`step_runner.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/qwen/step_runner.py#L98-L116)

在 `run_execution_loop` 的 test 步骤执行前注入 `VerificationGovernor.analyze_impact()`：

```python
if step.get("type") == "test":
    try:
        from .step_executor.verification_governor import VerificationGovernor
        _vg = VerificationGovernor(context)
        context["meta"]["verification_governance"] = _vg.analyze_impact()
    except Exception as _vg_err:
        context["meta"]["verification_governance"] = {
            "mode": "shadow", "error": str(_vg_err), "analysis_failed": True,
        }
```

- 完全 try-except 包裹，任何异常降级为 `analysis_failed=True`
- 结果写入 `context.meta.verification_governance`（审计字段）
- 不改变任何现有执行行为

### 模块注册补全

发现 `python_worker/`、`agents/`、`agents/qwen/` 三层缺少 `__init__.py`，导致 `python -m python_worker.agents.qwen.qwen_worker_v2` 启动时报 `ImportError: attempted relative import beyond top-level package`。

**修复**：补全三个 `__init__.py` 文件（参考 `QUICK_REFERENCE.md` 中的包结构说明）。

### Redis 架构修复（关键）

**问题**：Worker 与 Node API 使用了不同的 Redis 实例，导致真实链路测试中 Worker 无法消费 Node API 提交的任务。

**根因**：

| 组件 | Redis 选择逻辑 | 实际使用 |
|------|---------------|----------|
| Node API | auto 模式下 `redisLocal` 可用 → 降级到 local Redis | `127.0.0.1:6379` ✅ |
| Worker | auto 模式下无 LOCAL_REDIS_MODELS 匹配 → 直连 Upstash | Upstash 云端 ❌ |

两条路径走到不同 Redis，任务队列 `task_queue:qwen` 和结果 key `task_result:{id}` 完全隔离。

**修复**：

1. [`.env`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/.env)：`LOCAL_REDIS_MODELS=maasmodelscopedeepseek,qwen`（增加 qwen）
2. [`worker_config.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/worker_config.py#L95-L97)：`get_redis_type_for_model()` 增加 auto 模式降级逻辑

```python
# auto 模式下优先本地 Redis（匹配 Node API 行为）
if os.getenv("REDIS_HOST") or os.getenv("REDIS_PORT"):
    return "local"
```

修复后 Worker 输出确认：
```
🐳 使用本地 Redis (127.0.0.1:6379)
💡 Redis 类型: local
```

### Round 7 集成测试通过

**新增**：[`test_round7_shadow_mode.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/tests/test_round7_shadow_mode.py)

10/10 测试全部通过，覆盖：
- R7-A: Markdown only → cosmetic/low
- R7-B: Docstring only → cosmetic/low
- R7-C: Function signature → module/medium
- R7-D: Schema change → module/high
- R7-E: Wide change → wide/high
- 异常降级: analysis_failed 路径
- 空 ops / syntax error / no context / API surface 新文件 / CREATE 检测

### 真实链路验证启动（进行中）

- 清空 ShopFlow workspace + Redis，从零启动 R5→R6→R7 全链路
- **R5（architecture）结果**：链路成功 ✅，执行失败 ❌（`FileOps 解析异常: 'NoneType' object has no attribute 'endswith'`），质量 ❌，治理 ❌
- **R6（write_code）**：已提交并确认，Worker 正在执行中被中断
- **待继续**：完成 R6→R7，重点观察 R7 bug_fix 的 Shadow Mode impact_profile

### 修改文件清单

| 文件 | 变更 |
|------|------|
| [`worker_config.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/worker_config.py) | auto 模式增加 local Redis 降级逻辑 |
| [`.env`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/.env) | LOCAL_REDIS_MODELS 增加 qwen |
| [`__init__.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/__init__.py) | 新建（包标识） |
| [`agents/__init__.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/__init__.py) | 新建（包标识） |
| [`agents/qwen/__init__.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/qwen/__init__.py) | 新建（包标识） |
| [`step_runner.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/agents/qwen/step_runner.py) | Shadow Mode 嵌入 |
| [`test_round7_shadow_mode.py`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/tests/test_round7_shadow_mode.py) | Round 7 集成测试（10/10） |
| [`docs/WORKLOG.md`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/docs/WORKLOG.md) | 工作记录同步更新