# AlphaPilot Phase 2.0 — 安全边界与契约决策门控

> 版本: v1.1 | 日期: 2026-10-29 | 状态: 待审批
>
> 目的: 在冻结 Schema（Phase 2.1）前，固化全部语义决策，消除"字段统一但执行路径仍能绕过"的风险。
> 此文档不涉及代码实现。所有决策在此文档审批通过后才能进入 Phase 2.1。

---

## 决策 1: 路径语义三层分离

### 1.1 三层定义

| 层 | 名称 | 含义 | 来源 | 谁可扩充 |
|----|------|------|------|:---:|
| 1 | `workspace_roots` | VS Code 打开的工作区根目录集合 | Extension 自动采集 | 不可扩充 |
| 2 | `authorized_roots` | 经用户授权后允许访问的根目录集合 | 从 workspace_roots 中截取，或用户显式添加 | 仅用户可扩充 |
| 3 | `allowed_paths` | 按操作类型进一步限制的路径范围 | Authorizer 基于 authorized_roots 计算 | 仅 Authorizer |

### 1.2 约束

- `workspace_roots` 描述"用户在 VS Code 中打开了哪些目录"。它本身不授予任何文件系统权限。
- `authorized_roots` 必须是 `workspace_roots` 的子集（或用户显式向 Extension 添加的外部根）。**"工作区内" ≠ "所有操作均获授权"**。
- `allowed_paths` 必须在 `authorized_roots` 内。它进一步限制具体的 `read` / `write` / `execute` 范围。
- 任何路径校验的最终依据是 `allowed_paths`，不是 `workspace_roots`。

### 1.3 第一版支持范围

- 单个 `workspace_root` → 单个 `authorized_root` → `allowed_paths` 的 `read` / `write` / `execute` 三域。
- 多根预留给后续版本。`workspace_roots` 数组保留，但校验时 `len > 1` 会报"first-class multi-root"错误并拒绝执行（不静默回退到单根）。

### 1.4 示例

```
workspace_roots:  ["/home/user/projects/monorepo"]
authorized_roots: ["/home/user/projects/monorepo"]
allowed_paths: {
  "read":  ["/home/user/projects/monorepo"],
  "write": ["/home/user/projects/monorepo/projects/new-app"],
  "execute": ["/home/user/projects/monorepo/projects/new-app"]
}
```

读取范围可以比写入范围宽，但绝对不能包含 `.env`、`secrets/` 等凭据路径——即使这些路径在 `workspace_roots` 内。敏感路径策略（见决策 3）在 `allowed_paths` 之上叠加拒绝规则。

---

## 决策 2: 操作能力模型（六种操作，独立授权语义）

审查意见正确指出：`allowed_paths` 只定义了 `read`/`write`/`execute` 三个域，但 PathGuard 又增加了 `delete`/`create_dir`/`move`。各语言 Worker 不能自行解释这些规则。

### 2.1 能力定义

| 能力 | allowed_paths 域 | 语义 |
|------|:---:|------|
| **read** | `read` | 读取文件内容或枚举目录 |
| **write** | `write` | 创建或覆盖文件内容（不含目录创建） |
| **create_dir** | `write` + 父目录检查 | 在 allowed.write 内创建目录。**要求目标路径的最近已存在父目录也在 allowed.write 或 allowed.read 内** |
| **delete** | `write` + 独立确认 | 删除文件或空目录。**不允许递归删除**（递归删除走 `rmtree` 确认流程）。操作要求路径在 allowed.write 内 |
| **move** | `write` × 2 | 移动/重命名。**源和目标两端均必须在 allowed.write 内**。跨域移动（如从 write 域移到 read 域）拒绝 |
| **execute** | `execute` | 在指定 cwd 执行命令。**execute 域不授予命令的文件写入权限**——命令的写入副作用由命令隔离策略控制（见决策 4） |

### 2.2 Schema 表示

`allowed_paths` 在 task_context 中的表示：

```json
{
  "allowed_paths": {
    "read": ["/path/to/read/scope"],
    "write": ["/path/to/write/scope"],
    "execute": ["/path/to/execute/scope"]
  }
}
```

`delete` 和 `move` 使用 `write` 域 + 额外检查（由 PathGuard 在运行时叠加）。不引入独立的 `delete`/`move` 域，避免字段爆炸和 Worker 解析分歧。

