# Local Worker 文件生成失败 - 诊断与修复报告

**日期**: 2026-05-19  
**任务**: "写一个计算器模块"  
**状态**: ⚠️ **部分成功** (路由正确,但模型未输出协议格式)

---

## 🔍 问题诊断

### ✅ 已成功的部分

1. **路由正确**: 
   - Node API 正确路由到 `task_queue:local`
   - Local Worker 成功接收任务
   
2. **执行链正确**:
   - 意图识别: `write_code`
   - 人格选择: `engineer`
   - 执行链: `write → test` (简化链路)

3. **Worker 正常运行**:
   - Local Worker v3.0 正常监听队列
   - 任务执行完成并返回结果

---

### ❌ 失败的部分

#### 问题 1: write_step 未生成 FileOps

**现象**:
```json
"context": {
  "final_file_ops": [],  // ❌ 空数组
  "intermediate_results": [
    {
      "type": "write",
      "text": "Here's a thinking process that leads to the suggested output:\n\n1. **Analyze the Request:** The user wants \"code/content\" generated based on the persona of an \"engineer.\"..."
    }
  ]
}
```

**根本原因**:
- Local LLM (Gemma 4B) **没有遵循 `# FILE:` 协议**
- 模型输出了"工程师人格"的元思考内容,而不是代码
- `parse_fileops_v3` 无法解析自然语言,返回空数组

**日志证据**:
```
write_step 输出:
"Here's a thinking process that leads to the suggested output:
1. Analyze the Request: The user wants 'code/content' generated based on the persona of an 'engineer.'
...
作为一个"工程师"的人格，我的核心思维模式是：结构化、逻辑化、流程化..."
```

---

#### 问题 2: test_step 测试伪代码导致语法错误

**现象**:
```python
error: Traceback (most recent call last):
  File "code_executor.py", line 48, in _execute_code_in_process
    exec(code, {})
  File "<string>", line 26
    FUNCTION Solve_Problem(Input_Data, Constraints):
             ^^^^^^^^^^^^^
SyntaxError: invalid syntax
```

**根本原因**:
- test_step 从 write_step 的输出中提取了**伪代码** (`pseudocode`)
- 伪代码不是合法的 Python 语法,导致执行失败

**日志证据**:
```json
"tested_code": "pseudocode\nFUNCTION Solve_Problem(Input_Data, Constraints):\n    // Step 1: Input Validation..."
```

---

## 🛠️ 已实施的修复

### 修复 1: 增强 write_prompt (已完成)

**文件**: [`python_worker/agents/local_llm/step_executor/prompts.py`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\step_executor\prompts.py#L57-L145)

**修改内容**:
1. ✅ 添加**具体示例** (hello.py + tests/test_hello.py + README.md)
2. ✅ 强化约束:**禁止输出解释性文字**
3. ✅ 明确错误示例:
   - ❌ "Here's a thinking process..."
   - ❌ "作为一个工程师..."
4. ✅ 强调正确格式:直接输出 `# FILE:` 开头的代码

**预期效果**:
- Local LLM 更有可能遵循协议格式
- 减少自然语言输出的概率

---

## 📊 当前状态评估

| 组件 | 状态 | 说明 |
|------|------|------|
| 路由逻辑 | ✅ 正常 | Node API 正确路由到 local 队列 |
| Local Worker | ✅ 正常 | 成功接收并执行任务 |
| write_prompt | ✅ 已增强 | 添加了示例和更强约束 |
| parse_fileops_v3 | ✅ 正常 | 可以解析 # FILE: 协议 |
| Local LLM 输出 | ⚠️ 待验证 | 需要重新测试是否遵循协议 |
| final_file_ops | ❌ 为空 | 模型未输出协议格式 |

---

## 🚀 下一步行动

### 方案 A: 重新测试 (推荐先试这个)

**步骤**:
1. **重启 Local Worker** (加载新的 prompt)
2. **提交相同任务**: "写一个计算器模块"
3. **观察日志**: 检查 write_step 是否输出 `# FILE:` 格式

**命令**:
```powershell
# 1. 停止 Local Worker (Ctrl+C)
# 2. 重新启动
$env:WORKER_ID='local-worker-1'
python -m python_worker.agents.local_llm.local_worker_v3

# 3. 在 VSCode 中重新提交任务
```

**预期结果**:
- ✅ write_step 输出包含 `# FILE: calculator.py`
- ✅ `context["final_file_ops"]` 不为空
- ✅ 前端显示生成的文件

---

### 方案 B: 如果方案 A 仍然失败

**问题**: Local LLM (Gemma 4B) 能力有限,无法严格遵循协议

**解决方案**:

#### B1. 增强自然语言解析器 (兜底机制)

在 [`write_step.py`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\step_executor\write_step.py) 中添加更强的自然语言回退逻辑:

```python
# 如果 parse_fileops_v3 返回空,尝试更激进的自然语言解析
if not file_ops:
    # 尝试提取所有 Python 代码块
    code_blocks = re.findall(r'```python\n(.*?)\n```', result, re.DOTALL)
    if code_blocks:
        # 为每个代码块生成 FileOp
        for i, code in enumerate(code_blocks):
            file_ops.append(create_file_op(
                action="create",
                path=f"file_{i+1}.py",
                content=code,
                reason="natural-language-fallback"
            ))
```

#### B2. 调整 Persona 配置

修改 [`personas.py`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\personas.py),让 engineer 人格更倾向于输出代码而非文档:

```python
"system_prompt": """你是一位软件工程师。你的任务是：
1. 直接输出代码，不要任何解释
2. 必须使用 # FILE: 协议格式
3. 禁止输出思考过程或元描述"""
```

#### B3. 切换到更强大的本地模型

如果 Gemma 4B 确实无法遵循协议,考虑:
- 升级到 Gemma 7B 或更大模型
- 或使用 Qwen 2.5 7B (本地运行)

---

## 📝 总结

### 核心问题
Local LLM (Gemma 4B) **没有遵循 `# FILE:` 协议**,而是输出了自然语言描述。

### 已修复
- ✅ 增强了 write_prompt,添加了具体示例和更强约束
- ✅ 快速测试脚本验证通过

### 待验证
- ⏳ 需要重新测试,确认 Local LLM 是否遵循新 prompt

### 建议
1. **立即执行**: 重启 Local Worker 并重新测试
2. **如果仍失败**: 实施方案 B (增强自然语言解析器)
3. **长期方案**: 考虑升级到更强大的本地模型

---

**修复完成时间**: 2026-05-19  
**下一步**: 重新测试并观察 Local LLM 输出
