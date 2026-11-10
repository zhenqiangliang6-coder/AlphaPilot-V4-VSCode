# AlphaPilot Phase 2 架构设计：统一任务上下文与项目策略

> 版本: v0.4 | 日期: 2026-10-29 | 状态: 设计阶段（第三次修订，Phase 2.0 门控决策已固化）
>
> 变更: 响应 v0.3 审查意见。消除 6 个 P0 阻塞项和全部 P1 设计细节。新增 Phase 2.0 门控决策文档（`phase2-gate-decisions.md`）作为前置依赖。
> **与 v0.3 的最大差异**: 措辞从"35 个入口全注入"改为"35 个候选调用点逐项核验并覆盖实际副作用执行边界"。命令执行的隔离边界被明确标记为 Phase 1 残余风险。引入 `workspace_roots` / `authorized_roots` / `allowed_paths` 三层语义和六种操作各自独立的授权规则。

---

## 0. 前置依赖

**本文档的 Phase 2.1-2.4 实施以 Phase 2.0 门控决策文档审批为前提。**

[Phase 2.0 门控决策](./phase2-gate-decisions.md) 已固化：

| 决策 | 内容 |
|------|------|
| 决策 1 | `workspace_roots` / `authorized_roots` / `allowed_paths` 三层语义分离 |
| 决策 2 | 六种操作能力模型（read/write/create_dir/delete/move/execute）独立授权语义 |
| 决策 3 | 敏感路径五层 + 构建工具副作用策略 |
| 决策 4 | 命令执行隔离边界：v1 残余风险声明 + 缓解措施 |
| 决策 5 | create_new_project 冲突处理、UserConfirmation 对象模型、TaskContext 不可变约束 |
| 决策 6 | 唯一 Schema 来源 + 兼容期退出条件 + 错误类型约定 |
| 决策 7 | 工作区切换时上下文固化到任务，不依赖模块级全局状态 |
| 决策 8 | 入口审计验收标准：从"全注入"改为"逐项核验 + 副作用覆盖" |
| 决策 9 | 回滚测试成功条件（状态对比 + 冲突报告） |
| 决策 10 | 第一版不支持的能力清单 |

**此后文档仅引用门控决策的结论，不重复其论述。**

---

## 0. 审计结论

### 0.1 入口盘点：七类文件系统能力 × 五种组件

**审计原则**: 不预设"只审计写入"，不混淆"表项数量"与"实际执行点"，不把"搜索未发现"等同于"已证明不存在"。

**审计范围**: Python Worker / Node.js Worker / TypeScript Worker / Java Worker / node-api 的生产代码。排除 `tests/` 和锁文件等构建产物。

**搜索关键词**: `writeFile`/`writeFileSync`/`write_text`/`writeBytes`/`open(..., 'w')`/`truncate`/`mkdir`/`makedirs`/`createDirectories`/`readFile`/`read_text`/`readBytes`/`open(..., 'r')`/`os.walk`/`rglob`/`scandir`/`readdir`/`subprocess.run`/`Popen`/`exec`/`execAsync`/`spawn`/`ProcessBuilder`/`shutil`/`copy`/`move`/`rename`/`unlink`/`rmdir`/`tempfile`/`zipfile`/`tarfile`/`symlink`/`Files.delete`/`File.renameTo`

**关键词搜索无法证明盘点穷尽。最终审计记录应注明扫描目录、排除规则、人工追踪的调用链和未验证的动态执行路径。**

---

#### A. 文件读取与枚举 — 18 个候选调用点（均无访问控制）

| # | 组件 | 文件:行号 | 操作 | 路径来源 |
|---|------|-----------|------|---------|
| R1 | Python | `context_builder.py:104` | `os.walk(root)` | `workspace_path` |
| R2 | Python | `context_builder.py:357,417,497,534,594,621` | `path.read_text()` | rglob 结果 |
| R3 | Python | `context_builder.py:404,475,488,575` | `root.rglob()` | `workspace_path` |
| R4 | Python | `analyze_architecture.py:106` | `root.rglob("*.py")` | `workspace_path` |
| R5 | Python | `analyze_architecture.py:120` | `open(py_file, "r")` | rglob 结果 |
| R6 | Python | `code_analyzer.py:176` | `open(filepath, "r")` | `os.walk` 结果 |
| R7 | Python | `code_analyzer.py:236` | `os.walk(workspace_path)` | `workspace_path` |
| R8 | Python | `scan_workspace.py:201` | `os.scandir(current)` | `workspace_path` |
| R9 | Python | `changelog_step.py:141` | `open(changelog_path, "r")` | `meta["workspace_path"]` |
| R10 | Python | `git_upload.py:130,139` | `open(.gitignore, "r")` + `os.walk` | `workspace_path` |
| R11 | Python | `qwen_worker_v2.py:652` | `open(full_path, "r")` | file_ops.path |
| R12 | Node.js | `fix_step.js:20,156` | `readFile()` | context 传递 |
| R13 | Node.js | `environment_manager.js:24,129` | `readFile()` | `workspace_root` |
| R14 | Java | `TestStep.java:149` | `Files.readString()` | `workspace_root` |
| R15 | Java | `JavaEnvironmentManager.java:84,445` | `Files.walk()` | `workspaceRoot` |
| R16 | Java | `JavaEnvironmentManager.java:449` | `Files.lines()` | walk 结果 |
| R17 | Java | `FixStep.java:309` | `Files.readString()` | `workspaceRoot` |
| R18 | TS | `compile_step.js:21,98,133` | `readFile()` + `access()` | `workspace_root` |

