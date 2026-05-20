# Local Worker v3.2.3 ASCII 文件树功能实施报告

## 📋 修复概述

**修复日期**: 2026-05-19  
**修复范围**: 仅 Local Worker v3.0 (`python_worker/agents/local_llm/step_executor/`)  
**架构影响**: ✅ 零侵入其他 Worker（Qwen/Doubao/DeepSeek 保持不变）  
**方案选择**: 方案② - Gemma 输出 ASCII 文件树（无需前端改动）

---

## 🔍 需求分析

### 用户诉求
让 Local Worker 也能像 Qwen/Doubao 一样，拥有完整的流式输出和进度反馈，特别是**文件树的可视化展示**。

### 两种方案对比

#### 方案①：前端自动生成文件树图片
- ❌ 需要修改前端代码（违反"后端代码修改权限偏好"）
- ❌ 增加 Webview 复杂度
- ❌ Local Worker 能力有限，无法提供实时进度数据

#### 方案②：Gemma 输出 ASCII 文件树（✅ 推荐）
- ✅ **零前端改动**（符合架构约束）
- ✅ Gemma 4B 擅长文本生成，ASCII 树是它的强项
- ✅ 无需额外依赖，纯文本输出
- ✅ 符合 Local Worker "简化执行链"的定位
- ✅ 用户可直接复制粘贴使用

---

## 🛠️ 实施方案

### 修改文件清单

1. **`python_worker/agents/local_llm/step_executor/prompts.py`**
   - 修改 `write_prompt()` 函数
   - 添加 ASCII 文件树输出要求

2. **`python_worker/agents/local_llm/step_executor/write_step.py`**
   - 新增 `extract_ascii_tree()` 函数
   - 在 FileOps 解析后提取并展示 ASCII 树
   - 将 ASCII 树添加到 events 中供前端展示

3. **`test_local_worker_ascii_tree.py`** (新增)
   - 单元测试脚本
   - 验证 ASCII 树提取功能

### 核心代码变更

#### 1. prompts.py - write_prompt 函数

```python
def write_prompt(plan: str) -> str:
    """
    Multi‑File Protocol v3.2 — 对齐 persona system_prompt 的 ### 格式
    
    ⭐ v3.2.2 修复版：统一使用 ### 分隔符格式,避免与 persona system_prompt 冲突
    ⭐ v3.2.3 新增：要求 Gemma 4B 输出 ASCII 文件树（无需前端改动）
    """
    return f"""你现在处于 AlphaPilot OS v3.2 环境。

请严格按照以下"多文件输出协议"生成代码：

==========================
### <相对路径>
<代码内容>

### <测试文件路径>
<测试代码内容>

### <文档路径>
<文档内容>

### FILE_TREE
<ASCII 文件树结构>
==========================

【代码规划】：
{plan}

**重要提醒**:
1. 必须使用 `###` 作为文件分隔符
2. 不要输出任何解释、思考过程或元描述
3. 直接输出代码文件内容
4. 每个文件以 `### 文件名` 开头
5. **必须在最后输出 ASCII 文件树**（使用 ### FILE_TREE 分隔符）

**ASCII 文件树格式示例**:
```
### FILE_TREE
project/
├── calculator.py
├── tests/
│   └── test_calculator.py
└── README.md
```

**文件树规则**:
- 使用 ├─ 和 └─ 符号表示层级关系
- 文件夹后面加 /
- 缩进使用 4 个空格
- 只展示生成的文件，不要展示无关文件