### 2.3 目录创建的父目录规则

```
validate_create_dir(path, allowed_write, allowed_read):
  1. path.resolve() 必须在 allowed_write 内
  2. 向上查找最近已存在父目录 parent
  3. parent 必须在 (allowed_write ∪ allowed_read) 内
  4. 不要求 parent 在 allowed_write 内（否则新项目的父目录也需要写权限）
```

### 2.4 递归删除

```
validate_delete(path, recursive=False):
  1. path.resolve() 必须在 allowed_write 内
  2. 如果 recursive=False: 要求路径是文件或空目录
  3. 如果 recursive=True: 要求 AuthorizationResult.REQUIRE_CONFIRMATION，
     确认对象绑定路径和估算的影响文件数
  4. 敏感路径（.git, .env 等）在任何情况下都拒绝
```

### 2.5 各语言实现一致性

PathGuard 的六种方法（`validate_read` / `validate_write` / `validate_delete` / `validate_create_dir` / `validate_move` / `validate_execute`）必须在 Python / Node.js / TypeScript / Java 四个 Worker 中具有相同的语义。共享测试向量定义在本决策文档批准后由 Phase 2.3 产出。TypeScript 与 Node.js 是否共享同一 PathGuard 实现：第一版独立实现，共享测试向量验证语义一致性。

---

## 决策 3: 敏感路径与构建工具副作用策略

### 3.1 敏感路径三层

