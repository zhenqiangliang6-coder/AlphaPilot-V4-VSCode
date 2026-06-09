# AlphaPilot v2.2 - React Webview 快速测试指南 🚀

## ✅ 前置条件检查

### 1. 确认构建产物存在

```bash
# 检查 webview-dist 目录
ls d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\webview-dist\
```

**预期输出**:
```
index.html
assets/
  index-xxx.js   (约 157KB)
  index-xxx.css  (约 9.6KB)
```

### 2. 确认后端服务运行

启动所有后端服务:

```powershell
# 在项目根目录执行
.\start_all.ps1
```

**预期输出**:
```
🚀 正在启动 AlphaPilot 所有服务...

✅ Node API 已启动 (http://localhost:3000)
✅ Qwen Worker 已启动 (task_queue:qwen)
✅ DeepSeek Worker 已启动 (task_queue:deepseek)
✅ Doubao Worker 已启动 (task_queue:doubao)
```

---

## 🧪 测试步骤

### 测试 1: 打开 React Webview 面板 ⭐⭐⭐⭐⭐

#### 操作步骤:
1. 在 VSCode 中按 `F5` 启动扩展调试
2. 新窗口打开后,使用以下任一方式打开面板:
   - **快捷键**: `Ctrl+Shift+R`
   - **命令面板**: `Ctrl+Shift+P` → 输入 "AlphaPilot: 打开 React 面板"
   - **菜单**: 编辑器右上角的火箭图标 🚀

#### 预期结果:
✅ 右侧出现聊天面板  
✅ 顶部显示 "AlphaPilot Chat" 标题  
✅ 模型选择器显示 "通义千问 (Qwen)"  
✅ 中间空白区域显示欢迎语 "🚀 开始与 AlphaPilot 对话"  
✅ 底部有输入框和发送按钮  

#### 验证点:
- [ ] 无 JavaScript 错误 (按 F12 打开开发者工具查看控制台)
- [ ] 样式与 VSCode 主题一致 (深色/浅色模式自动适配)
- [ ] 布局响应式正常 (调整窗口大小观察)

---

### 测试 2: 模型选择器 ⭐⭐⭐⭐

#### 操作步骤:
1. 点击模型下拉菜单
2. 依次切换: Qwen → DeepSeek → Doubao → Qwen
3. 关闭面板再重新打开

#### 预期结果:
✅ 下拉菜单显示 3 个选项  
✅ 每个选项有描述文字 (快速响应/平衡性能/多模态支持)  
✅ 切换后立即生效  
✅ 重新打开后面板记住上次选择  

#### 验证点:
- [ ] localStorage 中有 `alphapilot-chat-storage`
- [ ] Zustand store 状态正确更新

**检查 localStorage**:
```javascript
// 在开发者工具控制台中执行
localStorage.getItem('alphapilot-chat-storage')
// 应该看到: {"state":{"selectedModel":"qwen_generate"},"version":0}
```

---

### 测试 3: 提交任务 ⭐⭐⭐⭐⭐

#### 操作步骤:
1. 在输入框中输入: `写一个 Python 函数,计算斐波那契数列`
2. 点击发送按钮或按 `Enter`

#### 预期结果:
✅ 用户消息显示在右侧 (蓝色气泡)  
✅ 输入框清空  
✅ 发送按钮禁用 (防止重复提交)  
✅ 控制台显示: `📤 Webview → Extension: { type: 'submit_task', ... }`  

#### 验证点:
- [ ] 消息时间戳正确
- [ ] 消息 ID 唯一

---

### 测试 4: 接收任务开始事件 ⭐⭐⭐⭐⭐

#### 前提:
Node API 成功提交任务并返回 `task_started` 消息

#### 预期结果:
✅ AI 占位消息出现 (左侧灰色气泡)  
✅ 工具栏显示 "AI 思考中..." 徽章 (蓝色闪烁)  
✅ 输入框禁用 (防止并发)  
✅ 步骤树初始为空  

#### 控制台日志:
```
📥 Extension → Webview: { type: 'task_started', payload: { task_id: '...', prompt: '...' } }
```

---

### 测试 5: 步骤追踪树 ⭐⭐⭐⭐⭐

#### 前提:
Backend 发送 `step_started` 和 `step_finished` 消息

#### 预期结果:
✅ 步骤依次显示:
```
执行步骤:
✅ 🔍 分析需求      12.3s
✅ 📋 制定计划      18.7s
⏳ ✍️ 编写代码      (运行中...)
⏸️ ⚡ 优化改进
⏸️ ✅ 测试验证
```

