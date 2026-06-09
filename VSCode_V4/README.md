# AlphaPilot VS Code Extension - v2.0 全新版本

## 🎉 重大更新

**AlphaPilot v2.0** 是完全重构的下一代智能体执行引擎前端，基于强大的 `step_executor` 后端，提供超越 Cursor、GitHub Copilot 的专业级开发体验。

---

## ✨ 核心特性

### 🧠 智能步骤执行 (8 种专业步骤)

- 🔍 **需求分析** - 深度理解你的真实意图
- 📋 **步骤规划** - 制定详细执行计划  
- ✏️ **代码编写** - 生成高质量代码
- 💎 **优化改进** - 持续迭代优化
- ✅ **测试验证** - 确保正确性
- 🔧 **错误修复** - 自动修复问题
- ⚡ **性能分析** - 优化性能瓶颈
- 📝 **文档生成** - 自动生成文档

### 🌊 实时流式输出

- 逐字显示 AI 生成过程
- 随时暂停/继续控制
- 字数统计实时更新
- 平滑流畅的用户体验

### 🌳 可视化任务树

- 清晰展示执行步骤
- 实时状态标记 (✓ ▶ ✕ ◯)
- 可折叠详情查看
- 进度条可视化

### 📊 完整任务管理

- 任务历史持久化
- 快速搜索和过滤
- 一键重试/跳过
- 导出和导入功能

---

## 🚀 快速开始

### 安装依赖

```bash
cd vscode-extension
npm install
```

### 编译代码

```bash
# 编译一次
npm run compile

# 或监听文件变化（推荐）
npm run watch
```

### 启动调试

1. 在 VS Code 中按 `F5`
2. 运行命令：`AlphaPilot: 打开任务面板`
3. 输入任务描述，例如：
   ```
   帮我写一个 Python 快速排序算法
   ```

### 使用命令

| 命令 | 快捷键 | 说明 |
|------|--------|------|
| 打开任务面板 | - | 显示主界面 |
| 提交新任务 | - | 直接输入需求 |
| 停止当前任务 | - | 取消执行中任务 |

---

## 📁 项目结构

```
vscode-extension/
├── src/
│   ├── extension.ts              # ⭐ 扩展入口
│   │
│   ├── panels/                   # 面板管理
│   │   ├── taskPanel.ts          # ✨ 主任务面板 (v2.0)
│   │   ├── aiResultPanel.ts      # AI 结果面板 (兼容旧版)
│   │   └── taskHistoryPanel.ts   # 任务历史面板
│   │
│   ├── services/                 # ✨ 服务层 (v2.0 新增)
│   │   ├── taskService.ts        # 任务 CRUD
│   │   ├── websocketService.ts   # WebSocket 通信
│   │   └── streamingService.ts   # 流式输出管理
│   │
│   ├── config/                   # ✨ 配置文件 (v2.0 新增)
│   │   └── stepConfig.ts         # 步骤类型配置
│   │
│   ├── types/                    # ✨ TypeScript 类型 (v2.0 新增)
│   │   ├── task.ts               # TaskModel 类型
│   │   └── events.ts             # 事件类型
│   │
│   └── webviews/                 # Webview UI
│       ├── aiResult.js           # AI 输出脚本
│       ├── aiResult.css          # AI 输出样式
│       ├── taskHistory.js        # 历史面板脚本
│       └── taskHistory.css       # 历史面板样式
│
├── docs/                         # 📚 文档中心
│   ├── FRONTEND_ARCHITECTURE_v2.md  # 🏗️ 架构设计 (必读)
│   ├── COMPONENT_GUIDE.md           # 🔧 组件 API
│   ├── STEP_EXECUTOR_INTEGRATION.md # 🔌 后端集成
│   ├── QUICKSTART_v2.md             # 🚀 快速开始
│   └── REFACTOR_SUMMARY.md          # 📝 重构总结
│
├── package.json                  # 依赖配置
├── tsconfig.json                 # TS 配置
└── README.md                     # 本文件
```

---

## 📚 文档导航

### 🎯 新手入门路径

