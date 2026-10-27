# 变更日志 (CHANGELOG)

## 2026-10-24 — 🔧 前端输出显示修复（三层治理）

### 概述
修复 AI 输出的 Markdown 内容在前端无法正常显示的问题：Markdown 表格被 AI 压缩为单行导致 react-markdown 无法识别、超长行无溢出保护导致布局破坏、Node API 重复路由导致流式事件丢失。

### 改动范围

#### Webview (webview/src/)
| 文件 | 改动 |
|---|---|
| `components/MarkdownRenderer.tsx` | 新增 `normalizeMarkdownTables()` 预处理函数，将 AI 压缩的单行 Markdown 表格还原为标准多行格式；导入 `useMemo` 缓存 |
| `index.css` | `.markdown-renderer` 和 `.markdown-renderer p` 添加 `overflow-wrap: anywhere` + `word-break: break-word` |

#### Node API (node-api/)
| 文件 | 改动 |
|---|---|
| `index.js` | 删除第 7.5 节旧版重复 `stream_chunk` 处理器（第 479-506 行），避免两个处理器消费同一请求导致新版 `stream_chunk` 事件丢失 |

### 核心设计决策
- **表格规范化在渲染层**：不在 Worker 侧修改输出（Worker = 真相），只在 Webview 投影层预处理，不破坏宪法信条
- **useMemo 缓存**：`normalizeMarkdownTables` 仅在 content 变化时重算，不增加渲染开销
- **算法兼容性**：通过连续 `---` cell 计数推断列数，正确处理 `| |` 产生的行边界 artifact

---

## 2026-10-19 — G1.2 结构化产物协议（Artifact Protocol）

### 概述
实现 G1 阶段结构化事件协议改造：Worker 产生的展示产物（Mermaid 架构图等）通过类型化信封，经 Extension 映射层抵达 Webview，具有明确身份、完整内容和唯一展示责任。严格遵循"Worker = 真相、Extension = 映射、Webview = 投影、协议 = 宪法"原则，不新增通信旁路。

### 改动范围

#### Worker (python_worker/)
| 文件 | 改动 |
|---|---|
| `worker_config.py` | 新增 `emit_artifact()` + `extract_and_emit_artifacts()`，复用 `/task/stream_chunk/:task_id` 路由 |
| `worker_respond_step.py` | LLM 输出完成后提取 Mermaid 产物，`stream_end` 之前发射 |
| `agents/openai/openai_worker.py` | 统一 `stream_chunk(task_id, content, phase, channel)` 签名 |
| `agents/deepeek/deepseek_worker.py` | 统一 `stream_chunk(task_id, content, phase, channel)` 签名 |

#### Node API (node-api/)
| 文件 | 改动 |
|---|---|
| `index.js` | `message_type` 分支判断（artifact_created / stream_chunk）；`completedTasks` Set 终态标记；`artifact_created` 字段校验与终态拒绝 |

#### Extension (vscode-extension/)
| 文件 | 改动 |
|---|---|
| `src/panels/reactPanel.ts` | 新增 `websocketService.on('artifact_created')` 监听，原样转发到 Webview |
| `webview/src/store/chatStore.ts` | 新增 `Artifact` 接口；`addArtifact` 幂等存储（按 task_id + artifact_id 去重）；persist 版本 3→4，迁移 qwen-turbo→qwen_generate；补全 `pendingImages`/`visionLimits` |
| `webview/src/utils/vscode.ts` | 补全 `ImageAttachment`/`BROWSER_SAFETY_MAX_RAW_BYTES`；`submitTask` 支持 images 参数 |
| `webview/src/App.tsx` | 新增 `artifact_created` 消息处理分支 |
| `webview/src/components/MessageList.tsx` | 传递 `artifacts` 属性到 ChatBubble |
| `webview/src/components/ChatBubble.tsx` | 产物卡片渲染 + Mermaid 去重剥离 |
| `webview/src/components/MermaidBlock.tsx` | 新增 `label` 属性 |

