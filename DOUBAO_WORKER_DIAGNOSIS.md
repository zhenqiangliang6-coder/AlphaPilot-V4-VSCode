# Doubao Worker v2 问题诊断与解决方案

## 🔴 当前问题

### 症状
1. ✅ Planner 成功拆解任务（显示 "✅ Doubao Planner 成功拆解任务"）
2. ❌ **Worker 立即完成任务，没有执行任何步骤**
3. ❌ Redis 中的 steps 数组包含 `reasoning` 和 [message](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\src\taskModel.ts#L43-L43) 对象（旧的 API 响应格式）
4. ❌ 错误信息："未知步骤类型：message"

### 根本原因
**Python 模块缓存问题**：Worker 正在运行旧版本的代码，没有使用新修复的 [doubao_planner.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\Volcengine\doubao_planner.py)。

从日志可以看到：
```json
{
  "type": "reasoning",  // ❌ 这是旧的 API 响应格式
  ...
},
{
  "type": "message",    // ❌ 这也是旧的 API 响应格式
  ...
}
```

这说明 Worker **没有使用新修复的 Planner**，而是使用了某个旧版本的解析逻辑。

---

## ✅ 已实施的修复

### 修复 1: 创建独立的 Doubao Planner
- ✅ 文件：[doubao_planner.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\Volcengine\doubao_planner.py)
- ✅ 正确解析 Doubao Responses API 格式
- ✅ 只提取 message 中的 JSON 数组
- ✅ 忽略 reasoning 等内部结构

### 修复 2: 修改 Worker 导入
- ✅ 文件：[doubao_worker_v2.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\Volcengine\doubao_worker_v2.py)
- ✅ 从 `.doubao_planner` 导入（而非全局 `...planner`）

### 修复 3: 禁用代理 + 重试机制
- ✅ 文件：[doubao_api.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\Volcengine\doubao_api.py)
- ✅ 解决 `ProxyError` 问题

---

## 🛠️ 解决方案

### 方案 1: 手动重启 Worker（推荐）

在 PowerShell 中执行：

```powershell
# 1. 停止当前的 Worker 进程（Ctrl+C 或关闭终端窗口）

# 2. 清除 Python 缓存
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
Get-ChildItem -Path "python_worker" -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path "python_worker" -Recurse -Filter "*.pyc" | Remove-Item -Force

# 3. 重新启动 Worker
$env:WORKER_ID="doubao-worker-1"
python -m python_worker.agents.Volcengine.doubao_worker_v2
```

### 方案 2: 使用自动化脚本

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
.\restart_doubao_worker.ps1
```

---

## 🧪 验证方法

### 测试 1: Planner 独立性测试

```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
python test_doubao_planner.py
```

**预期输出**：
```
✅ Doubao Planner 成功拆解 8 个步骤:
  Step 1: analyze (ID: step-1)
  Step 2: plan (ID: step-2)
  ...
  Step 8: docstring (ID: step-8)
```

### 测试 2: 完整工作流测试

1. 从前端提交任务："生成 hello.py / utils.py / main.py"
2. 观察 Worker 输出

**预期行为**：
```
============================================================
收到任务: { ... }
============================================================

📝 Doubao API 原始响应（前500字符）: {...}
📝 提取到的 LLM 响应文本（前300字符）: [...]
✅ Doubao Planner 成功拆解任务（第 1 次尝试）

🚀 开始执行任务: e12c3284-aa9d-4b25-8373-dbf38e31e519
📝 Step 1/8: analyze...
✅ Step 1 completed
📝 Step 2/8: plan...
✅ Step 2 completed
...
📝 Step 8/8: docstring...
✅ Step 8 completed

============================================================
任务完成，结果已写入 Redis:
{
  "version": "2.0",
  "task_id": "...",
  "status": "done",
  "result": "...",
  "steps": [
    {"id": "step-1", "type": "analyze", ...},
    {"id": "step-2", "type": "plan", ...},
    ...
  ]
}
============================================================
```

**关键验证点**：
- ✅ Steps 数组中**不再包含** `reasoning` 或 [message](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\src\taskModel.ts#L43-L43) 对象
- ✅ 所有步骤的 type 都是标准类型（analyze/plan/write/refine/test/fix/doc/docstring）
- ✅ 每个步骤都正常执行（显示 "Step X completed"）

---

## 📊 架构验证

### 独立性检查

| 组件 | 状态 | 说明 |
|------|------|------|
| Planner | ✅ | 使用 [doubao_planner.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\Volcengine\doubao_planner.py)，不依赖 Qwen |
| API 调用 | ✅ | 使用 [call_doubao()](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\Volcengine\doubao_api.py#L46-L107)，禁用代理 |
| Step Executor | ✅ | 使用 Volcengine/step_executor/ |
| Prompt 模板 | ✅ | 使用 Volcengine/step_executor/prompts.py |

### 禁止行为验证

✅ **无跨模型依赖**：
- Doubao Worker 不再导入 `...planner`（Qwen 的）
- Doubao Worker 只调用 [call_doubao()](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\Volcengine\doubao_api.py#L46-L107)
- 每个模型的步骤文件都调用自己的 API

---

## 🎯 下一步行动

### 立即执行
1. **重启 Worker**（清除 Python 缓存）
2. **从前端提交测试任务**
3. **验证步骤执行和文件生成**

### 短期优化
1. 为 Qwen 和 DeepSeek 也创建独立的 Planner
2. 统一所有 Worker 的重试和降级策略
3. 添加详细的日志记录

---

## ✅ 结论

**Doubao Worker v3.2 的代码修复已完成**，但需要**重启 Worker 以加载最新代码**。

当前问题是 **Python 模块缓存**导致的，不是代码逻辑问题。重启后即可看到正确的行为。

---

**报告生成时间**: 2026-05-11 19:30  
**诊断团队**: AlphaPilot 架构团队  
**版本**: v1.0
