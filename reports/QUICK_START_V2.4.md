# 模型无关流式协议 v2.4 快速启动指南

## 🚀 5分钟体验世界级流式输出

### 前置条件
- ✅ Node.js 已安装
- ✅ Python 3.9+ 已安装
- ✅ Redis 服务运行中
- ✅ 阿里云DashScope API Key配置完成

---

## 📦 第一步: 启动所有服务

```powershell
# 在项目根目录执行
.\start_all.ps1
```

**预期输出**:
```
🚀 AlphaPilot v2.4 启动中...

✅ Node API 已启动: http://localhost:3000
✅ WebSocket 服务已启动: ws://localhost:3000
✅ Qwen Worker v2 已启动
   · Worker ID: qwen-worker-1
   · 正在监听任务队列: task_queue:qwen
```

---

## 💻 第二步: 启动VSCode调试

1. 打开VSCode
2. 按 `F5` 启动调试
3. 新的VSCode窗口打开(扩展开发主机)

---

## 🎯 第三步: 测试模型无关任务提交

### 方法A: 使用AlphaPilot Chat面板

1. 在新VSCode窗口中,按 `Ctrl+Shift+P`
2. 输入 "AlphaPilot: Open Chat Panel"
3. 在聊天框中输入:
   ```
   写一个Python快速排序函数
   ```
4. 点击发送按钮

### 方法B: 使用curl命令测试

```bash
curl -X POST http://localhost:3000/task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "type": "task.generate",
    "payload": {"prompt": "写一个Python快速排序函数"},
    "meta": {
      "model": "qwen2.5",
      "stream": true
    }
  }'
```

**预期响应**:
```json
{
  "status": "submitted",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "model": "qwen2.5",
  "stream": true,
  "message": "任务已提交到队列"
}
```

---

## 👀 第四步: 观察流式输出效果

### 视觉验证点

#### 1. 思考过程展示 (channel = reasoning)
```
┌─ 💭 AI 思考过程 ───────────────┐
│ 让我先分析用户需求...          │ ← 紫色边框
│ 需要实现快速排序算法           │   淡紫背景
│ 时间复杂度应该是O(n log n)     │
│ 使用分治法策略...              │
└────────────────────────────────┘
```

**特征**:
- ✅ 紫色左边框 (`border-l-4 border-purple-500`)
- ✅ 💭 图标 + "AI 思考过程"标签
- ✅ 打字机效果逐字显示

---

#### 2. 最终产出展示 (channel = content)
```python
def quick_sort(arr):
    """快速排序实现"""
    if len(arr) <= 1:
        return arr
    
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    
    return quick_sort(left) + middle + quick_sort(right)
```

**特征**:
- ✅ Markdown代码高亮(vscDarkPlus主题)
- ✅ 右上角复制按钮(悬停显示)
- ✅ 语法高亮(关键字蓝色、字符串绿色)

---

#### 3. 阶段进度条 (phase驱动)
```
📊 任务进度: 3/5 步骤完成 60%
━━━━━━━━━━━━━━░░░░░░░░░░

✅ 🔍 分析需求                    2.3s
✅ 📋 制定计划                    1.8s
⏳ ✍️ 编写代码              ▶     ← 当前阶段
⏸️ ⚡ 优化改进
⏸️ ✅ 测试验证

[write] 17:01  ← 顶部阶段标签
```

**特征**:
- ✅ 进度条实时更新(蓝→绿渐变)
- ✅ 当前步骤蓝色边框+旋转动画
- ✅ 顶部显示当前阶段标签

---

## 🔍 第五步: 验证架构信条

### 检查Worker日志

在Worker终端中应看到:
```
📡 监听队列: task_queue:qwen

收到任务:
{
  "version": "2.0",
  "task_id": "a1b2c3d4-...",
  "type": "task.generate",
  "meta": {
    "model": "qwen2.5",
    "stream": true
  }
}

🔴 流式开始：a1b2c3d4 - 🧪 正在生成测试用例... (phase: analyze)
stream_chunk发送成功 (phase: analyze, channel: reasoning)
stream_chunk发送成功 (phase: analyze, channel: content)
```

**验证点**:
- ✅ type = "task.generate" (模型无关)
- ✅ meta.model = "qwen2.5" (配置化)
- ✅ stream_chunk携带phase和channel字段

---

### 检查Node API日志

在Node API终端中应看到:
```
📥 收到前端提交任务：
{
  "type": "task.generate",
  "payload": {"prompt": "写一个Python快速排序函数"},
  "meta": {"model": "qwen2.5", "stream": true}
}

🎯 路由到队列: task_queue:qwen (模型: qwen2.5)
✅ 任务已成功推入 Redis 队列

🔴 流式开始：a1b2c3d4 - ... (phase: analyze)
📡 向 1 个订阅者推送任务结果
```

