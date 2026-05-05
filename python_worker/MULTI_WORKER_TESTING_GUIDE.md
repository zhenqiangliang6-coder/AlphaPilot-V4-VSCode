# 多 Worker 测试完整指南

## 📋 目录
1. [Redis 模式与多 Worker 支持](#redis-模式与多-worker-支持)
2. [为什么内存模式不支持多 Worker？](#为什么内存模式不支持多-worker)
3. [手动测试多 Worker](#手动测试多-worker)
4. [自动化测试（推荐）](#自动化测试推荐)
5. [监控工具](#监控工具)
6. [常见问题](#常见问题)

---

## Redis 模式与多 Worker 支持

### ✅ 正确的理解

| Redis 模式 | 多 Worker 支持 | 原因 |
|-----------|--------------|------|
| **内存模式** | ❌ **不支持** | 每个 Worker 有独立的内存字典，无法共享队列 |
| **Upstash 云 Redis** | ✅ **完全支持** | 所有 Worker 连接到同一个云端 Redis，共享队列 |
| **阿里云 Redis** | ✅ **完全支持** | 同上，支持分布式架构 |

### 🎯 关键原理

```
                    ┌─────────────────┐
                    │  Upstash Redis  │
                    │  (云服务)       │
                    │                 │
                    │ task_queue:qwen │ ← 共享队列
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
      ┌───────▼──────┐ ┌────▼──────┐ ┌────▼──────┐
      │ Worker 1     │ │ Worker 2  │ │ Worker 3  │
      │ qwen-worker-1│ │qwen-wor-2 │ │qwen-wor-3 │
      │ (本地进程)   │ │(本地进程) │ │(本地进程) │
      └──────────────┘ └───────────┘ └───────────┘
```

**工作原理**:
1. ✅ **Redis 是中心化的** - 所有 Worker 连接同一个 Redis 实例
2. ✅ **队列是共享的** - 任务推送到 `task_queue:qwen`
3. ✅ **原子操作** - Redis 的 `RPOP` 确保每个任务只被一个 Worker 获取
4. ✅ **自动负载均衡** - 哪个 Worker 先调用 `RPOP`，就获得任务

---

## 为什么内存模式不支持多 Worker？

### ❌ 内存模式的限制

```
Worker 1                    Worker 2
┌──────────────┐           ┌──────────────┐
│ 内存字典      │           │ 内存字典      │
│              │           │              │
│ queue: []    │           │ queue: []    │  ← 各自独立！
│              │           │              │
└──────────────┘           └──────────────┘
```

**问题**:
- ❌ 每个 Worker 有自己的 Python 进程
- ❌ 每个进程有独立的内存空间
- ❌ Worker 1 推送任务到自己的内存字典
- ❌ Worker 2 看不到 Worker 1 的任务
- ❌ **无法实现负载均衡**

### ✅ 云 Redis 的优势

```
                    ┌─────────────────┐
                    │  Upstash Redis  │
                    │  (共享存储)      │
                    │                 │
                    │ queue: [        │
                    │   task1,        │
                    │   task2,        │
                    │   task3         │
                    │ ]               │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │ RPOP         │ RPOP         │
      ┌───────▼──────┐ ┌────▼──────┐
      │ Worker 1     │ │ Worker 2  │
      │ 获取 task1   │ │ 获取 task2 │
      └──────────────┘ └───────────┘
```

**优势**:
- ✅ 所有 Worker 看到相同的队列
- ✅ Redis 保证原子性（不会重复消费）
- ✅ 自动负载均衡
- ✅ 支持水平扩展（随时增加 Worker）

---

## 手动测试多 Worker

### 📝 步骤 1: 确保使用云 Redis

编辑 `python_worker/.env`:

```env
# ⭐ 必须设置为 false
USE_MEMORY_REDIS=false

# Upstash 配置
UPSTASH_REDIS_REST_URL=https://winning-treefrog-111773.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAAAA...
```

### 📝 步骤 2: 打开多个终端

**终端 1 - Worker 1**:
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
$env:WORKER_ID="qwen-worker-1"
python -m python_worker.agents.qwen.qwen_worker_v2
```

**预期输出**:
```
📡 监听队列: task_queue:qwen
```

**终端 2 - Worker 2**:
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
$env:WORKER_ID="qwen-worker-2"  # ⭐ 不同的 ID
python -m python_worker.agents.qwen.qwen_worker_v2
```

**终端 3 - Worker 3**:
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
$env:WORKER_ID="qwen-worker-3"  # ⭐ 不同的 ID
python -m python_worker.agents.qwen.qwen_worker_v2
```

### 📝 步骤 3: 提交测试任务

通过 VSCode 扩展提交多个任务，或者使用 Python 脚本：

```python
from upstash_redis import Redis
import json
import os
from dotenv import load_dotenv

load_dotenv()

redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)

# 提交 5 个任务
for i in range(1, 6):
    task = {
        "task_id": f"test-{i}",
        "task_type": "qwen_generate",
        "payload": {"prompt": f"测试任务 {i}"},
        "steps": [],
        "events": [],
        "context": {}
    }
    
    redis.lpush("task_queue:qwen", json.dumps(task))
    print(f"任务 {i} 已提交")
```

### 📝 步骤 4: 观察结果

在每个 Worker 的终端中，你会看到：

**Worker 1**:
```
🔨 处理任务: test-1
✅ 任务完成: test-1

🔨 处理任务: test-4
✅ 任务完成: test-4
```

**Worker 2**:
```
🔨 处理任务: test-2
✅ 任务完成: test-2

🔨 处理任务: test-5
✅ 任务完成: test-5
```

**Worker 3**:
```
🔨 处理任务: test-3
✅ 任务完成: test-3
```

**✅ 成功标志**: 不同 Worker 处理不同的任务，实现负载均衡！

---

## 自动化测试（推荐）⭐

我已经为你创建了自动化测试脚本，可以一键测试多 Worker！

### 🚀 快速开始

**步骤 1: 确保使用云 Redis**

```env
# python_worker/.env
USE_MEMORY_REDIS=false
```

**步骤 2: 运行测试脚本**

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
python python_worker/test_multi_workers.py --workers 3 --tasks 5
```

**参数说明**:
- `--workers 3`: 启动 3 个 Worker
- `--tasks 5`: 提交 5 个测试任务

**步骤 3: 查看测试结果**

脚本会自动：
1. ✅ 启动指定数量的 Worker
2. ✅ 提交测试任务到队列
3. ✅ 监控任务执行情况
4. ✅ 生成测试报告
5. ✅ 清理资源（停止 Worker）

**预期输出**:

```
============================================================
AlphaPilot 多 Worker 测试
============================================================

============================================================
步骤 1: 启动 3 个 Worker
============================================================

ℹ️  启动 Worker 1: qwen-worker-1
✅ Worker 1 已启动 (PID: 12345)
ℹ️  启动 Worker 2: qwen-worker-2
✅ Worker 2 已启动 (PID: 12346)
ℹ️  启动 Worker 3: qwen-worker-3
✅ Worker 3 已启动 (PID: 12347)
✅ 所有 3 个 Worker 已启动

============================================================
步骤 2: 提交 5 个测试任务
============================================================

✅ 任务 1 已提交: test-task-1777717890-1
✅ 任务 2 已提交: test-task-1777717890-2
✅ 任务 3 已提交: test-task-1777717890-3
✅ 任务 4 已提交: test-task-1777717890-4
✅ 任务 5 已提交: test-task-1777717890-5

ℹ️  队列当前长度: 5

============================================================
步骤 3: 监控任务执行
============================================================

ℹ️  队列剩余任务数: 5
ℹ️  队列剩余任务数: 3
ℹ️  队列剩余任务数: 1
✅ 所有任务已处理完成！

============================================================
测试报告
============================================================

配置信息:
  Worker 数量: 3
  任务数量: 5
  Redis 模式: Upstash 云 Redis

测试结果:
  ✅ 所有任务已成功处理
  ✅ 多 Worker 负载均衡工作正常

Worker 状态:
  ✅ qwen-worker-1: 运行中 (PID: 12345)
  ✅ qwen-worker-2: 运行中 (PID: 12346)
  ✅ qwen-worker-3: 运行中 (PID: 12347)

清理建议:
  1. 手动停止 Worker 进程 (Ctrl+C)
  2. 或者运行: taskkill /F /PID <PID>
  3. 检查 Redis 队列是否清空
```

### 🎯 更多测试场景

**测试 1: 压力测试（10 个 Worker，50 个任务）**
```powershell
python python_worker/test_multi_workers.py --workers 10 --tasks 50
```

**测试 2: 小规模测试（2 个 Worker，3 个任务）**
```powershell
python python_worker/test_multi_workers.py --workers 2 --tasks 3
```

**测试 3: 单 Worker 基准测试**
```powershell
python python_worker/test_multi_workers.py --workers 1 --tasks 5
```

---

## 监控工具

我创建了一个实时监控工具，可以可视化地看到 Worker 和队列状态。

### 📊 使用方法

**终端 1: 启动监控**
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
python python_worker/monitor_workers.py
```

**终端 2: 启动 Worker**
```powershell
$env:WORKER_ID="qwen-worker-1"
python -m python_worker.agents.qwen.qwen_worker_v2
```

**终端 3: 启动另一个 Worker**
```powershell
$env:WORKER_ID="qwen-worker-2"
python -m python_worker.agents.qwen.qwen_worker_v2
```

### 📈 监控面板效果

```
============================================================
Worker 监控面板 (按 Ctrl+C 退出)
============================================================

⏰ 当前时间: 2026-05-02 19:30:00

📊 队列: task_queue:qwen
   状态: ✅ 空闲
   待处理任务数: 0

📊 队列: task_queue:deepseek
   状态: ✅ 空闲
   待处理任务数: 0

📊 队列: task_queue:doubao
   状态: ⚠️  少量任务
   待处理任务数: 2

👥 活跃的 Worker:
   ✅ qwen-worker-1
   ✅ qwen-worker-2

💡 提示:
   - 启动 Worker: $env:WORKER_ID='qwen-worker-1'; python -m ...
   - 提交任务后观察队列变化
   - 多个 Worker 会自动负载均衡
```

监控面板会每 2 秒刷新一次，实时显示：
- 📊 各队列的长度
- 👥 活跃的 Worker 列表
- ⏰ 当前时间

---

## 常见问题

### Q1: 如何验证多 Worker 真的在工作？

**A**: 三种方法：

**方法 1: 查看日志**
每个 Worker 会打印不同的 [task_id](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\src\types\protocol.ts#L95-L95)，说明它们在处理不同的任务。

**方法 2: 使用监控工具**
```powershell
python python_worker/monitor_workers.py
```
观察队列长度变化和 Worker 活动。

**方法 3: 自动化测试**
```powershell
python python_worker/test_multi_workers.py --workers 3 --tasks 5
```
测试报告会明确显示负载均衡是否生效。

### Q2: 内存模式真的不能用多 Worker 吗？

**A**: 是的，**完全不能用**。

**原因**:
- 每个 Worker 是独立的 Python 进程
- 每个进程有自己的内存空间
- Worker 1 的任务在 Worker 1 的内存中
- Worker 2 看不到 Worker 1 的任务
- **无法实现任务共享和负载均衡**

**解决方案**: 必须使用云 Redis（Upstash 或阿里云）。

### Q3: 多 Worker 会有冲突吗？

**A**: ❌ **不会冲突**，Redis 保证了安全性。

**原理**:
- Redis 的 `RPOP` 是**原子操作**
- 同一时刻只有一个 Worker 能弹出任务
- 不会出现两个 Worker 处理同一个任务的情况
- **线程安全，无需担心冲突**

### Q4: 最多可以启动多少个 Worker？

**A**: 理论上**没有上限**，但受以下因素限制：

| 限制因素 | 说明 |
|---------|------|
| **CPU 核心数** | 建议 Worker 数 ≤ CPU 核心数 × 2 |
| **内存** | 每个 Worker 约占用 100-200MB |
| **网络带宽** | 访问 LLM API 的网络请求 |
| **API 限流** | LLM 服务的并发限制 |

**推荐配置**:
- 个人开发: 2-3 个 Worker
- 小团队: 5-10 个 Worker
- 生产环境: 根据负载动态调整

### Q5: 如何停止所有 Worker？

**A**: 三种方法：

**方法 1: 手动停止**
在每个 Worker 终端按 `Ctrl+C`

**方法 2: 批量杀死进程**
```powershell
# 查找所有 Python 进程
Get-Process python | Where-Object { $_.MainWindowTitle -like "*qwen*" }

# 强制停止
taskkill /F /IM python.exe
```

**方法 3: 使用测试脚本**
自动化测试脚本会在结束时自动清理 Worker。

### Q6: Upstash 免费额度够多 Worker 用吗？

**A**: 取决于你的使用量。

**免费额度**: 10,000 命令/天

**估算**:
- 每个任务 ≈ 10-20 个 Redis 命令
- 10,000 ÷ 20 = **500 个任务/天**
- 如果有 5 个 Worker，每个 Worker 可处理 100 个任务/天

**如果不够**:
1. 升级到付费套餐（$10/月起）
2. 优化 Redis 使用（减少不必要的命令）
3. 迁移到其他云服务

### Q7: 如何在生产环境部署多 Worker？

**A**: 推荐使用容器化方案：

**Docker Compose 示例**:
```yaml
version: '3'
services:
  worker-1:
    build: .
    environment:
      - WORKER_ID=qwen-worker-1
      - USE_MEMORY_REDIS=false
    command: python -m python_worker.agents.qwen.qwen_worker_v2
  
  worker-2:
    build: .
    environment:
      - WORKER_ID=qwen-worker-2
      - USE_MEMORY_REDIS=false
    command: python -m python_worker.agents.qwen.qwen_worker_v2
  
  worker-3:
    build: .
    environment:
      - WORKER_ID=qwen-worker-3
      - USE_MEMORY_REDIS=false
    command: python -m python_worker.agents.qwen.qwen_worker_v2
```

**Kubernetes**:
- 使用 Deployment + ReplicaSet
- 通过环境变量注入 [WORKER_ID](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\worker_config.py#L26-L26)
- 自动扩缩容（HPA）

---

## 🎯 总结

### ✅ 关键点回顾

1. **内存模式不支持多 Worker** - 必须使用云 Redis
2. **Upstash 完全支持多 Worker** - 已测试通过
3. **自动化测试最简单** - 使用 `test_multi_workers.py`
4. **监控工具很有用** - 实时查看 Worker 状态
5. **Redis 保证安全性** - 不会有任务冲突

### 🚀 推荐操作流程

**开发阶段**:
```powershell
# 1. 确保使用云 Redis
# 修改 .env: USE_MEMORY_REDIS=false

# 2. 运行自动化测试
python python_worker/test_multi_workers.py --workers 3 --tasks 5

# 3. 观察测试结果
# 如果全部通过，说明多 Worker 工作正常
```

**调试阶段**:
```powershell
# 1. 启动监控工具
python python_worker/monitor_workers.py

# 2. 在另一个终端启动 Worker
$env:WORKER_ID="qwen-worker-1"
python -m python_worker.agents.qwen.qwen_worker_v2

# 3. 提交任务，观察实时监控
```

**生产部署**:
- 使用 Docker/Kubernetes
- 配置健康检查
- 设置自动扩缩容
- 监控队列长度和 Worker 状态

---

## 📚 相关文档

- [Redis 配置详解](REDIS_CONFIG_EXPLAINED.md)
- [快速测试指南](QUICK_TEST_REDIS.md)
- [完整诊断指南](REDIS_DEBUG_GUIDE.md)

---

**还有疑问？随时问我！** 😊