| 层级 | 路径模式 | write 策略 | delete 策略 | read 策略 |
|------|---------|:---:|:---:|:---:|
| L0 凭据禁止 | `.env`, `.env.*`, `*.key`, `*.pem`, `*.p12`, `secrets.*`, `credentials.*`, `.git-credentials`, `.npmrc` | 拒绝 | 拒绝 | 拒绝 |
| L1 版本控制禁止 | `.git/config`, `.git/hooks/*`, `.git/HEAD`, `.git/index` | 拒绝 | 拒绝 | 允许 |
| L2 构建产物禁止直接写 | `node_modules/`, `target/`, `dist/`, `build/`, `__pycache__/`, `.venv/`, `venv/` | 拒绝直接写 | 拒绝 | 允许 |
| L3 锁文件禁止直接写 | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`, `Cargo.lock`, `Gemfile.lock` | 拒绝直接写 | 拒绝 | 允许 |
| L4 普通受控 | 其他路径 | allowed_paths | allowed_paths | allowed_paths |

### 3.2 构建工具副作用

Maven、npm、pytest、gradle 等构建工具**在执行时**需要写入 `target/`、`node_modules/`、缓存目录和测试输出。这与直接禁止写入这些路径的策略冲突。

**决策**: 区分"Worker 直接写入"和"命令执行环境写入"。

| 写入来源 | 策略 |
|---------|------|
| Worker 直接文件 API 写入 | L0-L4 全部生效。L2/L3 拒绝写入 |
| 命令执行环境（Maven/npm/pytest 等）写入 | L0/L1 生效。L2/L3 允许（因为这是构建工具的正常行为），但**限制写入范围在 cwd 子树内** |
| 命令执行环境写入超出 cwd 子树 | 拒绝。除非用户显式授权了该路径 |

这意味着命令执行环境的可写范围 = cwd 子树（由 `allowed_paths.execute` 限制）+ L2/L3 豁免。L0 凭据路径在任何情况下都不可写。

### 3.3 暂不接受授权（v1 设计限制）

以下操作在 v1 中不提供授权路径，一律拒绝：
- 直接写入 L0 凭据文件
- 直接写入 `.git/config` 或 `.git/hooks/`
- 递归删除（必须走确认流程）
- 源或目标不在 `allowed_paths.write` 内的 move 操作

---

## 决策 4: 命令执行隔离边界

审查意见最关键的指出：**PathGuard 不能单独阻止 Shell 绕过**。cwd 检查 + 命令黑名单 ≠ 强制执行边界。

### 4.1 能力分层

| 层 | 职责 | v1 实现状态 |
|----|------|:---:|
| 强制执行边界 | 进程级文件系统隔离、命令白名单、网络限制 | ❌ 未实现（v1 公开的残余风险） |
| Worker 内部 PathGuard | cwd 校验 + 命令策略过滤 + 审计记录 | ✅ Phase 2.3 实现 |

### 4.2 v1 的残余风险声明（必须写入设计文档）

由于 v1 不实现操作系统级进程隔离，以下风险在 v1 中**公开存在**：

1. Shell 命令可使用绝对路径写入 `allowed_paths.execute` 之外的目录
2. 命令可通过 `&&`、`;`、`$()`、反引号等方式串联危险操作
3. 命令可启动子进程，子进程不受当前 PathGuard 约束
4. `git push` 等网络操作目前没有独立的授权规则（E3 完全不过滤）
5. 环境变量（`PYTHONPATH`、`NODE_PATH` 等）可能影响命令行为

### 4.3 v1 缓解措施

| 措施 | 说明 |
|------|------|
| cwd ∈ allowed_paths.execute | 限制命令的工作目录 |
| BLOCKED_COMMANDS 扩展 | 阻止 `rm`、`mv`、`cp -r`、`chmod`、`sudo`、`su`、`mkfs`、管道+curl/wget |
| DANGEROUS_PATTERNS | 检测系统路径写入（`/etc/`、`/usr/`、`/opt/`）、权限提升 |
| 环境变量审查 | 检查 `PATH`、`PYTHONPATH`、`NODE_PATH` 等是否包含非授权路径 |
| 审计记录 | 每次 validate_execute 记录完整命令、cwd、用户和环境变量快照 |

### 4.4 宣称限制

在 v1 文档中**不使用以下措辞**：
- "强制执行边界已实现"
- "命令执行已完全隔离"
- "Shell 操作已被安全沙箱限制"

替代措辞：
- "命令执行受 Worker 内部防御层限制"
- "当前尚未实现操作系统级进程隔离（此为已知残余风险）"
- "BLOCKED_COMMANDS 提供第一层防御，但不能替代进程隔离"

### 4.5 v2+ 规划

- 操作系统级沙箱（容器/VM/jail）
- 网络策略（允许/拒绝出站连接、域名白名单）
- 文件系统可写范围的内核级限制
- 资源限制（CPU/内存/磁盘/超时）

---

## 决策 5: 冲突处理、用户确认与上下文不可变

### 5.1 create_new_project 统一冲突处理

所有组件（`validate_task_context`、`Authorizer`、调用方）使用**同一规则**：

| 情况 | 结果 |
|------|------|
| 目标不存在，父目录在 `authorized_roots` 内 | 允许创建 |
| 目标不存在，父目录不在 `authorized_roots` 内 | 拒绝：`TargetParentNotAuthorized` |
| 目标已存在（文件） | 拒绝：`TargetPathConflict` |
| 目标已存在（目录） | 返回 `ConfirmationRequired`，**不静默转换为 modify_existing_project** |

### 5.2 用户确认模型

审查意见正确指出：`user_confirmation=True` 是无效的确认模型。

```python
@dataclass(frozen=True)
class UserConfirmation:
    confirmation_id: str         # 幂等键
    task_id: str                 # 绑定任务
    scope: ConfirmationScope     # 确认对象
    granted_at: str              # ISO 时间戳
    expires_at: str | None       # 有效期
    context_hash: str            # 确认时的上下文哈希

@dataclass(frozen=True)
class ConfirmationScope:
    """确认了什么操作、在什么路径上、影响范围多大"""
    target_project_path: str
    project_mode: str
    allowed_paths: dict
    estimated_impact: str        # 人类可读的影响描述
    operation_specific: dict     # 操作特定的附加信息
                                 # 如 delete: {"path": ..., "recursive": True, "estimated_files": 42}