✅ 运行中的步骤高亮显示 (蓝色边框 + 背景)  
✅ 完成的步骤显示绿色背景  
✅ 每个步骤显示耗时  

#### 验证点:
- [ ] 步骤顺序正确 (analyze → plan → write → refine → test)
- [ ] 状态图标准确 (⏳/✅/❌/⏸️)
- [ ] 耗时计算正确 (completedAt - startedAt)

---

### 测试 6: 流式输出 ⭐⭐⭐⭐⭐

#### 前提:
Backend 发送 `stream_chunk` 消息

#### 预期结果:
✅ AI 回答逐字显示 (类似打字机效果)  
✅ 自动滚动到底部  
✅ 代码块正确渲染 (等宽字体 + 背景色)  
✅ 流畅无卡顿 (60 FPS)  

#### 性能指标:
- 每 chunk 延迟: <50ms
- 总流畅度: 60 FPS
- 内存占用稳定 (<150MB)

#### 示例输出:
```python
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
```

---

### 测试 7: 清空对话 ⭐⭐⭐

#### 操作步骤:
1. 进行几次对话
2. 点击工具栏的 "🗑️ 清空" 按钮

#### 预期结果:
✅ 所有消息消失  
✅ 输入框恢复可用  
✅ 工具栏徽章消失  
✅ Zustand store 重置  

#### 验证点:
- [ ] messages 数组为空
- [ ] currentTaskId 为 null
- [ ] isStreaming 为 false

---

### 测试 8: 停止任务 ⭐⭐⭐⭐

#### 操作步骤:
1. 提交任务后,等待步骤开始
2. 点击工具栏的 "⏹️ 停止" 按钮

#### 预期结果:
✅ 任务立即停止  
✅ 输入框恢复可用  
✅ 工具栏徽章消失  
✅ 控制台显示: `⏹️ 取消任务: { taskId: '...' }`  

#### 验证点:
- [ ] WebSocket 连接断开 (如果实现)
- [ ] Backend 收到取消请求

---

### 测试 9: 主题适配 ⭐⭐⭐⭐

#### 操作步骤:
1. 切换 VSCode 主题:
   - `Ctrl+K Ctrl+T` → 选择 "Dark+"
   - `Ctrl+K Ctrl+T` → 选择 "Light+"
   - `Ctrl+K Ctrl+T` → 选择 "High Contrast"

#### 预期结果:
✅ 背景色自动适配  
✅ 文字颜色自动适配  
✅ 按钮/输入框颜色跟随主题  
✅ 代码块背景色正确  

#### 验证点:
- [ ] 使用 CSS 变量 (`var(--vscode-*)`)
- [ ] Tailwind 配置正确映射
- [ ] 无硬编码颜色

---

### 测试 10: 错误处理 ⭐⭐⭐⭐

#### 场景 1: 后端未启动
**操作**: 不启动 Node API,直接提交任务  
**预期**: 
- ✅ 显示友好错误提示: "❌ 任务失败: 无法连接到后端"
- ✅ 输入框恢复可用

#### 场景 2: 网络超时
**操作**: 模拟慢网络 (开发者工具 Network 面板设置 Slow 3G)  
**预期**:
- ✅ 显示加载状态
- ✅ 超时后显示错误

#### 场景 3: 无效输入
**操作**: 输入空字符串或纯空格  
**预期**:
- ✅ 发送按钮禁用
- ✅ 不提交任务

---

## 🐛 常见问题排查

### 问题 1: Webview 显示空白

**症状**: 面板打开后完全空白

**排查步骤**:
1. 按 F12 打开开发者工具
2. 查看 Console 标签是否有错误
3. 查看 Network 标签是否有资源加载失败

**常见原因**:
- ❌ `webview-dist` 目录不存在
- ❌ 文件路径错误
- ❌ CSP 策略阻止脚本执行

**解决方案**:
```bash
# 重新构建
cd vscode-extension/webview
npm run build

# 确认文件存在
ls ../webview-dist/
```

---

### 问题 2: TypeScript 编译错误

**症状**: `npm run compile` 失败

**常见错误**:
```
Cannot find module '@/store/chatStore'
```

**解决方案**:
检查 `tsconfig.json` 中的 `paths` 配置:
```json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
```

---

### 问题 3: VSCode API 不可用

**症状**: 控制台显示 `acquireVsCodeApi is not defined`

**原因**: 在非 VSCode 环境中运行 (如浏览器)

**解决方案**: 
- ✅ 必须在 VSCode 扩展调试模式中测试
- ✅ 或使用 mock API (开发时)

