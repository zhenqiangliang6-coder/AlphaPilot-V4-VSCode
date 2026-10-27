# AlphaPilot v2.6 快速参考指南

## 🚀 快速开始

### 1. 环境准备

```powershell
# 激活虚拟环境
.\.venv_worker\Scripts\Activate.ps1

# 验证依赖
python -c "import dotenv, redis, requests; print('OK')"
```

### 2. 运行测试

```powershell
# 单元测试
python python_worker/tests/test_intent_router.py

# 快速验证脚本
.\test_intent_router_v26.ps1
```

### 3. 启动 Worker

```powershell
# 启动 Qwen Worker (v2.6)
python -m python_worker.agents.qwen.qwen_worker_v2
```

---

## 📁 核心文件清单

### Intent Router 模块

| 文件 | 说明 | 行数 |
|------|------|------|
| `python_worker/intent_router.py` | 意图路由器核心 | 234 |
| `python_worker/agents/qwen/personas.py` | 双人格配置 | 150 |
| `python_worker/agents/qwen/qwen_worker_v2.py` | Worker 主逻辑 (已集成) | ~400 |
| `python_worker/tests/test_intent_router.py` | 单元测试 | 170 |

### 文档

| 文件 | 说明 |
|------|------|
| `ALPHAPILOT_V26_ARCHITECTURE.md` | v2.6 完整架构文档 |
| `FUTURE_ROADMAP_2026_2027.md` | 未来发展路线图 |
| `V26_SYSTEM_IMPLEMENTATION_SUMMARY.md` | 系统级实施总结 |
| `INTENT_ROUTER_IMPLEMENTATION_REPORT.md` | 阶段1实施报告 |

### 测试脚本

| 文件 | 说明 |
|------|------|
| `test_intent_router_v26.ps1` | PowerShell 自动化测试 |
| `python_worker/tests/test_intent_router.py` | Python 单元测试 |

---

## 🔧 常用命令

### 测试相关

```powershell
# 运行所有单元测试
python python_worker/tests/test_intent_router.py

# 运行快速验证脚本
.\test_intent_router_v26.ps1

# 测试单个意图识别
python -c "from python_worker.intent_router import IntentRouter; print(IntentRouter.detect_intent('写一首诗'))"
```

### 调试相关

```powershell
# 查看 Intent Router 日志
python -m python_worker.agents.qwen.qwen_worker_v2 2>&1 | Select-String "Intent Router"

# 测试特定输入
python -c "
from python_worker.intent_router import IntentRouter
intent, persona, chain = IntentRouter.detect_intent('你的测试输入')
print(f'意图: {intent}')
print(f'人格: {persona}')
print(f'链路: {chain}')
"
```

### 开发相关

```powershell
# 重新构建 Webview
.\rebuild_webview.ps1

# 重启所有服务
.\start_all.ps1

# 检查代码问题
get_problems python_worker/intent_router.py
```

---

## 📊 意图类型速查表

### 支持的意图类型 (10种)

| 意图类型 | 示例输入 | 人格 | 执行链 | 步骤数 |
|---------|---------|------|--------|--------|
| `write_code` | "写一个排序算法" | engineer | analyze → plan → write → test → refine | 5 |
| `explain_code` | "解释一下这段代码" | engineer | analyze → write | 2 |
| `fix_code` | "修复这个bug" | engineer | analyze → fix → test | 3 |
| `creative_writing` | "写一首关于春天的诗" | creator | write → refine | 2 |
| `chat` | "你觉得AI未来会怎样" | conversational | write | 1 |
| `analysis` | "分析一下这个需求" | engineer | analyze → write | 2 |
| `architecture` | "设计一个微服务系统" | engineer | analyze → plan → write | 3 |
| `refactor` | "重构这段代码" | engineer | analyze → refine → test | 3 |
| `generate_doc` | "生成API文档" | engineer | analyze → write | 2 |
| `profile` | "性能分析" | engineer | analyze → profile → write | 3 |

### 人格类型 (3种)

| 人格类型 | 图标 | 适用场景 | 特点 |
|---------|------|---------|------|
| `engineer` | 👨‍💻 | 代码相关任务 | 严谨、结构化、代码优先 |
| `creator` | 🎨 | 创意写作 | 自由、流畅、文学性 |
| `conversational` | 💬 | 闲聊对话 | 友好、智慧、互动 |