**结论**: 全部 18 个读取候选调用点无任何访问控制。读取通常比写入宽，但在包含凭据文件的目录中，读取也需要边界。

---

#### B. 创建与写入 — 10 个候选执行点

| # | 组件 | 文件:行号 | 操作 | 路径来源 | 安全检查 | 备注 |
|---|------|-----------|------|---------|---------|------|
| W1 | Python | `test_step.py:264-270` | `test_dir.mkdir()` + `test_path.write_text()` | `meta["workspace_path"]` | ❌ | 直接写入点 |
| W2 | Python | `changelog_step.py:141,150` | `open(changelog_path, "w")` + `f.write()` | `meta["workspace_path"]` | ❌ | 直接写入点 |
| W3 | Python→node-api | `write_step.py`→`file_ops.py`→`FileOpsHandler.js:133,141` | Python 生成 file_ops → 序列化传输 → node-api `fs.writeFileSync()` | Python 端: LLM 生成 → node-api 端: `FileOpsHandler.workspaceRoot + op.path` | ⚠️ 有 `..`/symlink 越界禁止，**未实现** allowed_paths | 跨组件链路：生成端/传输端/执行端三层 |
| W4 | Node.js | `write_step.js:55-56` | `mkdir(dirname)` + `writeFile(filePath)` | file_ops.op.path | ❌ | 直接写入点 |
| W5 | Node.js | `test_step.js:45-46` | `mkdir(join(root, 'tests'))` + `writeFile(testPath)` | `context.workspace_root` | ❌ | 直接写入点 |
| W6 | Node.js | `test_step.js:126` | `writeFile(configPath, config)` | `context.workspace_root` + 固定子路径 | ❌ | 直接写入点 |
| W7 | TS | `compile_step.js:133` | `writeFile(configPath, ...)` | `context.workspace_root` + 固定子路径 | ❌ | 直接写入点 |
| W8 | Java | `WriteStep.java:78-79` | `Files.createDirectories()` + `Files.writeString()` | `workspaceRoot` + file_ops.path | ❌ | 直接写入点 |
| W9 | Java | `WriteStep.java:244-245` | `Files.createDirectories()` | `workspaceRoot` + 固定 Maven 结构 | ❌ | 直接写入点 |
| W10 | Java | `TestStep.java:58,66` | `Files.createDirectories()` + `Files.writeString()` | `workspaceRoot` | ❌ | 直接写入点 |

**口径修正**: v0.2 统计为"12 个写入入口"含读取项。W3 是跨组件的生产-传输-执行链路（三个环节需分别核验）。

---

#### C. 命令与子进程执行 — 7 个候选调用点

| # | 组件 | 文件:行号 | 操作 | Shell? | 现有过滤 |
|---|------|-----------|------|:---:|:---:|
| E1 | Python | `shell_executor.py:144` | `subprocess.run(cmd, shell=True, cwd=cwd)` | ✅ | ⚠️ 5 个硬编码模式（不阻止 `rm somefile`/`mv`/`cp`/`rm -rf /tmp/xxx`） |
| E2 | Python | `test_step.py:279` | `subprocess.run(["pytest", ..., cwd=workspace_path])` | ❌ list | ❌ |
| E3 | Python | `git_upload.py:66,89,284` | `_run_cmd()`→`subprocess.run(cmd, shell=True, cwd)` | ✅ | **无任何过滤** |
| E4 | Python | `code_analyzer.py:191` | `subprocess.run(["cloc", ...])` | ❌ list | ❌ |
| E5 | Node.js | `environment_manager.js:220` | `execAsync(cmd, {cwd: root})` | ✅ | ❌ |
| E6 | TS | `compile_step.js:73` | `execAsync('npx tsc --noEmit', {cwd: root})` | ✅ | ❌ |
| E7 | Java | `JavaEnvironmentManager.java:306,331` | `ProcessBuilder(cmd).directory(workspaceRoot).start()` | ✅ | ❌ |

**关键发现**:
- E1 `_is_dangerous()` 仅阻止 5 个硬编码模式；不阻止 `rm somefile`、`mv`、`cp`、`rm -rf /tmp/xxx`（显式排除 `/tmp`）
- E3 `_run_cmd()` **完全无任何过滤**——现在只用于 git 命令，但无架构保证
- 所有 `shell=True` 入口既无 `allowed_paths` 约束，也无 cwd 子路径限制
- **一个通用 Shell 入口（E1）可能比十个直接写入点（W1-W10）影响更大**

