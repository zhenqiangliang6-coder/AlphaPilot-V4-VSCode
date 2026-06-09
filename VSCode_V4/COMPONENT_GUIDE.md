# AlphaPilot 前端组件使用指南

## 📚 目录

1. [架构概览](#架构概览)
2. [核心服务](#核心服务)
3. [UI 组件](#ui 组件)
4. [快速开始](#快速开始)
5. [最佳实践](#最佳实践)

---

## 架构概览

### 分层架构

```
┌─────────────────────────────────────┐
│   Extension Layer (命令注册)         │
│   - extension.ts                    │
├─────────────────────────────────────┤
│   Panel Layer (面板管理)             │
│   - taskPanel.ts                    │
│   - historyPanel.ts                 │
├─────────────────────────────────────┤
│   Service Layer (业务逻辑)           │
│   - taskService                     │
│   - websocketService                │
│   - streamingService                │
├─────────────────────────────────────┤
│   Webview Layer (UI 渲染)            │
│   - HTML/CSS/JS                     │
└─────────────────────────────────────┘
```

---

## 核心服务

### 1. TaskService - 任务管理

**位置**: `src/services/taskService.ts`

**功能**:
- ✅ 任务提交、取消、查询
- ✅ 步骤管理
- ✅ 事件记录
- ✅ 持久化存储

**使用示例**:

```typescript
import { taskService } from './services/taskService';

// 初始化服务 (在 extension activate 时)
taskService.initialize(context);

// 提交任务
const taskId = await taskService.submitTask(
  '帮我写一个排序算法',
  'qwen_generate'
);

// 取消任务
await taskService.cancelTask(taskId);

// 获取任务详情
const task = taskService.getTask(taskId);

// 更新任务状态
taskService.updateTaskStatus(taskId, 'running');

// 添加步骤
taskService.addStep(taskId, {
  id: 'step_1',
  type: 'analyze',
  status: 'pending'
});

// 获取统计信息
const stats = taskService.getStats();
console.log(stats); 
// { total: 10, completed: 8, failed: 1, running: 1 }
```

**API 参考**:

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `submitTask` | prompt, type | Promise<string> | 提交任务，返回 taskId |
| `cancelTask` | taskId | Promise<void> | 取消任务 |
| `getTask` | taskId | Task\|undefined | 获取任务详情 |
| `getAllTasks` | - | Task[] | 获取所有任务 |
| `updateTaskStatus` | taskId, status | void | 更新任务状态 |
| `addStep` | taskId, step | void | 添加步骤 |
| `deleteTask` | taskId | void | 删除任务 |
| `clearHistory` | - | void | 清空历史 |
| `getStats` | - | Object | 获取统计信息 |

---

### 2. WebSocketService - 通信服务

**位置**: `src/services/websocketService.ts`

**功能**:
- 🔌 WebSocket 连接管理
- 📡 事件订阅/发布
- 🔄 自动重连
- 📨 消息队列

**使用示例**:

```typescript
import { websocketService } from './services/websocketService';

// 连接到服务器
await websocketService.connect('ws://localhost:3000');

// 订阅事件
const unsubscribe = websocketService.on('stream_chunk', (data) => {
  console.log('收到流式数据:', data.chunk);
});

// 取消订阅
unsubscribe();

// 发送消息
websocketService.send({
  event: 'subscribe_task',
  task_id: 'task_123'
});

// 订阅特定任务
websocketService.subscribeTask('task_123');

// 取消订阅
websocketService.unsubscribeTask('task_123');

// 断开连接
websocketService.disconnect();
```

**支持的事件类型**:

```typescript
// 流式输出
websocketService.on('stream_start', handler);
websocketService.on('stream_chunk', handler);
websocketService.on('stream_end', handler);
websocketService.on('stream_error', handler);

// 任务生命周期
websocketService.on('task_started', handler);
websocketService.on('task_completed', handler);
websocketService.on('task_failed', handler);
websocketService.on('task_cancelled', handler);

// 步骤事件
websocketService.on('step_started', handler);
websocketService.on('step_finished', handler);
websocketService.on('step_failed', handler);
```

---

### 3. StreamingService - 流式输出管理

**位置**: `src/services/streamingService.ts`

**功能**:
- 🌊 流式输出控制
- ⏸️ 暂停/继续
- 📊 字数统计
- 🗄️ 缓冲管理

**使用示例**:

```typescript
import { streamingService } from './services/streamingService';

// 开始流
streamingService.startStream('task_123');

// 追加内容
streamingService.appendChunk('task_123', '这是一段代码');

// 暂停流
streamingService.pauseStream('task_123');

// 恢复流
streamingService.resumeStream('task_123');

// 结束流
streamingService.endStream('task_123');

// 监听内容变化
streamingService.onChunk('task_123', (chunk) => {
  // 更新 UI
  outputElement.textContent += chunk;
});

// 获取状态
const state = streamingService.getStreamState('task_123');
console.log(state.charCount); // 字符数
console.log(state.isPaused);  // 是否暂停
```

---

## UI 组件

### 1. TaskPanel - 主任务面板

**位置**: `src/panels/taskPanel.ts`

**功能**:
- 🎨 Webview 渲染
- 📱 用户交互
- 🔄 实时更新
- 🎯 步骤树展示

**使用示例**:

```typescript
import { TaskPanel } from './panels/taskPanel';

// 显示面板
const panel = TaskPanel.show(extensionUri);

// 设置任务 ID
panel.setTaskId('task_123');

// 处理 WebSocket 事件
panel.handleEvent({
  event: 'stream_chunk',
  chunk: '代码内容'
});
```

**Webview 消息协议**:

```javascript
// Extension → Webview
{ type: 'set_task_id', taskId: '...' }
{ type: 'stream_start' }
{ type: 'append', content: '...' }
{ type: 'stream_end' }
{ type: 'step_started', stepType: 'analyze' }
{ type: 'step_finished', stepId: '...', output: {...} }
{ type: 'task_completed', result: {...} }
{ type: 'task_failed', error: '...' }

// Webview → Extension
{ type: 'webview_ready' }
{ type: 'pause_stream' }
{ type: 'resume_stream' }
{ type: 'stop_task' }
{ type: 'retry_step', stepId: '...' }
{ type: 'skip_step', stepId: '...' }
```

---

## 快速开始

### Step 1: 安装依赖

```bash
cd vscode-extension
npm install
```

### Step 2: 编译 TypeScript

```bash
npm run compile
```

或监听模式:

```bash
npm run watch
```

### Step 3: 启动后端服务

确保 Node API 和 Python Worker 已启动:

```bash
# Node API
cd node-api
node index.js

# Python Worker (可选)
cd python-worker
python qwen_worker.py
```

### Step 4: 调试扩展

1. 在 VS Code 中按 `F5`
2. 运行命令：`AlphaPilot: 打开任务面板`
3. 输入任务描述测试

---

## 最佳实践

### 1. 错误处理

```typescript
try {
  const taskId = await taskService.submitTask(prompt);
} catch (error: any) {
  vscode.window.showErrorMessage(`提交失败：${error.message}`);
  console.error('详细错误:', error);
}
```

### 2. 资源清理

```typescript
export function deactivate() {
  // 断开 WebSocket
  websocketService.disconnect();
  
  // 清理面板
  if (TaskPanel.currentPanel) {
    TaskPanel.currentPanel.dispose();
  }
}
```

### 3. 状态持久化

```typescript
// 保存当前任务 ID
context.workspaceState.update('current_task_id', taskId);

// 读取任务 ID
const taskId = context.workspaceState.get('current_task_id');
```

### 4. 性能优化

```javascript
// 防抖搜索
const debouncedSearch = debounce((query) => {
  // 搜索逻辑
}, 300);

// 节流滚动
const throttledScroll = throttle(() => {
  // 滚动处理
}, 100);
```

### 5. 日志记录

```typescript
// 统一日志格式
console.log('✅ 操作成功:', { taskId, stepId });
console.warn('⚠️ 警告信息:', data);
console.error('❌ 错误详情:', error);
```

---

## 配置说明

### stepConfig.ts - 步骤配置

```typescript
import { getStepConfig, getStepIcon } from './config/stepConfig';

// 获取步骤配置
const config = getStepConfig('analyze');
console.log(config.name);  // "需求分析"
console.log(config.icon);  // "🔍"
console.log(config.color); // "#4fc3f7"

// 快捷方法
const icon = getStepIcon('write');  // "✏️"
const name = getStepName('plan');   // "步骤规划"
```

支持的步骤类型:
- `analyze` - 需求分析 🔍
- `plan` - 步骤规划 📋
- `write` - 代码编写 ✏️
- `refine` - 优化改进 💎
- `test` - 测试验证 ✅
- `fix` - 错误修复 🔧
- `profile` - 性能分析 ⚡
- `doc` - 文档生成 📝

---

## 常见问题

### Q1: WebSocket 连接失败？

**A**: 检查后端服务是否运行在 `http://localhost:3000`

```bash
# 测试端口
curl http://localhost:3000/health
```

### Q2: 面板不显示内容？

**A**: 确认 Webview 消息传递正常

```typescript
// 在 extension.ts 添加调试
panel.handleEvent(event);
console.log('事件已发送到面板');
```

### Q3: 流式输出卡顿？

**A**: 检查缓冲区大小和回调性能

```typescript
// 限制缓冲区大小
if (stream.buffer.length > 100) {
  stream.buffer.shift(); // 丢弃最早的数据
}
```

---

## 进阶主题

### 自定义步骤流程

```typescript
// 定义自定义步骤序列
const customSteps = [
  { type: 'analyze', timeout: 30000 },
  { type: 'plan', timeout: 60000 },
  { type: 'write', timeout: 120000 },
  { type: 'test', timeout: 60000 }
];

// 执行自定义流程
for (const step of customSteps) {
  await executeStep(step.type, step.timeout);
}
```

### 多任务并行

```typescript
// 同时执行多个任务
const taskIds = await Promise.all([
  taskService.submitTask('任务 1'),
  taskService.submitTask('任务 2'),
  taskService.submitTask('任务 3')
]);
```

---

## 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发环境搭建

```bash
git clone https://github.com/your-org/alphapilot.git
cd alphapilot/vscode-extension
npm install
npm run watch
```

### 代码规范

- 使用 TypeScript 严格模式
- 遵循 ESLint 规则
- 添加必要的注释
- 编写单元测试

---

## 许可证

MIT License

---

祝你开发愉快！🎉

如有问题，请查看 [FRONTEND_ARCHITECTURE_v2.md](./FRONTEND_ARCHITECTURE_v2.md) 获取更多架构细节。
