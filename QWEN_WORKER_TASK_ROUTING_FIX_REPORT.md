# Qwen Worker 任务路由错误修复报告

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

**后果**: 
- Qwen Worker 无限循环拒绝任务
- Redis 队列中堆积大量无效请求
- Local LLM Worker 永远收不到自己的任务

---

## 🔍 根本原因分析

### 问题链路

1. **前端提交矛盾的任务**:
   ```json
   {
     "type": "local_generate",
     "model": "qwen-turbo"  // ❌ 应该是 "local-gemma4b"
   }
   ```

2. **Node API 根据 model 字段路由**:
   - `model = "qwen-turbo"` → 提取前缀 `"qwen"`
   - 推入队列：`task_queue:qwen` ❌

3. **Qwen Worker 检查任务类型**:
   - 期望：`type` 以 `"qwen_"` 开头
   - 实际：`type = "local_generate"`
   - 动作：拒绝并放回队列

4. **死循环形成**:
   - 任务被放回 `task_queue:qwen`
   - Qwen Worker 再次取出
   - 再次拒绝并放回
   - ...无限循环

### 代码位置

**文件**: [`python_worker/agents/qwen/qwen_worker_v2.py`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\qwen\qwen_worker_v2.py)

**问题代码**（第 224-228 行）:
```python
# 只处理 qwen_generate
if task_type and not task_type.startswith("qwen_"):
    redis.lpush(queue_name, task_json)  # ❌ 放回原队列
    print(f"⚠️ 收到不匹配的任务类型: {task_type}，已放回队列")
    time.sleep(1)
    continue
```

---

## 🛠️ 解决方案

### 核心思路：智能任务转发

当 Qwen Worker 收到不属于自己的任务时，**自动转发到正确的 Worker 队列**，而不是放回原队列。

### 实现细节

#### 1. 识别目标队列

根据任务类型或模型名称推断应该由哪个 Worker 处理：

```python
if task_type == "local_generate" or model.startswith("local-") or model.startswith("gemma"):
    target_queue = "task_queue:local"
elif task_type == "deepseek_generate" or model.startswith("deepseek"):
    target_queue = "task_queue:deepseek"
elif task_type == "doubao_generate" or model.startswith("doubao"):
    target_queue = "task_queue:doubao"
else:
    # 未知类型，放回原队列但增加延迟避免死循环
    redis.lpush(queue_name, task_json)
    time.sleep(5)
    continue
```

#### 2. 选择正确的 Redis 实例

根据目标队列类型选择对应的 Redis：

```python
if target_queue == "task_queue:local":
    # Local LLM Worker 使用 Upstash
    target_redis = redis  # 当前 Worker 的 redis 已经是 Upstash
elif target_queue in ["task_queue:deepseek", "task_queue:doubao"]:
    # 国内模型使用阿里云 Tair（如果配置了）
    try:
        from ...worker_config import create_redis_client
        target_redis = create_redis_client(model_name=f"{target_queue.split(':')[1]}_worker")
    except Exception as e:
        print(f"⚠️ 无法连接到阿里云 Tair，使用 Upstash: {e}")
        target_redis = redis
else:
    # 默认使用当前 Worker 的 Redis
    target_redis = redis
```

#### 3. 转发任务

```python
target_redis.lpush(target_queue, task_json)
print(f"✅ 任务已转发到 {target_queue}")

# ⭐ 关键：不将任务放回当前队列，避免死循环
continue
```

---

## 📊 修复效果

### 修复前
```
Qwen Worker: 收到 local_generate → 拒绝 → 放回队列 → 再次收到 → ...（死循环）
Local Worker: 永远收不到任务
Redis 队列: 堆积大量重复任务
```

### 修复后
```
Qwen Worker: 收到 local_generate → 识别目标队列 → 转发到 task_queue:local ✅
Local Worker: 从 task_queue:local 取出任务 → 正常执行 ✅
Redis 队列: 无重复任务，路由正确
```

---

## 🧪 测试验证

### 测试场景 1: Local LLM 任务误入 Qwen 队列

**输入**:
```json
{
  "task_id": "test-001",
  "type": "local_generate",
  "payload": {"prompt": "写一个排序函数"},
  "model": "qwen-turbo"  // ❌ 错误的 model
}
```