---

#### D. 目录创建 — 含于 B 类写入操作

W1/W4/W5/W8/W9/W10 均包含 `mkdir`/`Files.createDirectories`。

---

#### E. 删除与移动

| 调用方式 | 说明 |
|---------|------|
| 直接 API | 未发现生产代码中的直接调用 |
| Shell 命令路径 | E1 可执行 `rm`、`mv`（不被 `_is_dangerous` 拦截）；E3 完全不过滤 |

**结论**: "未发现直接调用" ≠ "能力不存在"。Shell 命令执行路径是删除和移动能力的实际载体。

---

#### F. 复制 / 压缩 / 临时文件

| 调用方式 | 说明 |
|---------|------|
| 直接 API | 未发现生产代码中的直接调用 |
| Shell 命令路径 | E1+E3 可执行 `cp`/`tar`/`zip`/`unzip` |

---

#### G. 符号链接

未发现 `os.symlink()` 等直接创建 API。但需验证现有符号链接不会被用于路径穿越。

---

### 0.2 入口盘点总表（修正措辞）

| 能力类别 | 候选调用点 | 可通过 Shell | 当前约束状态 |
|---------|:---:|:---:|------|
| A. 读取与枚举 | 18 | — | 全部无访问控制 |
| B. 创建与写入（直接） | 10 | E1/E3 | W3 有 partial 检查，其余无 |
| C. 命令执行 | 7 | N/A | 仅 E1 有字符串级黑名单 |
| D. 目录创建 | (含于 B) | E1/E3 | 无 |
| E. 删除与移动（直接） | 0 | E1/E3 | 无 |
| F. 复制/压缩/临时文件（直接） | 0 | E1/E3 | 无 |
| G. 符号链接（直接创建） | 0 | — | — |

**验收标准**: 35 个候选调用点逐项核验，并覆盖全部实际副作用执行边界。**安全覆盖率不以函数调用数量计算**——一个通用 Shell 入口（E1/E3）可能比十个直接文件写入点影响更大。

### 0.3 workspace_path 别名链（当前存在的 4 种取值路径）

```
VSCode: workspaceFolders[0].uri.fsPath
  → node-api: workspaceRoot (模块级可变单例——Phase 2.2 改为任务级固化)
    → Redis: task.payload.workspace_path
      → Python: meta["workspace_path"] / workspace_scan["root"]
      → Node.js: payload.workspace_path || task.workspace_path || '.'
      → Java: ctx["workspace_root"] || ctx["workspace_path"] || meta["workspace_path"] || "."
```

### 0.4 现有 contracts/ 结构

`contracts/task-protocol-v1.schema.json`:
- `payload` 类型为 `type: object`（无约束），`additionalProperties: true`
- 不存在 `task_context` / `workspace_path` / `target_project_path` / `allowed_paths` 的 schema 定义
- Schema 兼容 ≠ 运行时兼容——需检查 Redis 序列化与 Worker 解析链路

---

## 1. 架构边界定义

### 1.1 四层上下文模型

审查意见反复强调：不可变配置、可变运行时状态、累积产物和审计快照必须分开。

```
┌─────────── 四层上下文模型 ───────────┐
│                                      │
│ task_context (不可变)                 │
│   入队后禁止修改。需要调整 → 重新授权  │
│   Python 代码级: frozen dataclass     │
│   架构保证: Pipeline 阶段不写回       │
│                                      │
│ runtime_context (可变)                │
│   阶段执行时的工作状态                │
│   不能包含 allowed_paths、project_mode│
│   或 target_project_path 等授权字段   │
│                                      │
│ artifacts (累积)                      │
│   分析结果、计划、补丁、file_ops      │
│   测试报告、构建日志                  │
│                                      │
│ task_context_snapshot (审计)           │
│   执行时的 context 完整副本            │
│   resolver_proposal 和                │
│   authorizer_decision 为独立审计对象  │
│   不能将建议置信度解释为授权依据       │
│                                      │
└──────────────────────────────────────┘
```

| 对象 | 职责 | 可变? | 约束 |
|------|------|:---:|------|
| `task_context` | 任务目标、项目策略、路径授权 | 否 | 入队固化，阶段不可写回 |
| `runtime_context` | 执行阶段状态、工作变量 | 是 | 不含授权字段 |
| `artifacts` | 分析结果、补丁、报告 | 是 | 累积，不可反向修改授权 |
| `task_context_snapshot` | 审计与复现 | 否 | resolver_proposal ≠ authorizer_decision |

### 1.2 字段来源契约

