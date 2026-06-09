# 流式输出功能测试指南

## 🎯 概述

前端已实现完整的流式输出系统，但**后端还未发送流式事件**。为了测试前端功能，提供了 5 个内置测试命令来模拟后端行为。

## 🚀 快速开始

### 方式 ①：快速模式（推荐）

1. **打开命令面板**：按 `Ctrl+Shift+P`（Mac: `Cmd+Shift+P`）
2. **输入命令**：`AlphaPilot: 🧪 Quick Test Stream`
3. **选择测试**：弹出菜单选择 5 个测试之一
4. **观察结果**：会自动打开 AI Result 面板，显示流式内容

![快速测试步骤]()

### 方式 ②：逐个测试

直接运行对应的命令：

```
Ctrl+Shift+P → "AlphaPilot: 🧪 Test①..." → Enter
```

---

## 5️⃣ 测试内容详解

### 🧪 Test①：简单流式输出（3 秒）

**命令**：`alphapilot-copilot.testStreamSimple`

**场景**：快速验证基础功能
- 打开结果面板
- 逐字显示简单文本（每字 100ms）
- 3 秒完成

**验证点**：
- ✅ result 面板自动打开
- ✅ 文字逐字出现（不是一次全部）
- ✅ 滚动条自动到最新位置
- ✅ 任务完成后显示消息

---

### 🧪 Test②：暂停/继续控制

**命令**：`alphapilot-copilot.testStreamPause`

**场景**：测试用户交互控制
- 输出第一部分（约 500ms）
- 等待 5 秒（**用户时间**：点击面板 ⏸️ 按钮）
- 继续输出第二部分

**操作步骤**：
1. 运行命令
2. 看到"第一部分"内容后，**立即点击面板中的 ⏸️ 按钮**
3. 观察输出停止
4. 点击 ⏵️ 按钮恢复
5. 验证内容继续输出

**验证点**：
- ✅ 暂停时停止接收新内容
- ✅ 暂停时缓冲待发数据
- ✅ 继续时一次性释放缓冲数据
- ✅ 按钮状态正确切换

---

### 🧪 Test③：长文本流式输出

**命令**：`alphapilot-copilot.testStreamLong`

**场景**：测试大文本处理能力
- 输出 ~600 字的 Markdown 文本
- 包含代码块、格式化等
- 每字 20ms（较快速度）

**验证点**：
- ✅ 无卡顿，流畅显示
- ✅ Markdown 正确保存为纯文本
- ✅ 自动滚动工作正常
- ✅ 环境中完整性保持（头、尾都显示）

---

### 🧪 Test④：多并发流（3 个）

**命令**：`alphapilot-copilot.testStreamMultiple`

**场景**：测试多任务同时运行
- 3 个流同时开始
- 每个流输出 30-80ms 延迟（随机）
- 独立完成和清理

**验证点**：
- ✅ 多流同时进行，不相互干扰
- ✅ 使用不同的 taskId 隔离状态
- ✅ 每个流独立管理暂停状态
- ✅ 所有流都正确完成

---

### 🧪 Test⑤：错误处理

**命令**：`alphapilot-copilot.testStreamError`

**场景**：测试异常中断处理
- 输出部分内容
- 模拟异常（插入 ❌ 错误信息）
- 流结束

**验证点**：
- ✅ 异常信息正确显示
- ✅ 流能够正常结束（不会卡住）
- ✅ 错误提示给用户

---

## 📊 完整测试清单

运行所有 5 个测试后，检查以下内容：

### 面板行为
- [ ] AI Result 面板自动打开（test1 时）
- [ ] 内容自动滚动到最新
- [ ] ⏸️/⏵️ 按钮存在且可点击
- [ ] 关闭面板后重新打开无报错

### 流式功能
- [ ] 文字逐字显示（非一次全部）
- [ ] 暂停时确实停止
- [ ] 继续时显示缓冲内容
- [ ] 多个流互不干扰

### 后端集成准备
- [ ] taskHistoryManager 记录每个完成的任务
- [ ] Task History 面板能查看所有测试任务
- [ ] 基础绪的输出无错误

---

## 🔧 与后端集成

当后端实现流式事件时，只需要后端按以下格式发送：

```python
# python-worker example
socketio.emit('stream_start', {
    'task_id': task_id,
    'title': 'Processing...'
})

for chunk in generator():
    socketio.emit('stream_chunk', {
        'task_id': task_id,
        'chunk': chunk
    })
    
socketio.emit('stream_end', {
    'task_id': task_id
})
```

前端会自动处理这些事件，**无需任何改动**。

---

## 🐛 故障排除

### 问题：面板不打开
**原因**：WebSocket 未连接
**解决**：检查 localhost:3000 是否运行，查看扩展输出面板

### 问题：按钮不显示
**原因**：WebView 加载失败
**解决**：重新加载窗口（Ctrl+Shift+P → Developer: Reload Window）

### 问题：内容显示不完整
**原因**：编码问题或缓冲区溢出
**解决**：查看浏览器开发者工具（Ctrl+Shift+I）> Console

---

## 📝 开发者注意

### 关键文件

- `src/testEmulator.ts` — 5 个测试场景的实现
- `src/streamingManager.ts` — 流式状态管理
- `src/panels/aiResultPanel.ts` — UI 面板
- `src/webviews/aiResult.js` — WebView 脚本

### 添加新测试

在 `testEmulator.ts` 中添加新方法，然后在 `extension.ts` 注册命令：

```typescript
// 在 activate() 中
const testNew = vscode.commands.registerCommand('alphapilot-copilot.testStreamNew', async () => {
    await testEmulator.testNewFeature();
});
context.subscriptions.push(testNew);
```

---

## ✅ 验收标准

✅ 所有 5 个测试都能成功运行
✅ 流式内容正确显示
✅ 暂停/继续功能正常
✅ 未出现 JavaScript 错误
✅ 任务历史面板能记录测试任务

---

**最后更新**：2026 年 2 月 26 日  
**维护者**：Frontend Architecture Team
