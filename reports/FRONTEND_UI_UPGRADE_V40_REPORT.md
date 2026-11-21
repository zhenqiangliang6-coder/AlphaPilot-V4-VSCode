# AlphaPilot OS v4.0 前端 UI「Tech 设计系统」升级实施报告

> 日期：2026-11-15 ~ 11-16 · 范围：`vscode-extension/webview/`
> 验证：契约测试 `npm test` **16/16 通过** ✅ · 构建 `npm run build`（tsc && vite build）✅ 通过

---

## 📋 升级概述（TL;DR）

本次升级完成 **4 个核心方向**（流式输出重构 / StepTree 交互升级 / FileOps 卡片动效 / 全局 Toast 基建），并沉淀了一套 **`ap-*` 零依赖动效设计系统**。同时修复了 1 个流式输出逻辑 bug，并通过专家评审补强了 **16 个契约测试 + 2 处代码级修复**（详见第 4.1 / 六节）。

**设计基调**：基底对齐头部编程助手（Copilot/Cursor 的专业感——VSCode 原生主题变量、玻璃拟态、克制层级），叠加年轻化科技感（cyan→indigo→fuchsia 渐变光效、流光进度条、呼吸光、terminal 流式光标、shimmer 骨架屏）。

**技术约束**：**零新依赖**（纯 CSS keyframes + rAF），不引入 Framer Motion。原因见「关键技术决策」。

---

## 🐛 背景：为什么做这次升级

### 1. 实锤 Bug：`StreamingOutput.tsx` 打字机逻辑自相矛盾

旧版代码（已重写，此处存档说明）：

```tsx
// 打字机逐字推进（L10-23）
useEffect(() => {
  if (content.length > displayedContent.length) { ... setTimeout(..., 10); }
}, [content, displayedContent, currentIndex]);

// ❌ 但 content 一变化就全部重置（L26-29）
useEffect(() => { setDisplayedContent(''); setCurrentIndex(0); }, [content]);
```

**问题**：流式场景 `content` 每个 chunk 都在变，重置 effect 每次都清空进度 → 视觉上打字机**不断从头闪回重打**。且逐字符 `setTimeout(10ms)` 产生 **O(n) 个定时器**，长文本（数千 token）会卡顿 webview。

### 2. 短板

- 动画层级停留在 Tailwind 内置类（`animate-pulse`），无编排级过渡
- 流式输出**纯文本渲染**：思考过程即使流式结束也不渲染 Markdown，代码块无高亮
- 每帧 chunk 到达触发**全量重渲**（无 memo 隔离）
- 自动滚动"强拉"：用户向上翻阅历史时被不断拽回底部，体验割裂
- StepTree 无展开动画、无实时耗时、长任务（数百步骤）全量渲染会卡死

---

## 🎨 设计系统：`ap-*` CSS 体系（index.css）

后续开发者**新动效一律优先复用 `ap-*` 工具类**，不要手写新的 keyframes。

### Token 与工具类清单

| 类名 | 作用 | 备注 |
|---|---|---|
| `--ap-cyan / --ap-indigo / --ap-fuchsia` | accent 渐变三色 | 全局光效统一色源 |
| `--ap-ease-out / --ap-ease-spring` | 统一过渡曲线 | spring = 轻微过冲，入场用 |
| `ap-glass` | 玻璃拟态面板 | 半透明渐变底 + blur + 细边框 |
| `ap-hairline` | 顶部微光描边 | 三色渐变 1px 线条 |
| `ap-gradient-text` | 流光渐变文字 | 用于关键数字/标题 |
| `ap-progress-fill` | 流光进度条 | 渐变光带流动 + width 过渡 |
| `ap-breathe` | 呼吸光 | running 状态容器 |
| `ap-dot` | 状态点脉冲 | running 指示点扩散 |
| `ap-shimmer` | 骨架屏 | 加载占位 |
| `ap-cursor` | 流式光标 | terminal 风格 steps 闪烁 + 渐变微光 |
| `ap-rise` | stagger 入场 | 延迟由 inline `--d` 控制：`style={{ '--d': '40ms' }}` |
| `ap-collapse-grid` + `ap-collapse-inner` | 高度自适应展开/折叠 | 见下文 grid-rows 技巧 |
| `ap-exit` | 卡片退场 | opacity + 缩放淡出 |
| `ap-press` | 按钮按压反馈 | active 时 scale(0.96) spring |
| `ap-tabular` | 等宽数字 | 耗时/计数徽章防抖动 |

