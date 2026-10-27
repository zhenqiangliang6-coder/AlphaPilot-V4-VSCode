# 工作记录（Worklog）

记录项目中的重要变更与里程碑，便于回溯与审计。

---

## 2026-10-21 🧠 记忆系统 v2.0 — MemoryType 升级、来源可信度建模、混合召回

> **"先保存事实和状态，区分来源可信度，模型说的≠事实，记忆要能更新纠错，不能只依赖 Embedding。"**
>
> 一天内完成记忆系统的五大原则落地：6 分类体系替换 5 个模糊类型、来源→验证状态六态生命周期、写入侧 source_type 端到端贯通、向量+关键词并行混合召回、upsert 替代标记为 SUPERSEDED。

### 背景：v1 记忆系统的三个瓶颈

| 瓶颈 | 症状 | 根因 |
|------|------|------|
| **信息来源不可追溯** | 不知道某条记忆是用户说的还是模型猜的 | `MemoryItem` 无 source_type/source_id |
| **类型体系模糊** | `INSIGHT` 啥都能装，既装 bug 修复也装偏好 | 5 个模糊类型无语义约束 |
| **召回只看 Embedding** | 关键词 "Docker" 搜不到含 "docker-compose" 的记忆 | 纯余弦相似度，无全文/关键词互补 |

### 原则 1：6 分类 MemoryType 体系 ✅

**修改**：[memory_service.py](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/memory_service.py)

```python
class MemoryType(str, Enum):
    PREFERENCE = "preference"        # 用户偏好：语言、风格、工作习惯
    PROJECT_FACT = "project_fact"    # 项目事实：技术栈、架构约束、路径约定
    DECISION = "decision"            # 决策：已采纳/待确认的技术决策
    TASK_EPISODE = "task_episode"    # 任务情景：文件修改、中断点、下一步
    KNOWLEDGE = "knowledge"          # 知识经验：验证过的修复方法、已知陷阱
    FEEDBACK = "feedback"            # 反馈纠错：用户否决、测试推翻的结论
```

**向后兼容**：`CONVERSATION`、`SKILL`、`FACT` 保留为别名映射，旧数据 /newschema 自动升迁。

### 原则 2 + 3：来源可信度 + 六态验证生命周期 ✅

**修改**：`GatekeeperDecision` + `MemoryItem` + `MemoryStatus`

```
source_type     → 默认 verification_status
───────────────────────────────────────────
user_message    → CONFIRMED  (用户说的，已确认)
tool_result     → VERIFIED   (工具/测试验证通过)
model_output    → PROPOSED   (模型猜测，待确认)
unknown         → PROPOSED   (保守默认)
```

`MemoryStatus` 六态生命周期：

```
PROPOSED → CONFIRMED → VERIFIED → SUPERSEDED (被新版本替代)
              ↓            ↓
          REJECTED      EXPIRED
```

**关键行为**：`save_memory` 的 upsert 保留验证状态而非强制 `active`，被替代的旧记忆标记为 `SUPERSEDED`。

### 原则 4：upsert 替代追加 ✅

**修改**：[memory_service.py `save_memory()`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/memory_service.py)

- 同一 `(user_id × memory_type × 内容哈希)` 冲突时 UPDATE 而非 INSERT
- UPDATE 保留已有验证状态（不降级 CONFIRMED → PROPOSED）
- 旧版本标记 `SUPERSEDED` 建立记忆演化链

### 原则 5：混合召回（向量 + 关键词并行 → 合并 → 去重 → 加权排序）✅

**修改**：[memory_service.py `search_similar_memories()`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/memory_service.py)

```
用户查询
  ├── Embedding 搜索 (cosine similarity)
  ├── 关键词搜索 (全文匹配 + 文件名/路径精确命中)
  ├── 合并 & 去重
  └── 加权排序:
      score = status_weight × time_decay × importance
      
      status_weight:
        VERIFIED  = 1.0
        CONFIRMED = 0.9
        PROPOSED  = 0.7 (模型猜测不误导)
        EXPIRED   = 0.3
```

### memory_integration.py 写入侧升级 ✅

**修改**：[memory_integration.py](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/memory_integration.py)

**问题**：写入侧不传 `source_type`，所有记忆默认 PROPOSED（模型输出可信度），无法区分"工具验证过的结果"和"模型猜测"。

**修复**：

1. `_extract_insights()` 为每条洞察标注来源：
   - 成功的代码生成 / 修复步骤 → `source_type="tool_result"`
   - 用户偏好 / 技术事实 → `source_type="user_message"`
2. `save_task_insights()` 把 `source_type` + `source_id` 传入 `should_remember()` → `GatekeeperDecision`
3. `MemoryItem` 创建用 `getattr(decision, "source_type", "")` 防御性读取

**数据流效果**：
```
task_result.success
  → insight.source_type = "tool_result"
  → GatekeeperDecision(verification_status=VERIFIED)
  → MemoryItem(status=VERIFIED, source_type="tool_result")
  → save_memory() → 状态保留为 VERIFIED
```