### 核心设计决策
- **复用现有路由**：所有产物事件通过现有 `stream_chunk` HTTP 路由 + `message_type` 字段区分
- **不新增通信旁路**：Extension 沿用 G0 已确认的实际 Socket.IO 监听路径，不引入第二套 WS 机制
- **任务状态机不动**：artifact_created 不触发任务完成/失败/流结束，Node API 的 completedTasks 为终态权威来源
- **去重渲染**：artifact 到达后由独立展示路径负责，MarkdownRenderer 剥离对应 Mermaid 块
- **传输顺序**：Worker 先 `await emit_artifact()` 再 `stream_end()`，确保产物在任务终态前完成传输

### 待验证 (G3)
- [ ] 端到端 Mermaid SVG 渲染
- [ ] 旧消息兼容（无 message_type 的 stream_chunk）
- [ ] 未知 message_type 不误当作文本广播
- [ ] 重复事件幂等去重
- [ ] 终态后产物被拒
- [ ] Mermaid 不双重渲染
- [ ] 传输失败不伪造成功产物

---

## 版本 0.1.0 - 流式输出 + 任务历史

### ✨ 新增功能

#### 功能 ①：任务历史面板（Task History）
- **文件**：`src/taskHistory.ts`、`src/panels/taskHistoryPanel.ts`、`src/webviews/taskHistory.*`
- **说明**：
  - 自动保存所有任务（最多 50 条）
  - 支持搜索、删除、查看详情
  - 使用 VS Code globalState 持久化存储
  - 显示任务状态、时间、类型标记

- **新类**：
  ```typescript
  TaskHistoryManager  // управление историей
  TaskHistoryPanel    // UI 面板
  ```

#### 功能 ②：流式输出（Streaming Output）
- **文件**：`src/streamingManager.ts`、升级 `src/panels/aiResultPanel.ts`
- **说明**：
  - 支持 WebSocket 的流式事件：`stream_start`、`stream_chunk`、`stream_end`
  - 逐字显示 AI 输出而不是等待完成
  - 实时字数统计
  - 自动滚动到最新内容

- **新类**：
  ```typescript
  StreamingManager  // 管理流式输出状态
  StreamController  // 单个流的控制器
  ```

#### 功能 ③：暂停/继续控制（Pause/Resume）
- **说明**：
  - 用户可以点击 ⏸️ 暂停流式输出
  - 点击 ⏵️ 继续输出
  - 暂停时数据缓冲，继续时立即发送
  - 类似 GitHub Copilot 体验

### 🔧 修改的文件

#### 1. `src/extension.ts` (↑ 大幅升级)
- ✅ 添加 `TaskHistoryManager` 初始化
- ✅ 添加 `StreamingManager` 初始化
- ✅ 新增命令：`openTaskHistory`
- ✅ WebSocket 事件处理升级：
  - 添加 `stream_start`、`stream_chunk`、`stream_end` 监听
  - 任务完成时自动保存到历史
  - 提交任务时记录待处理任务
- ✅ 优化消息提示（显示任务 ID 前 8 位）

#### 2. `src/panels/aiResultPanel.ts` (↑ 升级)
**新增字段：**
```typescript
private streamingTasks: Set<string> = new Set();
private pausedTasks: Set<string> = new Set();
```

**新增方法：**
```typescript
startStreaming(taskId, title)         // 开始流式
appendStreamingContent(content, taskId) // 追加内容
streamComplete(taskId)                // 完成流式
isTaskPaused(taskId)                  // 检查暂停状态
getStreamingTasks()                   // 获取活跃流列表
```

**消息处理升级：**
```typescript
case "pause":   // 处理暂停请求
case "resume":  // 处理继续请求
```

**HTML 改进：**
- 添加暂停/继续按钮
- 添加流信息显示区
- 优化布局和响应式设计

#### 3. `src/webviews/aiResult.js` (↑ 大幅升级)
**流式输出支持：**
```javascript
handleStreamStart()   // 初始化流式状态
handleStreamChunk()   // 追加内容并滚动
handleStreamEnd()     // 完成流式
handleStreamControl() // 处理暂停/继续
```

**UI 反馈：**
- 实时字数统计
- 暂停/继续按钮切换
- 状态指示器变化
- 自动滚动到最新内容

#### 4. `src/webviews/aiResult.css` (↑ 改进)
**新增样式：**
```css
.control-btn          /* 控制按钮 */
.stream-info          /* 流信息显示 */
.title-area           /* 标题区域 */
```