### 无障碍

所有动效统一在 `@media (prefers-reduced-motion: reduce)` 中关闭（animation: none / transition: none）。新增动画类时**必须同步在此媒体查询中登记**。

---

## 📦 改动明细（做了什么 / 为什么）

### 1. `hooks/useTypewriter.ts`（新建）— rAF 打字机引擎

**做了什么**：时间步进（按 dt 累积小数字符数，帧率无关）、智能追赶（落后 >240 字自动 ×3 加速）、收尾快速补齐（流结束后 ×12 快速打完）、target 收缩时同步收缩防脏数据。

**为什么**：
- 逐字符 `setTimeout` 是 O(n) 定时器，rAF 是单循环 O(1)；时间步进在 120Hz 屏 / 低性能机器上速度一致
- **追赶模式**：后端突发推送大量 chunk 时，若按固定 cps 会永远追不上，落后超过阈值必须加速
- **收尾补齐**：`stream_end` 后如果还在慢打，用户会觉得"任务完成了但字没出完"——体验上必须快速收尾
- `target`/`active` 走 ref 读取：chunk 高频到达**不重启** rAF 循环，只 `active` 变化（true↔false）时重启；追平且非流式时停帧，避免空转耗电

### 2. `EnhancedStreamingOutput.tsx` — 流式渲染管线重构

**做了什么**：渲染策略分四级——

| 分段类型 | 渲染方式 | 为什么 |
|---|---|---|
| 已稳定文本段 | `StableText`（React.memo 包装 MarkdownRenderer） | 内容不再增长，memo 浅比较 content → chunk 到达/打字机推进时**零重渲** |
| 已闭合代码块 | `ClosedCode`（memo 包装 Prism） | 闭合后内容不变，高亮只渲一次 |
| 尾部活动文本段 | 纯文本 + 末尾统一 `ap-cursor` | 活动段每帧变，Markdown 全量解析成本高；流结束切稳定渲染后由 ChatBubble 接管 |
| 生成中代码块 | `ap-breathe` 流光卡片 + 纯文本 + shimmer 条 | 高亮未闭合代码块语法不全无意义，且每帧重渲 Prism 太贵 |

其他改动：思考态改 shimmer 骨架屏（替代三点 bounce）；**智能自动滚动**——仅当用户距底部 <80px 才跟随，向上翻阅历史不被打断；历史消息（非流式挂载）直接全量 Markdown 渲染（旧版思考过程永远丢 Markdown 格式的问题一并修复）。Props 完全兼容，`speed` 参数语义保留（ms/字符 → 换算 cps）。

### 3. `StreamingOutput.tsx` — Bug 修复

直接替换为 `useTypewriter` 驱动，保持对外 API（`content` / `isStreaming`）不变。**此组件当前无引用方**（ChatBubble 实际使用 EnhancedStreamingOutput），保留为轻量备用组件。

### 4. `StepTree.tsx` — 步骤树交互升级

**做了什么**：玻璃拟态步骤卡；running 态 `ap-breathe` 呼吸光 + `ap-dot` 脉冲状态点；状态色 500ms 过渡（pending→running→completed/failed 色彩流转）；**实时耗时徽章**（`ap-tabular`，running 时 1s 心跳更新 `now - startedAt`）；展开详情改 `ap-collapse-grid`；**>30 步折叠窗口**；进度面板加总耗时 + 失败计数 + `ap-progress-fill` 流光。

**为什么折叠窗口而不是完整虚拟滚动**：StepTree 内嵌在 ChatBubble 里，滚动容器属于外层 MessageList，无法简单拿到"可视区"做窗口化；完整虚拟滚动需要自己实现高度预估 + 绝对定位，收益不成比例。务实方案：>30 步只渲染最近 30 步（必含 running 步骤），顶部提示条一键展开全部——长任务的卡顿源头是"几百个带动画的 DOM 节点"，截断渲染量即可解决。