| 字段 | 来源 | LLM 可直接决定？ |
|------|------|:---:|
| `workspace_roots` | Extension 提供 | 否 |
| `authorized_roots` | 从 workspace_roots 截取或用户显式添加 | 否 |
| `target_project_path` | 策略决策 + 路径校验 | 仅可建议 |
| `project_mode` | 用户明确指令优先，规则辅助 | 仅可建议 |
| `target_language` | 显式要求 > 项目约定 > 工具能力 | 不可覆盖显式要求 |
| `allowed_paths` | Authorizer 基于 authorized_roots 计算 | 否 |
| `validation_plan` | 项目构建配置 + 任务要求 | 可建议，需校验可执行性 |

---

## 2. TaskContext 统一契约设计

### 2.1 协议位置

`task-protocol-v1.schema.json` 的 `queuedTask.payload.task_context`。唯一 Schema 来源，不创建独立的 `task-context-v1.schema.json`。

```json
{
  "payload": {
    "task_context": {
      "context_version": "1.0",
      "workspace_roots": ["/absolute/path/to/workspace"],
      "authorized_roots": ["/absolute/path/to/workspace"],
      "primary_root": "/absolute/path/to/workspace",
      "target_project_path": "/absolute/path/to/workspace/projects/image_animation",
      "project_mode": "create_new_project",
      "target_language": "java",
      "target_stack": ["spring-boot", "maven"],
      "allowed_paths": {
        "read": ["/absolute/path/to/workspace"],
        "write": ["/absolute/path/to/workspace/projects/image_animation"],
        "execute": ["/absolute/path/to/workspace/projects/image_animation"]
      },
      "create_if_missing": true,
      "require_user_confirmation": false,
      "integration_required": false,
      "validation_plan": { "compile": true, "test": true, "lint": false },
      "parent_task_id": null,
      "created_at": "2026-10-29T12:00:00Z"
    }
  }
}
```

taskResult 回传 snapshot:

```json
{
  "task_context_snapshot": {
    "context_version": "1.0",
    "task_context": { },
    "resolver_proposal": {
      "strategy": "create_new_project",
      "confidence": 0.92,
      "reasoning": "用户请求新建 Java 项目，工作区无同名项目"
    },
    "authorizer_decision": {
      "authorized": true,
      "require_user_confirmation": false,
      "allowed_paths_source": "template:create_new_project",
      "user_confirmations": []
    },
    "context_hash": "sha256:abc...",
    "hash_algorithm": "sha256",
    "hash_input_fields": [
      "context_version", "workspace_roots", "authorized_roots",
      "primary_root", "target_project_path", "project_mode",
      "target_language", "allowed_paths", "create_if_missing",
      "integration_required", "created_at"
    ]
  }
}
```

**context_hash 定义**:
- 对上述 `hash_input_fields` 进行规范化 JSON 序列化（排序键、紧凑格式）
- 使用 SHA256 哈希
- `hash_algorithm` 和 `hash_input_fields` 记录在快照中
- 时间戳参与哈希但不用于敏感信息检测
- Worker 无权修改快照；快照由 node-api 在任务提交时生成，Worker 只读

### 2.2 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `context_version` | string | ✅ | 契约版本 |
| `workspace_roots` | string[] | ✅ | VS Code 打开的工作区根目录（单根有效，多根拒绝） |
| `authorized_roots` | string[] | ✅ | 经授权后允许访问的根目录。⊆ workspace_roots 或用户显式添加 |
| `primary_root` | string | ✅ | 主根 |
| `target_project_path` | string | ✅ | 实际操作的项目目录 |
| `project_mode` | enum | ✅ | `modify_alphapilot` / `modify_existing_project` / `create_new_project` / `integrate_projects` |
| `target_language` | enum | ✅ | `python` / `java` / `javascript` / `typescript` |
| `target_stack` | string[] | ❌ | 技术栈提示 |
| `allowed_paths` | object | ✅ | `read` / `write` / `execute` 范围（见决策 2） |
| `create_if_missing` | boolean | ❌ | create_new_project: 目标不存在时创建 |
| `require_user_confirmation` | boolean | ❌ | Authorizer 判断 |
| `integration_required` | boolean | ❌ | 跨项目集成 |
| `integration_targets` | string[] | ❌ | 集成目标路径；每个路径必须在 authorized_roots 内 |
| `validation_plan` | object | ❌ | 验证步骤开关 |
| `parent_task_id` | string | ❌ | 父任务 ID |
| `created_at` | string | ❌ | ISO 时间戳 |

### 2.3 校验规则

路径校验使用显式异常类型，**不使用 assert**（Python `-O` 模式下 assert 会被移除）：

