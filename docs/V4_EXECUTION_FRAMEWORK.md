# V4 执行框架（Execution Framework）

目的：为 AlphaPilot 从 V3 平滑演进到 V4，建立一个统一的“执行引擎 + 插件化步骤系统 + 记忆驱动架构”，并为未来 V5 的自演化能力（Self-Evolving System）提供可验证的落地方案。

## 目标
- 统一任务生命周期（task → steps → step 状态机）
- 插件化 Step 接口，支持动态注册与回滚
- Memory Service 作为统一上下文提供者（可替换底层实现）
- 模型抽象层（model_provider）以便接入多模型/本地/云服务
- 完整可观测性：步骤级日志、指标、错误归因

## 高阶架构（概览）

```mermaid
graph LR
  A[Frontend VSCode] -->|task_request| B[Node API]
  B --> C[Memory Service (Postgres + pgvector)]
  B --> D[Task Dispatcher]
  D --> E[Worker V4 (Execution Engine)]
  E --> F[Steps Plugin Registry]
  E --> C
  E --> G[Model Provider (Qwen/Local/Doubao...)]
  E --> H[FileOps Service]
  C -->|embeddings / memories| I[Optional Vector DB (Milvus/Weaviate)]
```

## 主要组件

- `worker_v4.py`：主循环与任务获取逻辑（通过 Redis / queue）
- `core/`：状态机、执行链、上下文加载器、流式处理、错误归因、模型抽象
- `steps/`：每类 Step 都遵守 `StepInterface`（name, input_schema, output_schema, run）并按模型实现插件
- `adapters/`：Memory Adapter / FileOps Adapter / Redis Adapter（所有外部交互通过 adapter）
- `node-api/`：Task 接口、Memory Service API、FileOps API、Prisma 客户端

## Step 插件接口（最小契约）

接口要点：
- `name`：唯一标识
- `input_schema`：JSON Schema，用于校验输入
- `output_schema`：JSON Schema，定义结构化输出
- `run(context)`：幂等执行，返回 `{status, output, metrics}`
- `supports(model)`：声明支持的模型与版本

## 生命周期与状态机
- task: pending → running → done/failed
- step: pending → running → completed/failed/retry
- 状态变更必须写入 Memory Service（task_steps）并带 trace_id

## 上下文注入策略
- 启动任务前，Worker 调用 Memory Adapter 拉取：user preferences、project metadata、最近相关 tasks、文件 semantic snippets、embeddings top-k
- 将上下文按优先级注入 system/prompt、context.window（token-aware）

## 可演化能力（V5 可扩展点）
- 插件热插拔与版本化（Step Registry + semver）
- Step 自描述能力（能输出其性能指标与失败样本）
- Execution Engine 能使用历史执行数据自动重排步骤顺序或替换低效插件
- Memory Service 支持策略性写回（学习型记忆）

## 迁移实施要点（从现有代码到 V4）
1. 保障能力：先实现 Memory Adapter（Node API）并把 Worker 的直接 DB 访问替换为 Adapter 调用。
2. 抽出 `core`：把现有散落在不同 Worker 的执行流程抽成统一 `execution_chain` 与 `state_machine`。
3. 逐步插件化：先把 `analyze`/`plan`/`write` 三个步骤改为插件接口，确保向后兼容。
4. 引入监控与指标（Prometheus + Grafana）监控 step latency、failure rate、model latency。
5. 用小流量灰度：在 staging 用 10% 流量跑 V4，评估稳定性后逐步放量。

## 验收标准（短期）
- Task/Step 的状态可在 UI 中追溯并完全回放
- 插件可被动态禁用与启用，不重启 Worker
- Memory Service 能提供 top-k semantic search（响应 <200ms）

## 行动项（下一步）
- 在 `node-api` 中实现 `memoryService` HTTP API（完成 draft）
- 在 `python_worker` 中实现 `memory_adapter.py`（调用 memoryService）
- 将 `python_worker` 中 `analyze/plan/write` 重构为插件（基础抽象）
- 制定测试套件：step 单元测试 + 集成测试（task 全链路）

---

文档：详见 [docs/MEMORY_SERVICE_SPEC.md](MEMORY_SERVICE_SPEC.md)