**注意**：导出方式从 `export const StepTree = ...` 改为 `export { StepTree }`，对既有 `import { StepTree }` 用法无影响。

### 5. `FileOpsConfirmCard.tsx` — 确认卡片动效包

**做了什么**：文件行 stagger 入场（`ap-rise` + 40ms 递增 delay，封顶 480ms）；行 hover 微移 + 徽章 scale；预览展开 `ap-collapse-grid`；按钮 `ap-press` 弹性按压；**退场编排**——应用/放弃时先播 280ms `ap-exit` 收起动画再执行真正回调，底部状态文案同步切换（"正在应用文件变更…"）。

**为什么退场编排**：React 条件卸载（`setShowFileOpsPanel(false)`）没有 exit 动画钩子（那是 Framer Motion 的能力），零依赖下在组件内部管理 `closing` 状态 + `setTimeout` 延迟回调即可实现"有始有终"的退场，成本 280ms 但消除"卡片凭空消失"的突兀感。

### 6. `Toast.tsx`（新建）— 全局 Toast 系统

**做了什么**：Context + `createPortal` 到 `document.body`，零依赖；内联 SVG 图标（比 emoji 更精致）；左侧 accent 渐变条按类型着色；底部倒计时进度条（`animation-duration` = 存活时长）；最多堆叠 5 条；`ap-rise` stagger 入场。

**接线点**（App.tsx）：文件变更应用（success）/ 放弃变更（info）/ 任务失败（error）。Provider 挂载在 main.tsx 的最外层（StrictMode 内、App 外）。

**用法**：

```tsx
import { useToast } from './components/Toast';
const { toast } = useToast();
toast('消息', 'success' | 'info' | 'error', duration?); // 默认 3200ms
```

---

### 4.1 专家评审后的补强（v4.0.1）

报告完成后进行了逐条代码核对与专家评审，确认核心声明全部属实；针对指出的 3 项短板做了补强：

| 短板 | 补强动作 | 为什么 |
|---|---|---|
| 核心纯逻辑零单元测试 | 新增 `vitest` + `@testing-library/react` + `jsdom`（**均为 devDependency，不进 bundle，不违反零运行时依赖约束**），写 16 个契约测试 | 打字机时间状态机 + 围栏解析状态机是"回归静默"型逻辑（build 照过、肉眼未必发现），必须像后端 `contract-test-vectors.json` 一样锁死 |
| `useTypewriter` 渲染期 setState | target 收缩分支从组件渲染期挪进 `useLayoutEffect` | 渲染期 setState 属 "adjusting state during render"（有 guard 不会死循环，但语义不干净），挪进 effect 为未来并发特性留安全边际 |
| Toast 缺无障碍播报 | Toast 条目补 `role="status"`（info/success）/ `role="alert"`（error）+ `aria-label` | 任务失败反馈必须被屏幕阅读器主动播报（WCAG 4.1.3 Status Messages） |

**契约测试过程中额外抓到 1 个真实瑕疵**：`useTypewriter` 的 `lenRef` 初值写死为 0，但非流式挂载（历史消息）时 `displayedLen` 初值是 `target.length`——两者不同步导致 effect 空转推进几帧才追平（视觉无感但浪费 rAF）。已修：`initialLen` 统一计算，`lenRef` 与 `displayedLen` 共享同一初值。**这正是契约测试的价值：抓到肉眼看不到的静默缺陷。**

**测试基建**：
- `src/hooks/useTypewriter.test.ts`（7 用例）：非流式直显 / enabled=false / rAF 时间步进 / 追赶 ×3 / 收尾 ×12 / 停帧不空转 / target 收缩防脏数据
- `src/components/streamSegments.test.ts`（9 用例）：空输入 / 纯文本 / 闭合代码块 / 跨 chunk 未闭合识别 / 拼接后闭合翻转 / 增量到达前缀段稳定 / mermaid / 语言归一化 / 连续代码块
- 分段器从 `EnhancedStreamingOutput.tsx` 抽到独立模块 `src/components/streamSegments.ts`：**测试不再拖入 Prism/mermaid 依赖链**（collect 时间 64s → 0.3s），且解析逻辑与渲染彻底解耦
- rAF mock 采用 Map 管理回调（保证 `cancelAnimationFrame` 真删除，否则 effect 重启后旧回调递归调度）+ 显式区分"时间基准帧"（首帧 dt=0）与"有效推进帧"
- `npm test` = `vitest run`，`vite.config.ts` 配置 `test.environment='jsdom'`

