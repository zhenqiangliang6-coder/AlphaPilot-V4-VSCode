# AlphaPilot 前端架构设计 v2.0

## 🎯 愿景与目标

打造**业界领先的智能体执行引擎前端**,以 `step_executor` 为核心，提供超越 Cursor、GitHub Copilot 的用户体验。

### 核心价值
- **智能化**: 基于 step_executor 的 8 种步骤类型 (analyze/plan/write/refine/test/fix/profile/doc)
- **可视化**: 实时展示任务执行树和步骤状态
- **交互友好**: 流式输出、实时反馈、可中断控制
- **高性能**: 低延迟、高响应、优雅降级

---

## 🏗️ 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    VS Code Extension Layer                   │
├─────────────────────────────────────────────────────────────┤
│  extension.ts (命令注册 & 路由)                               │
│    └─> PanelManager (面板生命周期管理)                        │
│         ├─ TaskPanel (主任务面板)                             │
│         ├─ HistoryPanel (历史面板)                            │
│         └─ SettingsPanel (设置面板)                           │
├─────────────────────────────────────────────────────────────┤
│  Service Layer (服务层)                                       │
│    ├─ TaskService (任务管理)                                  │
│    ├─ StepExecutorService (步骤执行服务)                       │
│    ├─ StreamingService (流式输出服务)                          │
│    ├─ WebSocketService (通信服务)                             │
│    └─ StateManager (状态管理)                                 │
├─────────────────────────────────────────────────────────────┤
│  Webview Layer (UI 渲染层)                                    │
│    ├─ TaskView (任务视图 - React/Vue 风格组件)                 │
│    ├─ StepTree (步骤树组件)                                   │
│    ├─ StreamOutput (流式输出组件)                             │
│    ├─ EventTimeline (事件时间线)                              │
│    └─ ControlPanel (控制面板)                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
            ┌───────────────────────────────┐
            │      Node API / Python Worker │
            │    (step_executor 后端实现)     │
            └───────────────────────────────┘
```

---

## 📁 文件结构

```
vscode-extension/
├── src/
│   ├── extension.ts                      # 扩展入口 (命令注册)
│   ├── panelManager.ts          ✨ NEW   # 面板统一管理
│   │
│   ├── services/                ✨ NEW   # 服务层
│   │   ├── taskService.ts               # 任务 CRUD
│   │   ├── stepExecutorService.ts       # step_executor 适配
│   │   ├── streamingService.ts          # 流式输出管理
│   │   ├── websocketService.ts          # WebSocket 通信
│   │   └── stateManager.ts              # 全局状态管理
│   │
│   ├── panels/                  ✨ REFACTOR
│   │   ├── taskPanel.ts                 # 主任务面板 (统一 AI 结果 + 任务树)
│   │   ├── historyPanel.ts              # 历史面板
│   │   └── settingsPanel.ts     ✨ NEW   # 设置面板
│   │
│   ├── webviews/                ✨ REDESIGN
│   │   ├── taskView.html                # 主视图 HTML
│   │   ├── taskView.css                 # 主视图样式
│   │   └── taskView.js                  # 主视图逻辑
│   │   │
│   │   ├── components/          ✨ NEW   # UI 组件库
│   │   │   ├── stepTree.js              # 步骤树组件
│   │   │   ├── streamOutput.js          # 流式输出组件
│   │   │   ├── eventTimeline.js         # 事件时间线组件
│   │   │   ├── controlPanel.js          # 控制面板组件
│   │   │   └── progressBar.js           # 进度条组件
│   │   │
│   │   └── utils/               ✨ NEW   # 工具函数
│   │       ├── domUtils.js              # DOM 操作工具
│   │       ├── formatUtils.js           # 格式化/时间处理
│   │       └── themeUtils.js            # 主题适配
│   │
│   ├── types/                   ✨ NEW   # TypeScript 类型定义
│   │   ├── task.ts                      # TaskModel 类型
│   │   ├── step.ts                      # Step 类型
│   │   └── events.ts                    # 事件类型
│   │
│   └── config/                  ✨ NEW   # 配置文件
│       ├── defaultConfig.ts             # 默认配置
│       └── stepConfig.ts                # 步骤类型配置
│
├── package.json                          # 依赖配置
├── tsconfig.json                         # TypeScript 配置
└── docs/
    ├── FRONTEND_ARCHITECTURE.md   ✨ THIS # 架构设计文档
    ├── COMPONENT_GUIDE.md         ✨ NEW   # 组件使用指南
    └── STEP_EXECUTOR_INTEGRATION.md ✨ NEW # step_executor 集成指南
