# AlphaPilot OS v3.1 - DeepSeek & Doubao Worker 升级报告

## 📋 执行摘要

**升级时间**: 2026-05-11  
**升级范围**: DeepSeek Worker v2 → v3.0, Doubao Worker v2 → v3.0  
**架构基准**: Qwen Worker v3.0（已完成验证）  
**升级状态**: ✅ 代码完成，待测试验证

---

## 🎯 升级目标

基于 Qwen Worker v3.0 的成功经验，将 DeepSeek Worker 和 Doubao Worker 升级到相同的架构标准，实现：

1. **协议一致性**：所有 Worker 遵循 TaskModel v2、FileOps v3.0、流式协议 v2.4
2. **组件复用**：Intent Router、Persona Engine、Execution Chain 跨 Worker 共享
3. **功能对等**：DeepSeek/Doubao 具备与 Qwen 相同的核心能力
4. **向后兼容**：保留特殊任务类型（如 doubao_multimodal）

---

## 🏗️ 架构升级详情

### 1. DeepSeek Worker v2 → v3.0

#### 新增文件
- ✅ `python_worker/agents/deepeek/deepseek_worker_v3.py` (379 行)
- ✅ `python_worker/agents/deepeek/step_executor/docstring_step.py` (102 行)

#### 修改文件
- ✅ `python_worker/agents/deepeek/step_executor/execute_step.py` (支持 task_id + docstring)
- ✅ `python_worker/agents/deepeek/step_executor/__init__.py` (导出 docstring_step)

#### 核心升级内容

**① Intent Router 集成**
```python
from ...intent_router import IntentRouter

intent, persona_type, _ = IntentRouter.detect_intent(prompt)
```

**② Persona Engine 集成**
```python
from ..qwen.personas import get_persona_config

persona_config = get_persona_config(persona_type)
```

**③ Execution Chain 动态生成**
```python
BASE_CHAIN = ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring", "profile"]

INTENT_CHAINS = {
    "write_code": ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring"],
    "generate_doc": ["analyze", "plan", "write", "doc", "docstring"],
    "explain_code": ["analyze", "plan", "doc"],
    "creative_writing": ["analyze", "plan", "write", "refine"],
    "chat": ["analyze", "write"],
}
```

**④ FileOps v3.0 管理**
```python
context["final_file_ops"] = []  # ⭐ 唯一真相源
```

**⑤ Node API 通知机制**
```python
notify_url = f"{NODE_API_URL}/task/notify/{task_id}"
response = requests.post(notify_url, json=result_data, timeout=10)
```

**⑥ 流式输出支持**
```python
# execute_step 自动检测 task_id 参数
if "task_id" in sig.parameters:
    handler(step, context, events, task_id=task_id)
```

---

### 2. Doubao Worker v2 → v3.0

#### 新增文件
- ✅ `python_worker/agents/Volcengine/doubao_worker_v3.py` (415 行)
- ✅ `python_worker/agents/Volcengine/step_executor/docstring_step.py` (102 行)

#### 修改文件
- ✅ `python_worker/agents/Volcengine/step_executor/execute_step.py` (支持 task_id + docstring)
- ✅ `python_worker/agents/Volcengine/step_executor/__init__.py` (导出 docstring_step)

#### 核心升级内容

**① Intent Router + Persona Engine**
- 与 DeepSeek 完全相同的集成方式

**② 多模态任务向后兼容**
```python
if task_type == "doubao_multimodal":
    prompt = payload.get("prompt", "")
    image_url = payload.get("image_url")
    
    from .doubao_api import call_doubao
    result = call_doubao(prompt, image_url)
    return result
```

**③ 图片传递支持**
```python
if image_url:
    api_func_with_image = lambda p: call_doubao_wrapper(p, image_url)
    execute_step(task_id, step, events, context, api_func=api_func_with_image)
else:
    execute_step(task_id, step, events, context)
```

**其他升级内容与 DeepSeek 一致**

---

## 📊 升级对比表

| 功能模块 | Qwen v3.0 | DeepSeek v2 | DeepSeek v3.0 | Doubao v2 | Doubao v3.0 |
|---------|-----------|-------------|---------------|-----------|-------------|
| Intent Router | ✅ | ❌ | ✅ | ❌ | ✅ |
| Persona Engine | ✅ | ❌ | ✅ | ❌ | ✅ |
| Execution Chain | ✅ | ❌ | ✅ | ❌ | ✅ |
| FileOps v3.0 | ✅ | ❌ | ✅ | ❌ | ✅ |
| docstring_step | ✅ | ❌ | ✅ | ❌ | ✅ |
| task_id 支持 | ✅ | ❌ | ✅ | ❌ | ✅ |
| Node API 通知 | ✅ | ❌ | ✅ | ❌ | ✅ |
| 多模态支持 | N/A | N/A | N/A | ✅ | ✅ |

---

## 🔧 技术细节

### 1. 组件复用策略

**Intent Router**
- 路径: `python_worker/intent_router.py`
- 复用方式: 直接导入 `from ...intent_router import IntentRouter`
- 优势: 统一意图识别逻辑，避免重复实现

**Persona Engine**
- 路径: `python_worker/agents/qwen/personas.py`
- 复用方式: `from ..qwen.personas import get_persona_config`
- 优势: 三个人格配置（engineer/creator/conversational）统一管理

**Execution Chain 配置**
- 定义位置: 各 Worker v3.py 文件头部
- 配置内容: BASE_CHAIN + INTENT_CHAINS
- 优势: 每个 Worker 可自定义执行链，保持灵活性

