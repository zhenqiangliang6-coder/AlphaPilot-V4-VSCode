# AlphaPilot OS 记忆系统 - 快速参考指南

## 🚀 快速开始

### 1. 验证系统状态

```powershell
# 运行完整验证
.\test_memory_system.ps1
```

### 2. 在 Node API 中使用

```javascript
// node-api/index.js
const memoryService = require('./services/memoryService');

// 示例：创建任务时记录到数据库
app.post('/tasks/submit', async (req, res) => {
  const { userId, projectId, prompt, model } = req.body;
  const taskId = uuidv4();
  
  // 记录到 Memory Service
  await memoryService.createTask(taskId, userId, projectId, prompt, model);
  
  // ... 其他逻辑
});
```

### 3. 为 Worker 注入上下文

```javascript
// 在发送任务给 Worker 前
const context = await memoryService.loadContextForWorker(taskId);

const taskPayload = {
  task_id: taskId,
  prompt: task.prompt,
  system_context: context.system_context,
  project_context: context.project_context,
  memory_context: context.memory_context
};

// 发送给 Worker...
```

---

## 📚 常用 API

### 用户管理

```javascript
// 获取或创建用户
const user = await memoryService.getOrCreateUser(
  'github-123',           // external_id
  '张三',                  // name
  { language: 'zh-CN' }   // preferences
);

// 更新用户偏好
await memoryService.updateUserPreferences(user.id, {
  preferred_model: 'qwen',
  explanation_style: 'detailed'
});
```

### 项目管理

```javascript
// 获取或创建项目
const project = await memoryService.getOrCreateProject(
  user.id,                    // userId
  'My Project',              // name
  'D:\\Projects\\my-app',    // rootPath
  { languages: ['Python'] }  // techStack
);

// 查询项目记忆
const memories = await memoryService.queryProjectMemories(project.id);
```

### 任务管理

```javascript
const { v4: uuidv4 } = require('uuid');
const taskId = uuidv4();

// 创建任务
await memoryService.createTask(
  taskId,
  user.id,
  project.id,
  '帮我创建一个 FastAPI 应用',
  'qwen-max',
  'react-webview'
);

// 更新任务状态
await memoryService.updateTaskStatus(taskId, 'running');
await memoryService.updateTaskStatus(taskId, 'done', '任务完成摘要');

// 查询任务
const task = await memoryService.getTask(taskId);
```

### 步骤记录

```javascript
// 创建步骤
const analyzeStep = await memoryService.createTaskStep(taskId, 'analyze', {
  prompt: '帮我创建一个 FastAPI 应用'
});

// 更新步骤输出
await memoryService.updateTaskStep(analyzeStep.id, 'done', {
  analysis: '需要实现路由、模型、服务层...',
  tech_stack: ['FastAPI', 'SQLAlchemy']
});
```

### FileOps 记录

```javascript
// 记录文件操作
await memoryService.recordFileOp(
  taskId,
  analyzeStep.id,
  'create',              // op: create/update/delete
  'app/main.py',         // path
  'main',                // role: main/test/doc/config/meta
  '创建主应用文件',       // reason
  'analyze'              // from_step
);
```

### 文件版本管理

```javascript
// 获取或创建文件身份
const file = await memoryService.getOrCreateFile(project.id, 'app/main.py');

// 保存文件版本
await memoryService.saveFileVersion(
  file.id,
  taskId,
  analyzeStep.id,
  'from fastapi import FastAPI\n\napp = FastAPI()',
  'abc123hash'
);

// 查询版本历史
const versions = await memoryService.getFileVersions(file.id, 10);
```

### 长期记忆

```javascript
// 创建项目规则记忆
await memoryService.createMemory(
  'project',              // owner_type
  project.id,             // owner_id
  'rule',                 // memory_type: preference/rule/summary/pattern
  '所有 API 必须使用 async/await',
  5                       // importance: 1-5
);

// 创建用户偏好记忆
await memoryService.createMemory(
  'user',
  user.id,
  'preference',
  '用户喜欢详细的代码注释',
  4
);

// 查询记忆
const rules = await memoryService.queryProjectMemories(project.id, 'rule');
const prefs = await memoryService.queryUserMemories(user.id, 'preference');
```

---

## 🔍 查询示例

### 获取用户任务历史

```javascript
const tasks = await memoryService.getUserTasks(user.id, 50);
console.log(`用户共有 ${tasks.length} 个任务`);
```