```

---

## 🔧 核心服务设计

### 1. TaskService - 任务管理

```typescript
interface Task {
  id: string;
  type: string;
  prompt: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  steps: Step[];
  events: Event[];
  result?: any;
  createdAt: number;
  updatedAt: number;
}

class TaskService {
  // 提交任务
  submitTask(prompt: string, type: string): Promise<string>;
  
  // 取消任务
  cancelTask(taskId: string): Promise<void>;
  
  // 获取任务详情
  getTask(taskId: string): Promise<Task>;
  
  // 获取所有任务
  getAllTasks(): Promise<Task[]>;
  
  // 删除任务
  deleteTask(taskId: string): Promise<void>;
  
  // 清空历史
  clearHistory(): Promise<void>;
}
```

### 2. StepExecutorService - 步骤执行服务

```typescript
/**
 * 基于 step_executor 的 8 种步骤类型
 */
enum StepType {
  ANALYZE = 'analyze',     // 分析需求
  PLAN = 'plan',          // 规划步骤
  WRITE = 'write',        // 编写代码
  REFINE = 'refine',      // 优化改进
  TEST = 'test',          // 测试验证
  FIX = 'fix',            // 修复错误
  PROFILE = 'profile',    // 性能分析
  DOC = 'doc'            // 生成文档
}

interface Step {
  id: string;
  type: StepType;
  status: 'pending' | 'running' | 'completed' | 'failed';
  input: any;
  output: any;
  error?: string;
  startTime?: number;
  endTime?: number;
}

class StepExecutorService {
  // 执行单个步骤
  executeStep(step: Step, context: any): Promise<StepResult>;
  
  // 批量执行步骤
  executeSteps(steps: Step[], options: ExecuteOptions): AsyncGenerator<StepProgress>;
  
  // 获取步骤进度
  getStepProgress(stepId: string): Promise<StepProgress>;
  
  // 重试失败步骤
  retryStep(stepId: string): Promise<void>;
  
  // 跳过步骤
  skipStep(stepId: string): Promise<void>;
}
```

### 3. StreamingService - 流式输出管理

```typescript
interface StreamChunk {
  taskId: string;
  stepId?: string;
  content: string;
  timestamp: number;
}

class StreamingService {
  // 开始流
  startStream(taskId: string): void;
  
  // 追加内容
  appendChunk(chunk: StreamChunk): void;
  
  // 暂停流
  pauseStream(taskId: string): void;
  
  // 恢复流
  resumeStream(taskId: string): void;
  
  // 结束流
  endStream(taskId: string): void;
  
  // 获取流状态
  getStreamState(taskId: string): StreamState;
}
```

### 4. StateManager - 全局状态管理

```typescript
interface AppState {
  currentTask: Task | null;
  tasks: Task[];
  activePanel: string;
  settings: AppSettings;
  uiState: UIState;
}

class StateManager {
  // 订阅状态变化
  subscribe(listener: (state: AppState) => void): Unsubscribe;
  
  // 更新状态
  dispatch(action: Action): void;
  
  // 获取当前状态
  getState(): AppState;
  
  // 持久化状态
  persistState(): Promise<void>;
  