### 2. FileOps v3.0 生命周期管理

**初始化**
```python
context["final_file_ops"] = []  # 在 main_loop 中初始化
```

**写入**
```python
# 在 write_step、refine_step 等步骤中
context["final_file_ops"].extend(file_ops)
context["file_ops"] = context["final_file_ops"]  # 别名同步
```

**读取**
```python
# 在 docstring_step、doc_step 等消费步骤中
file_ops = context.get("final_file_ops") or context.get("file_ops") or []
```

**过滤**
```python
from ....file_ops import filter_valid_file_ops, get_python_files

valid_file_ops = filter_valid_file_ops(file_ops)
py_files = get_python_files(file_ops)
```

### 3. 流式协议 v2.4 实现

**通道映射规则**
- 思考类阶段 (`analyze`/`plan`/`refine`/`test`): `channel="reasoning"`
- 产出类阶段 (`write`): `channel="content"`

**自动检测机制**
```python
import inspect
sig = inspect.signature(handler)

if "task_id" in sig.parameters:
    handler(step, context, events, task_id=task_id)  # 新签名
else:
    handler(step, context, events)  # 旧签名（向后兼容）
```

---

## ✅ 架构合规性验证

### Worker = 真相（Truth Source）
- ✅ 所有决策（意图识别、人格选择、执行链构建）在 Worker 内完成
- ✅ FileOps 的生成和验证都在 Worker 内完成
- ✅ 前端、Node API、VSCode 插件不参与逻辑判断

### 协议 = 宪法（Protocol = Constitution）
- ✅ TaskModel v2: 统一的任务结果结构
- ✅ FileOps v3.0: final_file_ops 作为唯一真相源
- ✅ 流式协议 v2.4: channel.reasoning/content 分层
- ✅ 步骤状态机: pending → running → completed/failed

### Extension = 映射（Mapper）
- ✅ Node API 原样转发 final_file_ops，不做任何修改
- ✅ Node API 接收 Worker 通知后推送给前端

### Webview = 投影（Projector）
- ✅ 前端只展示 FileOps 和步骤进度，不参与逻辑判断
- ✅ 用户确认后，VSCode Plugin 执行写盘操作

---

## 🧪 测试计划

### 1. 单元测试（待执行）

**DeepSeek Worker**
```powershell
cd python_worker
python -m pytest tests/test_deepseek_worker_v3.py -v
```

**Doubao Worker**
```powershell
cd python_worker
python -m pytest tests/test_doubao_worker_v3.py -v
```

### 2. 集成测试（待执行）

**启动 Worker**
```powershell
cd python_worker/agents/deepeek
python deepseek_worker_v3.py

cd python_worker/agents/Volcengine
python doubao_worker_v3.py
```

**提交测试任务**
```python
# 测试 DeepSeek
task = {
    "task_id": "test-deepseek-001",
    "type": "deepseek_generate",
    "payload": {"prompt": "创建一个 Python 函数计算斐波那契数列"},
    "meta": {"retry_count": 0, "started_at": int(time.time() * 1000)}
}
redis.lpush("task_queue:deepseek", json.dumps(task))

# 测试 Doubao
task = {
    "task_id": "test-doubao-001",
    "type": "doubao_generate",
    "payload": {"prompt": "解释这段代码的功能"},
    "meta": {"retry_count": 0, "started_at": int(time.time() * 1000)}
}
redis.lpush("task_queue:doubao", json.dumps(task))
```

### 3. 端到端测试（待执行）

**验证点**
- [ ] Intent Router 正确识别意图
- [ ] Persona Engine 正确选择人格
- [ ] Execution Chain 按意图动态裁剪
- [ ] FileOps v3.0 正确生成和管理
- [ ] docstring_step 正确为 Python 文件添加文档字符串
- [ ] 流式输出正常显示（reasoning/content 通道）
- [ ] Node API 通知成功推送
- [ ] 取消机制正常工作
- [ ] 错误处理和 DLQ 写入正常

---

## 📝 后续工作

### 短期（1-2 天）
1. **运行测试脚本**：验证 DeepSeek 和 Doubao Worker v3.0 功能
2. **修复问题**：根据测试结果修复潜在 bug
3. **性能优化**：监控 Worker 响应时间和资源占用

### 中期（1 周）
1. **文档完善**：更新 MULTI_MODEL_WORKERS.md 和 QUICKSTART_TESTING.md
2. **监控增强**：添加 Worker 健康检查和指标采集
3. **日志优化**：结构化日志输出，便于排查问题

### 长期（1 月）
1. **更多模型支持**：Claude、Gemini、OpenAI Worker 升级
2. **执行链扩展**：新增 security_audit、i18n_translate 等步骤
3. **智能调度**：根据负载动态分配任务到不同 Worker

---

## 🎉 总结

本次升级成功将 DeepSeek Worker 和 Doubao Worker 从 v2 提升到 v3.0，实现了：

✅ **架构统一**：三个 Worker（Qwen/DeepSeek/Doubao）现在遵循相同的架构标准  
✅ **协议一致**：TaskModel v2、FileOps v3.0、流式协议 v2.4 全面落地  
✅ **组件复用**：Intent Router、Persona Engine 等核心组件跨 Worker 共享  
✅ **向后兼容**：保留特殊任务类型（doubao_multimodal），不影响现有功能  

**下一步**：运行测试验证，确保升级后的 Worker 在实际环境中稳定运行。

---

**报告生成时间**: 2026-05-11 15:30  
**报告作者**: AlphaPilot 架构团队  
**版本**: v1.0
