# AlphaPilot 前后端通信问题修复经验总结

> **创建时间:** 2026-05-04  
> **状态:** ✅ 已修复,前后端完整链路已打通  
> **适用场景:** 调试 Worker-Node-API-前端通信问题

---

## 📋 问题清单与解决方案

### 问题 1: Worker 无法调用 Node.js `/task/notify` 端点

#### 症状
```python
⚠️ 通知 Node.js 失败: name 'NODE_API_URL' is not defined
```

#### 根因
[qwen_worker_v2.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\qwen\qwen_worker_v2.py) 使用了 `NODE_API_URL` 和 `requests.post()`,但没有导入这两个依赖。

#### 修复方案
```python
# qwen_worker_v2.py 文件头部添加:
import requests  # 新增

from ...worker_config import (
    redis,
    WORKER_ID,
    create_empty_context,
    check_stop_flag,
    clear_stop_flag,
    get_worker_queue,
    NODE_API_URL,  # 新增: 从 worker_config 导入
)
```

#### 教训
- **显式导入**: 所有使用的非内置符号都必须有对应的 `import` 语句
- **检查导入完整性**: 添加新功能时立即检查并添加必要的导入语句
- **配置项集中管理**: 项目配置集中在 `worker_config.py`,使用时需明确导入

---

### 问题 2: `requests.post` 返回 MagicMock 对象

#### 症状
```python
📌 requests 模块: <module 'requests' from '...'>
 requests.post: <MagicMock id='1632028142864'>  ← 被 mock 了!
 response 类型: <class 'unittest.mock.MagicMock'>
⚠️ Node.js 返回错误状态码: <MagicMock name='mock().status_code'>
```

#### 根因
**所有 8 个 agent 的 `utils.py` 文件中都有全局 mock 代码:**
```python
# python_worker/agents/qwen/step_executor/utils.py (第174行)
requests.post = MagicMock()
```

当 [utils.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\qwen\step_executor\utils.py) 被导入时:
1. 替换整个 Python 进程中的 `requests.post`
2. 导致所有后续调用都返回 MagicMock 对象
3. Worker 无法真正调用 Node.js 的 `/task/notify` 端点
4. 前端永远收不到任务完成的通知

#### 修复方案
**删除所有 agent 的 utils.py 中的全局 mock:**

修复了以下 8 个文件:
1. ✅ [python_worker/agents/qwen/step_executor/utils.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\qwen\step_executor\utils.py)
2. ✅ [python_worker/agents/Volcengine/step_executor/utils.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\Volcengine\step_executor\utils.py)
3. ✅ [python_worker/agents/claude/step_executor/utils.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\claude\step_executor\utils.py)
4. ✅ [python_worker/agents/deepeek/step_executor/utils.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\deepeek\step_executor\utils.py)
5. ✅ [python_worker/agents/gemini/step_executor/utils.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\gemini\step_executor\utils.py)
6. ✅ [python_worker/agents/local_llm/step_executor/utils.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\local_llm\step_executor\utils.py)
7. ✅ [python_worker/agents/multi_agent/step_executor/utils.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\multi_agent\step_executor\utils.py)
8. ✅ [python_worker/agents/openai/step_executor/utils.py](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\agents\openai\step_executor\utils.py)

**修改内容:**
```python
# 修改前:
requests.post = MagicMock()  # ← 污染整个进程!

# 修改后:
# ⭐ 修复: 删除全局 mock,这些会污染整个 Python 进程
# 以下 mock 仅用于测试,不应在生产代码中使用
# builtins.open = MagicMock()
# time.sleep = MagicMock()
# random.random = MagicMock(return_value=0.5)
# requests.get = MagicMock()
# requests.post = MagicMock()  # ← 已注释
# os.remove = MagicMock()
# os.listdir = MagicMock(return_value=[])
# sqlite3.connect = MagicMock()
# subprocess.run = MagicMock()
```

#### 教训
1. **严禁在生产代码中全局 Mock 第三方库**
2. **Mock 应该只在测试框架作用域内使用** (使用 `patch` 装饰器或上下文管理器)
3. **隔离运行环境**: 确保业务脚本使用干净 Python 进程,避免与测试共享状态
4. **验证模块身份**: 打印 `type(requests.post)` 或 `requests.__file__` 确认真实库加载
5. **重启服务**: 最简单有效的方法是重启进程清除内存中的 Mock 状态

---

### 问题 3: 前端收到结果但不显示内容

#### 症状
- 前端只显示"任务完成"状态卡片
- 没有显示 AI 生成的代码内容
- 控制台日志显示收到了完整的 `task_result` 事件

#### 根因
**前端代码假设 `result` 是对象,有 `text` 字段:**
```typescript
// App.tsx (错误代码)
const handleTaskCompleted = (payload: any) => {
  updateMessage(payload.task_id, {
    content: payload.result?.text || '任务完成'  // ← 问题在这里!
  });
};
```

**但 Worker 返回的 `result` 是直接代码字符串:**
```json
{
  "result": "```python\ndef bubble_sort(input_list):\n    ..."
}
```

`payload.result?.text` 为 `undefined`,所以显示 "任务完成"

#### 修复方案
**兼容字符串和对象两种格式:**
```typescript
// App.tsx (修复后)
const handleTaskCompleted = (payload: any) => {
  setCurrentTaskId(null);
  setStreaming(false);
  
  // ⭐ 修复: result 可能是字符串(代码)或对象(有 text 字段)
  const content = typeof payload.result === 'string' 
    ? payload.result 
    : (payload.result?.text || '任务完成');
  
  updateMessage(payload.task_id, {
    content: content
  });
};
```

#### 验证修复
```bash
# 重新编译 Webview
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\webview
npm run build

