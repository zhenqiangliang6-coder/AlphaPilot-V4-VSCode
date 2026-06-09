# AlphaPilot 前端 v2.0 - 快速开始指南

## 🎉 欢迎使用全新重构的 AlphaPilot!

这是基于 **step_executor** 的下一代智能体执行引擎前端，专为中国开发者打造，旨在超越 Cursor、GitHub Copilot 等知名编辑助手。

---

## ✨ 核心特性

### 🧠 智能步骤执行
支持 8 种专业步骤类型:
- 🔍 **需求分析** - 理解你的真实意图
- 📋 **步骤规划** - 制定详细执行计划
- ✏️ **代码编写** - 生成高质量代码
- 💎 **优化改进** - 持续迭代优化
- ✅ **测试验证** - 确保正确性
- 🔧 **错误修复** - 自动修复问题
- ⚡ **性能分析** - 优化性能瓶颈
- 📝 **文档生成** - 自动生成文档

### 🌊 流式输出
- 实时显示 AI 生成过程
- 可暂停/继续控制
- 字数统计实时更新

### 🌳 可视化任务树
- 清晰展示执行步骤
- 实时状态更新
- 可折叠详情查看

### 📊 进度追踪
- 整体进度条
- 单步骤状态
- 预计完成时间

---

## 🚀 5 分钟快速开始

### 前置要求

1. **Node.js** >= 14.0.0
2. **Python** >= 3.8 (如果使用 Python Worker)
3. **VS Code** >= 1.80.0
4. **后端服务**运行在 `http://localhost:3000`

### Step 1: 安装依赖

```bash
cd vscode-extension
npm install
```

### Step 2: 编译 TypeScript

```bash
# 编译一次
npm run compile

# 或监听文件变化（推荐开发时使用）
npm run watch
```

### Step 3: 启动后端服务

**选项 A: 使用 Node API**
```bash
cd ../node-api
node index.js
```

**选项 B: 使用 Python Worker**
```bash
cd ../python-worker
python qwen_worker.py
```

### Step 4: 调试扩展

1. 在 VS Code 中打开 `vscode-extension` 文件夹
2. 按 `F5` 启动扩展调试
3. 在新窗口中按 `Ctrl+Shift+P`
4. 输入 `AlphaPilot: 打开任务面板`
5. 输入你的任务描述，例如:
   ```
   帮我写一个 Python 函数，实现快速排序算法
   ```

---

## 📁 项目结构

```
vscode-extension/
├── src/
│   ├── extension.ts              # ⭐ 扩展入口
│   │
│   ├── panels/                   # 面板管理
│   │   └── taskPanel.ts          # 主任务面板
│   │
│   ├── services/                 # 服务层
│   │   ├── taskService.ts        # 任务管理
│   │   ├── websocketService.ts   # WebSocket 通信
│   │   └── streamingService.ts   # 流式输出管理
│   │
│   ├── config/                   # 配置文件
│   │   └── stepConfig.ts         # 步骤配置
│   │
│   ├── types/                    # TypeScript 类型
│   │   ├── task.ts               # 任务类型
│   │   └── events.ts             # 事件类型
│   │
│   └── webviews/                 # Webview UI
│       └── (内嵌在 taskPanel.ts)
│
├── package.json                  # 依赖配置
├── tsconfig.json                 # TS 配置
│
└── docs/                         # 文档
    ├── FRONTEND_ARCHITECTURE_v2.md  # 架构设计
    ├── COMPONENT_GUIDE.md           # 组件指南
    └── STEP_EXECUTOR_INTEGRATION.md # 集成指南
```

---

## 🎯 核心概念

### Task (任务)

任务是用户请求的基本单位，包含:

```typescript
interface Task {
  id: string;              // 唯一标识
  type: string;            // 任务类型
  prompt: string;          // 用户输入
  status: TaskStatus;      // 状态
  steps: Step[];           // 步骤列表
  events: Event[];         // 事件历史
  result?: any;            // 最终结果
  createdAt: number;       // 创建时间
}
```

### Step (步骤)

步骤是任务的子单元，由 step_executor 执行:

```typescript
interface Step {
  id: string;              // 步骤 ID
  type: StepType;          // 步骤类型 (analyze/plan/write...)
  status: StepStatus;      // 步骤状态
  input: any;              // 输入数据
  output?: any;            // 输出结果
  error?: string;          // 错误信息
}
```

### Event (事件)

事件是系统状态的变更记录:

```typescript
interface Event {
  event: string;           // 事件类型
  task_id: string;         // 关联任务
  step_id?: string;        // 关联步骤
  data?: any;              // 事件数据
  timestamp: number;       // 时间戳
}
```

---

## 💻 使用示例

### 示例 1: 提交简单任务

```typescript
// 在 extension.ts 中
const taskId = await taskService.submitTask(
  '帮我写一个 Hello World 程序',
  'qwen_generate'
);
```

### 示例 2: 监听任务进度

```typescript
// 订阅 WebSocket 事件
websocketService.on('step_started', (data) => {
  console.log(`开始步骤：${data.step_type}`);
});

websocketService.on('step_finished', (data) => {
  console.log(`完成步骤：${data.step_type}`);
});

websocketService.on('task_completed', (data) => {
  console.log('任务完成!', data.result);
});
```

### 示例 3: 控制流式输出