```

**规则**:
- 确认绑定特定任务、路径和授权范围
- 目标路径或 `allowed_paths` 变化 → 确认失效，必须重新确认
- 确认可以设置有效期
- 确认决策记录在 `task_context_snapshot` 的 `authorizer_decision` 中

### 5.3 TaskContext 不可变（运行时约束，非 Python 语言级保证）

Python 的 `frozen=True` dataclass 提供结构层面的协助，但真正的不可变性由架构约束保证：

1. `task_context` 在 node-api 的任务提交时创建并固化
2. Redis 入队后，task_context 的 JSON 序列化副本不再被任何 Pipeline 阶段修改
3. Worker 在入口处读取 task_context，构造 PathGuard 实例并绑定
4. `runtime_context` 和 `artifacts` 可以变更，但不能包含 `allowed_paths`、`project_mode` 或 `target_project_path` 等授权相关字段
5. 如果任务执行中需要扩大授权范围，必须通过显式的**重新授权流程**（新确认 + 新 task_context_snapshot）

**代码约束（非 assert）**:

```python
class TaskContextValidationError(Exception):
    """Raised when task_context fails structural or semantic validation."""
    def __init__(self, message: str, reason_code: str):
        super().__init__(message)
        self.reason_code = reason_code

class AuthorizationDenied(Exception):
    """Raised when an operation is denied by PathGuard."""
    def __init__(self, message: str, reason_code: str, audit_record: dict):
        super().__init__(message)
        self.reason_code = reason_code
        self.audit_record = audit_record

class ConfirmationRequired(Exception):
    """Raised when user confirmation is required before proceeding."""
    def __init__(self, message: str, scope: ConfirmationScope):
        super().__init__(message)
        self.scope = scope
```

---

## 决策 6: Schema 来源与兼容期

### 6.1 唯一 Schema 来源

- 唯一规范来源：`contracts/task-protocol-v1.schema.json`
- `task_context` 的 `$defs` 定义在同一个文件中（通过 `$ref` 引用），不与独立文件重复定义
- `contracts/task-context-v1.schema.json` **不创建**。如果后续 task_context 需要独立版本管理，再评估拆分
- `python_worker/task_context_contract.py` 定义 Python 类型和校验逻辑，引用同一个 Schema 但不重新定义字段

### 6.2 兼容期

| 阶段 | 行为 | 时间 |
|------|------|------|
| Phase | 2.1-2.3: `build_or_extract_task_context()` 同时支持新旧协议 | 过渡期 |
| Phase | 2.4 开始: 统计旧协议流量比例 | 监控期 |
| 条件 | 旧协议流量 < 5% 且持续 7 天 | 达标 |
| 达标后 | 移除 `build_or_extract_task_context`，旧协议任务返回 `UnsupportedProtocolVersion` | 移除 |

**重要**: Phase 2.4 清理旧字段别名的代码清理，与兼容解析的移除是两个独立操作，不在同一 Phase 执行。

### 6.3 错误类型约定

所有契约相关的可编程错误使用明确的类型，不依赖字符串匹配：

| 错误类型 | 含义 | HTTP 类比 |
|---------|------|:---:|
| `TaskContextValidationError` | task_context 结构或语义校验失败 | 400 |
| `AuthorizationDenied` | PathGuard 拒绝操作 | 403 |
| `ConfirmationRequired` | 需要用户确认 | 401 |
| `UnsupportedProtocolVersion` | 协议版本不支持 | 400 |
| `TargetPathConflict` | 目标路径已存在 | 409 |
| `TargetParentNotAuthorized` | 目标父目录不在授权范围内 | 403 |

---

## 决策 7: 工作区切换与上下文绑定

### 7.1 问题

审查意见 CTX-01：如果 Worker 在执行阶段重新读取 node-api 的模块级 `workspaceRoot`（当前是单例），工作区切换后会导致任务 A 的后续阶段错误地使用工作区 B 的路径。

### 7.2 当前实现分析

```javascript
// node-api/index.js:136
let workspaceRoot = process.env.WORKSPACE_ROOT || null;

// node-api/index.js:804
workspaceRoot = path;  // 模块级可变单例
```

目前 `workspaceRoot` 是模块级可变单例。`/workspace/set` 可以随时修改它。如果任务 A 正在执行，而此时用户切换到工作区 B 并触发 `/workspace/set`，任务 A 的后续 `fileOpsHandler` 操作可能使用错误的根目录。

### 7.3 决策

**任务提交时固化上下文到 Redis**，Worker 只从自己拿到的任务数据中提取上下文，不跨任务读取 node-api 的全局状态。

```
任务提交流程:
  1. VSCode 扩展提交任务: {workspace_path, prompt, ...}
  2. node-api /task/submit:
     a. 处理 payload（兼容注入 workspace_path）
     b. 构建 task_context（包含固化后的 workspace_roots、allowed_paths 等）
     c. 将 task_context 写入 task.payload.task_context
     d. 将完整 task 写入 Redis 队列
  3. Worker 从 Redis 拉取任务:
     a. 从 task.payload.task_context 读取上下文
     b. 不从 node-api 的全局状态或环境变量重新获取 workspace_root
