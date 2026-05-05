#  紧急修复: 全局 Mock 污染 Python 进程

## 问题现象

```
 正在通知 Node.js: http://localhost:3000/task/notify/xxx
 requests 模块: <module 'requests' from '...'>
 requests.post: <MagicMock id='1632028142864'>  ← 被 mock 了!
 response 类型: <class 'unittest.mock.MagicMock'>
 Node.js 返回错误状态码: <MagicMock name='mock().status_code'>
```

## 根本原因

**所有 agent 的 `utils.py` 文件中都有全局 mock 代码:**

```python
# python_worker/agents/qwen/step_executor/utils.py (第174行)
requests.post = MagicMock()
```

**当 `utils.py` 被导入时,这些代码会:**
1. 替换整个 Python 进程中的 `requests.post`
2. 导致所有后续调用 `requests.post()` 都返回 MagicMock 对象
3. Worker 无法真正调用 Node.js 的 `/task/notify` 端点
4. 前端永远收不到任务完成的通知

**这是严重的生产环境 bug!** Mock 代码应该只在测试文件中使用,不应该出现在生产代码中!

## 修复内容

### 删除所有 agent 的 utils.py 中的全局 mock

修复了以下 8 个文件:

1. ✅ `python_worker/agents/qwen/step_executor/utils.py`
2. ✅ `python_worker/agents/Volcengine/step_executor/utils.py`
3. ✅ `python_worker/agents/claude/step_executor/utils.py`
4. ✅ `python_worker/agents/deepeek/step_executor/utils.py`
5. ✅ `python_worker/agents/gemini/step_executor/utils.py`
6. ✅ `python_worker/agents/local_llm/step_executor/utils.py`
7. ✅ `python_worker/agents/multi_agent/step_executor/utils.py`
8. ✅ `python_worker/agents/openai/step_executor/utils.py`

**修改内容:**
```python
# 修改前:
requests.post = MagicMock()  # ← 污染整个进程!

# 修改后:
# requests.post = MagicMock()  # ← 已注释,仅保留注释说明
```

## 影响范围

- **前端输出**: 修复后 Worker 可以真正调用 `/task/notify`,前端将收到任务完成事件
- **所有 Agent**: 修复了所有 agent 的全局 mock 污染问题
- **测试代码**: 如果测试需要 mock,应该在测试文件中局部 mock,而不是在生产代码中全局 mock

## 下一步

**立即重启 Qwen Worker v2:**

```powershell
# 在 Worker 终端按 Ctrl+C 停止
# 然后重新启动
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker
python agents/qwen/qwen_worker_v2.py
```

**这次应该看到:**

```
 正在通知 Node.js: http://localhost:3000/task/notify/xxx
 requests 模块: <module 'requests' from '...'>
 requests.post: <function post at 0x...>  ← 真正的函数!
 response 类型: <class 'requests.models.Response'>  ← 真正的 Response 对象!
 response: <Response [200]>  ← 成功!
✅ Node.js 已成功接收通知，将推送给前端
```

**前端将显示完整的 AI 生成过程和代码!** 

---

## 教训总结

1. **永远不要在生产代码中使用全局 mock**
2. **Mock 应该只在测试文件中局部使用**
3. **导入时的副作用会污染整个进程**
4. **调试时发现 MagicMock,立即检查是否有全局 mock**

---

*修复时间: 2026-05-04*  
*状态: ✅ 已完成,需要重启 Worker*