  // 加载状态
  loadState(): Promise<AppState>;
}
```

---

## 🎨 UI 组件设计

### 1. TaskPanel - 主任务面板

**功能特性:**
- 🌳 **步骤树可视化**: 折叠/展开步骤详情
- 📊 **实时进度条**: 显示整体执行进度
- 🔄 **流式输出**: 逐字显示 AI 生成内容
- ⏸️ **暂停/继续**: 随时控制执行流程
- 🎯 **步骤导航**: 快速跳转到特定步骤
- 📝 **代码高亮**: 语法高亮显示

**布局设计:**
```
┌────────────────────────────────────────────────────┐
│ AlphaPilot · 智能体任务执行                         │
├────────────────────────────────────────────────────┤
│ [📊 进度条] 60% (3/5 步骤完成)                      │
├──────────────┬─────────────────────────────────────┤
│              │                                     │
│  🌳 步骤树   │   📝 流式输出区                      │
│  ├─ ✓ analyze│                                     │
│  ├─ ✓ plan   │   正在生成代码...                   │
│  ├─ ▶ write  │   def hello_world():                │
│  ├─ ◯ test   │       print("Hello")                │
│  └─ ◯ doc    │                                     │
│              │                                     │
│              │   [⏸️ 暂停] [🔄 重试] [⏭️ 跳过]       │
├──────────────┴─────────────────────────────────────┤
│ 📡 事件时间线                                       │
│ 12:30:45  ▶ step_started: write                    │
│ 12:30:46  📝 stream_chunk: "def hello..."          │
│                                                    │
└────────────────────────────────────────────────────┘
```

### 2. StepTree 组件 - 步骤树

**Props:**
```javascript
{
  steps: Step[],
  activeStepId: string,
  onStepClick: (stepId: string) => void,
  onRetry: (stepId: string) => void,
  onSkip: (stepId: string) => void
}
```

**渲染逻辑:**
```javascript
function renderStepIcon(status) {
  switch(status) {
    case 'completed': return '✓';  // 绿色
    case 'running': return '▶';    // 蓝色闪烁
    case 'failed': return '✕';     // 红色
    case 'pending': return '◯';    // 灰色
    case 'skipped': return '⊘';    // 黄色
  }
}
```

### 3. StreamOutput 组件 - 流式输出

**特性:**
- 自动滚动到最新内容
- 支持 Markdown 渲染
- 代码块语法高亮
- 字数统计实时更新

**API:**
```javascript
class StreamOutput {
  append(text: string): void;
  clear(): void;
  scrollToBottom(): void;
  setMarkdown(markdown: string): void;
  getCharCount(): number;
}
```

### 4. EventTimeline 组件 - 事件时间线

**事件类型映射:**
```javascript
const EVENT_ICONS = {
  'task_started': '🚀',
  'step_started': '▶',
  'step_finished': '✓',
  'stream_chunk': '📝',
  'error': '❌',
  'task_completed': '🎉',
  'task_cancelled': '⏹️'
};
```

---

## 🔄 数据流设计

### 任务执行流程

```
用户发起任务
    ↓
extension.ts 注册命令
    ↓
TaskService.submitTask(prompt)
    ↓
Node API /task/submit
    ↓
返回 task_id
    ↓
WebSocketService.subscribe(task_id)
    ↓
接收 events:
  - task_started
  - step_started (analyze)
  - stream_start
  - stream_chunk
  - stream_end
  - step_finished
  - step_started (plan)
  - ...
  - task_result
    ↓
StateManager.dispatch({ type: 'UPDATE_TASK', payload })
    ↓
UI 组件重新渲染
    ↓
用户看到实时更新
```

### step_executor 集成流程

```python
# Python Worker 端
from step_executor import execute_step

def process_task(task_id: str, prompt: str):
    # 1. 分析步骤
    step_analyze = {
        "id": "step_1",
        "type": "analyze",
        "status": "pending"
    }
    execute_step(task_id, step_analyze, events, context)
    
    # 发送事件到前端
    emit_event("step_finished", {
        "task_id": task_id,
        "step_id": "step_1",
        "output": step_analyze["output"]
    })
    
    # 2. 规划步骤
    step_plan = {
        "id": "step_2",
        "type": "plan",
        "status": "pending"
    }
    execute_step(task_id, step_plan, events, context)
    
    # ... 依此类推
```

---

## 🎯 核心功能实现

### 1. 任务提交流程

```typescript
// extension.ts
async function handleCommand(prompt: string) {
  const panel = TaskPanel.show(context.extensionUri);
  
  // 提交任务到后端
  const taskId = await taskService.submitTask(prompt, 'qwen_generate');
  
  // 告诉面板当前任务 ID
  panel.setTaskId(taskId);
  
  // 订阅 WebSocket 事件
  websocketService.subscribe(taskId, (event) => {
    panel.handleEvent(event);
  });
}
```

### 2. 步骤树渲染

```javascript
// stepTree.js
function renderStepTree(steps) {
  const container = document.getElementById('step-tree');
  
  steps.forEach((step, index) => {
    const stepEl = document.createElement('div');
    stepEl.className = `step step--${step.status}`;
    stepEl.dataset.stepId = step.id;
    
    const icon = getStepIcon(step.status);
    const title = `${index + 1}. ${getStepTypeName(step.type)}`;
    
    stepEl.innerHTML = `
      <div class="step-header">
        <span class="step-icon">${icon}</span>
        <span class="step-title">${title}</span>
        <span class="step-time">${formatDuration(step)}</span>
      </div>
      <div class="step-content">
        <pre>${JSON.stringify(step.output, null, 2)}</pre>
      </div>
    `;
    
    // 点击展开/折叠
    stepEl.querySelector('.step-header').addEventListener('click', () => {
      stepEl.classList.toggle('expanded');
    });
    
    container.appendChild(stepEl);
  });
}
```

### 3. 流式输出处理

```javascript
// streamingService.js
class StreamingService {
  constructor() {
    this.streams = new Map(); // taskId -> StreamState
  }
  
