# Local LLM Worker 执行链优化报告

## 📋 问题背景

用户反馈："用python写一个排序函数"任务耗时 **13 分钟**，其中：
- 模型加载：3 分钟
- 8 步执行链：10 分钟（每步 1-2 分钟）

虽然功能正常，但用户体验较差。

---

## 🎯 优化目标

将简单任务的执行时间从 **13 分钟** 缩短到 **2-3 分钟**。

---

## 🔍 根本原因

### 当前执行链配置
```python
INTENT_CHAINS = {
    "write_code": ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring"],
}
```

**问题**：所有 [write_code](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\webview\src\components\IntentBadge.tsx#L9-L9) 任务都使用完整的 8 步链路，包括：
- analyze（分析需求）
- plan（制定计划）
- write（编写代码）
- refine（优化代码）
- test（测试代码）
- fix（修复错误）
- doc（生成文档）
- docstring（添加文档字符串）

对于简单任务（如"写一个排序函数"），这些步骤过于冗余。

---

## 🛠️ 解决方案

### 方案：智能简化执行链 ⭐

#### 核心思路
根据提示词的复杂度和意图，动态选择执行链长度：
- **复杂任务**（>50 字符或包含复杂关键词）：完整 8 步链路
- **简单任务**（<50 字符且包含简单关键词）：简化 2 步链路（write → test）

#### 实现细节

**1. 新增 `simple_code` 意图链路**
```python
INTENT_CHAINS = {
    # 完整工程链路（复杂任务）
    "write_code": ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring"],
    
    # ⭐ 简化代码生成链路（简单任务）
    "simple_code": ["write", "test"],
    
    # 其他链路保持不变
    "generate_doc": ["analyze", "plan", "write", "doc", "docstring"],
    "explain_code": ["analyze", "plan", "doc"],
    "creative_writing": ["analyze", "plan", "write", "refine"],
    "chat": ["analyze", "write"],
}
```

**2. 智能判断逻辑**
```python
def build_execution_chain(intent: str, prompt: str = "") -> list:
    """根据意图和提示词复杂度选择执行链"""
    
    # 默认链路
    chain = INTENT_CHAINS.get(intent, BASE_CHAIN)
    
    # ⭐ 智能简化：如果提示词很短且包含简单关键词
    simple_keywords = ["写一个", "实现一个", "创建一个", "排序", "函数", "工具"]
    is_simple_task = (
        len(prompt) < 50 and  # 提示词很短
        any(kw in prompt for kw in simple_keywords) and  # 包含简单关键词
        intent == "write_code"  # 是代码生成任务
    )
    
    if is_simple_task:
        print(f"\n💡 检测到简单任务，使用简化执行链: write → test")
        return INTENT_CHAINS.get("simple_code", ["write", "test"])
    
    return chain
```

**3. 更新调用点**
```python
# 修改前
execution_chain = build_execution_chain(intent)

# 修改后
execution_chain = build_execution_chain(intent, prompt)
```

---

## 📊 预期效果

### 对比分析

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| **执行步骤数** | 8 步 | 2 步 | -75% |
| **LLM 调用次数** | 8 次 | 2 次 | -75% |
| **预计耗时** | 10 分钟 | 2-3 分钟 | -70% |
| **总耗时（含加载）** | 13 分钟 | 5-6 分钟 | -54% |

### 适用场景

#### ✅ 使用简化链路（2 步）
- "用python写一个排序函数"
- "实现一个快速排序"
- "创建一个工具函数"
- "写一个简单的计算器"

#### ✅ 使用完整链路（8 步）
- "设计一个电商系统的订单管理模块，包含数据库设计、API接口、单元测试..."
- "重构这个遗留代码库，优化性能并添加文档"
- "实现一个支持并发的高性能Web服务器"

---

## 🧪 验证方法

### 测试用例 1: 简单任务
```bash
提交任务: "用python写一个排序函数"
预期输出:
  💡 检测到简单任务，使用简化执行链: write → test
  🔄 执行步骤 [RUNNING]: write (ID: step-1)
  ✅ 步骤完成: write
  🔄 执行步骤 [RUNNING]: test (ID: step-2)
  ✅ 步骤完成: test
```

### 测试用例 2: 复杂任务
```bash
提交任务: "设计一个完整的用户认证系统，包含JWT token、刷新机制、权限控制..."
预期输出:
  🧠 Local LLM Worker v3.0 决策：
    意图: write_code
    人格: 工程师 (👨‍💻)
    执行链: analyze → plan → write → refine → test → fix → doc → docstring
```

---

## 📦 修改文件清单

### 核心修改
1. **[`python_worker/agents/local_llm/local_worker_v3.py`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\local_worker_v3.py)**
   - 新增 `simple_code` 意图链路
   - 优化 [build_execution_chain()](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\local_worker_v3.py#L65-L92) 函数，支持智能简化
   - 更新调用点，传入 prompt 参数

---

## 🚀 部署步骤

### 1. 停止当前 Worker
```powershell
Stop-Process -Name python -Force
```

### 2. 清除缓存
```powershell
cd d:\Copilot_Alphapilot\Copilot_Alphapilot
python restart_local_worker_with_fix.py
```

### 3. 重启 Worker
```powershell
.\start_local_worker.ps1
```

### 4. 验证优化
重新提交任务："用python写一个排序函数"

**预期结果**:
- ✅ 看到日志：`💡 检测到简单任务，使用简化执行链: write → test`
- ✅ 只执行 2 个步骤（write + test）
- ✅ 总耗时从 13 分钟缩短到 5-6 分钟

---

## 🎓 经验总结

### 关键洞察
1. **不是所有任务都需要完整链路**: 简单任务过度处理会浪费时间和资源
2. **智能判断很重要**: 基于提示词长度和关键词自动选择执行策略
3. **用户体验优先**: 在保证质量的前提下，尽可能缩短响应时间

### 后续优化方向
1. **更精细的意图识别**: 区分"简单函数"、"中等模块"、"复杂系统"
2. **自适应超时**: 根据任务复杂度动态调整超时时间
3. **缓存机制**: 对于常见任务（如排序、搜索），缓存标准实现
4. **并行执行**: 某些步骤可以并行（如 doc 和 docstring）

---

## 📝 相关文档

- [Local LLM Worker v3.0 架构文档](./LOCAL_LLM_WORKER_V3_IMPLEMENTATION_REPORT.md)
- [执行链卡住问题诊断报告](./LOCAL_LLM_WORKER_HANG_DIAGNOSIS_REPORT.md)
- [Code Executor 超时保护修复](./LOCAL_LLM_CODE_EXECUTOR_TIMEOUT_FIX_REPORT.md)

---

**优化完成时间**: 2026-05-16  
**优化人员**: AlphaPilot AI Assistant  
**预期提升**: 简单任务执行时间减少 70%