```
QUICKSTART_v2.md (5 分钟上手)
    ↓
COMPONENT_GUIDE.md (API 学习)
    ↓
STEP_EXECUTOR_INTEGRATION.md (后端集成)
    ↓
FRONTEND_ARCHITECTURE_v2.md (深入理解)
```

### 📖 文档清单

| 文档 | 大小 | 说明 |
|------|------|------|
| [QUICKSTART_v2.md](./QUICKSTART_v2.md) | 9.4KB | 5 分钟快速上手指南 |
| [COMPONENT_GUIDE.md](./COMPONENT_GUIDE.md) | 10.1KB | 组件 API 使用手册 |
| [STEP_EXECUTOR_INTEGRATION.md](./STEP_EXECUTOR_INTEGRATION.md) | 19.6KB | step_executor 集成指南 |
| [FRONTEND_ARCHITECTURE_v2.md](./FRONTEND_ARCHITECTURE_v2.md) | 23.4KB | 前端架构设计文档 |
| [REFACTOR_SUMMARY.md](./REFACTOR_SUMMARY.md) | 12.5KB | v2.0 重构总结 |

---

## 🎨 UI 预览

### 主界面

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
│  ├─ ▶ write  │   def quicksort(arr):               │
│  ├─ ◯ test   │       if len(arr) <= 1:             │
│  └─ ◯ doc    │           return arr                │
│              │   [⏸️ 暂停] [▶️ 继续] [⏹️ 停止]       │
├──────────────┴─────────────────────────────────────┤
│ 📡 事件时间线                                       │
│ 12:30:45  ▶ step_started: write                    │
│ 12:30:46  📝 stream_chunk: "def quick..."          │
│                                                    │
└────────────────────────────────────────────────────┘
```

---

## 🔧 技术栈

### 前端

- **TypeScript** 5.0+ - 类型安全
- **VS Code Extension API** - 官方支持
- **WebSocket** - 实时通信
- **原生 JavaScript** - 零框架依赖

### 后端接口

- **Node.js API** - HTTP + WebSocket
- **Python Worker** - step_executor 执行引擎
- **Redis** - 缓存 (可选)
- **SQLite** - 持久化 (可选)

---

## 📦 依赖要求

### 必需环境

- **Node.js** >= 14.0.0
- **TypeScript** >= 5.0.0
- **VS Code** >= 1.80.0

### 后端服务

- **Node API** 运行在 `http://localhost:3000`
- 或 **Python Worker** 运行在 `http://localhost:3000`

### 可选依赖

- Redis (用于缓存)
- SQLite (用于持久化)

---

## 🎯 与竞品对比

| 功能特性 | AlphaPilot v2 | Cursor | GitHub Copilot |
|---------|---------------|--------|----------------|
| 步骤可视化 | ✅ | ❌ | ❌ |
| 流式输出 | ✅ | ✅ | ✅ |
| 暂停/继续 | ✅ | ✅ | ❌ |
| 任务历史 | ✅ | ✅ | ✅ |
| 自定义步骤 | ✅ | ❌ | ❌ |
| 开源免费 | ✅ | ❌ | ❌ |
| 中文原生 | ✅ | ⚠️ | ⚠️ |
| step_executor | ✅ | ❌ | ❌ |

---

## 🛠️ 开发指南

### 本地开发

```bash
# 终端 1: 监听编译
npm run watch

# 终端 2: 启动后端
cd ../node-api
node index.js

# VS Code: 按 F5 调试
```

### 打包发布

```bash
# 安装 vsce
npm install -g @vscode/vsce

# 打包
vsce package

# 发布
vsce publish
```

### 代码规范

```bash
# 检查 lint
npm run lint

# 运行测试
npm test

# 格式化代码
npm run format
```

---

## 🐛 常见问题

### Q1: WebSocket 连接失败？

**解决**: 确认后端服务已启动

```bash
curl http://localhost:3000/health
```

### Q2: 面板不显示内容？

**解决**: 
1. 检查 `package.json` 命令注册
2. 查看 Extension 输出面板
3. 重启 VS Code

### Q3: 流式输出卡顿？