```

**并发验证用例 CTX-01**（补充到 v0.4 测试清单）:

```
1. 任务 A 提交（workspace=/ws/A），进入执行
2. node-api 收到 /workspace/set {workspace: /ws/B}
3. 任务 B 提交（workspace=/ws/B），进入执行
4. 验证:
   a. 任务 A 的所有阶段使用 /ws/A 的上下文
   b. 任务 B 的所有阶段使用 /ws/B 的上下文
   c. 任务 A 的 file_ops 写入 /ws/A 而非 /ws/B
   d. 任务 B 的 file_ops 写入 /ws/B 而非 /ws/A
```

---

## 决策 8: 入口审计验收标准

### 8.1 措辞修正

| v0.3 措辞 | v0.4 修正 |
|----------|----------|
| "35 个入口全注入" | "35 个候选调用点逐项核验，并覆盖全部实际副作用执行边界" |
| "W3 已受控" | "W3 (FileOpsHandler) 已有 √/symlink 越界检查，尚未实现 allowed_paths 子目录限制" |
| "E1 危险命令过滤" | "E1 有字符串级黑名单防御层，不构成命令隔离强制执行边界" |

### 8.2 验收标准

安全覆盖率不能按"函数调用数"计算。一个通用 Shell 入口（E1）可能比十个直接文件写入点（W1-W10）影响更大。

| 审计对象 | 验收要求 |
|---------|---------|
| 直接读写点 (W1-W10) | 逐项验证路径来源、是否经过 PathGuard、是否存在绕过路径 |
| FileOps 链路 (W3) | 区分 Python 生成端、序列化传输端和 node-api 执行端，验证全链路 |
| 命令执行点 (E1-E7) | 验证 cwd 约束、命令过滤、环境变量审查、间接副作用能力 |
| 间接文件系统操作 | 测试 E1/E3 是否可通过 Shell 访问授权范围外的资源 |
| 符号链接 | 验证已有符号链接不会被利用进行路径穿越 |

---

## 决策 9: 回滚测试成功条件

### 9.1 问题

审查意见指出 ROLLBACK-01 的条件不够具体。"恢复不覆盖用户未提交修改"需要明确的定义。

### 9.2 成功条件

```
ROLLBACK-01 验证步骤:
  1. 任务执行前: 记录文件 A 的 SHA256
  2. 任务执行: 修改文件 A, 创建文件 B
  3. 任务完成后: 用户手动修改文件 A（用不同的内容）
  4. 执行回滚:
     a. 文件 A → 不覆盖（因为用户已修改），生成冲突报告
     b. 文件 B → 删除（因为任务创建的）
  5. 验证:
     a. 文件 A 的内容 = 步骤 3 用户修改后的内容
     b. 文件 B 不存在
     c. 冲突报告中包含文件 A 的路径、任务后 SHA256、用户修改后 SHA256
```

---

## 决策 10: 第一版不支持的能力

以下能力明确不在 v1 范围内，避免设计文档暗示它们会被实现：

| 能力 | 状态 | 说明 |
|------|:---:|------|
| 操作系统级进程隔离 | ❌ v2+ | v1 仅依赖 Worker 内部防御层 |
| 多根工作区 (multi-root) | ❌ v2+ | v1 仅支持单根，多根请求拒绝并返回明确错误 |
| 网络策略控制 | ❌ v2+ | git push 等网络操作暂不受单独授权规则约束（除命令黑名单外） |
| 资源限制（CPU/内存/磁盘） | ❌ v2+ | 命令执行无资源配额 |
| 跨任务授权传递 | ❌ v2+ | 每个任务独立授权，不继承其他任务的 allowed_paths |
| LLM 意图分类器 | ❌ 第一版 | Resolver 仅使用规则引擎 |

---

> **审批门**: 以上 10 项决策全部审批通过后，进入 Phase 2.1。
>
> **下一步**: 审批通过 → Phase 2.1（契约层：仅 Schema 和校验逻辑，不改生产代码）。