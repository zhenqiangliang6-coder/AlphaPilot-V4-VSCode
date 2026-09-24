# Memory Service 规范（Memory Service Spec）

目的：定义 AlphaPilot 的记忆层（Memory Service）数据模型、API、embedding 管线与演进路径，保证 V4 的一致性并为 V5 的横向扩展与向量外置留下清晰接口。

## 设计原则
- **结构化 + 语义化 + 版本化**：同时支持结构化表（tasks/files/versions）与语义向量（embeddings）。
- **可替换的存储后端**：Memory Adapter 层必须隐藏底层实现（Postgres 本地 / 托管向量 DB）。
- **审计与回滚优先**：每个修改都要有版本记录（file_versions / task_steps）。

## 建议 DB 布局（Prisma 模型摘要）

示例（高层）：

```prisma
model User {
  id          Int      @id @default(autoincrement())
  externalId  String?  @unique
  name        String?
  preferences Json?
  projects    Project[]
  tasks       Task[]
  createdAt   DateTime @default(now())
}

model Project { ... }
model Task { id String @id ... }
model TaskStep { id Int @id @default(autoincrement()) ... }
model File { id Int @id @default(autoincrement()) ... }
model FileVersion { id Int @id @default(autoincrement()) content String }
model Memory { id Int @id ... }
model Embedding { id Int @id ... vector Unsupported("vector") }
```

（完整 schema 请转写自 `AlphaPilot OS — PostgreSQL3.3.txt` 到 `prisma/schema.prisma`）

## Embeddings 管线
- 在 task 或 file_version 写入后：
  1. 触发 embedding 生成任务（异步队列）
  2. 生成 embedding（向量维度建议 1536 或 1024，视模型）
  3. 将 vector 写入 Postgres 的 `embeddings` 表（pgvector）或写入外部向量 DB
  4. 为常用检索字段建立 HNSW 索引（外部 DB）或 GIN/ivfflat（Postgres）

## API 设计（Node API）
- `POST /memory/query`：semantic + filters → 返回 top-k hits（带 score）
- `POST /memory/save`：保存自然语言记忆（user/project/task）
- `GET /memory/project/:id`：项目记忆汇总
- `POST /workspace/set`：设置当前工作区（FileOps 路径）

## 抽象与适配器策略
- `memory_adapter` 在 Worker 侧提供：
  - `getUserMemory(userId, opts)`
  - `getProjectMemory(projectId, opts)`
  - `getSemanticContext(query, topK)`
  - `saveFileVersion(fileId, content, metadata)`
- Adapter 实现应允许在配置中把 Embedding 存储切换到外部向量 DB，而不改 Worker 代码。

## 数据治理与保留策略
- 冷/热分层：保留最近 90 天的 full embeddings 在 Postgres（或外置）用于低延迟检索；老旧 embeddings 存档到对象存储
- 敏感数据红线：记忆中敏感内容必须标记并支持删除/脱敏
- 备份策略：每日增量 + 每周全量（DB 与向量索引）

## 向量外置迁移计划（Postgres -> Milvus/Weaviate）
1. 抽出 Adapter：实现 `vectorWrite(vector, ownerType, ownerId)` 与 `vectorSearch(qVector, topK)` 接口
2. 开启双写：同时写 Postgres 与 外部 DB，监控差异（采样比对）
3. 切换读取：在灰度通道将查询指向外部 DB，评估性能/精度
4. 停止写入 Postgres 或 将 Postgres 转为冷存档

## 性能与运维注意事项
- Embedding 批量生成避免同步阻塞主流程
- 使用异步队列（Redis / RQ / Celery）处理 embedding 任务
- 监控向量查询延迟和 recall（精度）指标

## 安全与权限
- Memory API 必须认证并基于 project/user 做访问控制
- 所有写操作需记录 `actor_id` 与 `task_id`，用于审计

---

## 快速行动清单（30/60/90 天）
- 30 天：把 SQL 草案迁移到 `prisma/schema.prisma`，实现基础 `memoryService` API（save/get/query），并实现 `memory_adapter` 读。 
- 60 天：实现 embedding 异步管线（生成→写入→索引），在 staging 上完成 top-k 检索。 
- 90 天：实现向量外置 Adapter、双写灰度，并完成回滚/备份策略。