# 重新编译 Extension
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension
npm run compile
```

#### 教训
1. **前后端数据格式要对齐**: 明确约定返回值格式(字符串 vs 对象)
2. **防御性编程**: 使用 `typeof` 检查数据类型,兼容多种格式
3. **详细日志**: 在控制台打印完整的 `payload` 对象,便于调试
4. **类型提示**: 使用 TypeScript 定义明确的接口类型

---

## 🎯 完整的通信链路

```
[前端 VS Code Extension]
    ↓ (WebSocket/Socket.IO)
[Node.js API: localhost:3000]
    ↓ (Redis LPUSH)
[Redis Queue: task_queue:qwen]
    ↓ (Redis RPOP)
[Python Worker: qwen_worker_v2.py]
    ↓ (调用 LLM API)
[Qwen LLM: 通义千问]
    ↓ (返回结果)
[Python Worker: 写入 Redis]
    ↓ (HTTP POST)
[Node.js API: /task/notify]
    ↓ (Socket.IO emit)
[前端: 收到 task_result 事件]
    ↓ (渲染)
[用户看到 AI 生成的代码]
```

---

## 🔧 调试检查清单

### 当 Worker 无法通知 Node.js 时
- [ ] 检查 `NODE_API_URL` 是否正确定义
- [ ] 检查 `requests` 模块是否正确导入
- [ ] 打印 `type(requests.post)` 确认不是 MagicMock
- [ ] 打印 `requests.__file__` 确认模块路径
- [ ] 检查 Worker 日志是否有 HTTP 请求错误

### 当 `requests.post` 返回 MagicMock 时
- [ ] 搜索代码中的 `= MagicMock()` 赋值语句
- [ ] 检查所有 `utils.py` 文件是否有全局 mock
- [ ] 重启 Python 进程清除 Mock 状态
- [ ] 检查是否在同一会话中运行了测试代码

### 当前端不显示结果时
- [ ] 检查控制台是否收到 `task_result` 事件
- [ ] 打印 `payload.result` 的完整结构
- [ ] 检查前端代码是否正确提取结果内容
- [ ] 验证 `typeof payload.result` 的类型

---

## 📝 最佳实践总结

### 1. Python 模块导入规范
- ✅ 所有使用的非内置符号都必须有对应的 `import` 语句
- ✅ 配置项从 `worker_config.py` 明确导入
- ✅ 添加新功能时立即检查导入完整性

### 2. Mock 使用规范
- ✅ **严禁在生产代码中全局 Mock**
- ✅ Mock 仅在测试框架作用域内使用
- ✅ 使用 `patch` 装饰器或上下文管理器
- ✅ 通过依赖注入传递 Mock 对象

### 3. 前后端通信规范
- ✅ 明确约定数据返回格式(字符串 vs 对象)
- ✅ 使用防御性编程兼容多种格式
- ✅ Worker 任务完成后必须调用 `/task/notify`
- ✅ 在日志中记录通知发送状态

### 4. 调试方法
- ✅ 打印关键变量的类型和值
- ✅ 使用详细的结构化日志
- ✅ 逐层检查通信链路
- ✅ 重启服务清除异常状态

---

## 🚀 快速验证命令

```powershell
# 1. 检查 Worker 是否正常启动
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker
python agents/qwen/qwen_worker_v2.py

# 预期输出:
# 🚀 Qwen Worker v2 已启动
#    · Worker ID: qwen-worker-1
#    · Node API: 已连接
#    · 正在监听任务队列...

# 2. 检查 Node.js 是否正常
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\node-api
node index.js

# 预期输出:
# Node API 已启动: http://localhost:3000
# WebSocket 服务已启动: ws://localhost:3000

# 3. 重新加载 VS Code Extension
# Ctrl+Shift+P → Developer: Reload Window

# 4. 提交测试任务
# "请用python写一个简单的排序函数"

# 5. 预期看到:
# - 任务提交成功
# - AI 生成代码
# - 前端正确渲染结果
```

---

##  相关文档
- [GLOBAL_MOCK_POLLUTION_FIX.md](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\GLOBAL_MOCK_POLLUTION_FIX.md) - 全局 Mock 污染修复详情
- [FINAL_FIX_REPORT.md](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\FINAL_FIX_REPORT.md) - 完整修复报告
- [ACTION_PLAN_FINAL.md](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\ACTION_PLAN_FINAL.md) - 测试指南

---

## 🎯 明天计划: 前端美化

### 待优化项目
1. **流式输出显示**: 实时显示 AI 思考过程
2. **代码高亮**: 使用 ReactMarkdown + SyntaxHighlighter
3. **步骤进度条**: 显示任务执行进度
4. **交互优化**: 复制代码、折叠展开、加载动画

### 技术选型
```typescript
// Markdown 渲染
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'

// 代码高亮主题
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
```

---

*修复完成时间: 2026-05-04 19:17*  
*状态: ✅ 所有问题已修复,前后端完整链路已打通*  
*下一步: 前端美化与交互优化*
