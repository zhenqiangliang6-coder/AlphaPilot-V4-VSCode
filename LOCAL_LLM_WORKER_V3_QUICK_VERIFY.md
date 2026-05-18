# Local LLM Worker v3.0 执行链路修复 - 快速验证指南

## ✅ 修复完成状态

- [x] 所有代码文件已修改（11个文件）
- [x] 语法检查通过（无错误）
- [x] 架构信条对齐验证完成
- [x] 实施报告已生成
- [ ] **真实环境测试待执行（需要您操作）**

---

## 🚀 快速验证步骤

### Step 1: 启动 Local LLM Worker

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
.\start_local_worker.ps1
```

**预期输出**:
```
🚀 Local LLM Worker v3.0 已启动
   · Worker ID: local_llm_worker_001
   · Node API: 已连接
   · 正在监听任务队列...

📡 Local LLM Worker v3.0 监听队列: queue:local_generate
```

### Step 2: 提交测试任务

打开新的 PowerShell 窗口，执行：

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker
python submit_test_task.py --worker local_llm --prompt "写一个 Python 排序函数，支持升序和降序"
```

或者手动创建测试任务：

```python
import sys
import os
import json
import time

sys.path.insert(0, os.path.abspath('.'))
from worker_config import create_redis_client, get_worker_queue

redis = create_redis_client()
queue_name = get_worker_queue("local_generate")

task = {
    "task_id": f"test_{int(time.time())}",
    "task_type": "local_generate",
    "payload": {
        "prompt": "写一个 Python 排序函数，支持升序和降序"
    },
    "meta": {
        "retry_count": 0,
        "started_at": int(time.time() * 1000)
    }
}

redis.lpush(queue_name, json.dumps(task))
print(f"✅ 任务已提交: {task['task_id']}")
```

### Step 3: 观察 Worker 输出

在 Worker 窗口中，你应该看到：

```
============================================================
收到任务:
{
  "task_id": "test_xxx",
  "task_type": "local_generate",
  "payload": {...}
}
============================================================

🧠 Local LLM Worker v3.0 决策：
  意图: write_code (或 simple_code)
  人格: 工程师 (👨‍💻)
  执行链: write → test

📋 动态生成 2 个步骤 (意图: write_code)

[步骤执行日志...]

✅ Local LLM write_step 生成 1 个 FileOp
   - create: main.py (file)

============================================================
任务完成，结果已写入 Redis:
{
  "task_id": "test_xxx",
  "status": "success",
  ...
}
============================================================

📡 正在通知 Node.js: http://localhost:3000/task/notify/test_xxx
✅ Node.js 已成功接收通知，将推送给前端
```

### Step 4: 前端验证（VSCode Chat）

1. **重新加载 VSCode 窗口**:
   - `Ctrl+Shift+P` → `Reload Window`

2. **打开 AlphaPilot Chat**:
   - `Ctrl+Shift+A`

3. **输入测试提示词**:
   ```
   写一个 Python 排序函数，支持升序和降序
   ```

4. **观察流式输出**:
   - ✅ 应该看到 `✍️ 正在生成代码...`
   - ✅ 应该看到代码逐块显示
   - ✅ 应该看到 `🧪 正在生成并执行测试...`

5. **检查 FileOps 面板**:
   - ✅ 应该出现文件操作列表
   - ✅ 显示 `create: main.py`
   - ✅ 点击"应用"后文件应写入磁盘

---

## 🔍 关键验证点

### 1. 流式输出是否正常？

**成功标志**:
- ✅ 前端实时显示代码生成过程
- ✅ 不是一次性显示全部内容
- ✅ 有明确的阶段提示（分析、计划、生成、测试等）

**失败标志**:
- ❌ 前端长时间无响应
- ❌ 突然一次性显示所有内容
- ❌ 没有任何输出

### 2. FileOps 是否正确生成？

**成功标志**:
- ✅ Worker 日志显示 `✅ Local LLM write_step 生成 X 个 FileOp`
- ✅ 每个 FileOp 包含 action, path, content, type 字段
- ✅ context["final_file_ops"] 非空

**失败标志**:
- ❌ Worker 日志显示 `[WARN] 未检测到多文件协议，降级为单文件模式`
- ❌ FileOps 列表为空
- ❌ 前端看不到文件操作面板

