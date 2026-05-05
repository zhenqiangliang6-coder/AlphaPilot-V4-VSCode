# Qwen 架构重构 - 验证清单

## 📋 使用说明
请在测试前逐项检查以下内容，确保重构成功。

---

## ⚠️ 重要前提：包结构完整性

### ✅ 必须存在的 __init__.py 文件

在运行 Worker 之前，请确认以下文件存在：

- [ ] `python-worker/__init__.py` 
- [ ] `python-worker/agents/__init__.py`
- [ ] `python-worker/agents/qwen/__init__.py`
- [ ] `python-worker/agents/qwen/step_executor/__init__.py`

**这些文件可以为空，但必须存在！** 否则 Python 无法识别包结构，会导致：

```
ModuleNotFoundError: No module named 'worker_config'
```

### 🔧 如何创建

如果缺少任何 `__init__.py` 文件，创建空文件即可：

```bash
# 方法 1: 使用 touch 命令（Linux/Mac）
touch python-worker/__init__.py
touch python-worker/agents/__init__.py
touch python-worker/agents/qwen/__init__.py

# 方法 2: 使用 PowerShell（Windows）
New-Item -Path "python-worker\__init__.py" -ItemType File
New-Item -Path "python-worker\agents\__init__.py" -ItemType File
New-Item -Path "python-worker\agents\qwen\__init__.py" -ItemType File

# 方法 3: 手动创建
# 在对应目录中新建文本文档，重命名为 __init__.py
```

---

## ✅ 代码质量检查

### 1. 导入规范检查

- [ ] 所有 `step_executor/` 包内文件使用相对导入
  - [ ] `analyze_step.py`: `from .qwen_api import ...`
  - [ ] `plan_step.py`: `from .prompts import ...`
  - [ ] `write_step.py`: `from .utils import ...`
  - [ ] `refine_step.py`: `from .qwen_api import ...`
  - [ ] `test_step.py`: `from .utils import ...`
  - [ ] `fix_step.py`: `from .qwen_api import ...`
  - [ ] `profile_step.py`: `from .utils import ...`
  - [ ] `doc_step.py`: `from .qwen_api import ...`
  - [ ] `execute_step.py`: `from .analyze_step import ...`

- [ ] **根目录模块使用相对导入（跨包）**
  - [ ] `refine_step.py`: `from ..code_executor import run_python` ✅
  - [ ] `test_step.py`: `from ..code_executor import run_python` ✅
  - [ ] `fix_step.py`: `from ..code_executor import run_python` ✅
  - [ ] `profile_step.py`: `from ..code_executor import run_python` ✅
  - [ ] `doc_step.py`: `from ..code_executor import run_python` ✅

- [ ] 根目录模块使用绝对导入（同包内）
  - [ ] `from worker_config import create_event`
  - [ ] ~~`from code_executor import run_python`~~ ❌ (已改为相对导入)

- [ ] `qwen_api.py` 添加了路径处理
  ```python
  import sys
  import os
  sys.path.insert(0, os.path.abspath(...))
  ```

---

### 2. 文件完整性检查

- [ ] 所有 step 文件都有标准文件头
  ```python
  # step_executor/xxx_step.py
  # ---------------------------------------------------------
  # 步骤说明
  # ---------------------------------------------------------
  ```

- [ ] `__init__.py` 导出列表完整
  - [ ] 核心步骤函数导出
  - [ ] 扩展步骤函数导出
  - [ ] `execute_step` 导出
  - [ ] 工具函数导出
  - [ ] Prompt 模板导出

---

### 3. 语法检查

运行以下命令确认没有语法错误：

```bash
cd python-worker/agents/qwen
python -m py_compile qwen_api.py
python -m py_compile step_executor/__init__.py
python -m py_compile step_executor/execute_step.py
python -m py_compile step_executor/*_step.py
```

预期结果：**无错误输出**

---

## 🧪 功能测试

### 基础环境检查

- [ ] Redis 服务可用
  ```bash
  redis-cli ping
  # 应返回：PONG
  ```

- [ ] 环境变量配置正确
  ```bash
  # 检查 .env 文件
  DASHSCOPE_API_KEY=your_key_here
  UPSTASH_REDIS_REST_URL=your_url
  UPSTASH_REDIS_REST_TOKEN=your_token
  WORKER_ID=qwen-worker-v2
  ```

- [ ] Python 依赖已安装
  ```bash
  pip list | grep -E "requests|upstash_redis|python-dotenv"
  ```

---

### Worker 启动测试

- [ ] 能够成功启动 Worker
  
  **方式 1：从子包目录启动**
  ```bash
  cd python-worker/agents/qwen
  python qwen_worker_v2.py
  ```
  
  **方式 2：从根目录使用 -m 启动（推荐）**
  ```bash
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
python -m python-worker.agents.qwen.qwen_worker_v2
  ```
  
  预期输出：
  ```
  🚀 Qwen Worker v2 已启动
     · Worker ID: qwen-worker-1
     · Node API: 已连接
     · 正在监听任务队列...
  ```

- [ ] Worker 连接到 Redis 成功
  - 观察日志中是否有连接错误

---

### 任务执行测试

#### 测试 1: 简单任务提交

- [ ] 运行测试脚本
  ```bash
  cd python-worker
  python test_qwen_worker_v2.py
  ```

- [ ] 任务成功提交到队列
  - 看到 "✅ 任务已推送到 Redis 队列"

- [ ] Worker 接收到任务
  - Worker 日志显示 "收到任务:"

- [ ] 任务执行完成
  - 看到 "任务完成，结果已写入 Redis:"

#### 测试 2: 手动提交任务

