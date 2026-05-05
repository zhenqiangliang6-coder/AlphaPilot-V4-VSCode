# Step Executor 模块

## 📁 目录结构

```
step_executor/
│
├── __init__.py              # 模块入口，统一导出 API
├── qwen_api.py              # Qwen API 调用封装
├── utils.py                 # 工具函数（extract_code / fake pytest / fake env）
├── prompts.py               # 所有 prompt 模板（10 个函数）
│
├── execute_step.py          # ★ 统一步骤调度器（新增）
│
├── analyze_step.py          # analyze 步骤执行器
├── plan_step.py             # plan 步骤执行器
├── write_step.py            # write 步骤执行器
├── refine_step.py           # refine 步骤执行器
│
├── test_step.py             # test 步骤执行器
├── fix_step.py              # fix 步骤执行器
├── profile_step.py          # profile 步骤执行器
├── doc_step.py              # doc 步骤执行器
│
└── README.md                # 模块文档

```

## 🎯 模块化设计原则

### 1. **单一职责**
每个文件负责一个明确的功能：
- `analyze_step.py`：分析用户需求，提取关键点
- `plan_step.py`：生成代码结构规划
- `write_step.py`：根据规划生成代码
- `refine_step.py`：执行代码并优化
- `test_step.py`：pytest 风格单元测试 + fake pytest
- `fix_step.py`：mock-aware 自动修复
- `profile_step.py`：mock-aware 性能分析
- `doc_step.py`：生成 .md 文档 + docstring
- `utils.py`：通用工具函数
- `prompts.py`：统一的 prompt 模板（10 个函数）
- `qwen_api.py`：API 调用封装

### 2. **关注点分离**
- **Prompt 层**（`prompts.py`）：只负责生成提示词
- **执行层**（`*_step.py`）：只负责业务逻辑
- **工具层**（`utils.py`）：只提供辅助功能
- **API 层**（`qwen_api.py`）：只负责外部调用

### 3. **可测试性**
每个模块独立可测，互不依赖：
```python
from step_executor import analyze_prompt, plan_prompt, write_prompt

# 单独测试 prompt 生成
analysis = analyze_prompt("实现一个快速排序算法")
plan = plan_prompt(analysis)
code = write_prompt(plan)
```

## 🔧 核心工具

### utils.py

#### extract_code(text: str) -> str
从 LLM 输出中提取代码块

#### FAKE_PYTEST
fake pytest 实现，支持：
- `pytest.raises(Exception)`
- 上下文管理器协议
- 异常匹配验证

#### FAKE_ENVIRONMENT
mock 环境配置，包括：
- `builtins.open` → MagicMock
- `time.sleep` → MagicMock
- `random.random` → 固定返回值
- `requests.get/post` → MagicMock
- `os.remove/listdir` → MagicMock
- `sqlite3.connect` → MagicMock
- `subprocess.run` → MagicMock

## 📝 Prompt 模板

### 核心工作流 Prompt（标准四阶段）

#### analyze_prompt(user_input: str) -> str
分析用户需求的 prompt

#### plan_prompt(analysis: str) -> str
生成代码结构规划的 prompt

#### write_prompt(plan: str) -> str
根据规划生成代码的 prompt

#### refine_prompt(code: str, exec_summary: str) -> str
根据执行结果优化代码的 prompt

### 扩展步骤 Prompt

#### test_prompt(code: str) -> str
生成 pytest 风格单元测试的 prompt

#### fix_prompt(code: str, error_message: str) -> str
生成自动修复代码的 prompt

#### profile_prompt(code: str) -> str
生成性能分析的 prompt

#### doc_prompt(code: str) -> str
生成完整文档的 prompt

#### docstring_prompt(code: str) -> str
为代码添加 docstring 的 prompt

#### optimize_prompt(code: str, exec_summary: str) -> str
生成代码优化的 prompt

## 🚀 使用示例

