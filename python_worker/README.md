# AlphaPilot VSCode 扩展 - MVP 版本

**版本**: 0.1.0  
**状态**: ✅ 完成  
**架构**: 三层分离（Webview / Extension / Backend）  
**最后更新**: 2026年2月28日

---

## 🎯 MVP 核心概念

AlphaPilot MVP 是一个企业级可扩展的 VSCode AI 代码补全插件，遵循**严格的三层架构**：

```
┌──────────────────┐
│   Webview 层     │  只显示内容，不处理逻辑
│ (aiResult.js)    │  只接收: append | done | error
└────────┬─────────┘
         │ 简化消息
         ↓
┌──────────────────┐
│  Extension 层    │  协议映射和流程控制
│ extension.ts     │  HTTP 调用 → 轮询结果 → 裁剪消息
└────────┬─────────┘
         │ HTTP
         ↓
┌──────────────────┐
│   Backend        │  业务逻辑和 AI 处理
│ Node API + Redis │  完整 TaskModel 流转
│ qwen_worker.py   │  真实 API 调用
└──────────────────┘
```

---

## 📦 核心改动（2026年2月28日）

### ✅ Webview 层 (`aiResult.js`)
- 重写为只接收 3 种简化消息：**`append` | `done` | `error`**
- **完全移除** TaskModel 解析、version、meta、worker_id 处理
- 只负责文本渲染，无业务逻辑

### ✅ Extension 层 (`extension.ts`)
- **改为 HTTP 调用** 而不是 spawn Worker 进程
- 流程：POST /task/submit → GET /task/result (轮询) → 协议裁剪
- 状态映射：
  - `streaming` → `{ type: "append", content: chunk }`
  - `done` → `{ type: "done" }`
  - `error` → `{ type: "error", message: msg }`

### ❌ 已删除/弃用
- `workerManager.ts` - 不再 spawn 进程
- `worker_mvp.py` - 不需要新的 worker，使用现有的 qwen_worker.py
- `streamingManager.ts` 中的复杂暂停/继续逻辑（MVP 不需要）

---

## 🚀 使用步骤

### 前置需求
```bash
# 1. 启动 Node API（localhost:3000）
cd node-api
node index.js

# 2. 启动 Redis（或 Upstash）
redis-server
# 或 Upstash 在线版本

# 3. 启动 Qwen Worker（监听 Redis 队列）
cd python-worker
python qwen_worker.py
# 需要 DASHSCOPE_API_KEY 环境变量
```

### VSCode 中的使用
```
1. Ctrl+Shift+P
2. 输入 "AlphaPilot: 代码补全 (MVP)"
3. 输入 prompt
4. 查看 AI 输出面板中的流式结果
```

---

## 📋 架构原则

### 一句话原则
> **Worker = 真相 | Extension = 映射 | Webview = 投影**

### 三层职责

**Webview 层（前端 UI）**
- ✅ DO: 显示文本，处理用户点击（复制/清空）
- ❌ DON'T: 解析 JSON，处理错误重试，关心 version/meta

**Extension 层（协议裁剪）**
- ✅ DO: 调用 HTTP API，轮询结果，进行状态映射
- ❌ DON'T: 启动子进程，修改 TaskModel 内容，拼接 JSON

**Backend（Node API + Worker）**
- ✅ DO: 输出完整 TaskModel，遵守协议规范
- ❌ DON'T: 裁剪协议，修改前端协议

---

## 🔧 开发指南

### 编译 TypeScript
```bash
cd vscode-extension
npm run compile
# 输出到 out/ 目录
```

### 文件结构
```
src/
├── extension.ts           # 主入口，HTTP 调用
├── panels/
│   └── aiResultPanel.ts   # 协议映射中转
├── webviews/
│   ├── aiResult.js        # 最简单的前端
│   ├── aiResult.html      # 简化 HTML
│   └── aiResult.css       # 样式
└── taskModel.ts           # 类型定义
```

### 修改规则（MVP 完成后）

1. **修改 Webview**（aiResult.js）
   - 只能改显示逻辑
   - 不能添加新的消息类型

2. **修改 Extension**（extension.ts）
   - 只能改 HTTP 调用的细节
   - 必须保持协议裁剪的一致性
   - 不能删除任何状态判断

3. **修改 Backend**
   - 使用现有的 qwen_worker.py
   - 未来扩展用 openai_worker.py、deepseek_worker.py 等
   - **所有 Worker 必须输出完整 TaskModel**

---

## ✅ MVP 标准达成情况

| 项目 | 状态 | 说明 |
|------|------|------|
| Webview 层简化 | ✅ | 只接收 append/done/error |
| Extension 协议裁剪 | ✅ | 正确映射状态到消息 |
| HTTP 集成 | ✅ | 调用 Node API 而非 spawn |
| TaskModel 版本统一 | ✅ | 1.0 格式贯穿全链路 |
| 流式输出 | ✅ | 实时显示 chunk 内容 |
| 错误处理 | ✅ | 显示错误消息 |
| 编译无错 | ✅ | npm run compile 通过 |

---

## 🚫 严格禁止

根据初始需求（前端.txt），以下行为**绝对禁止**：

```javascript
❌ Webview 中出现 JSON.parse(TaskModel)
❌ Webview 处理 retry 逻辑
❌ Webview 解析 status 字段
❌ Extension spawn Worker 进程
❌ Extension 修改 TaskModel 内容
❌ Worker 输出裸字符串（不是 JSON）
❌ Server 推送包含 worker_id 给前端
```

---

## 🔮 未来扩展路线

MVP 完成后，可以扩展：

1. **多 Worker 支持**
   - openai_worker.py
   - deepseek_worker.py
   - 本地模型 worker
   - 自动选择最快的 worker

2. **Persona 模块**
   - 不同 AI 角色（Copilot / Claude / 专家）
   - 在 Backend 实现，前端无感知

3. **更复杂的任务类型**
   - code_refactor
   - code_explain
   - test_generation
   - 都复用同一套流式架构

4. **高级功能**
   - 暂停/继续流式输出
   - 流式内容编辑
   - 多文件同时处理

---

## 📞 常见问题

**Q: 为什么不直接 spawn Worker？**  
A: 因为这样会破坏可扩展性。使用 HTTP + Redis 允许 Worker 独立运行，支持多个 Worker 并行处理。

**Q: Webview 为什么这么简单？**  
A: 职责分离原则。前端只负责显示，其他逻辑都在 Backend。这样修改 AI 逻辑时不需要改前端。

**Q: 能加暂停/继续吗？**  
A: 可以，但改在 Backend（Node API）实现，前端只接收信号显示。

---

## 📝 更新日志

**v0.1.0 (2026-02-28)** - MVP 完成
- ✅ 实现三层架构
- ✅ 简化 Webview 协议
- ✅ HTTP 集成 Node API
- ✅ 轮询 /task/result 获取流式更新
- ✅ 编译无错，可运行测试