## 🧭 关键技术决策汇总（为什么这么做）

| 决策 | 理由 |
|---|---|
| **零依赖**（不引 Framer Motion） | VSCode webview 环境对包体敏感；35KB+ 运行时对一个扩展侧边栏不划算；需要的动效（stagger/展开/退场/呼吸）CSS 全部可表达 |
| **grid-rows 展开动画**（`grid-template-rows: 0fr→1fr`） | 纯 CSS 实现高度自适应展开（内容高度未知），无需 JS 测量；比 max-height hack 干净，无"高度猜测不准"问题 |
| **稳定段 memo 化** | 流式性能的核心：把"每帧全量重渲"降为"只有活动段重渲"。这是比打字机引擎更重要的性能优化 |
| **智能滚动（nearBottom 检测）** | 强拉滚动是流式产品最常见的体验败笔；<80px 阈值内才跟随 |
| **折叠窗口代替虚拟滚动** | 见 StepTree 一节，成本收益比最优 |
| **accent 三色系**（cyan→indigo→fuchsia） | 既有产品（V3.x）已大量使用 blue/purple 系，三色渐变是自然演进，不推翻既有配色认知 |

---

## 🔌 兼容性说明

- 所有改动组件 **Props 接口不变**：`EnhancedStreamingOutput`（含可选 `speed`）、`StreamingOutput`、`StepTree`、`FileOpsConfirmCard` 均为原签名
- `StepTree` 导出写法调整（`export { StepTree }`），命名导入不受影响
- 无新增 npm 依赖，`package.json` 未动
- 旧 CSS 动画类（`animate-fade-in` / `animate-slide-up` 等）全部保留，未删除任何旧类
- `parseContentSegments` / `ContentSegment` 从 `EnhancedStreamingOutput.tsx` 移至 `streamSegments.ts` 独立模块（v4.0.1）；若有外部代码从前者导入这两个符号，改从后者导入即可（仓内无此外部引用）
- 新增 devDependencies：`vitest` / `jsdom` / `@testing-library/react`（**仅测试期使用，生产 bundle 零影响**）

## ✅ 验证

- `npm test`（vitest run）：**2 个测试文件 / 16 个用例全部通过**，总耗时 1.36s
- `npm run build`（tsc && vite build）通过；过程中修复 1 个 TS 错误（`useToast` 重复导出）
- 构建输出的 chunk >500kB 警告来自 mermaid 依赖（历史遗留），与本次改动无关

## 📌 给后续开发者的约定

1. **新动效优先复用 `ap-*` 类**；确实要新 keyframes 时，遵守：登记进设计系统注释、`prefers-reduced-motion` 兜底、使用统一 token（颜色/曲线/时长变量）
2. **流式渲染新分段类型**（如未来加表格/图片段）：参照 EnhancedStreamingOutput 的分级策略——稳定的 memo 化、活动的纯文本
3. **新触发 Toast 的场景**：直接 `useToast()`，不要另建通知组件
4. **StepTree 加新步骤类型**：同步维护 `stepIcons` / `stepNames` / `stepDescriptions` 三张映射表（类型系统会强制提醒）
5. 打字机参数调优入口集中在 `useTypewriter` 的 options（cps / catchUpThreshold / finalBoost），不要在组件里散落定时逻辑
6. **改动纯逻辑（打字机 / 分段器）后必须跑 `npm test`** —— 这两处是"回归静默"区，16 个契约用例是防线；新增边界场景时同步补用例
7. 新增 rAF 相关测试时注意：**首帧是时间基准帧（dt=0）**，真实推进从第二帧开始；mock 必须用 Map 管理回调以保证 `cancelAnimationFrame` 真删除