```python
def validate_task_context(tc: dict) -> None:
    if tc is None:
        raise TaskContextValidationError("task_context 缺失", "MISSING_CONTEXT")

    workspace_roots = [Path(r).resolve() for r in tc["workspace_roots"]]

    # 单根约束（v1）
    if len(workspace_roots) > 1:
        raise TaskContextValidationError(
            "v1 不支持多根工作区（multi-root workspace）",
            "MULTI_ROOT_NOT_SUPPORTED",
        )

    for root in workspace_roots:
        if not root.is_dir():
            raise TaskContextValidationError(
                f"workspace_root 不存在: {root}",
                "WORKSPACE_ROOT_NOT_FOUND",
            )

    # authorized_roots ⊆ workspace_roots（或用户显式添加——v1 先仅检查子集）
    authorized = [Path(r).resolve() for r in tc["authorized_roots"]]
    for ar in authorized:
        if not any(_is_subpath_of(ar, wr) for wr in workspace_roots):
            raise TaskContextValidationError(
                f"authorized_root 不在 workspace_roots 内: {ar}",
                "AUTHORIZED_ROOT_OUTSIDE_WORKSPACE",
            )

    tp = Path(tc["target_project_path"]).resolve()
    mode = tc.get("project_mode")

    if mode == "create_new_project":
        if not tc.get("create_if_missing"):
            raise TaskContextValidationError(
                "create_new_project 需要 create_if_missing=True",
                "MISSING_CREATE_IF_MISSING",
            )
        parent = tp
        while parent != parent.parent and not parent.exists():
            parent = parent.parent
        if not parent.is_dir():
            raise TaskContextValidationError(
                f"目标路径无可用的已存在父目录: {tp}",
                "TARGET_PARENT_NOT_FOUND",
            )
        if not _is_authorized(tp, authorized):
            raise TaskContextValidationError(
                f"目标不在 authorized_roots 内: {tp}",
                "TARGET_NOT_AUTHORIZED",
            )
        if tp.exists():
            raise ConfirmationRequired(
                "create_new_project 目标已存在，不可静默复用",
                scope=ConfirmationScope(
                    target_project_path=str(tp),
                    project_mode="create_new_project",
                    allowed_paths=tc["allowed_paths"],
                    estimated_impact=f"目标路径已存在: {tp}",
                    operation_specific={"existing_path": str(tp), "is_directory": tp.is_dir()},
                ),
            )
    elif mode == "integrate_projects":
        integration_targets = tc.get("integration_targets", [])
        if not integration_targets:
            raise TaskContextValidationError(
                "integrate_projects 需要 integration_targets",
                "MISSING_INTEGRATION_TARGETS",
            )
        for it in integration_targets:
            it_path = Path(it).resolve()
            if not _is_authorized(it_path, authorized):
                raise TaskContextValidationError(
                    f"集成目标不在 authorized_roots 内: {it}",
                    "INTEGRATION_TARGET_NOT_AUTHORIZED",
                )
        # 主目标也必须有效
        if not tp.is_dir():
            raise TaskContextValidationError(
                f"target_project_path 不存在: {tp}",
                "TARGET_NOT_FOUND",
            )
        if not _is_authorized(tp, authorized):
            raise TaskContextValidationError(
                f"目标不在 authorized_roots 内: {tp}",
                "TARGET_NOT_AUTHORIZED",
            )
    else:
        if not tp.is_dir():
            raise TaskContextValidationError(
                f"target_project_path 不存在: {tp}",
                "TARGET_NOT_FOUND",
            )
        if not _is_authorized(tp, authorized):
            raise TaskContextValidationError(
                f"目标不在 authorized_roots 内: {tp}",
                "TARGET_NOT_AUTHORIZED",
            )

    if mode not in VALID_MODES:
        raise TaskContextValidationError(f"无效 project_mode: {mode}", "INVALID_MODE")

    if tc["target_language"] not in SUPPORTED_LANGUAGES:
        raise TaskContextValidationError(
            f"不支持 target_language: {tc['target_language']}",
            "UNSUPPORTED_LANGUAGE",
        )

    for domain in ("read", "write", "execute"):
        for p in tc["allowed_paths"].get(domain, []):
            normalized = Path(p).resolve()
            if not _is_authorized(normalized, authorized):
                raise TaskContextValidationError(
                    f"allowed_paths.{domain} 路径不在 authorized_roots 内: {p}",
                    "ALLOWED_PATH_OUTSIDE_AUTHORIZED",
                )
```

### 2.4 新项目 `allowed_paths` 模板（v0.4 修订）

审查意见指出：将 `target.parent` 直接作为读授权范围太宽。

```python
def new_project_allowed_paths(target: str) -> dict:
    tp = Path(target).resolve()
    return {
        "read": [
            str(tp),  # 目标目录（创建后即可读取其内容）
            # 不将 tp.parent 加入 read —— 新项目不需要读取父目录的所有内容
            # 如需读取特定参考文件（如模板），由 Authorizer 根据任务类型精确添加
        ],
        "write": [str(tp)],
        "execute": [str(tp)],
    }
```

### 2.5 过渡期策略

