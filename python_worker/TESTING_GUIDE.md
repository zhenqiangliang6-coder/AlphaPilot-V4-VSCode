# 多模型 Worker v2 测试指南

## 📋 概述

现在你有**三个测试脚本**可以测试 Qwen、DeepSeek 和 Doubao Worker：

1. **`test_multi_model_workers.py`** - 交互式测试（推荐）
2. **`test_all_workers.py`** - 批量对比测试
3. **`test_qwen_worker_v2.py`** - 仅测试 Qwen (旧版)

## 🚀 快速开始

### 方式一：交互式测试（推荐）⭐

**特点**: 每次测试一个模型，可以选择模型和自定义 prompt

```bash
cd python-worker
python test_multi_model_workers.py
```

**测试流程**:

1. **选择模型**
   ```
   请选择要测试的模型:
   1. QWEN
   2. DEEPSEEK
   3. DOUBAO
   
   请输入选项 (1-3): 2  # 选择 DeepSeek
   ```

2. **输入自定义 Prompt**（可选）
   ```
   输入自定义 prompt (直接回车使用默认): 
   ```

3. **启动 Worker**
   
   根据提示在另一个终端窗口启动对应的 Worker：
   
   ```bash
   # 如果选择 Qwen
   cd python-worker/agents/qwen
   python -m agents.qwen.qwen_worker_v2
   
   # 如果选择 DeepSeek
   cd python-worker/agents/deepeek
   python -m agents.deepeek.deepseek_worker_v2
   
   # 如果选择 Doubao
   cd python-worker/agents/Volcengine
   python -m agents.Volcengine.doubao_worker_v2
   ```

4. **查看结果**
   
   测试脚本会自动检查执行结果并显示详细报告。

---

### 方式二：批量对比测试

**特点**: 同时测试所有三个模型，对比性能和结果

```bash
cd python-worker
python test_all_workers.py
```

**前提条件**: 需要同时启动所有三个 Worker：

```bash
# 终端 1 - Qwen Worker
# Qwen
cd C:\Users\DavidLiang\Desktop\Copilot_Alphapilot
python -m python_worker.agents.qwen.qwen_worker_v2
# DeepSeek
cd C:\Users\DavidLiang\Desktop\Copilot_Alphapilot
python -m python_worker.agents.deepeek.deepseek_worker_v2

# Doubao
cd C:\Users\DavidLiang\Desktop\Copilot_Alphapilot
python -m python_worker.agents.Volcengine.doubao_worker_v2
```

**输出示例**:

```
批量提交任务到所有 Worker
================================================================================

✅ QWEN 任务已提交
   · Task ID: test-qwen-1711900000000
   · Prompt: 写一个函数，计算斐波那契数列的第 n 项

✅ DEEPSEEK 任务已提交
   · Task ID: test-deepseek-1711900000001
   · Prompt: 写一个函数，计算斐波那契数列的第 n 项

✅ DOUBAO 任务已提交
   · Task ID: test-doubao-1711900000002
   · Prompt: 写一个函数，计算斐波那契数列的第 n 项

等待所有任务执行完成...

✅ QWEN 成功完成! (耗时：5.23s)
✅ DEEPSEEK 成功完成! (耗时：6.45s)
✅ DOUBAO 成功完成! (耗时：4.89s)

测试结果对比
================================================================================

📊 总体统计:
   · 总任务数：3
   · 成功：3
   · 失败：0

📋 详细结果:

QWEN:
   状态：done
   耗时：5.23 秒
   步骤数：4
      - analyze: success
      - plan: success
      - write: success
      - test: success

DEEPSEEK:
   状态：done
   耗时：6.45 秒
   步骤数：4
      - analyze: success
      - plan: success
      - write: success
      - test: success

DOUBAO:
   状态：done
   耗时：4.89 秒
   步骤数：4
      - analyze: success
      - plan: success
      - write: success
      - test: success

================================================================================
批量测试完成!
================================================================================
```

---

## 📊 测试功能

### ✅ 测试的功能点

1. **任务提交流程** - 验证 Redis 队列推送
2. **Worker 执行** - 验证 Planner + Step Executor 完整流程
3. **步骤状态管理** - pending → running → success/error
4. **结果写入** - 验证 TaskModel v2 格式
5. **取消机制** - 测试任务取消功能（可选）

### 🎯 支持的模型

| 模型 | Task Type | Worker 模块 | 状态 |
|------|-----------|-------------|------|
| **Qwen** | `qwen_generate` | `agents.qwen.qwen_worker_v2` | ✅ |
| **DeepSeek** | `deepseek_generate` | `agents.deepeek.deepseek_worker_v2` | ✅ |
| **Doubao** | `doubao_generate` | `agents.Volcengine.doubao_worker_v2` | ✅ |

---

## 🛠️ 故障排查

### Worker 未响应

**问题**: 提交任务后 Worker 没有反应

**解决方案**:
1. 确认 Worker 正在运行
2. 检查 Redis 连接
   ```bash
   redis-cli ping
   ```
3. 检查队列是否有任务
   ```bash
   LLEN task_queue
   ```

### 任务执行失败

**问题**: 任务状态为 "error"

**解决方案**:
1. 查看错误信息
   ```python
   result = redis.get("task_result:task-id")
   print(result["error"]["message"])
   ```
2. 检查 `.env` 文件中的 API Key 配置
3. 查看 Worker 日志

### 等待超时

**问题**: 测试脚本显示 "等待超时"

**解决方案**:
1. 增加等待时间（修改 `max_wait` 参数）
2. 确认 Worker 正常运行
3. 检查模型 API 是否正常响应

---

## 📈 性能对比

使用批量测试脚本可以对比不同模型的性能：

### 对比维度

1. **响应速度** - 从提交到完成的总耗时
2. **步骤数量** - 执行的步骤数
3. **代码质量** - 生成代码的可执行性
4. **测试通过率** - 自动生成的测试是否通过

### 预期结果

根据模型特性：

- **Qwen**: 中文理解好，响应速度快
- **DeepSeek**: 推理能力强，代码质量高
- **Doubao**: 综合能力强，实用导向

---

## 💡 最佳实践

### 1. 先单独测试每个模型

使用 `test_multi_model_workers.py` 逐个测试，确保每个 Worker 都能正常工作。

### 2. 再批量对比

所有 Worker 都正常后，使用 `test_all_workers.py` 进行性能对比。

### 3. 记录测试结果

建议记录每次测试的结果，包括：
- 响应时间
- 成功率
- 代码质量评分

### 4. 定制化测试

根据实际需求修改测试 prompt，例如：
```python
TEST_PROMPT = """
实现一个完整的 RESTful API，包含以下功能：
1. 用户注册和登录
2. 数据增删改查
3. 权限验证
"""
```

---

## 🔧 自定义测试

### 修改默认 Prompts

编辑 `test_multi_model_workers.py`:

```python
MODEL_CONFIGS = {
    "qwen": {
        "task_type": "qwen_generate",
        "worker_module": "agents.qwen.qwen_worker_v2",
        "default_prompt": "你的自定义 prompt"  # 修改这里
    },
    # ...
}
```

### 调整等待时间

编辑 `test_multi_model_workers.py`:

```python
# 增加等待时间（默认 120 秒）
max_wait = 180  # 改为 180 秒
```

---

## 📚 参考文档

- [多模型 Worker 统一架构](MULTI_MODEL_WORKERS.md)
- [快速开始指南](QUICKSTART_TESTING.md)
- [实现总结](IMPLEMENTATION_SUMMARY.md)

---

DavidLiang - 2026-03-31