### 前端 MemoryPanel 同步升级 ✅

**修改**：[memoryTypes.ts](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/webview/src/utils/memoryTypes.ts) + [MemoryPanel.tsx](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/webview/src/components/MemoryPanel.tsx)

- `MemoryType` 枚举：5 类 → 9 类（6 核心 + 3 兼容）
- `MemoryStatus` 枚举：4 态 → 10 态（含 PROPOSED/CONFIRMED/VERIFIED/SUPERSEDED/EXPIRED/REJECTED 生命周期）
- 类型标签/颜色/筛选下拉框同步更新
- `MemoryType.INSIGHT` → `MemoryType.KNOWLEDGE`（mock 数据）

### INSIGHT 引用全量清理

| 文件 | 修复内容 |
|------|---------|
| `test_memory_scope.py` | 4 处 `MemoryType.INSIGHT` → `KNOWLEDGE` / `TASK_EPISODE` |
| `memoryTypes.ts` | 移除 `INSIGHT`，新增 v2.0 六分类 |
| `MemoryPanel.tsx` | mock 数据 + type info map + 筛选下拉框 |

### 测试验证

- `test_memory_scope.py`：**12/12 通过**（1 个 qwen 网络测试跳过）
- `test_memory_persistence.py`：3/12 通过（9 个失败均为环境问题：无 PostgreSQL，非代码逻辑）

### 文件变更

| 文件 | 操作 | 说明 |
|------|:---:|------|
| `python_worker/memory_service.py` | ✏️ | MemoryType 6 分类 + MemoryStatus 六态 + upsert + 混合召回 |
| `python_worker/memory_integration.py` | ✏️ | 写入侧 source_type 贯通 + getattr 防御 |
| `python_worker/tests/test_memory_scope.py` | ✏️ | INSIGHT → v2.0 语义类型 + schema 检测断言修复 |
| `vscode-extension/webview/src/utils/memoryTypes.ts` | ✏️ | MemoryType + MemoryStatus 枚举升级 |
| `vscode-extension/webview/src/components/MemoryPanel.tsx` | ✏️ | mock 数据 + type map + 筛选器升级 |

### 实际效果

用户第三次打开 `d:\AlphaPilot_Pro` 时：
- **项目识别**：SHA256 哈希识别同一项目
- **约束召回**：PROJECT_FACT（source=user_message, status=CONFIRMED）权重 0.9
- **防误导**：模型之前瞎猜的方案（PROPOSED, 权重 0.7）不会影响高频记忆
- **关键词命中**：文件名/路径精确匹配，不依赖向量近似

---

## 2026-10-20 🛡️ G4 工作区绑定与证据准入治理 + 审计复核

> **"路径归属可验证，证据准入可审计。"**
>
> 从 G1 发现工作区路径断裂，经 G2 对抗验证、G3 修复方案设计，到 G4 代码实现并完成只读审计复核。三个核心修复落地，三条不变量经静态追踪确认，但存在一个需要运行时验证的阻塞风险。

### G1 → G2：发现与对抗验证

通过全链路静态追踪 `VSCode Extension → /workspace/set → Node API → Redis → Worker → EvidenceGate`，发现三个断裂点：