- [ ] 创建测试脚本 `manual_test.py`:
  ```python
  from worker_config import redis
  from TaskModel_v2 import TaskModel
  import json
  
  task = TaskModel.create_task_submit(
      task_id="manual-test-001",
      task_type="qwen_generate",
      payload={"prompt": "写一个函数，计算两个数的和"}
  )
  redis.lpush("task_queue", json.dumps(task))
  print("✅ 任务已提交")
  ```

- [ ] 运行脚本并提交任务

- [ ] 在 Worker 日志中看到任务执行过程

- [ ] 检查结果
  ```python
  result = redis.get("task_result:manual-test-001")
  print(result)
  ```

---

### 步骤执行验证

- [ ] **Analyze 步骤**执行成功
  - 步骤状态：pending → running → success
  - 输出包含需求分析

- [ ] **Plan 步骤**执行成功
  - 基于 analyze 结果生成规划
  - 步骤状态正确流转

- [ ] **Write 步骤**执行成功
  - 生成可运行的 Python 代码
  - 代码块格式正确（```python）

- [ ] **Refine 步骤**执行成功（如果触发）
  - 代码执行并优化
  - 输出优化后的代码

- [ ] **Test 步骤**执行成功（如果触发）
  - 生成单元测试
  - 运行测试并输出结果

---

### 取消机制测试

- [ ] 设置取消标记
  ```python
  redis.set("stop:test-task-id", "1")
  ```

- [ ] Worker 检测到取消标记
  - 日志显示 "🛑 任务已被用户取消"

- [ ] 步骤状态变为 cancelled

- [ ] 清理取消标记
  ```python
  redis.delete("stop:test-task-id")
  ```

---

## 📊 数据流验证

### Redis 数据检查

- [ ] 任务队列正常
  ```bash
  redis-cli LRANGE task_queue 0 -1
  # 应该有任务或为空（已消费）
  ```

- [ ] 任务结果正常
  ```bash
  redis-cli GET task_result:{task_id}
  # 应该返回 JSON 格式的结果
  ```

- [ ] 事件流记录正常
  - 检查结果中的 `events` 数组
  - 应包含 `analyze_output`, `plan_output` 等事件

---

### TaskModel v2 兼容性

- [ ] 结果符合 v2 规范
  - [ ] `version`: "2.0"
  - [ ] `task_id`: 正确的 ID
  - [ ] `status`: "done" / "error" / "cancelled"
  - [ ] `steps`: 包含所有执行步骤
  - [ ] `events`: 包含事件流
  - [ ] `context`: 包含上下文信息

---

## 🔍 错误处理验证

### 常见错误场景

- [ ] **API Key 错误**
  - 提交任务后，Worker 应报告 "LLM 调用失败"
  - 错误信息清晰可读

- [ ] **Redis 连接失败**
  - Worker 启动时应报告连接错误
  - 错误堆栈完整

- [ ] **Prompt 为空**
  - 抛出 `ValueError: prompt 不能为空`
  - 任务状态变为 error

- [ ] **JSON 解析失败**
  - Planner 应处理 LLM 返回的非 JSON 内容
  - 有适当的错误提示

- [ ] **ModuleNotFoundError**
  - 使用 `-m` 方式运行时不应出现模块找不到错误
  - 所有跨包导入都应使用 `..` 相对导入

---

## 📝 文档验证

### 文档完整性

- [ ] `ARCHITECTURE_REFACTOR.md` 内容完整
  - [ ] 架构图清晰
  - [ ] 示例代码正确
  - [ ] 迁移指南可行

- [ ] `QUICK_REFERENCE.md` 实用性强
  - [ ] 常用操作有示例
  - [ ] 常见问题有解答
  - [ ] 命令可直接复制使用

- [ ] `UPDATE_SUMMARY.md` 总结全面
  - [ ] 修改文件清单完整
  - [ ] 关键修复点清晰
  - [ ] 后续工作建议合理

---

## 🎯 最终确认

### 重构目标达成

- [ ] ✅ Prompt 规范化：所有 Prompt 集中到 `prompts.py`
- [ ] ✅ 模块化设计：每个步骤独立，职责清晰
- [ ] ✅ 可复用架构：新增步骤只需 3 步
- [ ] ✅ 导入规范：相对导入正确使用
- [ ] ✅ 包结构完整：所有 __init__.py 文件存在
- [ ] ✅ **跨包导入修复：使用 `..` 相对导入**

### 代码质量

- [ ] ✅ 所有文件通过语法检查
- [ ] ✅ 注释完整，易于理解
- [ ] ✅ 格式统一，风格一致

### 功能完整性

- [ ] ✅ Worker 能正常启动（支持两种启动方式）
- [ ] ✅ 任务能正常提交和执行
- [ ] ✅ 步骤状态管理正常
- [ ] ✅ 取消机制有效

### 文档完善度

- [ ] ✅ 架构文档详细
- [ ] ✅ 快速参考实用
- [ ] ✅ 更新总结清晰

---

## 📅 测试记录

### 第一次测试

- **日期**: __________
- **测试人**: __________
- **测试结果**: 
  - [ ] 通过
  - [ ] 部分通过
  - [ ] 失败
- **问题记录**:
  ```
  1. ...
  2. ...
  ```
- **解决方案**:
  ```
  1. ...
  2. ...
  ```

### 第二次测试（如有必要）

- **日期**: __________
- **测试人**: __________
- **测试结果**: 
  - [ ] 通过
  - [ ] 部分通过
  - [ ] 失败

---

## ✅ 验收签字

- **开发负责人**: __________ 日期：__________
- **测试负责人**: __________ 日期：__________
- **项目经理**: __________ 日期：__________

---

**版本**: 1.2 (已修复跨包导入)  
**更新日期**: 2026-03-28  
**文档位置**: `python-worker/agents/qwen/CHECKLIST.md`