### 完整的四阶段工作流
```python
from step_executor import (
    run_analyze_step,
    run_plan_step,
    run_write_step,
    run_refine_step
)

# 初始化上下文
context = {"intermediate_results": []}
events = []

# 1. analyze - 分析需求
step1 = {
    "id": "step-1",
    "type": "analyze",
    "input": {"prompt": "实现一个快速排序算法"}
}
run_analyze_step(step1, context, events)

# 2. plan - 生成规划
step2 = {
    "id": "step-2",
    "type": "plan",
    "input": {}
}
run_plan_step(step2, context, events)

# 3. write - 生成代码
step3 = {
    "id": "step-3",
    "type": "write",
    "input": {}
}
run_write_step(step3, context, events)

# 4. refine - 执行并优化
step4 = {
    "id": "step-4",
    "type": "refine",
    "input": {}
}
run_refine_step(step4, context, events)
```

### 使用 prompt 模板
```python
from step_executor import (
    analyze_prompt,
    plan_prompt,
    write_prompt,
    refine_prompt,
    call_qwen
)

# 1. 分析需求
analysis_prompt_text = analyze_prompt("实现一个快速排序算法")
analysis = call_qwen(analysis_prompt_text)

# 2. 生成规划
plan_prompt_text = plan_prompt(analysis)
plan = call_qwen(plan_prompt_text)

# 3. 生成代码
write_prompt_text = write_prompt(plan)
code_text = call_qwen(write_prompt_text)

# 4. 执行并优化
exec_result = run_python(code_text)
exec_summary = f"stdout:\n{exec_result['stdout']}\nstderr:\n{exec_result['stderr']}"
refine_prompt_text = refine_prompt(code_text, exec_summary)
optimized_code = call_qwen(refine_prompt_text)
```

### 执行 test 步骤
```python
from step_executor import run_test_step

context = {
    "intermediate_results": [
        {
            "type": "write",
            "text": "```python\ndef add(a, b):\n    return a + b\n```"
        }
    ]
}

step = {"id": "step-5", "type": "test", "input": {}}
events = []

run_test_step(step, context, events)
print(step["output"]["text"])
```

### 使用 fake pytest
```python
from step_executor import FAKE_PYTEST

code = """
def test_add():
    assert add(1, 2) == 3
    
def test_error():
    with pytest.raises(ValueError):
        raise ValueError("expected")
"""

full_code = FAKE_PYTEST + "\n\n" + code
result = run_python(full_code)
```

## ✅ 已完成的功能

### 核心四阶段（完整工作流）
- ✅ `analyze_step.py` - 分析用户需求
- ✅ `plan_step.py` - 生成代码规划
- ✅ `write_step.py` - 生成实现代码
- ✅ `refine_step.py` - 执行并优化代码

### 扩展步骤
- ✅ `test_step.py` - 自动生成并运行单元测试
- ✅ `fix_step.py` - 自动修复代码错误
- ✅ `profile_step.py` - 性能分析
- ✅ `doc_step.py` - 生成文档

### 基础设施
- ✅ `prompts.py` - 10 个完整的 prompt 模板
- ✅ `qwen_api.py` - Qwen API 调用封装
- ✅ `utils.py` - 核心工具函数
- ✅ `__init__.py` - 统一的模块导出
- ✅ `README.md` - 完整的模块文档

## 📊 标准工作流程

```
用户输入
   ↓
[analyze] → 需求分析
   ↓
[plan]     → 代码规划
   ↓
[write]    → 实现代码
   ↓
[refine]   → 执行 + 优化
   ↓
[test]     → 测试验证（可选）
   ↓
[fix]      → 修复错误（如果需要）
   ↓
[profile]  → 性能分析（可选）
   ↓
[doc]      → 生成文档（可选）
```

## 🎯 下一步计划

### 增强功能
- [ ] 添加步骤执行的日志记录
- [ ] 实现步骤执行的超时控制
- [ ] 添加步骤执行结果的缓存
- [ ] 支持自定义 prompt 模板
- [ ] 实现步骤间的依赖检查

### 可观测性
- [ ] 添加详细的执行日志
- [ ] 实现性能指标收集
- [ ] 添加错误追踪和恢复机制

## 📚 相关文档

- [智能体任务执行工作流规范](../../TASK_MODEL_SPECIFICATION.md)
- [步骤执行器扩展规范](../../ENHANCEMENT_SETUP.md)
- [AlphaPilot 架构信条](../../ARCHITECTURE_MANIFESTO.md)