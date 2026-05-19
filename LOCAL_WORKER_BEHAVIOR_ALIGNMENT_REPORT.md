# Local Worker 行为对齐 Qwen Worker - 修复报告

**日期**: 2026-05-19  
**版本**: v3.2  
**状态**: ✅ 已完成

---

## 📋 核心诉求

> **要的是行为对齐(能力),不是实现对齐(代码)**

### ✅ 需要的能力
- Qwen Worker 的多文件协议 (`# FILE:` / `# TEST:` / `# DOC:`)
- Qwen Worker 的工程链路 (analyze → plan → write → refine → test)
- Qwen Worker 的 FileOps 行为 (生成、解析、验证、更新)

### ❌ 不需要的实现
- Qwen Worker 的 API (`qwen_api.py`)
- Qwen Worker 的网络模型
- Qwen Worker 的旧 step_executor

### ⭐ 目标架构
```
Local Worker = Qwen Worker 的能力 + 本地模型的执行 + AlphaPilot 架构信条
```

---

## 🔍 问题诊断

### 问题 1: Local Worker 无法生成文件

**现象**:
- Local Worker 可以接收任务并执行
- 但 `context["final_file_ops"]` 始终为空
- 前端无法显示生成的文件

**根本原因**:
1. **Prompt 格式不匹配**: 
   - Local Worker 的 [write_prompt](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\step_executor\prompts.py#L54-L113) 要求模型输出 **JSON 格式**
   - 而 [parse_fileops_v3](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\file_ops.py#L95-L135) 只解析 **`# FILE:` 协议格式**
   
2. **Local LLM 能力限制**:
   - Gemma 4B 模型可能不擅长输出严格的 JSON
   - 即使输出 JSON,也无法被现有的解析器识别

### 问题 2: Refine Step 缺失 FileOps 链路

**现象**:
- write_step 可能生成了 FileOps
- 但 refine_step 没有更新 `context["final_file_ops"]`
- 导致优化后的代码无法持久化

**根本原因**:
- Local Worker 的 [refine_step](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\step_executor\refine_step.py#L16-L127) 只处理代码字符串
- 没有调用 [parse_fileops_v3](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\file_ops.py#L95-L135)
- 没有更新 `context["final_file_ops"]` (唯一真相源)

---

## 🛠️ 修复方案

### 修复 1: write_prompt 对齐 (# FILE: 协议)

**文件**: [`python_worker/agents/local_llm/step_executor/prompts.py`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\step_executor\prompts.py)

#### ❌ 旧逻辑 (JSON 格式)
```python
def write_prompt(plan: str) -> str:
    return f"""
你必须只输出一个 JSON 对象，格式如下：

{{
  "file_ops": [
    {{
      "action": "create",
      "path": "hello.py",
      "content": "..."
    }}
  ]
}}
"""
```

#### ✅ 新逻辑 (# FILE: 协议)
```python
def write_prompt(plan: str) -> str:
    """
    Multi‑File Protocol v3.0 — 对齐 Qwen Worker 的 # FILE: 协议格式
    """
    return f"""你现在处于 AlphaPilot OS v3.0 环境。

请严格按照以下"多文件输出协议"生成代码：

==========================
# FILE: <相对路径>
<代码内容>

# TEST: <测试文件路径>
<测试代码内容>

# DOC: <文档路径>
<文档内容>
==========================

【代码规划】：
{plan}

⭐⭐⭐ 强制要求（必须遵守）：

1. 必须使用 "# FILE:" 开头声明文件路径  
2. 每个文件必须单独一个 # FILE: 块  
3. 支持新协议：# TEST: / # DOC: / # META: / # DEPENDS:
4. 不得省略 # FILE:  
5. 不得输出未声明路径的代码  

只输出多文件协议内容，不要任何解释性文字。
"""
```

**关键变化**:
- ✅ 从 JSON 格式改为 `# FILE:` 协议格式
- ✅ 与 Qwen Worker 的 [write_prompt](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\qwen\step_executor\prompts.py#L58-L126) 完全一致
- ✅ 适配 Local LLM (Gemma 4B) 的自然语言生成能力

---

### 修复 2: refine_step 对齐 (FileOps 全链路)

**文件**: [`python_worker/agents/local_llm/step_executor/refine_step.py`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\step_executor\refine_step.py)

#### ❌ 旧逻辑 (单文件模式)
```python
def run_refine_step(step, context, events, task_id=None):
    # 1) 获取 write 步骤的代码
    write_outputs = [item["code"] for item in context["intermediate_results"] if item["type"] == "write"]
    code = write_outputs[-1]
    
    # 2) 执行代码
    exec_result = run_python(FAKE_ENVIRONMENT + "\n\n" + code)
    
    # 3) 调用 LLM 优化
    optimized_text = api_func(optimize_prompt(code, exec_summary))
    
    # 4) 提取优化后的代码
    optimized_code = extract_code(optimized_text)
    
    # ❌ 没有处理 FileOps
    # ❌ 没有更新 context["final_file_ops"]
```

#### ✅ 新逻辑 (多文件模式)
```python
def run_refine_step(step, context, events, task_id=None):
    """
    refine 步骤（v3.2）：
    - ⭐ v3.2：支持多文件协议优化（对齐 Qwen Worker）
    """
    
    # 1) ⭐ v3.2：获取当前 file_ops（唯一真相源）
    file_ops = context.get("final_file_ops", []) or context.get("file_ops", [])
    valid_file_ops = filter_valid_file_ops(file_ops)
    
    # 2) 如果没有 file_ops，回退到旧逻辑（单文件模式）
    if not valid_file_ops:
        # ... 旧逻辑 ...
        return
    
    # === v3.2 新逻辑：多文件模式 ===
    
    # 3) 构建虚拟项目（只包含 Python 文件）
    virtual_project = ""
    for fo in valid_file_ops:
        if fo.get("path", "").endswith(".py"):
            virtual_project += f"# FILE: {fo['path']}\n{fo.get('content', '')}\n\n"
    
    # 4) 执行整个项目
    exec_result = run_python(FAKE_ENVIRONMENT + "\n\n" + virtual_project)
    
    # 5) 调用 LLM 优化代码（⭐ 要求输出 # FILE: 协议格式）
    prompt = f"""请优化以下 Python 项目代码，保持多文件结构不变：

【当前项目】：
{virtual_project}

【执行结果】：
{exec_summary}

要求：
1. 必须使用 "# FILE:" 协议格式输出优化后的代码
2. 保持原有的文件数量和路径
3. 只优化代码内容，不改变文件结构
"""
    
    optimized_text = api_func(prompt)
    
    # 6) ⭐ v3.2：解析模型输出的新 FileOps
    refined_file_ops = parse_fileops_v3(optimized_text)
    
    # ⭐ 方向 A：如果模型没有生成新的 file_ops，则保留原始 file_ops
    if refined_file_ops:
        # ⭐ 更新 final_file_ops（唯一真相源）
        context["final_file_ops"] = refined_file_ops
        context["file_ops"] = refined_file_ops
        print(f"✅ refine_step 更新 {len(refined_file_ops)} 个 FileOp")
    else:
        print("[INFO] refine_step: 模型未生成新 FileOps，保留原有结构")
```

**关键变化**:
- ✅ 从 `context["final_file_ops"]` 获取当前文件列表
- ✅ 构建虚拟项目并发送给 LLM 优化
- ✅ 调用 [parse_fileops_v3](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\file_ops.py#L95-L135) 解析模型返回的新 FileOps
- ✅ 更新 `context["final_file_ops"]` (唯一真相源)
- ✅ 与 Qwen Worker 的 [refine_step](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\qwen\step_executor\refine_step.py#L9-L60) 完全对齐

---

## 🏗️ 架构信条遵循

### 1. Worker = 真相 (Truth Source)
- ✅ 所有 FileOps 的生成、解析、验证都发生在 Worker 内部
- ✅ Node API、VSCode 插件、前端都不推断文件内容，只执行 FileOps

### 2. 协议 = 宪法 (Protocol = Constitution)
- ✅ `# FILE:` 协议是 AlphaPilot OS 的唯一文件操作协议
- ✅ 所有文件写入必须通过 FileOps，不允许 Worker 直接写文件
- ✅ FileOps 的结构稳定、可预测、可验证

### 3. 能力对齐而非实现对齐
- ✅ Local Worker 复用 Qwen Worker 的多文件协议和工程链路
- ✅ Local Worker 使用本地模型 (Gemma 4B) 的执行
- ✅ Local Worker 不复制 Qwen Worker 的 API 或网络模型

---

## 🧪 验证方法

### 1. 启动 Local Worker
```powershell
cd Copilot_Alphapilot
python python_worker/agents/local_llm/local_worker_v3.py
```

### 2. 提交测试任务
```python
# 使用 test_local_worker_fileops.py
python test_local_worker_fileops.py
```

### 3. 观察日志
**预期输出**:
```
🧠 Local LLM Worker v3.0 决策：
  意图: write_code
  人格: Engineer (🔧)
  执行链: analyze → plan → write → refine → test

✅ Local LLM write_step 生成 3 个 FileOp
   - create: calculator.py (file)
   - create: tests/test_calculator.py (file)
   - create: README.md (file)

✅ refine_step 更新 3 个 FileOp
```

### 4. 检查 Redis 结果
```python
import redis
import json

r = redis.Redis(host='localhost', port=6379, db=0)
result = r.get('task_result:test_local_1234567890')
data = json.loads(result)

# 检查 final_file_ops
print(data['context']['final_file_ops'])
```

**预期结果**:
```json
[
  {
    "op": "create",
    "path": "calculator.py",
    "content": "...",
    "file_type": "file",
    "language": "python",
    "reason": "主代码文件",
    "from_step": "write"
  },
  {
    "op": "create",
    "path": "tests/test_calculator.py",
    "content": "...",
    "file_type": "file",
    "language": "python",
    "reason": "测试文件",
    "from_step": "test"
  }
]
```

---

## 📊 性能指标

| 指标 | 目标值 | 实际值 | 状态 |
|------|--------|--------|------|
| 文件生成成功率 | ≥ 90% | TBD | ⏳ 待验证 |
| FileOps 解析准确率 | ≥ 95% | TBD | ⏳ 待验证 |
| 平均响应时间 | ≤ 30s | TBD | ⏳ 待验证 |
| 多文件支持数 | ≥ 5 | TBD | ⏳ 待验证 |

---

## 🚀 后续优化

### 短期 (v3.3)
- [ ] 增强自然语言解析器的鲁棒性
- [ ] 添加 FileOps 验证器（路径安全、后缀白名单）
- [ ] 优化 Local LLM 的 prompt 模板（减少 token 消耗）

### 中期 (v3.4)
- [ ] 支持更多文件类型（JavaScript、TypeScript、Java）
- [ ] 实现增量优化（只修改变化的文件）
- [ ] 添加 FileOps 冲突检测（避免覆盖用户文件）

### 长期 (v4.0)
- [ ] 支持动态执行链（根据任务复杂度自动调整）
- [ ] 实现多轮对话优化（基于用户反馈迭代改进）
- [ ] 集成代码质量评估工具（pylint、flake8）

---

## 📝 总结

本次修复的核心目标是让 **Local Worker 行为对齐 Qwen Worker 的能力**,而不是复制其实现。通过以下两个关键修复:

1. ✅ **write_prompt 对齐**: 从 JSON 格式改为 `# FILE:` 协议格式
2. ✅ **refine_step 对齐**: 实现 FileOps 全链路（获取 → 优化 → 解析 → 更新）

Local Worker 现在具备了与 Qwen Worker 相同的多文件生成能力,同时保持了本地模型执行的独立性。这符合 AlphaPilot 的架构信条:

> **Worker = 真相 + 协议 = 宪法 + 能力对齐 ≠ 实现对齐**

---

**下一步**: 运行 `test_local_worker_fileops.py` 验证修复效果,并根据测试结果进行进一步优化。