```python
def build_or_extract_task_context(payload: dict) -> dict:
    if "task_context" in payload:
        tc = payload["task_context"]
        validate_task_context(tc)
        return tc

    LOG.warning("task_context 缺失，尝试兼容解析（Phase 2.4 监控期后移除）")

    ws_path = payload.get("workspace_path")
    if not ws_path or not Path(ws_path).is_dir():
        raise TaskContextValidationError(
            "旧协议任务缺少有效 workspace_path",
            "COMPAT_MISSING_WORKSPACE_PATH",
        )

    tc = {
        "context_version": "1.0-compat",
        "workspace_roots": [ws_path],
        "authorized_roots": [ws_path],
        "primary_root": ws_path,
        "target_project_path": ws_path,
        "project_mode": "modify_existing_project",
        "target_language": payload.get("target_language") or _infer(payload),
        "allowed_paths": _minimal_allowed_paths(ws_path),
        "created_at": now_iso(),
    }
    validate_task_context(tc)
    return tc
```

**约束**: Feature flag 关闭 ≠ 安全关闭。兼容上下文同样经过 `validate_task_context()` + PathGuard。

---

## 3. ProjectStrategy：分离建议与授权

### 3.1 两层架构

```
Resolver (建议者)          Authorizer (授权者)
输入: user_prompt           输入: StrategyProposal
      workspace_roots             authorized_roots
      workspace_structure         user_confirmations
      active_file
                          职责: 验证存在性/授权范围
职责: 提出策略建议               冲突检测/影响评估
无权: 授予权限                  生成 allowed_paths

输出: StrategyProposal     输出: AuthorizedStrategy
      (confidence ≠ 授权)        (唯一安全权限来源)
```

### 3.2 决策优先级

```
P1: 用户明确指令
P2: 规则推断
P3: 询问用户
P4 (可选): LLM 意图分类（不绕过 Authorizer）
```

### 3.3 Authorizer 验证规则（显式错误类型）

```python
class Authorizer:
    def authorize(self, proposal, authorized_roots, user_confirmations=None):
        # 1. 目标存在性
        if proposal.mode == "create_new_project":
            target = Path(proposal.target_path)
            parent = target
            while parent != parent.parent and not parent.exists():
                parent = parent.parent
            if not parent.exists():
                raise TaskContextValidationError(
                    f"无可用的已存在父目录: {target}",
                    "TARGET_PARENT_NOT_FOUND",
                )
            if target.exists():
                raise ConfirmationRequired(
                    "create_new_project 目标已存在",
                    scope=ConfirmationScope(
                        target_project_path=str(target),
                        project_mode="create_new_project",
                        allowed_paths={},
                        estimated_impact=f"目标路径已存在: {target}",
                        operation_specific={"existing_path": str(target)},
                    ),
                )
        else:
            if not Path(proposal.target_path).is_dir():
                raise TaskContextValidationError(
                    f"target_project_path 不存在: {proposal.target_path}",
                    "TARGET_NOT_FOUND",
                )

        # 2. 授权范围
        if not _is_authorized(Path(proposal.target_path), authorized_roots):
            raise AuthorizationDenied(
                f"目标不在 authorized_roots 内: {proposal.target_path}",
                "TARGET_NOT_AUTHORIZED",
                audit_record={"target": proposal.target_path, "authorized_roots": [str(r) for r in authorized_roots]},
            )

        # 3. 高影响确认（绑定 scope）
        if proposal.mode in ("modify_alphapilot", "integrate_projects"):
            confirmed = self._find_confirmation(proposal, user_confirmations or [])
            if not confirmed:
                raise ConfirmationRequired(
                    f"模式 {proposal.mode} 需要用户确认",
                    scope=ConfirmationScope(
                        target_project_path=proposal.target_path,
                        project_mode=proposal.mode,
                        allowed_paths={},
                        estimated_impact="修改 AlphaPilot 源码或跨项目集成",
                        operation_specific={},
                    ),
                )

        # 4. 生成 allowed_paths
        allowed = TEMPLATES[proposal.mode](proposal.target_path, authorized_roots)
        return AuthorizedStrategy(proposal, allowed)

    def _find_confirmation(self, proposal, confirmations):
        for c in confirmations:
            if (c.scope.target_project_path == proposal.target_path
                and c.scope.project_mode == proposal.mode
                and not self._is_expired(c)):
                return c
        return None
```

---

## 4. 路径安全策略

### 4.1 强制执行边界（已知暂未实现） + Worker 内部 PathGuard（防御层）

**重要声明**: [Phase 2.0 门控决策 4](./phase2-gate-decisions.md) 明确规定：v1 无操作系统级进程隔离。命令执行存在残余风险。

```
层 1: 强制执行边界（架构目标，v1 未实现）
  - 进程级文件系统隔离: ❌ v2+
  - 命令白名单: ❌ v2+
  - 网络策略: ❌ v2+
  - 资源限制: ❌ v2+

层 2: Worker 内部 PathGuard（v1 唯一防御层）
  - cwd 校验 + 命令策略过滤 + 环境变量审查 + 审计记录
  - 不宣称"命令执行已完全隔离"
  - 命令仍可能通过绝对路径、子进程或环境变量影响授权范围外的文件
```