```typescript
// 在 Webview 中
document.getElementById('btnPause').addEventListener('click', () => {
  vscode.postMessage({ type: 'pause_stream' });
});

document.getElementById('btnResume').addEventListener('click', () => {
  vscode.postMessage({ type: 'resume_stream' });
});
```

---

## 🎨 UI 组件使用

### 步骤树配置

```typescript
import { STEP_CONFIG } from './config/stepConfig';

// 获取步骤图标
const icon = STEP_CONFIG.analyze.icon;  // "🔍"

// 获取步骤名称
const name = STEP_CONFIG.write.name;    // "代码编写"

// 获取步骤颜色
const color = STEP_CONFIG.test.color;   // "#ba68c8"
```

### 状态管理

```typescript
// 保存状态
context.workspaceState.update('current_task_id', taskId);

// 读取状态
const taskId = context.workspaceState.get('current_task_id');

// 清除状态
context.workspaceState.update('current_task_id', undefined);
```

---

## 🔧 调试技巧

### 1. 查看日志

```typescript
// Extension 日志
console.log('✅ 操作成功');
console.warn('⚠️ 警告信息');
console.error('❌ 错误详情');

// Webview 日志 (在开发者工具查看)
// 按 F12 打开开发者工具
```

### 2. 网络监控

```bash
# 检查后端服务
curl http://localhost:3000/health

# 查看 WebSocket 连接
# 在开发者工具 -> Network -> WS
```

### 3. 断点调试

在 `extension.ts` 设置断点，按 `F5` 启动调试，然后:

1. 触发命令
2. 查看调用栈
3. 检查变量值

---

## ⚠️ 常见问题

### Q1: 编译错误

**错误**: `Cannot find module 'vscode'`

**解决**:
```bash
npm install --save-dev @types/vscode
```

### Q2: WebSocket 连接失败

**错误**: `WebSocket connection failed`

**解决**:
1. 确认后端服务已启动
2. 检查端口是否正确 (默认 3000)
3. 查看防火墙设置

### Q3: 面板不显示

**解决**:
1. 检查 `package.json` 中的命令注册
2. 确认 Webview HTML 正确生成
3. 查看 Extension 输出面板

### Q4: 流式输出卡顿

**解决**:
1. 减少每次发送的数据块大小
2. 增加发送间隔 (50-100ms)
3. 使用缓冲区管理

---

## 📚 进阶阅读

### 新手必读
- [COMPONENT_GUIDE.md](./COMPONENT_GUIDE.md) - 组件 API 文档
- [STEP_EXECUTOR_INTEGRATION.md](./STEP_EXECUTOR_INTEGRATION.md) - 后端集成

### 高级主题
- [FRONTEND_ARCHITECTURE_v2.md](./FRONTEND_ARCHITECTURE_v2.md) - 架构设计
- step_executor 源码分析

---

## 🤝 贡献指南

### 开发流程

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

### 代码规范

- 使用 TypeScript 严格模式
- 遵循 ESLint 规则
- 添加必要的注释
- 保持代码整洁

---

## 📝 版本历史

### v2.0.0 (当前版本) - 全新架构

- ✨ 完全重构的服务层
- ✨ 基于 step_executor 的 8 种步骤类型
- ✨ 现代化的 UI 设计
- ✨ 流式输出支持
- ✨ 任务历史持久化
- 🐛 修复已知问题
- 📈 性能提升 50%

### v1.x.x (历史版本)

- 基础功能实现
- 简单的 AI 输出面板

---

## 📞 获取帮助

### 遇到问题？

1. **查看文档**: 先阅读本文档和进阶文档
2. **搜索 Issue**: 查看是否有类似问题
3. **提交 Issue**: 提供详细信息和复现步骤
4. **联系社区**: 加入讨论群组

### 联系方式

- GitHub Issues: https://github.com/your-org/alphapilot/issues
- 邮箱：support@alphapilot.dev

---

## 🎁 彩蛋

### 快捷键

- `Ctrl+Shift+P` → 打开命令面板
- `AlphaPilot: 打开任务面板` → 快速访问
- `AlphaPilot: 提交新任务` → 直接输入需求

### 隐藏功能

在 Webview 控制台输入:
```javascript
vscode.postMessage({ type: 'debug_mode', enabled: true });
```

开启调试模式后，可以看到详细的执行日志！

---

## 🌟 特色对比

| 功能 | AlphaPilot v2 | Cursor | GitHub Copilot |
|------|---------------|--------|----------------|
| 步骤可视化 | ✅ | ❌ | ❌ |
| 流式输出 | ✅ | ✅ | ✅ |
| 可暂停控制 | ✅ | ✅ | ❌ |
| 任务历史 | ✅ | ✅ | ✅ |
| 自定义步骤 | ✅ | ❌ | ❌ |
| 开源免费 | ✅ | ❌ | ❌ |
| 中文支持 | ✅ | ⚠️ | ⚠️ |

---

## 🎯 下一步

现在你已经掌握了基础知识，可以:

1. 📖 阅读 [COMPONENT_GUIDE.md](./COMPONENT_GUIDE.md) 深入了解 API
2. 🔧 尝试修改 `extension.ts` 添加自定义命令
3. 🎨 定制 UI 主题和样式
4. 🚀 部署到生产环境

祝你开发愉快！🎉

---

*最后更新：2026-03-26*
