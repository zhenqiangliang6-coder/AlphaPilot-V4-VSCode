# Node API 任务路由修复报告 - 符合架构信条版

## 📋 问题现象

Qwen Worker v3.0 不断收到并拒绝 `local_generate` 类型的任务，形成死循环：

```
============================================================
收到任务:
{
  "task_id": "b1bce6ef-a86e-4595-b063-303522289a32",
  "type": "local_generate",  // ❌ Local LLM Worker 的任务
  "model": "qwen-turbo"      // ⚠️ 但 model 字段却是 qwen-turbo
}
============================================================

⚠️ 收到不匹配的任务类型: local_generate，已放回队列
```

---

## 🔍 根本原因分析

### 架构信条回顾
> **Worker = 真相**: 所有代码生成与逻辑决策在 Worker 内完成。  
> **Extension = 映射**: 仅负责转发消息，不做决策。

**关键原则**：
- ✅ 每个 Worker **只监听自己的队列**
- ✅ 不属于自己的任务**根本不应该出现在这个队列里**
- ❌ Worker 不应该"智能转发"别人的任务（违反职责单一原则）

### 问题链路

1. **前端提交矛盾的任务**:
   ```json
   {
     "type": "local_generate",
     "model": "qwen-turbo"  // ❌ 应该是 "local-gemma4b"
   }
   ```

2. **Node API 根据 model 字段路由**（❌ 错误）:
   - `model = "qwen-turbo"` → 提取前缀 `"qwen"`
   - 推入队列：`task_queue:qwen` ❌

3. **Qwen Worker 检查任务类型**:
   - 期望：`type` 以 `"qwen_"` 开头
   - 实际：`type = "local_generate"`
   - 动作：拒绝并放回队列（✅ 符合架构信条）

4. **死循环形成**:
   - 任务被放回 `task_queue:qwen`
   - Qwen Worker 再次取出
   - 再次拒绝并放回
   - ...无限循环

### 真正的根因
**Node API 的路由逻辑错误**，而不是 Worker 的容错能力不足。

---

## 🛠️ 解决方案

### 核心思路：修正 Node API 的路由逻辑

**错误的做法**（我之前的修复）：
- ❌ 让 Qwen Worker "智能转发"不匹配的任务
- ❌ 违反了"Worker = 真相"的架构信条
- ❌ Worker 承担了不属于它的职责