### 获取任务的完整执行链

```javascript
const task = await memoryService.getTask(taskId);
console.log('任务步骤:', task.steps);
console.log('文件操作:', task.file_ops);
```

### 获取 Worker 上下文

```javascript
const context = await memoryService.loadContextForWorker(taskId);

// 注入到 prompt
const fullPrompt = `
${context.system_context}

项目信息:
${JSON.stringify(context.project_context)}

用户偏好:
${JSON.stringify(context.memory_context.user_preferences)}

项目规则:
${context.memory_context.project_memories.map(m => `- ${m.content}`).join('\n')}

用户请求: ${task.prompt}
`;
```

---

## 🛠️ 维护命令

### 查看数据库表结构

```bash
cd node-api
npx prisma studio
```

### 生成新的迁移

```bash
# 修改 schema.prisma 后
npx prisma migrate dev --name your_migration_name
```

### 重置数据库（谨慎使用）

```bash
npx prisma migrate reset --force
```

### 重新生成 Prisma Client

```bash
npx prisma generate
```

---

## ⚠️ 注意事项

### 1. 事务处理

对于需要原子性的操作，使用 Prisma 事务：

```javascript
await memoryService.prisma.$transaction(async (prisma) => {
  // 多个操作要么全部成功，要么全部失败
  await prisma.task.create({...});
  await prisma.taskStep.create({...});
});
```

### 2. 错误处理

所有 Memory Service 方法都会抛出异常，记得捕获：

```javascript
try {
  await memoryService.createTask(...);
} catch (error) {
  console.error('创建任务失败:', error);
  // 降级策略：继续执行但不记录到数据库
}
```

### 3. 性能优化

- 批量操作时使用 `$transaction`
- 查询时只选择需要的字段（`select`）
- 避免 N+1 查询，使用 `include` 预加载关联数据

---

## 📊 数据库表关系图

```
users (1) ──────< projects (N)
  │                     │
  │                     └──< files (N)
  │                            │
  │                            └──< file_versions (N)
  │
  └──< tasks (N)
         │
         ├──< task_steps (N)
         │       │
         │       └──< task_file_ops (N)
         │       └──< file_versions (N)
         │
         ├──< task_file_ops (N)
         │
         ├──< memories (N)
         │
         └──< embeddings (N) [待启用]

memories 可通过 owner_type 关联:
  - user_id → users
  - project_id → projects
  - task_id → tasks
```

---

## 🎯 最佳实践

### 1. 任务生命周期管理

```javascript
// 1. 任务开始时
await memoryService.createTask(taskId, userId, projectId, prompt, model);
await memoryService.updateTaskStatus(taskId, 'running');

// 2. 每个步骤完成后
await memoryService.updateTaskStep(stepId, 'done', output);

// 3. 任务结束时
await memoryService.updateTaskStatus(taskId, 'done', summary);

// 4. 生成任务总结记忆
await memoryService.createMemory(
  'task',
  taskId,
  'summary',
  summary,
  3
);
```

### 2. 文件变更追踪

```javascript
// 每次 FileOps 执行后
for (const fileOp of fileOps) {
  await memoryService.recordFileOp(
    taskId, stepId, fileOp.op, fileOp.path, fileOp.role
  );
  
  if (fileOp.op === 'create' || fileOp.op === 'update') {
    const file = await memoryService.getOrCreateFile(projectId, fileOp.path);
    await memoryService.saveFileVersion(
      file.id, taskId, stepId, fileOp.content, hash(fileOp.content)
    );
  }
}
```

### 3. 智能上下文注入

```javascript
// 根据任务类型动态加载相关记忆
const context = await memoryService.loadContextForWorker(taskId);

// 额外加载相似任务的历史
const similarTasks = await memoryService.prisma.task.findMany({
  where: {
    project_id: task.project_id,
    prompt: { contains: extractKeywords(task.prompt) }
  },
  take: 3,
  orderBy: { created_at: 'desc' }
});

context.memory_context.similar_tasks = similarTasks;
```

---

## 🔗 相关文档

- [完整实施报告](./MEMORY_SYSTEM_IMPLEMENTATION_REPORT.md)
- [Prisma 官方文档](https://www.prisma.io/docs)
- [PostgreSQL 文档](https://www.postgresql.org/docs/)

---

**最后更新**: 2026-05-21  
**版本**: AlphaPilot OS v3.1 Memory System