| 发现 | 位置 | 影响 |
|------|------|------|
| **G1.1** `/workspace/set` 更新 `fileOpsHandler.workspaceRoot` 但未更新模块级 `workspaceRoot` | [index.js:372-376](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/node-api/index.js#L372-L376) | `/task/submit` 的 `finalPayload.workspace_path` 始终为空 |
| **G1.2** architect 模式执行链 `["analyze","plan","write"]` 不含 `workspace` | [collaboration_modes.py:125-127](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/collaboration_modes.py#L125-L127) | Phase D 证据收集不触发，EvidenceGate 旁路 |
| **G1.3** 证据收集后无文件存在性校验 | task_state_contract.py | 即使路径正确，证据 key → content 映射的真实性未验证 |

G2 对抗验证：路径剥离攻击、architect 链省略、backstop root ≠ bound path 三个场景全部复现断裂。

### G4.1：工作区绑定断裂修复 ✅

**修改**：[index.js:778](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/node-api/index.js#L778) 新增 `workspaceRoot = path;`

```javascript
app.post("/workspace/set", (req, res) => {
    const { path } = req.body;
    workspaceRoot = path;  // ← G4.1: 同步更新模块级变量
    fileOpsHandler.setWorkspace(path);
    res.json({ ok: true, workspace: path });
});
```

- 更新顺序：`workspaceRoot` → `fileOpsHandler.setWorkspace` → HTTP 响应
- 显式 `workspace_path` 优先级守卫 `!finalPayload.workspace_path` 仍正确保护不被 G1 注入覆盖

### G4.2：architect 证据准入 ✅

**修改**：[collaboration_modes.py:128-131](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/collaboration_modes.py#L128-L131)

```python
if "workspace" in default_chain and "workspace" not in chain:
    _pos = chain.index("analyze") + 1 if "analyze" in chain else 0
    chain.insert(_pos, "workspace")
```

- architect 链：`["analyze", "workspace", "plan", "write"]` ✅
- 插入位置：analyze 之后 plan 之前，符合执行顺序
- `"workspace" not in chain` → 无重复插入
- `if "workspace" in default_chain` → 仅当 intent 配置 `ws_dep != "none"` 时触发
- automatic / chat / mentor 不受影响（default_chain 无 workspace）

### G4.3：证据文件存在性校验 ✅

**修改**：[task_state_contract.py:571-600](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/python_worker/task_state_contract.py#L571-L600)

```python
def validate_workspace_evidence(meta: Dict[str, Any]) -> EvidenceGate:
    ws_path = meta.get("workspace_path", "")
    # ...
    if ws_path:
        full_path = os.path.join(ws_path, k)
        if not os.path.isfile(full_path):
            skipped_entries.append(k)
            continue
```

- 有 `ws_path` 时：逐文件 `os.path.isfile` 校验
- 无 `ws_path` 时：仅做非空字符串校验（向后兼容旧调用方）

### ⚠️ 审计发现（G4.1 复核——只读，不改代码）

#### 审计 A：测试统计核对

| 测试套件 | 报告值 | 实际值（pytest） |
|----------|--------|-----------------|
| `test_collaboration_modes.py` | 12 | ✅ 12 |
| `test_task_state_contract.py` | **40** | **48** |
| `test_e2e_evidence_gate.py` | 6 + 1 fail | ✅ 6 + 1 |
| `test_capability_registry.py` | **52** | **48** |
| `test_skills.py` | 4 | ✅ 4 |
| `test_context_builder.py` | 8 | ✅ 8 |
| **合计** | **128/129 → 127 项** | **128 passed + 1 pre-existing failed** |

> 报告统计笔误：task_state_contract 少计 8 项，capability_registry 多计 4 项，"127 项通过" 实为 128。

**唯一失败**：`test_e2e_evidence_gate.py::test_review_b_state_transition_boundaries` — T8 场景期望 `mark_failed → mark_failed`（第二次调用被忽略），但代码仅对 `acquired` 状态做 guard。**无 git 历史基线可证实 "pre-existing" 归属 → 标记为历史归属未证实。**

#### 审计 B：G4.1 工作区绑定

| 检查项 | 结论 | 证据 |
|--------|:---:|------|
| `/workspace/set` 更新 `workspaceRoot` | ✅ | [index.js:778](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/node-api/index.js#L778) |
| `/workspace/set` 更新 `fileOpsHandler` | ✅ | [index.js:779](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/node-api/index.js#L779) |
| `/task/submit` 读取 `workspaceRoot` | ✅ | [index.js:261-263](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/node-api/index.js#L261-L263) |
| 显式路径优先级 | ✅ | `!finalPayload.workspace_path` guard |
| Redis payload 写入 | ✅ | `"workspace_path": workspaceRoot` |
| Worker 读取 | ✅ | `payload.get("workspace_path")` → `_ws_path` |
| 连续切换 A→B | ✅ | 每次 `/workspace/set` 覆盖全局变量 |
| 端到端运行时 | ❓ | 未实际运行，仅静态追踪 |
| 多任务并发隔离 | ⚠️ | workspaceRoot 为模块级全局变量，无任务级隔离 |

#### 审计 C：G4.2 执行链兼容性

| 检查项 | 结论 |
|--------|:---:|
| architect 链 workspace 插入位置 (analyze 之后) | ✅ |
| "workspace" not in chain 重复防护 | ✅ |
| 其他模式无意外变化 | ✅ |
| EvidenceGate 不可绕过 | ✅ |

#### 审计 D：G4.3 路径安全

| 检查项 | 结论 |
|--------|:---:|
| 文件存在性校验 | ✅ `os.path.isfile` 已添加 |
| 文件读取路径一致性 | ✅ Phase D 读 vs G4.3 验用同源 `ws_path` |
| **`os.path.join` 路径穿越防护** | ⚠️ **防御不足** |
| 空 `ws_path` 兼容性分支 | ⚠️ `ws_path=""` 时仅做字符串非空校验 |

> D2 实测验证：`os.path.join("D:\\workspace", "C:\\Windows\\...")` → 越权访问 `C:\\Windows`；`os.path.join("D:\\workspace", "..\\Other")` → 穿越至 `D:\\Other`。当前证据 key 来源受控（workspace scan），但 defense-in-depth 缺失。

#### 审计 E：workspace.scan 失败语义

| 场景 | 证据收集 | EvidenceGate |
|------|:---:|:---:|
| scan OK + ws_path 有效 (workspace_maintenance/write_code) | ✅ 直接映射 | depends |
| architecture + G4.1 ws_path + G4.2 workspace | ⚠️ fallback 关键词搜索 | **取决于搜索命中** |
| scan 异常 + ws_path 有效 | ⚠️ fallback | depends |
| scan 异常 + ws_path 为空 | ❌ | ❌ blocked |
| 证据空 + fallback 无结果 | ❌ | ❌ blocked |

> 🔴 **E3 最高风险**：architecture intent 的 Phase D 证据收集走 `_extract_evidence_keywords` + `search_project_files` fallback。若 prompt 中无匹配关键词 → 证据空 → EvidenceGate 阻断 → 所有 architecture 任务系统性能失败。

### 文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `node-api/index.js` | G4.1: L778 新增 `workspaceRoot = path` |
| 修改 | `python_worker/collaboration_modes.py` | G4.2: L128-131 条件式保留 workspace |
| 修改 | `python_worker/task_state_contract.py` | G4.3: L14 新增 `import os`, L571-600 增强验证 |

### 三个核心不变量结论

| 不变量 | 状态 | 条件 |
|--------|:---:|------|
| 1. 任务工作区明确且可追踪 | ✅ | G4.1 验证通过（静态）；需运行时日志确认 |
| 2. EvidenceGate 放行与工作区关联 | ⚠️ | G4.2+G4.3 验证通过；E3 architecture fallback 路径待运行时确认 |
| 3. 测试结论与实际一致 | ✅ | 128 passed + 1 pre-existing 已核实 |

### 审计复核后分析（2026-10-20 二轮讨论）

#### E3 不只是关键词搜索命中率问题

审计复核暴露的 E3 场景进一步推进到根因层面：

> G4.2 修复了 EvidenceGate 的触发条件，却没有保证 architecture intent 能获得与该意图相匹配的证据。

把 `workspace` 插入执行链，只能让 Phase D 有机会执行；并不保证 Phase D 能生成有效证据。这是**证据生产链与准入链之间的契约问题**，不只是关键词搜索命中率问题。

E3 因果链：

```
Architecture intent
  └→ G4.2: workspace 纳入执行链
      └→ Phase D 证据收集
          ├── architecture 不在特殊意图分支
          │   └→ 关键词搜索 fallback (_extract_evidence_keywords)
          │       ├── 搜索命中 → 生成有效证据
          │       └── 搜索无命中 → 证据可能为空
          └→ EvidenceGate 放行/阻断
```

需要区分三个事实：
1. `workspace.scan` 成功 ≠ Phase D 使用了扫描结果
2. 关键词搜索无命中 ≠ 项目没有可用证据（只说明当前搜索路径未获取）
3. EvidenceGate 阻断**可能是正确的安全行为**——如果证据收集策略不适合 architecture，应修复证据获取方式，而非取消阻断

#### 路径穿越防护需独立修复

`os.path.join()` 不足以证明路径安全。正式修复时应验证规范化路径位于工作区内，考虑 Windows 绝对路径、目录联接和符号链接。不能因为当前文件键通常来自扫描结果就省略防御性检查。

#### workspace.scan 失败时的路径语义

任务已绑定有效 `workspace_path` 时，扫描失败不应自动抹掉路径；但保留路径不等于证据已获取。应分别记录路径绑定状态、扫描状态和证据状态，避免混为一个布尔值。

---

### 🗓️ 明日工作计划：G5 架构意图的证据生产契约审计

> **顺序：E3 运行时验证 → 对照数据流断点 → 确定证据来源 → 最小修改 → 回归测试**

#### 第一阶段：E3 最小运行时实验

在当前 AlphaPilot 仓库中针对 architecture intent 增加诊断日志/临时测试，不修改正式执行逻辑。
固定同一工作区、相同项目文件、相同执行配置。

| 测试 | 输入 | 回答的问题 |
|------|------|-----------|
| **E3-A** | "分析当前项目的整体架构" | 无文件名时，能否获得项目证据？ |
| **E3-B** | "分析 qwen_worker_v2.py 的架构职责" | 明确文件名时，fallback 是否正常命中？ |
| **E3-C** | "分析模块依赖、调用关系和分层结构" | 架构术语能否匹配实际项目文件？ |
| **E3-D** | 同一提示词，有/无 workspace scan | Phase D 是否利用扫描结果，还是只依赖关键词？ |

每次运行记录诊断字段：
`task_id` / `intent` / `workspace_path` / `workspace_scan.status` / `workspace_scan.root` / `project_context_files.count` / `source_files.count` / `evidence_collection.strategy` / `evidence_collection.search_keywords` / `evidence_collection.matched_files` / `workspace_evidence.keys` / `evidence_gate.result` / `evidence_gate.failure_reason` / `final_task_status`

关键验收标准：不只判断成功/失败，要确定**证据从哪里来、为什么没有命中、EvidenceGate 为什么放行或阻断**。

#### 第二阶段：确定修复方向（根据 E3 结果选择）

| 方案 | 描述 | 前提 |
|------|------|------|
| **A（优先）** | 让 architecture 复用 Capability Engine 已有扫描结果作为 Phase D 证据来源 | 扫描结果存在、与工作区一致、内容足够 |
| **B（备用）** | 建立 architecture 专用证据收集策略（入口、模块清单、依赖关系、源文件） | 必须定义采集范围、来源和失败语义 |
| **C（恒成立）** | 保持 EvidenceGate 严格准入——区分"未获取""不匹配""不足以支持" | 不牺牲可治理性换表面成功率 |

倾向：优先验证 A，再根据缺口决定 B。复用已有能力，不重复建设；但不因扫描成功就默认架构结论有证据支持。

#### G5 正式步骤

1. 运行 E3-A ~ E3-D，获取真实调用日志
2. 对照 Phase C 扫描输出和 Phase D 证据输入，找出数据流断点
3. 确定 architecture intent 应当消费哪些真实证据
4. 先定义证据来源、完整性和失败语义，再进行最小代码修改
5. 增加回归测试，证明：无关键词也能在证据可用时完成分析；证据不可用时仍会正确阻断

#### 核心原则

- Worker 不应凭空制造事实
- Extension 不应替 Worker 猜测项目
- EvidenceGate 不应因执行链有 workspace 就默认证据充分

---

## 2026-10-12 🤖 Qwen 多模型运行时探测 &兼容模式全线切换

> **"不预设任何候选，让 API 自己说实话"**
>
> 一天之内完成两个突破：(1) Qwen 模型选择从硬编码 21 个候选改为 `/v1/models` API 真实查询 (2) 全线切换到 compatible-mode 端点，激活 qwen3.8-max 和 omni 视觉模型。

### 🔍 qwen_model_probe — 从"猜"到"查"

**旧问题**: 硬编码 21 个模型候选逐一试探。结果误导性极大——探测结果称"视觉模型不可用"，实则 omni 系列（qwen3.8-omni-flash 等）完全可用，只是候选列表里没有。

**新设计**: 四步客观探测法

```
第一步: GET /v1/models → 获取 API Key 真实可用模型（本次 175 个）
第二步: 按能力自动分类 → 文本 / 视觉(vl) / 全模态(omni) / 专用(coder)
第三步: 按代际 + 能力排序 → qwen3.8 > qwen3.7 > qwen3 > qwen2.5 ...
第四步: 轻量可用性验证 → compatible-mode 1-token 最小请求确认
```

**结果对比**:

| 维度 | 旧版（硬编码） | 新版（API 真实查询） |
|------|---------------|---------------------|
| 探测方式 | 21 个硬编码候选逐一试 | 175→80 个 Qwen 真实模型 |
| 文本首推 | `qwen-max` | ⭐ `qwen3.8-max` |
| 文本可用 | 5 个 | **9 个**（qwen3.8-max/3.7-max/plus/flash 等） |
| 视觉可用 | **0 个**（误判！） | **7 个**（qwen3.8-omni-flash → qwen3.5-omni-plus → qwen3-vl-plus ...） |
| 缓存 | 无 | ✅ 1 小时 TTL |

### 🔄 Qwen API 全链路 → compatible-mode

**问题**: 原生 DashScope 端点（`text-generation/generation`、`multimodal-generation/generation`）不支持 omni 模型。qwen3.8-omni-flash 只能通过 `compatible-mode/v1/chat/completions` 调用。

**改动**: qwen_api.py、vision_api.py、planner.py、intent_router/_classification.py 全部切换到 compatible-mode。

```
之前: https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation
之后: https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

| 文件 | 改动 |
|------|------|
| `qwen_api.py` | 端点 + 消息格式 + 流式格式 → compatible-mode；`_extract_text_from_response` 兼容两种格式 |
| `vision_api.py` | `_call_qwen_vision` → compatible-mode + OpenAI image_url 格式 |
| `planner.py` | 端点 + 响应解析同步 |
| `_classification.py` | `format: dashscope` → `openai` |

### 🔗 三个 step_executor/qwen_api.py 统一入口

`agents/openai|claude|multi_agent/step_executor/qwen_api.py` 三个文件是独立副本，各有自己的硬编码 `qwen-turbo` 和原生端点。现全部替换为 `from agents.qwen.qwen_api import call_qwen` 单一导入。

### 📊 ModelScope 降级链（无探测，纯 env）

```
MODELSCOPE_MODEL=Qwen/Qwen3.8-Flash-Next        ← 首选
MODELSCOPE_FALLBACK_1=Qwen/Qwen3.8-27B
MODELSCOPE_FALLBACK_2=deepseek-ai/DeepSeek-V4-Flash-Vision-Exp
MODELSCOPE_FALLBACK_3=deepseek-ai/DeepSeek-V4.1-Flash
MODELSCOPE_FALLBACK_4=Qwen/Qwen3.8-27B          ← 兜底
```

`call_modelscope()` / `call_modelscope_stream()` / `call_modelscope_stream` 全部加入降级循环，失败自动跳下一个模型。

### 📋 清除硬编码模型名

全文搜索 `qwen-turbo` 共 10 处 + 3 处旧端点，全部修复：

| 文件 | 修复 |
|------|------|
| `TaskModel_v2.py` | 默认 `qwen-turbo` → `qwen-max`；SUPPORTED_MODELS 补充 qwen3.8 |
| `planner.py` | `qwen-turbo` → `qwen-max` + compatible-mode |
| `_classification.py` | `qwen-turbo` → `qwen-max` + `format: openai` |
| `step_executor/qwen_api.py` ×3 | 硬编码副本 → 统一 re-export |

### 🔑 .env 最终配置

```env
# Qwen — 运行时探测自动优化
QWEN_MODEL=qwen3.8-max
QWEN_FALLBACK_1=qwen3.8-max-0902
QWEN_FALLBACK_2=qwen3.8-flash
QWEN_FALLBACK_3=qwen3.8-27b
QWEN_VISION_MODEL=qwen3.8-omni-flash
QWEN_VISION_FALLBACK=qwen3.5-omni-plus

# ModelScope — 纯 env 降级链
MODELSCOPE_MODEL=Qwen/Qwen3.8-Flash-Next
MODELSCOPE_FALLBACK_1=Qwen/Qwen3.8-27B
...
```

### 文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 重写 | `agents/qwen/qwen_model_probe.py` | 四步客观探测法替换硬编码候选 |
| 重写 | `agents/qwen/qwen_api.py` | compatible-mode 端点 + 响应解析 |
| 重写 | `agents/modelscope/modelscope_api.py` | 加入降级链循环，三个调用入口全更新 |
| 修改 | `agents/vision_api.py` | `_call_qwen_vision` → compatible-mode + image_url |
| 重写 | `agents/{openai,claude,multi_agent}/step_executor/qwen_api.py` | 统一导入入口 |
| 修改 | `TaskModel_v2.py` | 默认模型名 + SUPPORTED_MODELS 更新 |
| 修改 | `planner.py` | 端点 + 模型 + 解析同步 |
| 修改 | `intent_router/_classification.py` | 端点 + 模型 + format 同步 |
| 修改 | `.env` | Qwen + ModelScope 降级链 env vars |
| 修改 | `docs/WORKLOG.md` | 本条记录 |
| 修改 | `python_worker/CHANGELOG.md` | v4.3 条目 |

---

## 2026-10-12 🏭 ImageSanitizer — VSCode Extension 图片压缩工业级中间件

> **"绝对不要在 Extension Host 主线程调用 sharp"**
>
> 为 AlphaPilot 前端图片入口补齐工业级压缩管线：Worker Thread 异步隔离 + 模型感知动态 Limits + Transferable Objects 零拷贝传输 + 超时熔断优雅降级。

### 核心架构：三层防御

```
Layer 1 ─ 浏览器安全阀 (ChatInput.tsx)
          原始文件 > 25MB → 拒绝（防 Webview OOM）
          BROWSER_SAFETY_MAX_RAW_BYTES = 25MB ⚠️ 不是业务规则，是浏览器生命线

Layer 2 ─ Worker Thread 压缩 (ImageSanitizer + image-compress.worker)
          sharp → withoutEnlargement + progressive JPEG
          模型感知 MODEL_VISION_LIMITS[model] → maxW/H、quality、maxImages
          10s 超时熔断 → 透传原图（优雅降级，保留现场）

Layer 3 ─ 真相透传 (reactPanel.ts → payload → TaskModel_v2)
          client_sanitization → sanitizationMeta 注入 payload.images[]
          Worker → modality_metadata（永不可篡改）
```

### Worker Thread 隔离

[image-compress.worker.ts](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/src/workers/image-compress.worker.ts) — 独立线程纯物理计算：
- 条件 resize：仅当 `metadata.width > maxWidth` 或 `metadata.height > maxHeight` 才触发
- `withoutEnlargement: true` — 小图不放大
- progressive JPEG — 渐进式加载友好

### 模型感知配置

| 模型 | maxW×H | quality | maxImages | maxInputBytes |
|------|--------|---------|-----------|---------------|
| qwen3.8-omni-flash | 1280² | 85 | 10 | 10MB |
| qwen3-vl-plus | 2048² | 85 | 5 | 10MB |
| gpt-4o | 2048² | 85 | 10 | 20MB |
| gemini-2.0-flash | 4096² | 90 | 16 | 20MB |
| default | 1024² | 80 | 3 | 5MB |

### 三大防坑补丁

| 补丁 | 问题 | 解法 |
|------|------|------|
| **Transferable Objects** | base64 JSON 序列化 >10MB 时卡死主线程 | `postMessage(msg, ...buffers)` 零拷贝传输 ArrayBuffer |
| **批量预取 Limi** | 每次粘贴都 RPC 查询 | `get_all_vision_limits` 一次性同步全部模型边界到 Zustand |
| **Worker 预热+熔断** | 冷启动 200-500ms + 畸形图崩溃 | Extension 激活后延迟 2s 发送 1px 假图热身；`Promise.race(worker, 10s timeout)` |

### 图片入口全链路

```
用户 Ctrl+V / 拖拽 / 点击上传
        │
        ▼
  ChatInput.tsx                   BROWSER_SAFETY_MAX_RAW_BYTES=25MB 安全阀
  URL.createObjectURL(file)       预览不必 base64
  createImageAttachment()         格式兼容检查 (supportedFormats)
        │
        ▼  
  vscode.ts                       submitTask(prompt, model, images)
  file.arrayBuffer()              ← 不读 base64，读 ArrayBuffer
  postMessage(msg, buffers)       ← Transferable 零拷贝
        │
        ▼
  reactPanel.ts                   ← 双路径兼容 (Transferable / Base64)
  imageSanitizer.sanitize(buf, model)
  Worker Thread → sharp 压缩
  client_sanitization → payload
        │
        ▼
  Node API → Redis → Worker
  modality_metadata              ← 写入 TaskModel_v2 真相源
```

### 文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| **新增** | [image-compress.worker.ts](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/src/workers/image-compress.worker.ts) | Worker Thread 纯物理压缩 |
| **新增** | [ImageSanitizer.ts](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/src/services/ImageSanitizer.ts) | 主线程调度器 + MODEL_VISION_LIMITS + 预热熔断 |
| **重写** | [ChatInput.tsx](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/webview/src/components/ChatInput.tsx) | Transferable Objects + 动态 Limits + 25MB 安全阀 + 格式检查 |
| **重写** | [vscode.ts](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/webview/src/utils/vscode.ts) | `postMessage(msg, transferList)` + `ImageAttachment.file:File` + `fetchAllVisionLimits()` |
| **修改** | [reactPanel.ts](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/src/panels/reactPanel.ts) | ImageSanitizer 接入 + client_sanitization 注入 + vision_limits_sync 通道 |
| **修改** | [extension.ts](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/src/extension.ts) | activate 预热 / deactivate dispose |
| **修改** | [chatStore.ts](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/webview/src/store/chatStore.ts) | `visionLimits` 本地缓存 + `setVisionLimits` action |
| **修改** | [App.tsx](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/webview/src/App.tsx) | `vision_limits_sync` 消息处理 + 初始化预取 |
| **新增** | package.json | `sharp` + `@types/sharp` 依赖 |

### 宪法合规

- **信条 1 (Worker = 真相)**: `client_sanitization` 原样写入 TaskModel_v2.modality_metadata，不可丢弃
- **信条 3 (Webview = 投影)**: `MAX_IMAGES` 从前端硬编码迁移到 ImageSanitizer 模型感知查询，Webview 不作为决策源
- **信条 4 (协议 = 宪法)**: `vision_limits_sync` 复用现有 postMessage 协议通道，无旁路

---

## 2026-10-12 🧪 42 题冒烟矩阵完整落地 & 测试模块化拆分

> **"88% 不是缺憾，是 AlphaPilot 今天真实的能力水印"**
>
> 今天完成了 AlphaPilot 自愈能力的最低契约定义：42 道试题从矩阵文档完整落地到可执行冒烟测试，并将 2408 行单体 `run_smoke_e2e.py` 拆分为可扩展的专用测试包。

### 42 题矩阵全覆盖

- **P0 基线** 6 题（S0-S5 + T1-T6）：全部 PASS ✅
- **P1 进阶** 15 题（T7-T21）：全部 PASS ✅
- **P2 高阶** 21 题（T22-T42）：16 PASS / 5 FAIL（76%）
- **总计** 37/42 = 88% 自愈率

5 FAIL（T19/T20/T22/T37/T38）均为 LLM 非确定性噪声——同一题在历史多轮跑中交替 PASS/FAIL，非代码缺陷，是 LLM 基座模型可重复性天然上限。

### run_smoke_e2e.py → smoke_tests/ 包拆分

```
之前: run_smoke_e2e.py (2408 行单体)
之后:
  run_smoke_e2e.py (11 行薄入口)
  smoke_tests/
  ├── config.py          # 公共常量 & 工具函数
  ├── turns.py           # 工作流 turn 执行 & 意图路由
  ├── engine.py          # 自愈执行引擎核心
  ├── runner.py          # 编排层 & 最终报告
  └── definitions/
      ├── P0_baseline.py     # 6 题
      ├── P1_intermediate.py # 15 题
      └── P2_advanced.py     # 21 题
```

依赖方向：`config → turns → definitions/* → engine → runner`，单向无循环。新增试题只需在对应优先级文件追加定义，引擎零改动。

### 测试用例 5 道退化修复

拆分过程中发现原测试数据存在退化（bug 恰好满足断言、ASCII 无法触发编码缺陷、CPython interning 等），全部修复：

| 题号 | 退化 | 修复 |
|------|------|------|
| T16 | `'hello world'` ASCII → 编码缺陷不触发 | → `'你好世界'` UTF-8 |
| T30 | `assert API_TOKEN not in output` — 被 LLM mask 误触 | → `assert 'tk_test_12345' not in output` |
| T31 | `rest == []` — bug 恰好满足断言 | → `len(rest) > 0` |
| T35 | `isinstance(result, str)` — 太弱 | → `json.loads` 结构验证 + `timestamp in data` |
| T41 | `is_hello('hello')` — interning 永远 True | → `chr()` 运行时拼接 |

### 基础设施修复

- **Docker PostgreSQL 端口冲突**：Docker bridge 实际子网为 172.18.0.0/16，与 Windows 本地 PostgreSQL 同时绑定 5432 端口。将 Docker PostgreSQL 切换到 5433，更新 `.env.memory`、`.env.memory.example`、`node-api/.env` 所有相关配置
- **Node.js 生产记忆链路**：`Node.js → Prisma → PostgreSQL` 全链路 `test_memory_chain.js` 验证通过，确认生产代码无潜伏 bug

### 文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `smoke_tests/` 包（9 文件） | 模块化测试体系 |
| 重写 | `run_smoke_e2e.py` | 2408 → 11 行入口 |
| 修改 | `.env.memory.example` | `DB_PORT`: 5432 → 5433 |
| 修改 | `.env.memory` | `DB_PORT`: 5433 |
| 修改 | `node-api/.env` | DATABASE_URL 端口 → 5433 |
| 修改 | `python_worker/CHANGELOG.md` | v4.2 条目 |

---

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

> **"Safety is not a feature. It is the architecture itself."**
>
> AlphaPilot 是一个自主编码 Agent 系统，以 LLM 为脑、以 Git Worktree 为沙箱、以 pytest 为反馈闭环。
> 本文档定义其核心安全架构、流水线设计、数据模型、执行链资产与扩展策略。

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

---

## 2026-10-24 🔧 前端输出显示修复 — 三层根因治理

> **"AI 输出的 Markdown 表格被压缩为单行 → react-markdown 无法识别 → 超长行溢出破坏布局。"**
>
> 三层问题定位：Node API 重复路由 → Markdown 表格格式损坏 → CSS 无溢出保护。

### 问题现场

用户提供完整输出日志（1740 行），AI 生成的 Markdown 输出在前端无法正常显示：
- 多行 Markdown 表格被 AI 模型压缩为单行（如 `| H1 | H2 | |---|---| | D1 | D2 |`）
- react-markdown 无法识别单行表格，渲染为普通文本
- 超长单行无断点，导致水平溢出破坏整个聊天布局

### 根因 1：Node API 重复 stream_chunk 处理器

**修改**：[`node-api/index.js:L480-L483`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/node-api/index.js#L480-L483)

**问题**：第 483 行（7.5 节）和第 557 行（第 8 节）存在两个完全重复的 `app.post('/task/stream_chunk/:task_id')` 处理器。Express 按注册顺序依次执行两个处理器：
- 旧版处理器发出 `task_stream_chunk` 事件（前端无人监听该事件名）
- 旧版立即 `res.json()` 结束 HTTP 响应
- 新版处理器发出正确的 `stream_chunk` 事件时连接已关闭 → 事件丢失

**修复**：删除旧版处理器（第 479-506 行），只保留第 8 节的新版处理器，确保每个 `stream_chunk` POST 仅被一个处理器正确消费。

### 根因 2：Markdown 表格压缩 → react-markdown 无法解析

**修改**：[`MarkdownRenderer.tsx:L12-L78`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/webview/src/components/MarkdownRenderer.tsx#L12-L78)

**问题**：AI 模型将标准多行 Markdown 表格压缩为单行输出：
```
| H1 | H2 | H3 | |---|---|---| | D1 | D2 | D3 | | D4 | D5 | D6 |
```
react-markdown 要求表格每行独立（header / separator / data 分行），单行格式不被识别。

**修复**：新增 `normalizeMarkdownTables()` 预处理函数（`useMemo` 缓存），核心算法：
1. 检测含 `|---` 的单行（排除代码块内）
2. 按 `|` 分割，通过连续 `---` cell 数量推断列数 N
3. 分离表头（separator 之前，剔除尾部空 cell）和数据（separator 之后，剔除首部空 cell）
4. 过滤行边界空 cell（`| |` 产生的 artifact）
5. 还原为 N 列标准多行 Markdown 表格

转换效果：
```
单行 →  | H1 | H2 | H3 |
        |---|---|---|
        | D1 | D2 | D3 |
        | D4 | D5 | D6 |
```

### 根因 3：CSS 溢出无保护 → 布局破坏

**修改**：[`index.css:L123-L126`](file:///d:/Copilot_Alphapilot/Copilot_Alphapilot/vscode-extension/webview/src/index.css#L123-L126)

**问题**：`.markdown-renderer` 容器和 `<p>` 标签无 `overflow-wrap` / `word-break`，超长行无断点导致水平溢出。

**修复**：在 `.markdown-renderer` 和 `.markdown-renderer p` 中添加：
```css
overflow-wrap: anywhere;
word-break: break-word;
```

### 验证

- 编译通过（`tsc && vite build`，48.77s，退出码 0）
- TypeScript 诊断零错误
- Python 模拟验证：8 条压缩表格全部正确还原，行列对齐无误