  startStream(taskId) {
    const streamState = {
      taskId,
      isPaused: false,
      buffer: [],
      charCount: 0,
      element: document.getElementById(`stream-${taskId}`)
    };
    
    this.streams.set(taskId, streamState);
  }
  
  appendChunk(taskId, content) {
    const stream = this.streams.get(taskId);
    if (!stream) return;
    
    if (stream.isPaused) {
      stream.buffer.push(content);
      return;
    }
    
    stream.element.textContent += content;
    stream.charCount += content.length;
    this.autoScroll(stream.element);
    this.updateCounter(stream);
  }
  
  pauseStream(taskId) {
    const stream = this.streams.get(taskId);
    if (stream) {
      stream.isPaused = true;
    }
  }
  
  resumeStream(taskId) {
    const stream = this.streams.get(taskId);
    if (stream) {
      stream.isPaused = false;
      // 消费缓冲区
      while (stream.buffer.length) {
        this.appendChunk(taskId, stream.buffer.shift());
      }
    }
  }
}
```

### 4. 步骤执行器映射

```typescript
// stepConfig.ts
export const STEP_CONFIG = {
  analyze: {
    name: '需求分析',
    icon: '🔍',
    color: '#4fc3f7',
    description: '分析用户需求和上下文'
  },
  plan: {
    name: '步骤规划',
    icon: '📋',
    color: '#81c784',
    description: '制定详细的执行计划'
  },
  write: {
    name: '代码编写',
    icon: '✏️',
    color: '#ffb74d',
    description: '生成代码实现'
  },
  refine: {
    name: '优化改进',
    icon: '💎',
    color: '#e57373',
    description: '优化和改进代码质量'
  },
  test: {
    name: '测试验证',
    icon: '✅',
    color: '#ba68c8',
    description: '运行测试确保正确性'
  },
  fix: {
    name: '错误修复',
    icon: '🔧',
    color: '#ff8a65',
    description: '修复发现的问题'
  },
  profile: {
    name: '性能分析',
    icon: '⚡',
    color: '#4db6ac',
    description: '分析和优化性能'
  },
  doc: {
    name: '文档生成',
    icon: '📝',
    color: '#7986cb',
    description: '生成文档和注释'
  }
};
```

---

## 🎨 主题与样式

### CSS 变量系统

```css
:root {
  /* 基础颜色 */
  --primary-color: #4fc3f7;
  --success-color: #81c784;
  --warning-color: #ffb74d;
  --error-color: #e57373;
  --info-color: #ba68c8;
  
  /* 背景色 */
  --bg-primary: var(--vscode-editor-background);
  --bg-secondary: var(--vscode-sideBar-background);
  --bg-tertiary: var(--vscode-editorGroupHeader-tabsBackground);
  
  /* 边框 */
  --border-color: var(--vscode-editorGroup-border);
  
  /* 文字 */
  --text-primary: var(--vscode-editor-foreground);
  --text-secondary: var(--vscode-descriptionForeground);
  
  /* 动画 */
  --transition-fast: 150ms;
  --transition-normal: 300ms;
  --transition-slow: 500ms;
}
```

### 响应式设计

```css
/* 移动端适配 */
@media (max-width: 600px) {
  .step-tree {
    max-width: 100%;
    overflow-x: auto;
  }
  
  .stream-output {
    font-size: 12px;
  }
  
  .controls {
    flex-wrap: wrap;
  }
}
```

---

## 🚀 性能优化

### 1. 虚拟滚动

对于大量步骤或事件，使用虚拟滚动技术：

```javascript
class VirtualList {
  constructor(container, items, itemHeight) {
    this.container = container;
    this.items = items;
    this.itemHeight = itemHeight;
    this.visibleStart = 0;
    this.visibleEnd = 0;
    
    this.container.addEventListener('scroll', () => {
      this.render();
    });
  }
  