**优化：**
- 更好的布局（Flexbox）
- VS Code 主题集成
- 响应式设计
- 平滑的动画和过渡

#### 5. `package.json` (↑ 更新)
- 添加新命令：`alphaMinimalExtension.openTaskHistory`
- 添加激活事件：对应新命令

### 📁 新增文件

| 文件 | 说明 |
|------|------|
| `src/taskHistory.ts` | 历史数据管理类 |
| `src/streamingManager.ts` | 流式输出管理类 |
| `src/panels/taskHistoryPanel.ts` | 历史面板 UI |
| `src/webviews/taskHistory.html` | 历史面板 HTML(在 TS 中) |
| `src/webviews/taskHistory.js` | 历史面板逻辑 |
| `src/webviews/taskHistory.css` | 历史面板样式 |
| `FEATURE_GUIDE.md` | 功能详细说明 |
| `BACKEND_INTEGRATION.md` | 后端集成指南 |
| `QUICKSTART.md` | 快速开始指南 |
| `CHANGELOG.md` | 本文件 |

### 🔄 向后兼容性

✅ **完全向后兼容**
- 现有的 `task_result` 事件仍然有效
- 如果后端不实现流式事件，插件会自动降级到普通模式
- 所有现有功能保持不变

### 📊 代码统计

**新增代码行数：**
- `taskHistory.ts`: ~180 行
- `streamingManager.ts`: ~100 行
- `taskHistoryPanel.ts`: ~150 行
- `aiResultPanel.ts`: +80 行（增强）
- `aiResult.js`: +150 行（增强）
- `aiResult.css`: +100 行（增强）
- `taskHistory.js`: ~200 行
- `taskHistory.css`: ~200 行
- 文档: ~1000 行

**总计：新增约 2000+ 行代码和文档**

### 🎯 核心改进

| 维度 | 改进 |
|------|------|
| **用户体验** | 流式输出 + 暂停/继续 + 历史面板 |
| **功能完整性** | 从"等待结果"到"看过程" |
| **工程师友好度** | 支持快速查找、复用、批量操作 |
| **系统架构** | 引入流式管理、事件驱动、持久化存储 |
| **代码质量** | TypeScript 严格类型、清晰的接口设计 |

### 🚀 后续可扩展方向

- [ ] 导出任务历史为 JSON/CSV
- [ ] 按日期/标签归档任务
- [ ] 任务分组和收藏
- [ ] 流式输出速度控制
- [ ] 自定义历史保留数量
- [ ] 任务对比（两个任务的 Prompt 对比）
- [ ] 批量操作（删除多个、导出多个）
- [ ] 搜索高级功能（正则、时间范围等）

### ✅ 测试清单

- [x] TypeScript 编译无错误
- [x] 任务历史面板 UI 展示正常
- [x] 流式消息处理逻辑正确
- [x] 暂停/继续状态管理正常
- [x] 向后兼容现有接口
- [x] 文档完整和准确

### 📝 文档说明

三份详细文档：

1. **[FEATURE_GUIDE.md](./FEATURE_GUIDE.md)** - 功能详解
   - 每个功能的详细说明
   - 架构设计和类说明
   - UI/UX 设计规范

2. **[BACKEND_INTEGRATION.md](./BACKEND_INTEGRATION.md)** - 后端集成
   - WebSocket 事件说明
   - 代码示例（Python）
   - 向后兼容说明

3. **[QUICKSTART.md](./QUICKSTART.md)** - 快速开始
   - 用户友好的快速指南
   - 常见使用场景
   - 故障排查

---

## 总结

这次升级将 AlphaPilot 从一个"任务提交工具"升级为"全能 AI 工作助手"：

✨ **从 1.0 → 2.0 的跨越：**
```
v1.0: 提交任务 → 等待结果
v2.0: 提交任务 → 看流式输出 → 暂停观察 → 查看历史 → 快速复用
```

🎯 **核心价值：**
- 工程师可以**边看边做**，不用等
- 支持**快速复用**过去的 prompt
- 体验类似 **ChatGPT/Cursor/Copilot** 的流式和暂停
- **不改底层**，完美向后兼容

---

**作者**: GitHub Copilot  
**日期**: 2026 年 2 月 26 日  
**状态**: ✅ 完成并测试通过