### 4.2 PathGuard 六种安全能力（操作能力模型，见决策 2）

| 方法 | 允许域 | 语义 |
|------|:---:|------|
| `validate_read(path)` | `allowed.read` | 读取内容或枚举 |
| `validate_write(path)` | `allowed.write` + 敏感路径策略 | 创建/覆盖文件 |
| `validate_delete(path, recursive=False)` | `allowed.write` + 确认 | 删除文件/空目录；递归需确认 |
| `validate_create_dir(path)` | `allowed.write` + 父目录在 `allowed.write ∪ allowed.read` | 创建目录 |
| `validate_move(src, dest)` | 两端均在 `allowed.write` | 移动/重命名 |
| `validate_execute(cwd, command)` | `allowed.execute` + 命令策略 | 命令执行 |

### 4.3 安全检查流水线

```
Step 1: resolve()         规范化
Step 2: authorized_roots   根授权
Step 3: allowed_paths      域检查
Step 4: sensitive_path     敏感分层
Step 5: command_policy     (execute only)
Step 6: audit_log          审计
```

### 4.4 安全不变量

- PathGuard 拒绝不可覆盖
- Worker 不可替换 PathGuard
- symlink 用 `realpath()` 检查
- TOCTOU: `Path.resolve()` 与最终文件操作之间仍可能存在竞争——这是 Python 层面的已知限制，不是充分保证。需要操作系统级隔离才是真正的解决方案

### 4.5 敏感路径五层（见决策 3）

| 层级 | 路径模式 | write | delete | read |
|------|---------|:---:|:---:|:---:|
| L0 凭据禁止 | `.env`, `*.key`, `*.pem`, `secrets.*` | 拒绝 | 拒绝 | 拒绝 |
| L1 版本控制禁止 | `.git/config`, `.git/hooks/*` | 拒绝 | 拒绝 | 允许 |
| L2 构建产物禁止直接写 | `node_modules/`, `target/`, `dist/` | 拒绝直接写 | 拒绝 | 允许 |
| L3 锁文件禁止直接写 | `*.lock` | 拒绝直接写 | 拒绝 | 允许 |
| L4 普通受控 | 其他 | allowed_paths | allowed_paths | allowed_paths |

**构建工具副作用豁免**: 命令执行环境可写入 L2/L3 路径（这是构建工具的正常行为），但写入范围限制在 cwd 子树内。L0/L1 永不豁免。

### 4.6 命令安全策略（防御层，非隔离边界）

```
validate_execute(cwd, command):

  1. cwd 必须在 allowed.execute 内
  2. BLOCKED_COMMANDS 扩展（v0.3 → v0.4 不变）:
     - rm, mv, cp -r, chmod, sudo, su, mkfs, dd
     - 管道 + curl/wget
     - /tmp 排除规则已移除
  3. 环境变量审查 (PATH, PYTHONPATH, NODE_PATH)
  4. 系统路径检查 (/etc/, /usr/, /opt/)
  5. 审计: 完整命令 + cwd + 用户 + 环境变量快照

残余风险（v1 公开声明）:
  命令可通过绝对路径写入 allowed.execute 之外的目录
  命令可通过 &&、;、$()、反引号串联危险操作
  子进程不受当前 PathGuard 约束
  git push 等网络操作暂无独立授权规则
```

### 4.7 35 个候选调用点 PathGuard 注入计划（Phase 2.3，不是入口计数验收标准）

注入计划以表格列出只是因为 Phase 2.3 需要知道在哪里加调用。**Phase 2.4 的安全验收不以"35 个注入点全部加了调用"为标准，而以"实际执行边界验证"为标准。**

**Python Worker:**

| 候选点 | 注入 | 风险级别 |
|------|------|:---:|
| R1-R11 | `validate_read()` | 中 |
| W1 | `validate_create_dir()` + `validate_write()` | 高 |
| W2 | `validate_write(changelog_path)` | 高 |
| W3 生成端 | `validate_write()` — file_ops 生成前校验 | 高 |
| W3 执行端 | FileOpsHandler: allowed_paths 检查 | **最高** |
| E1 | `validate_execute(cwd, command)` — shell_executor | **最高** |
| E2-E4 | `validate_execute()` | 高 |

**Node.js / TS / Java Worker:** 见 [Phase 2.0 门控决策 8](./phase2-gate-decisions.md)，详细注入计划在 Phase 2.3 分组件展开。

---

## 5. 验收测试设计

### 5.1 E2E（18 项，新增 CTX-02 并发验证）