  render() {
    const scrollTop = this.container.scrollTop;
    this.visibleStart = Math.floor(scrollTop / this.itemHeight);
    this.visibleEnd = Math.min(
      this.visibleStart + Math.ceil(this.container.clientHeight / this.itemHeight),
      this.items.length
    );
    
    // 只渲染可见区域
    const visibleItems = this.items.slice(this.visibleStart, this.visibleEnd);
    // ... 渲染逻辑
  }
}
```

### 2. 防抖与节流

```javascript
// 防抖：用于搜索输入
function debounce(fn, delay) {
  let timer = null;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

// 节流：用于滚动事件
function throttle(fn, limit) {
  let lastCall = 0;
  return function(...args) {
    const now = Date.now();
    if (now - lastCall >= limit) {
      lastCall = now;
      fn.apply(this, args);
    }
  };
}
```

### 3. 消息队列

```typescript
class MessageQueue {
  private queue: any[] = [];
  private isProcessing = false;
  
  enqueue(message: any) {
    this.queue.push(message);
    if (!this.isProcessing) {
      this.process();
    }
  }
  
  async process() {
    this.isProcessing = true;
    while (this.queue.length > 0) {
      const message = this.queue.shift();
      await this.handleMessage(message);
    }
    this.isProcessing = false;
  }
}
```

---

## 🔒 错误处理与容错

### 错误边界

```javascript
class ErrorBoundary {
  constructor(renderFn) {
    this.renderFn = renderFn;
  }
  
  render(error) {
    if (error) {
      return `
        <div class="error-boundary">
          <h3>❌ 发生错误</h3>
          <p>${error.message}</p>
          <button onclick="location.reload()">刷新页面</button>
        </div>
      `;
    }
    return this.renderFn();
  }
}
```

### 重试机制

```typescript
async function retryableRequest<T>(
  fn: () => Promise<T>,
  maxRetries = 3,
  delay = 1000
): Promise<T> {
  let lastError: Error;
  
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as Error;
      console.warn(`重试 ${i + 1}/${maxRetries}:`, error);
      
      if (i < maxRetries - 1) {
        await sleep(delay * Math.pow(2, i)); // 指数退避
      }
    }
  }
  
  throw lastError;
}
```

---

## 📊 监控与日志

### 性能指标收集

```javascript
const metrics = {
  taskStartTime: 0,
  stepDurations: [],
  streamLatency: [],
  
  markStart() {
    this.taskStartTime = performance.now();
  },
  
  recordStep(stepId: string, duration: number) {
    this.stepDurations.push({ stepId, duration });
  },
  
  recordStreamLatency(latency: number) {
    this.streamLatency.push(latency);
  },
  
  report() {
    console.log('性能报告:', {
      总耗时：performance.now() - this.taskStartTime,
      平均步骤耗时：avg(this.stepDurations.map(d => d.duration)),
      平均流延迟：avg(this.streamLatency)
    });
  }
};
```

---

## 🎯 MVP 实施路线图

### Phase 1: 核心功能 (Week 1-2)
- [ ] 基础面板框架搭建
- [ ] TaskService 实现
- [ ] WebSocket 连接
- [ ] 基本步骤树展示
- [ ] 流式输出支持

### Phase 2: 增强功能 (Week 3-4)
- [ ] 步骤控制面板 (暂停/重试/跳过)
- [ ] 事件时间线
- [ ] 进度条可视化
- [ ] 代码高亮
- [ ] 错误处理

### Phase 3: 优化完善 (Week 5-6)
- [ ] 性能优化 (虚拟滚动/防抖节流)
- [ ] 主题系统
- [ ] 响应式布局
- [ ] 监控日志
- [ ] 单元测试

### Phase 4: 高级特性 (Week 7-8)
- [ ] 多任务并行
- [ ] 任务模板
- [ ] 自定义步骤流程
- [ ] 导出/导入功能
- [ ] 插件市场

---

## 📚 参考资源

### 优秀开源项目参考
- **Cursor**: https://cursor.sh
- **GitHub Copilot**: https://copilot.github.com
- **Tabnine**: https://www.tabnine.com
- **Codeium**: https://codeium.com

### 技术栈选择理由
- **原生 JavaScript**: 零依赖，轻量快速
- **TypeScript**: 类型安全，易于维护
- **VS Code Webview API**: 官方支持，稳定可靠
- **WebSocket**: 实时双向通信

---

## ✅ 成功标准

### 用户体验指标
- ⚡ **首屏加载时间** < 500ms
- 🔄 **流式输出延迟** < 100ms
- 📊 **步骤切换响应** < 50ms
- 🎨 **UI 流畅度** 60fps

### 功能完整性
- ✅ 支持全部 8 种 step_executor 步骤类型
- ✅ 完整的错误处理和重试机制
- ✅ 离线缓存和数据持久化
- ✅ 完善的文档和示例

---

## 🎉 总结

本设计方案旨在打造**业界领先的智能体执行引擎前端**,基于强大的 `step_executor` 后端能力，提供：

1. **直观的可视化界面** - 步骤树、进度条、事件时间线
2. **流畅的交互体验** - 流式输出、实时反馈、可中断控制
3. **可靠的错误处理** - 重试机制、降级策略、用户友好提示
4. **卓越的性能表现** - 虚拟滚动、消息队列、性能监控

通过这一设计，AlphaPilot 将超越现有知名编辑助手，成为开发者的首选 AI 编程伙伴！
