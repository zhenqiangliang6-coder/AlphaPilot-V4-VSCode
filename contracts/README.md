# AlphaPilot task protocol

`task-protocol-v1.schema.json` is the shared envelope contract for task submission and
execution. The Extension creates versioned submissions, the Node API validates and
normalizes them before queueing, and Workers reject unsupported explicit protocol
versions. The Qwen Worker is the first Worker adapter; other model workers currently
ignore these additive fields and remain on their legacy result envelopes. A missing
version remains accepted at the Node/Worker boundary for legacy clients; newly
submitted tasks are always emitted as protocol `1.0`.

`trace_id` is assigned by the Extension and propagated unchanged through the queue and
Worker result. `task_id` remains the server-owned lifecycle identifier.

The schema reserves explicit `awaiting_authorization` and authorization decision
states. This defines the wire shape; it does not claim that a resumable approval
workflow or post-approval test execution is implemented yet.

---

# Multi-Worker Orchestration Protocol

`task-orchestration-v1.schema.json` defines the cross-worker orchestration contract.
When the user submits a multi-language / multi-project request, the python_worker
Orchestrator decomposes it into independent subtasks, distributes them to the
appropriate language Workers (node_worker / ts_worker / java_worker), and aggregates
the results.

## Architecture Tenets (架构信条)

| Layer | Role | Multi-Worker Impact |
|-------|------|---------------------|
| **python_worker** (大脑) | Intent classification, decomposition, orchestration, aggregation | Owns `orchestrator.py` — all decision logic |
| **node/ts/java worker** (手脚) | Pure execution, no decisions | **Unchanged** — receive clear instructions via DI |
| **contracts/** (宪法) | Message format definition | Added `task-orchestration-v1.schema.json` |
| **Extension** (映射) | UI ↔ task mapping | **Unchanged** — still sends 1 task, receives 1 result |
| **Webview** (投影) | Display only | **Unchanged** |

## Execution Flow

```
User Input: "Build TS task manager + JS mini backend"
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  python_worker Orchestrator (orchestrator.py)            │
│                                                          │
│  analyze(prompt):                                        │
│    ┌─ LLM classify → is_multi_language=true              │
│    ├─ languages_detected: [typescript, javascript]       │
│    └─ strategy: parallel                                 │
│                                                          │
│  decompose:                                              │
│    ├─ Subtask-0: TS task manager → ts_worker             │
│    └─ Subtask-1: JS mini backend → node_worker           │
│                                                          │
│  execute (parallel):                                     │
│    ┌─ LPUSH ts_worker    ← SubTask-0  ─┐                 │
│    └─ LPUSH node_worker  ← SubTask-1  ─┤ parallel        │
│                                          │                │
│  wait & aggregate:                      │                │
│    ┌─ Poll result:task_result:orch-0    │                │
│    └─ Poll result:task_result:orch-1   ─┘                │
│                                                          │
│  aggregate → orchestrationResult:                        │
│    { status: "all_success",                              │
│      files_by_language: {                                │
│        typescript: ["task.ts", "task.service.ts"],       │
│        javascript: ["user.model.js", "app.js"]           │
│      }                                                   │
│    }                                                     │
└─────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Zero-Invasion (零侵入)
The orchestrator is additive — it does not modify the existing single-worker path.
When `ORCHESTRATOR_ENABLED=false` or the input is single-language, the flow is
unchanged.

### 2. Parallel-First (并行优先)
Sub-tasks with no data dependencies execute concurrently via `ThreadPoolExecutor`.
Each sub-task gets its own isolated workspace directory to prevent file conflicts.

### 3. Graceful Degradation (降级安全)
Any failure in LLM classify, JSON parsing, or sub-task execution triggers automatic
fallback to the single-worker path. No orchestration error blocks the user.

### 4. DI Continuity (依赖注入延续)
The language Workers (node_worker / ts_worker / java_worker) continue using the DI
architecture established in Phase 2.4. The orchestrator treats them as black-box
executors — it only needs to know the queue name and task type.

## Language → Worker Queue Mapping

| Target Language | Worker Queue | Task Type | Worker |
|-----------------|-------------|-----------|--------|
| `python` | `task_queue:qwen` | `qwen_generate` | Qwen Worker (python_worker) |
| `javascript` | `node_worker` | `node_generate` | Node.js Worker |
| `typescript` | `ts_worker` | `ts_generate` | TypeScript Worker |
| `java` | `java_worker` | `java_generate` | Java Worker |

## Feature Toggles

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `ORCHESTRATOR_ENABLED` | `true` | Enable multi-worker orchestration |
| `ORCHESTRATOR_MAX_PARALLEL` | `4` | Max concurrent sub-tasks |
| `ORCHESTRATOR_MULTI_THRESHOLD` | `2` | Min languages to trigger orchestration |
| `ORCHESTRATOR_POLL_INTERVAL` | `1.0` | Result polling interval (seconds) |

---

# E2E Test Results (Phase 2.4 JS/TS Worker Merge)

| Date | JS Worker | TS Worker | Total |
|------|-----------|-----------|-------|
| 2026-10-30 | 5/5 PASS | 5/5 PASS | **10/10 PASS** |

### JS Worker Tests (node_worker — 10-step chain)
| ID | Label | Duration | Result |
|----|-------|----------|--------|
| JS-001 | express_crud_api | 116.5s | ✅ PASS |
| JS-002 | async_file_processor | 189.9s | ✅ PASS |
| JS-003 | event_emitter_logger | 191.6s | ✅ PASS |
| JS-004 | npm_package | 154.8s | ✅ PASS |
| JS-006 | promise_pool | 90.3s | ✅ PASS |

### TS Worker Tests (ts_worker — 11-step chain incl. compile)
| ID | Label | Duration | Result |
|----|-------|----------|--------|
| TS-001 | result_type | 124.9s | ✅ PASS |
| TS-002 | generic_utilities | 82.6s | ✅ PASS |
| TS-004 | type_guards | 205.3s | ✅ PASS |
| TS-005 | decorators | 121.1s | ✅ PASS |
| TS-006 | async_result | 194.8s | ✅ PASS |

### Code Reduction (DI Architecture)
```
Before: node_worker/qwen_worker.js (199L) + ts_worker/qwen_worker.js (180L) = 379L
After:  node_worker/qwen_worker.js (219L) + ts_worker/qwen_worker.js  (26L) = 245L
TS Worker reduction: 180L → 26L (-86%)
```

### Bug Fixes Applied During Testing
1. `ConvertTo-Json` single-element array bug → JS array literal
2. `Push-Location` missing → correct cwd for worker import
3. `_guessFilePath` matching `Express.js` before `server.js` → lowercase-first regex
4. `# FILE:` markers missing → prompt reinforcement
5. Recursive file search → `findFile()` for subdirectory-savvy verification