**预期输出**:
```
⚠️ 收到不匹配的任务类型: local_generate
🔄 转发到 Local LLM Worker 队列: task_queue:local
✅ 任务已转发到 task_queue:local
```

**验证方法**:
1. 启动 Qwen Worker
2. 向 `task_queue:qwen` 推送一个 `local_generate` 任务
3. 观察日志，确认任务被转发
4. 启动 Local LLM Worker，确认能收到该任务

### 测试场景 2: DeepSeek/Doubao 任务误入 Qwen 队列

**输入**:
```json
{
  "task_id": "test-002",
  "type": "deepseek_generate",
  "payload": {"prompt": "解释这段代码"},
  "model": "qwen-turbo"  // ❌ 错误的 model
}
```

**预期输出**:
```
⚠️ 收到不匹配的任务类型: deepseek_generate
🔄 转发到 DeepSeek Worker 队列: task_queue:deepseek
✅ 任务已转发到 task_queue:deepseek
```

---

## 📦 修改文件清单

### 核心修复
1. **[`python_worker/agents/qwen/qwen_worker_v2.py`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\qwen\qwen_worker_v2.py)**
   - 导入 `create_redis_client`
   - 替换简单的"放回队列"逻辑为"智能转发"逻辑
   - 支持转发到 `local`、`deepseek`、`doubao` 队列
   - 未知类型任务增加 5 秒延迟，避免死循环

---

## 🚀 部署步骤

### 1. 停止当前 Qwen Worker
```powershell
Stop-Process -Name python -Force
```

### 2. 清除 Redis 队列中的垃圾任务
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
.\clear_redis_queues.ps1
```

### 3. 清除 Python 缓存
```powershell
python restart_local_worker_with_fix.py
```

### 4. 重启 Qwen Worker
```powershell
# 在 PowerShell 中运行
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker
python -m agents.qwen.qwen_worker_v2
```

### 5. 验证修复
重新提交一个 Local LLM 任务，观察 Qwen Worker 日志：

**预期结果**:
- ✅ 看到日志：`🔄 转发到 Local LLM Worker 队列: task_queue:local`
- ✅ 看到日志：`✅ 任务已转发到 task_queue:local`
- ✅ Local LLM Worker 能正常接收并执行任务
- ❌ 不再出现"已放回队列"的死循环

---

## 🎓 经验总结

### 关键教训

1. **任务类型与模型必须一致**:
   - `type: "local_generate"` ↔ `model: "local-gemma4b"`
   - `type: "qwen_generate"` ↔ `model: "qwen-turbo"`
   - 不一致会导致路由错误

2. **Worker 应该具备容错能力**:
   - 不要简单地拒绝不匹配的任务
   - 应该智能转发到正确的 Worker
   - 这符合 AlphaPilot OS 的"Worker = 真相"信条

3. **避免死循环**:
   - 拒绝任务时不要放回原队列
   - 或者增加显著延迟（如 5 秒）
   - 最好是转发到正确的目的地

### 架构改进建议

1. **前端任务提交校验**:
   ```typescript
   // 在 Webview 中增加校验
   if (model === 'qwen-turbo' && type !== 'qwen_generate') {
       throw new Error('Model 和 Type 不匹配');
   }
   ```

2. **Node API 增强路由逻辑**:
   ```javascript
   // 如果 type 和 model 矛盾，优先信任 type
   if (type === 'local_generate') {
       model = 'local-gemma4b';  // 强制修正
   }
   ```

3. **Worker 健康检查**:
   ```python
   # 定期检查队列中是否有不属于自己的任务
   def check_foreign_tasks():
       for task in queue:
           if not belongs_to_me(task):
               forward_to_correct_worker(task)
   ```

---

## 📝 相关文档

- [AlphaPilot OS v3.1 Worker 升级架构方案](./ALPHAPILOT_V30_ARCHITECTURE.md)
- [Node API 任务路由机制](./NODE_API_TASK_SUBMISSION_FIX_REPORT.md)
- [Qwen Worker v3.0 架构](./WORKER_V3_UPGRADE_COMPLETE_REPORT.md)

---

**修复完成时间**: 2026-05-16  
**修复人员**: AlphaPilot AI Assistant  
**修复状态**: ✅ 已完成智能转发逻辑  
**待办事项**: ⏳ 需要重启 Qwen Worker 并清除 Redis 队列中的垃圾任务