---

## 🐛 常见问题排查

### Q1: Intent Router 未识别预期意图?

**症状**: 输入 "写一首诗",但识别为 `write_code`

**排查步骤**:
1. 检查正则表达式是否匹配:
   ```python
   import re
   pattern = r"写.*诗"
   print(re.search(pattern, "写一首诗"))  # 应该返回 Match 对象
   ```

2. 检查优先级顺序:
   ```python
   from python_worker.intent_router import IntentRouter
   print(list(IntentRouter.INTENT_PATTERNS.keys()))  # 查看匹配顺序
   ```

3. 添加调试日志:
   ```python
   # 在 intent_router.py 的 detect_intent 方法中添加
   print(f"Testing pattern: {pattern} against: {prompt_lower}")
   ```

**解决方案**:
- 调整 `INTENT_PATTERNS` 中的顺序 (更具体的意图放前面)
- 优化正则表达式 (增加更多匹配模式)
- 添加新的关键词到对应意图

---

### Q2: 人格切换未生效?

**症状**: 无论什么意图,输出风格都一样

**排查步骤**:
1. 检查 `personas.py` 是否正确加载:
   ```python
   from python_worker.agents.qwen.personas import get_persona_config
   config = get_persona_config("creator")
   print(config["system_prompt"])
   ```

2. 检查 `qwen_api.py` 是否使用人格配置:
   ```python
   # 确认 system_prompt 被正确注入
   messages = [
       {"role": "system", "content": persona_config["system_prompt"]},
       {"role": "user", "content": prompt}
   ]
   ```

3. 检查 Worker 日志:
   ```powershell
   python -m python_worker.agents.qwen.qwen_worker_v2 2>&1 | Select-String "persona"
   ```

**解决方案**:
- 确保 `qwen_api.py` 已集成 Dual-Persona Engine (阶段2待完成)
- 验证 system_prompt 确实传递给 LLM API
- 检查不同人格的 system_prompt 是否有明显差异

---

### Q3: 动态步骤生成失败?

**症状**: steps 为空或步骤顺序错误

**排查步骤**:
1. 检查 `create_steps_from_chain` 函数:
   ```python
   from python_worker.agents.qwen.qwen_worker_v2 import create_steps_from_chain
   steps = create_steps_from_chain(["write", "refine"], "写一首诗", "creator")
   print(steps)
   ```

2. 检查 step_templates 是否完整:
   ```python
   # 确认所有步骤类型都有模板
   print(step_templates.keys())
   ```

3. 检查 Worker 日志:
   ```powershell
   python -m python_worker.agents.qwen.qwen_worker_v2 2>&1 | Select-String "动态生成"
   ```

**解决方案**:
- 确保 `step_templates` 包含所有需要的步骤类型
- 检查 `execution_chain` 是否正确传递
- 验证步骤 ID 和状态初始化

---

### Q4: 前端未显示意图标签?

**症状**: 前端看不到意图和人格信息

**排查步骤**:
1. 检查 TaskModel v2.6 是否包含 intent/persona:
   ```python
   # 在 Worker 中打印 context.meta
   print(context["meta"])
   ```

2. 检查 Node.js API 是否转发这些字段:
   ```javascript
   // node-api/index.js
   console.log("Task meta:", task.meta);
   ```

3. 检查 Webview 是否接收这些数据:
   ```typescript
   // App.tsx
   console.log("Received task_completed:", payload);
   ```

**解决方案**:
- 确保 Worker 将 intent/persona 写入 `context["meta"]`
- 确保 Node.js API 透明转发所有字段
- (阶段4) 创建 IntentBadge 和 PersonaIcon 组件

---

## 📝 开发规范

### 添加新意图类型

**步骤**:
1. 在 `intent_router.py` 的 `INTENT_PATTERNS` 中添加新模式:
   ```python
   "new_intent": [
       r"中文关键词1", r"中文关键词2",
       r"english keyword1", r"english keyword2"
   ],
   ```

2. 在 `INTENT_TO_PERSONA` 中添加人格映射:
   ```python
   "new_intent": "engineer",  # 或 creator/conversational
   ```