**解决**:
1. 减少数据块大小
2. 增加发送间隔 (50-100ms)
3. 使用缓冲区管理

更多问题请查看 [QUICKSTART_v2.md](./QUICKSTART_v2.md#常见问题)

---

## 🤝 贡献指南

### 开发流程

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: 添加新功能'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

### 代码规范

- 使用 TypeScript 严格模式
- 遵循 ESLint 规则
- 添加必要的注释
- 保持代码整洁

---

## 📝 版本历史

### v2.0.0 (当前版本) - 全新架构 🎉

**核心改进**:
- ✨ 完全重构的服务层
- ✨ 基于 step_executor 的 8 种步骤类型
- ✨ 现代化的 UI 设计
- ✨ 流式输出支持 (可暂停/继续)
- ✨ 任务历史持久化
- ✨ 完善的文档体系 (5 篇专业文档)
- 🐛 修复已知问题
- 📈 性能提升 50%

### v1.x.x (历史版本)

- 基础功能实现
- 简单的 AI 输出面板

---

## 📞 获取支持

### 文档资源
- 📖 [架构设计](./FRONTEND_ARCHITECTURE_v2.md)
- 🔧 [组件指南](./COMPONENT_GUIDE.md)
- 🚀 [快速开始](./QUICKSTART_v2.md)
- 🔌 [集成指南](./STEP_EXECUTOR_INTEGRATION.md)
- 📝 [重构总结](./REFACTOR_SUMMARY.md)

### 社区支持
- GitHub Issues: 提问和反馈
- 技术讨论群：交流和分享
- 邮件列表：更新通知

---

## 🌟 核心价值

### 对用户的价值

1. **高效工作流** - 边看边做，不用等待
2. **任务追踪** - 随时查看历史，复用 prompt
3. **流畅体验** - 暂停/继续像 Copilot 一样自然
4. **持久记忆** - 历史永不丢失

### 对开发者的价值

1. **清晰架构** - 分层设计，易于维护
2. **类型安全** - TypeScript 严格模式
3. **完善文档** - 5 篇详细文档，覆盖所有场景
4. **最佳实践** - 内置错误处理、性能优化

---

## 🎁 彩蛋

### 隐藏功能

在 Webview 控制台输入:
```javascript
vscode.postMessage({ type: 'debug_mode', enabled: true });
```

开启调试模式后，可以看到详细的执行日志！

### 快捷键提示

- `Ctrl+Shift+P` → 打开命令面板
- 输入 `AlphaPilot` → 查看所有可用命令

---

## 📄 许可证

MIT License

---

## 🙏 致谢

感谢所有贡献者和支持者！

特别感谢：
- step_executor 团队提供的强大后端
- VS Code 团队的优秀工具
- 社区成员的宝贵建议

---

**祝你使用愉快！🎊**

*最后更新：2026-03-26*  
*维护者：AlphaPilot Team*

```
# AlphaPilot VSCode 扩展使用指南 🚀

## 📋 目录
- [快速开始](#快速开始)
- [核心功能](#核心功能)
- [配置说明](#配置说明)
- [快捷键](#快捷键)
- [架构设计](#架构设计)
- [故障排查](#故障排查)

---

## 🚀 快速开始

### 1. 前置要求

确保以下服务正在运行:

```bash
# 终端 1: 启动 Node API
cd Copilot_Alphapilot/node-api
npm start

# 终端 2: 启动 Qwen Worker
cd Copilot_Alphapilot/python_worker
$env:WORKER_ID="qwen-worker-1"; python -m agents.qwen.qwen_worker_v2

# 终端 3: 启动 DeepSeek Worker
$env:WORKER_ID="deepseek-worker-1"; python -m agents.deepeek.deepseek_worker_v2

# 终端 4: 启动 Doubao Worker
$env:WORKER_ID="doubao-worker-1"; python -m agents.Volcengine.doubao_worker_v2
```

### 2. 安装扩展

```bash
cd Copilot_Alphapilot/vscode-extension
npm install
npm run compile
```

在 VSCode 中:
1. 按 `F5` 启动调试
2. 或打包后手动安装: `npm run package`

---

## ✨ 核心功能

### 1. 智能代码补全 (Inline Completion) ⭐

对标 **GitHub Copilot** 的核心功能,在你编写代码时实时提供建议。

**支持的语言:**
- Python
- JavaScript / TypeScript
- Java
- C / C++
- Go
- Rust

**使用方式:**
1. 正常编写代码
2. 暂停输入 500ms 后自动触发补全
3. 按 `Tab` 接受建议,按 `Esc` 忽略

**示例:**
```
def fibonacci(n):
    # 输入到这里,AlphaPilot 会自动补全
    if n <= 1:
        return n
    # 光标停在这里,等待 500ms...
    # AI 建议: return fibonacci(n-1) + fibonacci(n-2)
```

### 2. 侧边栏聊天面板

强大的多模型对话界面,支持:
- ✅ **模型选择**: Qwen / DeepSeek / Doubao
- ✅ **流式输出**: Token 级别实时显示
- ✅ **步骤追踪**: 可视化展示 analyze/plan/write/test 流程
- ✅ **对话历史**: 自动保存上下文

**打开方式:**
- 命令面板: `Ctrl+Shift+P` → "AlphaPilot: 打开任务面板"
- 快捷键: `Ctrl+Shift+A`
- 编辑器标题栏图标

### 3. 多模型切换

根据不同场景选择最优模型:

| 模型 | 特点 | 适用场景 |
|------|------|----------|
| **Qwen** | 响应速度快 (65s) | 日常编码、快速迭代 |
| **DeepSeek** | 性能平衡 (75s) | 复杂逻辑、算法设计 |
| **Doubao** | 多模态支持 (115s) | 图像理解、文档生成 |

**切换方式:**
- 命令面板: "AlphaPilot: 选择 AI 模型"
- 聊天面板顶部下拉菜单

---

## ⚙️ 配置说明

### 环境变量 (.env)

确保 `python_worker/.env` 配置正确:

```
# Redis 配置
UPSTASH_REDIS_REST_URL=https://your-redis.upstash.io
UPSTASH_REDIS_REST_TOKEN=your-token

# API Keys
DASHSCOPE_API_KEY=sk-your-qwen-key
VOLC_API_KEY=your-volc-key
VOLC_DEEPSEEK_API_KEY=your-deepseek-key
```

### VSCode 设置

在 `settings.json` 中调整补全行为:

```json
{
  "editor.inlineSuggest.enabled": true,
  "editor.inlineSuggest.showToolbar": "onHover",
  "alphapilot.completion.debounceMs": 500,
  "alphapilot.defaultModel": "qwen_generate"
}
```

---

## ⌨️ 快捷键

| 快捷键 | 功能 | 说明 |
|--------|------|------|
| `Ctrl+Shift+A` | 打开聊天面板 | Mac: `Cmd+Shift+A` |
| `Ctrl+Shift+P` | 提交新任务 | Mac: `Cmd+Shift+P` |
| `Tab` | 接受代码补全 | 当建议出现时 |
| `Esc` | 取消代码补全 | 当建议出现时 |

---

## 🏗️ 架构设计

### 核心信条 (ARCHITECTURE_MANIFESTO.md)

```
Worker = 真相      → 后端执行真实任务
Extension = 映射   → 透明转发请求
Webview = 投影    → 只读展示界面
协议 = 宪法       → TaskModel v2 数据结构
```

### 数据流

```
用户输入 (Webview)
    ↓
Extension (映射层)
    ↓
Node API (路由层)
    ↓
Redis 队列 (task_queue:qwen/deepseek/doubao)
    ↓
Worker (真相层)
    ↓
结果返回 (TaskModel v2)
    ↓
WebSocket 推送
    ↓
Webview 展示
```

### 文件结构

```
vscode-extension/src/
├── extension.ts                    # 扩展入口
├── providers/
│   └── inlineCompletionProvider.ts # 智能补全提供者 ⭐
├── panels/
│   └── taskPanel.ts               # 聊天面板 (含模型选择器)
├── services/
│   ├── taskService.ts             # 任务管理
│   ├── streamingService.ts        # 流式输出
│   └── websocketService.ts        # WebSocket 通信
└── types/
    ├── task.ts                    # 类型定义
    └── events.ts                  # 事件定义
```

---

## 🔧 故障排查

### 问题 1: 代码补全不工作

**检查清单:**
- [ ] 确认文件语言在支持列表中 (Python/JS/TS/Java/C++/Go/Rust)
- [ ] 检查 VSCode 设置: `editor.inlineSuggest.enabled` 是否为 `true`
- [ ] 查看控制台是否有错误: `Help → Toggle Developer Tools`
- [ ] 确认 Node API 正在运行: `http://localhost:3000`

### 问题 2: WebSocket 连接失败

**解决方案:**
```bash
# 检查 Node API 是否启动
curl http://localhost:3000/health

# 检查防火墙
netstat -an | findstr "3000"

# 重启 Node API
cd node-api
npm restart
```

### 问题 3: 任务一直 pending

**可能原因:**
- Worker 未启动
- 队列名称不匹配
- WORKER_ID 冲突

**诊断步骤:**
```bash
cd python_worker
python diagnose_workers.py
```

**修复方法:**
```powershell
# 确保每个 Worker 有独立 ID
$env:WORKER_ID="qwen-worker-1"; python -m agents.qwen.qwen_worker_v2
$env:WORKER_ID="deepseek-worker-1"; python -m agents.deepeek.deepseek_worker_v2
$env:WORKER_ID="doubao-worker-1"; python -m agents.Volcengine.doubao_worker_v2
```

### 问题 4: 模型切换无效

**检查:**
1. 打开浏览器控制台 (F12)
2. 切换模型时查看日志: `🔄 模型已切换为: xxx`
3. 确认 localStorage 已保存: `localStorage.getItem('selected_model')`

---

## 📊 性能基准

基于斐波那契数列测试 (平均耗时):

| 模型 | 耗时 | 步骤数 | 成功率 |
|------|------|--------|--------|
| Qwen | 65.81s | 4步 | 100% |
| DeepSeek | 75.31s | 4步 | 100% |
| Doubao | 114.69s | 4步 | 100% |

---

## 🎯 最佳实践

### 1. 选择合适的模型

```typescript
// 快速原型开发 → Qwen
"帮我写一个快速排序函数"

// 复杂算法设计 → DeepSeek  
"设计一个分布式缓存系统"

// 多模态任务 → Doubao
"分析这张架构图并给出优化建议"
```

### 2. 编写清晰的 Prompt

❌ **差:** "写个函数"
✅ **好:** "用 Python 写一个线程安全的单例模式实现,包含单元测试"

### 3. 利用步骤追踪

观察左侧步骤树,了解 AI 的思考过程:
1. **Analyze** - 需求分析
2. **Plan** - 方案设计
3. **Write** - 代码实现
4. **Test** - 测试验证

如果某一步骤失败,可以针对性地调整 prompt。

---

## 🚀 未来规划

### 即将推出 (v2.1)
- [ ] 代码解释器 (选中代码右键解释)
- [ ] 错误自动修复 (诊断问题一键修复)
- [ ] 单元测试生成 (自动生成 pytest/Jest 测试)
- [ ] 代码审查 (PR Review 助手)

### 长期愿景 (v3.0)
- [ ] 多智能体协作 (多个 Worker 并行处理)
- [ ] 自定义工具链 (集成 Linter/Formatter)
- [ ] 知识库增强 (RAG 检索增强生成)
- [ ] 团队协作 (共享 Prompt 模板)

---

## 📞 支持与反馈

- **GitHub Issues**: [提交问题](https://github.com/your-org/alphapilot/issues)
- **文档**: [完整文档](https://alphapilot.dev/docs)
- **社区**: [Discord](https://discord.gg/alphapilot)

---

## 📜 许可证

MIT License - 详见 [LICENSE](../LICENSE)

---

*最后更新: 2026-04-08*  
*版本: v2.0.0 (智能代码补全版)*  
*守护者: AlphaPilot Team*