---

### 问题 4: 消息不显示

**症状**: 提交任务后,AI 消息不出现

**排查步骤**:
1. 检查控制台是否有 `📥 Extension → Webview` 日志
2. 检查 Backend 是否发送消息
3. 检查 WebSocket 连接状态

**常见原因**:
- ❌ Backend 未启动
- ❌ WebSocket 连接失败
- ❌ 消息格式不匹配

**解决方案**:
```powershell
# 重启所有服务
.\start_all.ps1

# 检查 Node API 日志
# 查看是否有错误输出
```

---

## 📊 性能基准

### 构建性能
| 操作 | 预期时间 | 实际时间 |
|------|---------|---------|
| Vite 构建 | <3s | 1.04s ✅ |
| TypeScript 编译 | <5s | ? |
| 总计 | <8s | ? |

### 运行时性能
| 指标 | 目标值 | 实测值 |
|------|--------|--------|
| 首屏渲染 | <200ms | ? |
| HMR 更新 | <100ms | ? |
| 消息更新 | <50ms | ? |
| 内存占用 | <150MB | ? |

---

## ✅ 验收清单

### 功能验收
- [ ] React 组件正确渲染
- [ ] Zustand 状态管理正常
- [ ] VSCode API 通信正常
- [ ] Tailwind CSS 样式正确
- [ ] 构建产物输出到正确位置

### 性能验收
- [ ] 首屏渲染 <200ms
- [ ] HMR 更新 <100ms
- [ ] 内存占用 <150MB
- [ ] 无内存泄漏

### 代码质量
- [ ] TypeScript 零错误
- [ ] ESLint 零警告
- [ ] 组件职责清晰
- [ ] 注释完整

### 用户体验
- [ ] 界面美观
- [ ] 交互流畅
- [ ] 错误提示友好
- [ ] 主题适配完美

---

## 🎯 下一步规划

### 阶段 2.3: 高级组件 (下次)
- [ ] DiffViewer (代码差异对比)
- [ ] CodeBlock (语法高亮 - Prism.js)
- [ ] FileExplorer (文件树)
- [ ] Terminal (终端集成)

### 阶段 2.4: 性能优化
- [ ] 虚拟滚动 (react-window)
- [ ] 懒加载 (React.lazy)
- [ ] Service Worker (离线缓存)
- [ ] 代码分割 (Vite code splitting)

### 阶段 2.5: 用户体验
- [ ] 动画过渡 (Framer Motion)
- [ ] 快捷键支持
- [ ] 自定义主题
- [ ] 国际化 (i18n)

---

## 📝 测试报告模板

```markdown
# AlphaPilot v2.2 测试报告

**测试日期**: 2026-04-08  
**测试人员**: [你的名字]  
**VSCode 版本**: 1.114.0  
**操作系统**: Windows 25H2

## 测试结果汇总

| 测试项 | 状态 | 备注 |
|--------|------|------|
| 测试 1: 打开面板 | ✅/❌ | |
| 测试 2: 模型选择器 | ✅/❌ | |
| 测试 3: 提交任务 | ✅/❌ | |
| 测试 4: 任务开始事件 | ✅/❌ | |
| 测试 5: 步骤追踪树 | ✅/❌ | |
| 测试 6: 流式输出 | ✅/❌ | |
| 测试 7: 清空对话 | ✅/❌ | |
| 测试 8: 停止任务 | ✅/❌ | |
| 测试 9: 主题适配 | ✅/❌ | |
| 测试 10: 错误处理 | ✅/❌ | |

## 发现的问题

### 问题 1: [描述]
- **严重程度**: 高/中/低
- **复现步骤**: ...
- **预期行为**: ...
- **实际行为**: ...
- **截图**: ...

## 性能数据

- 首屏渲染: ___ ms
- 消息更新: ___ ms
- 内存占用: ___ MB

## 总结

[总体评价和改进建议]
```

---

## 🚀 立即行动

### 现在就开始测试!

1. **按 F5** 启动扩展调试
2. **按 Ctrl+Shift+R** 打开 React 面板
3. **输入任务** 并提交
4. **观察效果** 并记录问题

### 遇到问题?

- 📖 查看 [`REACT_WEBVIEW_GUIDE.md`](REACT_WEBVIEW_GUIDE.md) 完整文档
- 🐛 按 F12 打开开发者工具查看错误
- 💬 随时告诉我具体问题

---

**祝你测试顺利!** 🎉

*最后更新: 2026-04-08*  
*版本: v2.2.0*  
*守护者: AlphaPilot Team*