现在 please directly output code file:"""
```

#### 2. write_step.py - extract_ascii_tree 函数

```python
def extract_ascii_tree(text: str) -> str:
    """
    从 LLM 输出中提取 ASCII 文件树
    
    参数:
        text: LLM 完整输出文本
    
    返回:
        str: ASCII 文件树字符串，如果未找到则返回空字符串
    """
    # 查找 ### FILE_TREE 分隔符
    pattern = r'###\s*FILE_TREE\s*\n(.*?)(?:\n###|\Z)'
    match = re.search(pattern, text, re.DOTALL)
    
    if match:
        tree_content = match.group(1).strip()
        print(f"[INFO] 成功提取 ASCII 文件树 ({len(tree_content)} 字符)")
        return tree_content
    
    print("[WARN] 未找到 ASCII 文件树 (### FILE_TREE)")
    return ""
```

#### 3. write_step.py - 集成 ASCII 树展示

```python
# 如果解析到 FileOps，更新 context["final_file_ops"]
if file_ops:
    context["final_file_ops"] = file_ops
    print(f"[SUCCESS] write_step 生成 {len(file_ops)} 个 FileOps")
    
    #  v3.2.3 新增：解析并展示 ASCII 文件树
    ascii_tree = extract_ascii_tree(result)
    if ascii_tree:
        print("\n 生成的文件结构:")
        print(ascii_tree)
        print()
        
        # 将 ASCII 树添加到 events 中，供前端展示
        if task_id:
            event = create_event(
                "file_tree",
                {"ascii_tree": ascii_tree, "file_count": len(file_ops)}
            )
            events.append(event)
```

---

## ✅ 验证结果

### 单元测试通过

```bash
$ python test_local_worker_ascii_tree.py

🧪 Local Worker v3.2.3 ASCII 文件树功能验证

测试 1 (extract_ascii_tree): ✅ 通过
测试 2 (write_prompt 包含要求): ✅ 通过
测试 3 (无文件树容错): ✅ 通过

🎉 所有测试通过！Local Worker v3.2.3 ASCII 文件树功能就绪！
```

### 关键指标

- ✅ 成功提取 ASCII 文件树（78 字符）
- ✅ 正确识别所有文件（calculator.py、test_calculator.py、README.md）
- ✅ write_prompt 包含所有必要要求（FILE_TREE、ASCII 文件树、├─、文件夹标记）
- ✅ 容错处理：当 LLM 未输出文件树时，返回空字符串不报错

---

## 🚀 端到端测试步骤

### 测试脚本

已提供快速测试脚本：`test_local_worker_ascii_tree.py`

### 完整链路测试步骤

1. **清除缓存并重启 Local Worker**:
   ```powershell
   cd d:\Copilot_Alphapilot\Copilot_Alphapilot
   Get-ChildItem -Path . -Recurse -Filter '__pycache__' -Directory | Remove-Item -Recurse -Force
   $env:WORKER_ID='local-worker-1'
   python -m python_worker.agents.local_llm.local_worker_v3
   ```

2. **提交多文件生成任务**（通过前端或 Node API）:
   ```json
   {
     "task_id": "test-xxx",
     "type": "local_generate",
     "payload": {
       "prompt": "写一个计算器模块，包含 calculator.py、tests/test_calculator.py 和 README.md"
     },
     "model": "local-gemma4b"
   }
   ```

3. **预期输出**:
   ```
   [INFO] 成功解析 3 个文件 (### 分隔符格式)
   [DEBUG] parse_nl_fileops_enhanced 返回: 3 个文件
     - calculator.py: XXX 字符
     - tests/test_calculator.py: XXX 字符
     - README.md: XXX 字符
   [SUCCESS] write_step 生成 3 个 FileOps
   
   [INFO] 成功提取 ASCII 文件树 (XX 字符)
   
    生成的文件结构:
   project/
   ├── calculator.py
   ├── tests/
   │   └── test_calculator.py
   └── README.md
   ```

4. **验证点**:
   - ✅ 日志中出现 `[INFO] 成功提取 ASCII 文件树`
   - ✅ 控制台打印 ASCII 文件树结构
   - ✅ events 中包含 `file_tree` 事件（供前端展示）
   - ✅ 不再出现 `[WARN] 未找到 ASCII 文件树`（除非 LLM 真的没输出）

---

## 📊 修复前后对比

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 文件树展示 | ❌ 无 | ✅ ASCII 文本树 |
| 前端改动 | N/A | ✅ 零改动 |
| 用户体验 | 只能看文件列表 | 可看结构化树形图 |
| 可复制性 | ❌ 无法复制 | ✅ 可直接复制粘贴 |
| 架构合规性 | N/A | ✅ 完全符合规范 |
| 实施成本 | N/A | 仅需修改 2 个文件 |

---

##  总结

### 修复成果
✅ **精准定位**: 修改 Local Worker 的 2 处代码（prompts.py + write_step.py）  
✅ **零副作用**: 不影响 Qwen/Doubao/DeepSeek 等其他 Worker  
✅ **零前端改动**: 完全在后端实现，符合架构约束  
✅ **立即生效**: 清除缓存后重启即可生效  

### 架构信条遵守
- ✅ **模型独立性**: Local Worker 独立增强，不跨模型依赖
- ✅ **协议一致性**: 使用标准的 `create_event()` 接口传递 file_tree 事件
- ✅ **最小侵入**: 仅添加新功能，不重构现有逻辑
- ✅ **向后兼容**: 当 LLM 未输出文件树时，优雅降级（返回空字符串）

### 关键教训
️ **方案选择的重要性**: 在架构约束下，选择最适合的方案（方案②）比追求完美视觉效果更重要  
️ **容错设计**: 必须考虑 LLM 可能不遵循 prompt 的情况，提供优雅的降级机制  
⚠️ **主动测试验证**: 遵循"修改 → 清除缓存 → 运行测试 → 观察日志"的闭环工作流

### 后续建议
1. **前端适配**（可选）: 如果未来允许修改前端，可以在 Webview 中渲染 ASCII 树为更美观的样式
2. **监控日志**: 观察 Local Worker 是否稳定输出 ASCII 文件树
3. **优化 Prompt**: 根据实际测试结果，微调 write_prompt 以提高 Gemma 4B 的遵从率

---

**修复完成时间**: 2026-05-19 20:00  
**修复负责人**: AlphaPilot Team  
**架构审核**: ✅ 符合 v3.2.3 架构规范  
**测试状态**: ✅ 单元测试通过，等待端到端验证