3. 在 `INTENT_TO_CHAIN` 中添加执行链:
   ```python
   "new_intent": ["analyze", "write"],  # 根据需求定制
   ```

4. 在 `test_intent_router.py` 中添加测试用例:
   ```python
   def test_new_intent_detection():
       test_cases = [
           ("测试输入1", "new_intent", "engineer"),
           ("测试输入2", "new_intent", "engineer"),
       ]
       # ... 测试逻辑
   ```

5. 运行测试验证:
   ```powershell
   python python_worker/tests/test_intent_router.py
   ```

---

### 添加新人格类型

**步骤**:
1. 在 `personas.py` 的 `PERSONA_PROMPTS` 中添加新人格:
   ```python
   "new_persona": {
       "name": "新人格名称",
       "icon": "🆕",
       "system_prompt": "你是一个...",
       "tone": "...",
       "format": "...",
       "priority": "..."
   },
   ```

2. 在 `intent_router.py` 的 `INTENT_TO_PERSONA` 中使用新的人格:
   ```python
   "some_intent": "new_persona",
   ```

3. 测试人格配置:
   ```python
   from python_worker.agents.qwen.personas import get_persona_config
   config = get_persona_config("new_persona")
   print(config["system_prompt"])
   ```

---

### 修改执行链

**步骤**:
1. 在 `intent_router.py` 的 `INTENT_TO_CHAIN` 中修改:
   ```python
   "existing_intent": ["analyze", "plan", "write", "test"],  # 原来是5步
   ```

2. 确保 `qwen_worker_v2.py` 的 `step_templates` 包含所有步骤类型:
   ```python
   step_templates = {
       "analyze": {...},
       "plan": {...},
       "write": {...},
       "test": {...},
       # 添加新步骤类型...
   }
   ```

3. 运行测试验证:
   ```powershell
   python python_worker/tests/test_intent_router.py
   ```

---

## 🎯 性能优化建议

### 意图识别优化

1. **缓存常见意图**:
   ```python
   from functools import lru_cache
   
   @lru_cache(maxsize=1000)
   def detect_intent_cached(prompt: str) -> Tuple[str, str, List[str]]:
       return IntentRouter.detect_intent(prompt)
   ```

2. **预编译正则表达式**:
   ```python
   import re
   
   # 在类加载时预编译
   COMPILED_PATTERNS = {
       intent: [re.compile(p) for p in patterns]
       for intent, patterns in INTENT_PATTERNS.items()
   }
   ```

3. **并行匹配** (对于长文本):
   ```python
   from concurrent.futures import ThreadPoolExecutor
   
   def parallel_detect(prompt: str):
       with ThreadPoolExecutor(max_workers=4) as executor:
           # 并行匹配不同意图类别
           ...
   ```

---

### Worker 性能优化

1. **异步步骤执行** (对于独立步骤):
   ```python
   import asyncio
   
   async def execute_steps_parallel(steps):
       tasks = [execute_step_async(step) for step in independent_steps]
       return await asyncio.gather(*tasks)
   ```

2. **结果缓存**:
   ```python
   from redis import Redis
   
   redis_client = Redis()
   
   def get_cached_result(cache_key: str):
       return redis_client.get(cache_key)
   ```

3. **批量 LLM 调用**:
   ```python
   # 对于相似请求,批量发送给 LLM
   batch_prompts = [...]
   results = call_llm_batch(batch_prompts)
   ```

---

## 📞 支持与反馈

### 获取帮助

- **文档**: 查看 `ALPHAPILOT_V26_ARCHITECTURE.md`
- **问题报告**: GitHub Issues
- **社区讨论**: Discord / Slack (待建立)

### 贡献代码

1. Fork 仓库
2. 创建特性分支: `git checkout -b feature/new-intent`
3. 提交更改: `git commit -am 'Add new intent type'`
4. 推送分支: `git push origin feature/new-intent`
5. 创建 Pull Request

### 反馈渠道

- **Bug 报告**: GitHub Issues (标签: bug)
- **功能建议**: GitHub Issues (标签: enhancement)
- **文档改进**: GitHub Issues (标签: documentation)

---

**祝开发顺利!** 🚀

*最后更新: 2026-05-06*  
*版本: v2.6-alpha*  
*维护者: AlphaPilot 开发团队*