**验证点**:
- ✅ 正确识别task.generate类型
- ✅ 根据model路由到对应队列
- ✅ 转发stream_chunk时携带phase/channel

---

### 检查Webview控制台

在VSCode开发者工具(Help → Toggle Developer Tools)中应看到:
```
📥 Extension → Webview: {
  type: "stream_chunk",
  payload: {
    task_id: "a1b2c3d4-...",
    chunk: "def quick_sort",
    phase: "write",
    channel: "content"
  }
}

🔄 handleStreamChunk - phase: write channel: content
✅ content 更新 - 长度: 14
```

**验证点**:
- ✅ Webview接收到完整的phase和channel信息
- ✅ 根据channel分离更新reasoningContent或contentChannel
- ✅ 无数据伪造或篡改

---

## 🎨 第六步: 切换不同模型测试

### 测试Qwen模型
```json
{
  "type": "task.generate",
  "payload": {"prompt": "写一首关于编程的诗"},
  "meta": {
    "model": "qwen2.5",
    "stream": true
  }
}
```

### 测试DeepSeek模型(需配置API Key)
```json
{
  "type": "task.generate",
  "payload": {"prompt": "解释什么是递归"},
  "meta": {
    "model": "deepseek-chat",
    "stream": true
  }
}
```

### 测试Doubao模型(需配置API Key)
```json
{
  "type": "task.generate",
  "payload": {"prompt": "生成一个React组件"},
  "meta": {
    "model": "doubao-pro",
    "stream": true
  }
}
```

**验证点**:
- ✅ 前端无需修改代码
- ✅ 只需更改`meta.model`字段
- ✅ Worker自动路由到对应队列

---

## 📊 第七步: 性能基准测试

### 测量指标

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 首token延迟 | <500ms | 从发送到第一个chunk的时间 |
| token生成速度 | >20 tokens/s | 统计10秒内的chunk数量 |
| UI渲染帧率 | >50 FPS | Chrome DevTools Performance面板 |
| 内存占用 | <200MB | Task Manager监控 |

### 测试命令

```bash
# 使用time命令测量端到端延迟
time curl -X POST http://localhost:3000/task/submit \
  -H "Content-Type: application/json" \
  -d '{...}'
```

---

## 🐛 常见问题排查

### 问题1: 看不到思考过程

**症状**: 只显示代码,没有紫色边框的思考卡片

**原因**: Worker未发送`channel="reasoning"`的chunk

**解决**:
1. 检查Worker日志是否有`stream_chunk发送成功 (channel: reasoning)`
2. 确认test_step.py等步骤执行器已更新到最新版本
3. 重启Worker服务

---

### 问题2: 阶段标签不更新

**症状**: 顶部一直显示"[analyze]",不切换到"[write]"

**原因**: Worker未发送正确的`phase`字段

**解决**:
1. 检查Worker发送的stream_chunk是否包含phase字段
2. 确认App.tsx中`handleStepStarted`正确调用`setCurrentPhase`
3. 刷新Webview( Ctrl+R )

---

### 问题3: 模型切换无效

**症状**: 修改`meta.model`后仍使用默认模型

**原因**: Node API未正确提取model字段

**解决**:
1. 检查Node API日志中的`路由到队列: xxx (模型: yyy)`
2. 确认`getWorkerQueue(model)`函数正确解析模型前缀
3. 检查Redis中任务数据的meta.model字段

---

### 问题4: TypeScript编译错误

**症状**: chatStore.ts或App.tsx报错

**解决**:
```bash
cd vscode-extension/webview
npm run build
```

查看详细错误信息并修复。

---

## 📖 相关文档

- 📘 [完整实施报告](MODEL_AGNOSTIC_STREAMING_PROTOCOL_V2.4.md)
- 📗 [架构信条](ARCHITECTURE_MANIFESTO.md)
- 📙 [TaskModel v2规范](python_worker/TaskModel_v2.py)
- 📕 [前端美化指南](FRONTEND_BEAUTIFICATION_COMPLETE.md)

---

## 🎉 成功标志

如果你看到以下效果,说明v2.4协议已成功部署:

✅ **模型无关**: 前端提交`task.generate`,后端根据`meta.model`自动路由  
✅ **思考分离**: 紫色边框显示💭思考过程,主区域显示Markdown代码  
✅ **阶段可视**: StepTree进度条实时更新,顶部显示[write]标签  
✅ **流畅体验**: 打字机效果逐字显示,无明显卡顿  
✅ **架构纯净**: Worker产生真实数据,Extension透明转发,Webview只读渲染  

**恭喜!你已成功体验世界级的流式智能体系统!** 🚀

---

*最后更新: 2026-05-05*  
*版本: v2.4*