### 3. 任务是否完整执行？

**成功标志**:
- ✅ 所有步骤状态为 "completed"
- ✅ result_data 包含完整的 steps, events, context
- ✅ Node.js 收到通知并返回 200

**失败标志**:
- ❌ 某个步骤状态为 "failed"
- ❌ 任务卡在 "running" 状态
- ❌ Node.js 通知失败

---

## 🐛 常见问题排查

### 问题1: Worker 启动失败

**可能原因**:
- Redis 未启动
- Python 依赖缺失
- 端口被占用

**解决方案**:
```powershell
# 检查 Redis
redis-cli ping  # 应该返回 PONG

# 检查依赖
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker
pip install -r requirements.txt

# 检查端口
netstat -ano | findstr :6379
```

### 问题2: 流式输出不工作

**可能原因**:
- task_id 未正确传递
- stream_start/chunk/end 调用失败
- Node API 未正确转发事件

**解决方案**:
1. 检查 Worker 日志是否有 `[WARN] stream_start 失败` 警告
2. 确认 `execute_step` 调用了 `handler(step, context, events, task_id=task_id)`
3. 检查 Node API 是否正确监听并转发事件

### 问题3: FileOps 未生成

**可能原因**:
- LLM 输出格式不符合多文件协议
- `parse_fileops_v3` 解析失败
- file_ops 模块导入失败

**解决方案**:
1. 检查 Worker 日志是否有 `[ERROR] Local LLM 解析 FileOps 失败`
2. 确认 LLM 输出了正确的 `# FILE:` 标记
3. 验证 `from file_ops import parse_fileops_v3` 是否成功

---

## 📊 与 Qwen Worker v2 对比

| 特性 | Qwen Worker v2 | Local LLM Worker v3.0 (修复后) | 状态 |
|------|----------------|--------------------------------|------|
| **意图识别** | ✅ IntentRouter | ✅ IntentRouter | ✅ 对齐 |
| **人格选择** | ✅ get_persona_config | ✅ get_persona_config | ✅ 对齐 |
| **执行链构建** | ✅ build_execution_chain | ✅ build_execution_chain (智能简化) | ✅ 对齐 |
| **流式输出** | ✅ 所有步骤支持 task_id | ✅ 所有步骤支持 task_id | ✅ 对齐 |
| **FileOps 生成** | ✅ parse_fileops_v3 | ✅ parse_fileops_v3 + 增强日志 | ✅ 对齐 |
| **步骤调度** | ✅ execute_step (inspect) | ✅ execute_step (inspect) | ✅ 对齐 |
| **取消机制** | ✅ check_stop_flag | ✅ check_stop_flag | ✅ 对齐 |
| **Node API 通知** | ✅ POST /task/notify | ✅ POST /task/notify | ✅ 对齐 |

---

## 💡 下一步优化建议

### 短期（本周）
1. ⏳ 为 Local LLM 的 `call_qwen` 实现真正的流式 API 调用（目前是同步调用 + 模拟流式）
2. ⏳ 增加更多调试日志，特别是 FileOps 解析环节
3. ⏳ 编写自动化测试脚本，覆盖所有意图类型

### 中期（本月）
1. ⏳ 支持更多本地模型（Ollama, LM Studio 等）
2. ⏳ 优化执行链智能简化逻辑（基于提示词复杂度）
3. ⏳ 增加性能监控和指标收集

### 长期（季度）
1. ⏳ 实现自适应执行链（V4 阶段目标）
2. ⏳ 支持状态恢复和错误归因
3. ⏳ 集成更多工具函数（Git, Docker 等）

---

## ✅ 验收标准

Local LLM Worker v3.0 修复成功的标志：

1. ✅ 能够生成完整项目文件（不仅仅是文本回复）
2. ✅ 前端实时显示流式输出（不是等待全部完成后才显示）
3. ✅ FileOps 面板正确展示文件操作列表
4. ✅ 用户确认后文件能正确写入磁盘
5. ✅ 所有步骤都能正常执行（analyze → plan → write → test → ...）
6. ✅ 任务取消机制正常工作
7. ✅ 错误处理和重试机制正常

**兄弟，现在所有代码都已经修复完毕！请按照上面的步骤进行真实环境测试，如果有任何问题随时告诉我！** 🚀