| ID | 场景 | 验收条件 |
|----|------|---------|
| E2E-01 | 修改 AlphaPilot | 目标指向源码模块 |
| E2E-02 | 新建 Java 工具 | 目标在 `projects/` 下 |
| E2E-03 | 新建 TS 项目 | tsconfig 正确位置 |
| E2E-04 | Pipeline 一致性 | 全阶段同一 target_project_path |
| E2E-05 | 工作区切换 | 新任务使用新 workspace_roots |
| E2E-06 | `..` 穿越 | PathGuard 拒绝 |
| E2E-07 | symlink 逃逸 | `realpath()` 捕获 |
| E2E-08 | 缺少 workspace_roots | 明确错误 |
| E2E-09 | 缺少 task_context | 兼容上下文+WARNING |
| E2E-10 | Pipeline 失败 | 报告已完成/失败阶段 |
| E2E-11 | 敏感路径保护 | L0 路径拒绝 |
| E2E-12 | 现有项目修改 | 保留构建方式 |
| SEC-01 | 执行边界验证 | 从 Shell 入口尝试访问 `allowed_paths` 外资源 → 验证实际隔离效果（明确：v1 可能无法完全阻止） |
| CTX-01 | 工作区切换上下文绑定 | 任务 A（ws/A）执行中切换 ws/B，A 仍使用 ws/A |
| CTX-02 | 并发上下文隔离 | A 和 B 同时执行，互不干扰 |
| PATH-01 | 目标不存在 | 父目录合法 → 允许；越界 → 拒绝 |
| ROLLBACK-01 | 用户修改恢复 | 任务后用户修改的文件不覆盖，生成冲突报告 |
| AUDIT-01 | 审计 | snapshot 含 context_hash、策略决策、授权范围 |

### 5.2 ROLLBACK-01 详细验证步骤

```
1. 任务前: 记录文件 A 的 SHA256
2. 任务执行: 修改文件 A，创建文件 B
3. 任务后: 用户手动修改文件 A
4. 回滚:
   a. 文件 A → 不覆盖（用户已修改），冲突报告含 A 的路径、任务后 SHA256、用户修改后 SHA256
   b. 文件 B → 删除
5. 验证: A = 用户修改后的内容，B 不存在，冲突报告完整
```

### 5.3 CTX-01/CTX-02 详细验证步骤（见门控决策 7）

### 5.4 单元测试

| 模块 | 内容 |
|------|------|
| `TaskContextValidator` | 合法/非法字段；已有 vs 新建；已存在冲突 |
| `PathGuard`（三语言独立实现，共享向量） | `..` 穿越；symlink；敏感分层；六种操作边界；命令策略 |
| `build_or_extract_task_context` | 新字段优先；兼容上下文也在安全链 |
| `Resolver` | 四模式选择；降级 |
| `Authorizer` | 存在性；授权范围；冲突检测；确认绑定 |

---

## 6. 实施顺序（v0.4 修订）

**前置**: [Phase 2.0 门控决策](./phase2-gate-decisions.md) 全部审批通过。

### Phase 2.1: 契约层（仅 Schema 和校验逻辑，不改生产代码）
- 搜索 `workspace_path`/`workspace_root` 引用，确认 Redis 序列化
- 扩展 `contracts/task-protocol-v1.schema.json`，新增 `task_context` 的 `$defs`（唯一 Schema 来源）
- 新增 `python_worker/task_context_contract.py`（类型定义 + 显式异常类型 + 校验逻辑）
- 全量测试确认零破坏
- **门槛**: 旧协议测试全过，新 Schema 通过，**不引入独立的 task-context-v1.schema.json**

### Phase 2.2: 组装与授权层
- `ProjectStrategyResolver`（规则引擎）
- `ProjectStrategyAuthorizer`（独立校验，含 `UserConfirmation` 对象模型）
- node-api `/task/submit`: 固化 task_context 到 Redis
- 任务提交时绑定上下文，Worker 不跨任务读取 node-api 全局状态
- `worker_runtime`: `build_or_extract_task_context()`
- **门槛**: Resolver 只建议，Authorizer 独立授权；兼容上下文走校验

### Phase 2.3: 执行边界与 PathGuard
- 先打通受控文件操作与命令执行边界（在现有条件下最大化防御）
- 四语言 PathGuard 实现 + 候选调用点注入
- 三语言共享测试向量
- **门槛**: **明确记录 v1 残余风险（命令隔离未完成）**

### Phase 2.4: 安全回归与迁移
- 18 E2E 场景 + 四 Worker 全量测试
- 覆盖越界读取/写入/删除/命令副作用/并发/回滚/兼容协议
- 旧协议流量监控
- 清理：达到弃用条件后（旧流量 < 5% × 7 天）移除兼容路径
- **旧字段别名清理与兼容解析移除是两个独立操作**

---

## 7. v1 不支持的能力（公开声明）

| 能力 | 状态 |
|------|:---:|
| 操作系统级进程隔离 | ❌ |
| 多根工作区 | ❌ |
| 网络策略控制 | ❌ |
| 资源限制 | ❌ |
| LLM 意图分类器 | ❌ |
| 跨任务授权传递 | ❌ |

---

> **下一步**: Phase 2.0 门控决策审批 → Phase 2.1 契约层。