**正确的做法**（本次修复）：
- ✅ **Node API 根据 [type](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\src\types\task.ts#L7-L7) 字段路由**，而非 `model` 字段
- ✅ Qwen Worker 只处理 `qwen_generate` 任务
- ✅ Local Worker 只处理 `local_generate` 任务
- ✅ 各司其职，符合架构信条

### 实现细节

#### 1. 新增 `getWorkerQueueByType` 函数

**文件**: [`node-api/index.js`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\node-api\index.js)

```javascript
// ⭐ 根据任务类型获取队列名称（✅ 符合架构信条）
function getWorkerQueueByType(taskType) {
    const TYPE_QUEUE_MAP = {
        "qwen_generate": "task_queue:qwen",
        "deepseek_generate": "task_queue:deepseek",
        "doubao_generate": "task_queue:doubao",
        "local_generate": "task_queue:local",
        "openai_generate": "task_queue:openai",
        "claude_generate": "task_queue:claude",
        "gemini_generate": "task_queue:gemini",
    };

    return TYPE_QUEUE_MAP[taskType] || "task_queue";
}
```

#### 2. 修改任务提交路由逻辑

**修改前**（第 199 行）:
```javascript
const queueName = getWorkerQueue(model);  // ❌ 根据 model 路由
```

**修改后**:
```javascript
const queueName = getWorkerQueueByType(type);  // ✅ 根据 type 路由
```

#### 3. 保留旧的 `getWorkerQueue` 函数

为了向后兼容，保留原有的 `getWorkerQueue(model)` 函数，但不再在主流程中使用。

---

## 📊 修复效果

### 修复前
```
前端提交: type="local_generate", model="qwen-turbo"
Node API: 根据 model="qwen-turbo" → 推入 task_queue:qwen ❌
Qwen Worker: 收到 type="local_generate" → 拒绝并放回队列
死循环: 任务在队列中无限循环
```

### 修复后
```
前端提交: type="local_generate", model="qwen-turbo"
Node API: 根据 type="local_generate" → 推入 task_queue:local ✅
Local Worker: 从 task_queue:local 取出任务 → 正常执行 ✅
Qwen Worker: 不会收到不属于自己的任务 ✅
```

---

## 🧪 测试验证

### 测试场景 1: Local LLM 任务

**输入**:
```json
{
  "type": "local_generate",
  "payload": {"prompt": "写一个排序函数"},
  "model": "qwen-turbo"  // ❌ 错误的 model，但不影响路由
}
```

**预期输出**:
```
🎯 路由到队列: task_queue:local (任务类型: local_generate)
💾 使用 Redis: Upstash
✅ 任务已成功推入 Redis 队列
```

**验证方法**:
1. 启动 Node API
2. 提交一个 `local_generate` 任务
3. 观察 Node API 日志，确认路由到 `task_queue:local`
4. 启动 Local LLM Worker，确认能收到该任务

### 测试场景 2: Qwen 任务

**输入**:
```json
{
  "type": "qwen_generate",
  "payload": {"prompt": "解释这段代码"},
  "model": "qwen-turbo"
}
```

**预期输出**:
```
🎯 路由到队列: task_queue:qwen (任务类型: qwen_generate)
💾 使用 Redis: Upstash
✅ 任务已成功推入 Redis 队列
```

---

## 📦 修改文件清单

### 核心修复
1. **[`node-api/index.js`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\node-api\index.js)**
   - 新增 `getWorkerQueueByType()` 函数（根据任务类型路由）
   - 修改任务提交逻辑：从 `getWorkerQueue(model)` 改为 `getWorkerQueueByType(type)`
   - 保留 `getWorkerQueue()` 函数用于向后兼容

### 未修改文件
2. **[`python_worker/agents/qwen/qwen_worker_v2.py`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\qwen\qwen_worker_v2.py)**
   - 保持不变（拒绝并放回队列的逻辑符合架构信条）

---

## 🚀 部署步骤

### 1. 停止当前服务
```powershell
# 停止 Node API
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force

# 停止 Qwen Worker
Get-Process python -ErrorAction SilentlyContinue | Where-Object {$_.CommandLine -like "*qwen*"} | Stop-Process -Force
```

### 2. 清除 Redis 队列中的垃圾任务
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
.\clear_redis_queues.ps1
```

### 3. 重启 Node API
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\node-api
node index.js
```

### 4. 重启 Qwen Worker
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python_worker.agents.qwen.qwen_worker_v2
```

### 5. 验证修复
重新提交一个 Local LLM 任务，观察 Node API 日志：

**预期结果**:
- ✅ 看到日志：`🎯 路由到队列: task_queue:local (任务类型: local_generate)`
- ✅ Local LLM Worker 能正常接收并执行任务
- ✅ Qwen Worker 不会收到不属于自己的任务
- ❌ 不再出现"已放回队列"的死循环

---

## 🎓 经验总结

### 关键教训

1. **架构信条必须严格遵守**:
   - Worker 不应该承担不属于它的职责
   - "智能转发"看似聪明，实则违反职责单一原则
   - 正确的方式是**从源头修复**（Node API 路由逻辑）

2. **任务类型 vs 模型名称**:
   - `type` 字段表示**任务类型**（决定由哪个 Worker 处理）
   - `model` 字段表示**使用的模型**（决定调用哪个 API）
   - 两者应该一致，但如果不一致，**优先信任 [type](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\src\types\task.ts#L7-L7)**

3. **路由逻辑应该在网关层**:
   - Node API 作为网关，负责任务路由
   - Worker 作为执行单元，只处理自己的任务
   - 这样架构清晰，易于维护和扩展

### 架构改进建议

1. **前端任务提交校验**:
   ```typescript
   // 在 Webview 中增加校验
   const TASK_MODEL_MAP = {
       "local_generate": "local-gemma4b",
       "qwen_generate": "qwen-turbo",
       "deepseek_generate": "deepseek-chat",
       "doubao_generate": "doubao-pro",
   };
   
   if (TASK_MODEL_MAP[type] && model !== TASK_MODEL_MAP[type]) {
       console.warn(`警告: ${type} 任务应该使用 ${TASK_MODEL_MAP[type]} 模型`);
   }
   ```

2. **Node API 增强日志**:
   ```javascript
   console.log(`🎯 路由决策: type=${type}, model=${model} → queue=${queueName}`);
   ```

3. **Worker 健康监控**:
   ```python
   # 定期检查队列长度
   queue_length = redis.llen(queue_name)
   if queue_length > 100:
       print(f"⚠️ 队列积压: {queue_name} ({queue_length} 个任务)")
   ```

---

## 📝 相关文档

- [AlphaPilot OS 架构信条](./ARCHITECTURE_MANIFESTO.md)
- [Node API 任务路由机制](./NODE_API_TASK_SUBMISSION_FIX_REPORT.md)
- [Qwen Worker v3.0 架构](./WORKER_V3_UPGRADE_COMPLETE_REPORT.md)
- [多模型任务队列隔离策略](./DUAL_REDIS_V28_IMPLEMENTATION_REPORT.md)

---

**修复完成时间**: 2026-05-16  
**修复人员**: AlphaPilot AI Assistant  
**修复状态**: ✅ 已完成 Node API 路由逻辑修正  
**架构合规性**: ✅ 完全符合"Worker = 真相"信条  
**待办事项**: ⏳ 需要重启 Node API 和 Qwen Worker 并验证修复效果
