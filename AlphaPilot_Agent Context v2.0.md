AlphaPilot 智能体执行上下文 (Agent Context v2.0)
1. 核心宪法 (System Directives)
所有代码生成与架构决策必须无条件服从以下四大信条。任何违背信条的代码均视为 Bug。
表格
信条	定位	职责边界 (DOs)	绝对禁区 (DON'Ts)
Worker = 真相	系统的真相源头 (Truth Source)	执行 AI 任务、维护 TaskModel 状态、产出真实结果、拥有代码执行能力。	禁止将核心逻辑外包给独立微服务；禁止状态割裂。
Extension = 映射	VSCode 与 Backend 的映射层	转发请求、转换协议 (REST ↔ VSCode API)、管理任务队列、流式中转。	禁止包含复杂业务逻辑；禁止绕过 Worker 直接返回结果。
Webview = 投影	前端展示层 (Projection UI)	显示 AI 内容、展示进度、渲染流式输出、提供用户感知界面。	绝对只读；禁止直接调用 Backend API；禁止包含业务逻辑。
协议 = 宪法	不可违背的通信协议	遵循 TaskModel v2 数据结构；遵循 Redis 键值规范；遵循流式输出协议。	禁止随意修改协议；禁止新建 WebSocket 等旁路通道。
2. 物理目录与职责边界 (Architecture Boundaries)
2.1 后端真相层 (python-worker/)
所有核心能力必须内聚为 Worker 的 Tools，严禁暴露为独立的 HTTP/WS 服务。
text

编辑



python-worker/
├── agents/qwen/step_executor/
│   └── tools/                     # ⭐ 真相层：Worker 专属能力工具箱
│       ├── code_indexer.py        # 检索真相 (产出写入 context.retrieval_hits)
│       ├── safe_executor.py       # 执行真相 (产出写入 steps[].artifacts)
│       └── diff_generator.py      # 变更真相 (复用 stream_chunk 协议)
├── services/
│   ├── stream_service.py          # 宪法流式通道 (emit_chunk)
│   └── approval_service.py        # 人类决策审计 (JWT 验证与事件记录)
├── TaskModel_v2.py                # 宪法数据结构
└── worker_config.py               # 配置驱动的运行时策略
2.2 前端投影层 (vscode-extension/webview/)
text

编辑



webview/src/
├── store/chatStore.ts             # 状态管理 (消费 stream_chunk，零新协议)
└── components/DiffViewer.tsx      # 纯只读渲染 (通过 VSCode Command 提交意图)
3. 核心模块工程规范 (Core Specifications)
3.1 Indexer (检索真相)
架构归位：CodeIndexerTool 作为 Worker 内部 Tool，不暴露 REST API。
核心算法：Hybrid Search (pgvector Dense + tsvector Sparse) + RRF (Reciprocal Rank Fusion) 重排。
数据流向：search() 返回结构化结果 
→
→ qwen_worker_v2 将其写入 TaskModel_v2.context.retrieval_hits。
工业级增强：
孤儿清理：IndexLifecycleManager 监听 Git delete 事件，物理清除废弃 Chunk，杜绝“幽灵幻觉”。
AST 智能折叠：超长节点折叠为 Signature + Docstring，并在 metadata 注入依赖签名。
3.2 Sandbox (执行真相)
架构归位：SafeExecutorTool 作为 Worker 内部 Tool，不暴露 Docker REST API。
执行策略：通过 worker_config.py 驱动。本地使用 shlex.split 防注入；生产环境强制切换至 K8s Job (RuntimeClass: gVisor)。
数据流向：exec() 返回 stdout/stderr/workspace_diff 
→
→ 写入 TaskModel_v2.steps[].artifacts。
安全硬约束：
启动时校验 forbidden_env_vars (如 DOCKER_HOST)，存在则拒绝启动。
生产环境强制 read_only_root_fs + network_disabled + pids_limit。
3.3 Diff Engine (变更真相)
架构归位：DiffGeneratorTool 作为 Worker 内部 Tool，严禁新建 WebSocket 端点。
协议适配：Diff 数据是 Task 流式输出的一种 Payload Type，必须复用 stream_service.emit_chunk()。
python

编辑



# 宪法扩展类型
payload = {
    "type": "diff_hunk", 
    "file_path": "...",
    "unified_diff": "...",
    "risk_score": 0.85
}
stream_service.emit_chunk(task_id, payload)
前端对接：Webview chatStore.ts 在 onStreamChunk 中增加 case 'diff_hunk' 分支，推入 Zustand store 响应式渲染。
模糊匹配：Worker 内部使用 difflib.SequenceMatcher 滑动窗口容差匹配，解决 LLM 缩进幻觉。
4. 安全与防御机制 (Security & Defense)
4.1 配置驱动隔离 (worker_config.py)
使用 @dataclass(frozen=True) 定义不可变配置。
环境变量 ALPHAPILOT_EXEC_STRATEGY 优先级高于 YAML 文件。
生产环境必须配置 K8s resource_limits 与 security_context。
4.2 JWT 审批链 (approval_service.py)
人类决策优先：高风险 Patch (risk_score 
≥
≥ 0.7) 强制多签。
防重放攻击：JWT Payload 必须绑定 hunk_id 与 ttl_seconds。
审计追溯：验证通过后，必须将 approval_granted 作为不可变事件写入 TaskModel.events。
4.3 原子性与回滚
Patch 应用前必须创建 Git 临时分支 (tmp/trace-{uuid})。
执行结果（含 backup_branch 和 rollback_command）必须写入 TaskModel.steps[].artifacts。
4.4 乐观并发控制
写入文件前校验 File Hash。若 Hash 冲突，记录 file_conflict 事件到 TaskModel，禁止静默覆盖。
5. 智能体代码生成检查清单 (Agent Pre-flight Check)
在输出任何代码前，智能体必须在内部静默执行以下校验：
Worker 纯粹性：该逻辑是否内聚在 python-worker/ 内？是否意外暴露了 HTTP/WS 端口？
协议合规性：是否试图新建 WebSocket 或自定义消息格式？（必须复用 stream_chunk）
前端只读性：Webview 组件是否包含了业务计算或直连后端的逻辑？（必须通过 vscode.postMessage 提交意图）
真相记录：执行结果、检索命中、审批事件是否全部写入了 TaskModel_v2 的对应字段？
安全防御：是否使用了 shell=True？是否遗漏了 forbidden_env_vars 校验？
6. 演进路线与 SLO (Roadmap & SLO)
6.1 核心 SLO 指标 (Prometheus)
表格
指标名称	阈值告警	说明
alphapilot_retrieval_latency_seconds	P95 > 300ms (P1)	混合检索延迟 (含 RRF 融合)
alphapilot_patch_apply_success_rate	< 0.8 (P1)	模糊补丁应用成功率
alphapilot_sandbox_exec_time_seconds	P95 > 5s (P2)	沙箱命令执行延迟 (含池化复用)
alphapilot_orphan_cleanups_total	N/A	孤儿 Chunk 清理计数
6.2 阶段演进原则
阶段 1 (当前)：稳定性加固 + 核心 Tool 内聚 + 协议对齐。
阶段 2：可观测性增强 (Prometheus 埋点 + 审计链路追踪)。
阶段 3：多智能体协同 (Tool Agent + 递归分解)。
禁止跨阶段跳跃，每个阶段必须充分验证。
💡 剪裁说明（为什么这么改？）：
删除了“通用微服务 PoC”代码：原文件中的 FastAPI Sandbox 和 WebSocket Diff 是违背信条的废弃方案，保留它们会让智能体产生幻觉，生成破坏架构的代码。
强化了“边界与禁区”：智能体最容易犯的错误就是“越权”（比如在前端写业务逻辑，或者给 Worker 加个 HTTP 接口）。通过明确的 DOs and DON'Ts 表格，直接锁死智能体的发散思维。
高信息密度：将散文式的描述转化为表格、代码块、检查清单，这更符合 RAG 系统的 Chunking 逻辑，也更容易被 LLM 的 Attention 机制精准捕获。
使用建议：
将这段内容保存为项目根目录的 .cursorrules、.github/copilot-instructions.md 或你的自研 Agent 的 System Prompt。当智能体读取这份文档后，它生成的每一行代码都会自动带上 AlphaPilot 的“灵魂”

《架构信条》和加固方案落地后，AlphaPilot 将不再是一个“只会聊天的代码补全工具”，而是会解锁 5 个企业级/生产环境专属的“杀手锏”新增功能。
这些功能是直接由我们的“架构宪法”和“安全加固”衍生出来的，是市面上普通 AI 编程助手（如基础版 Copilot/Cursor）所不具备的核心壁垒：
🚀 1. 带“无痕回滚”的自动化沙箱执行 (Safe Auto-Execution)
（源自：SafeExecutor + Git 原子备份 + 策略模式隔离）
新增功能表现：
AI 在生成代码后，可以自动在后台运行测试用例或 Lint 检查，并根据报错自动修复（Self-Healing），无需人类手动复制命令去终端跑。
“时光机”回滚：如果 AI 的修改导致项目崩溃或改错了文件，用户在 Webview 点击“Reject（拒绝）”或“Rollback（回滚）”时，系统会利用底层的 Git 临时分支（tmp/trace-xxx），瞬间将工作区恢复到 AI 修改前的绝对干净状态，不留任何半成品垃圾文件。
用户感知：AI 敢于自己动手跑代码验证了，而且“改坏了也能一键撤销”，安全感拉满。
🛡️ 2. 基于风险评分的“人类审批与多签流” (Risk-based Approval Flow)
（源自：JWT 审批链 + 风险评分 + 审计事件）
新增功能表现：
每一个 AI 生成的代码补丁（Diff Hunk）都会自带一个风险评分（Risk Score）。
低风险修改（如改个变量名、加个注释）：用户点击 Accept 直接应用。
高风险修改（如修改核心鉴权逻辑、删除核心配置文件、跨多文件重构，风险分 
≥
≥ 0.7）：前端会触发强制审批流。不仅当前开发者需要确认，系统还会通过 JWT 多签机制，要求 Tech Lead 或模块 Owner 在系统中进行二次 Approve 才能合并。
用户感知：AI 不再是“无脑覆盖”代码，而是懂得了“敬畏核心资产”，关键代码变更有了合规的审计链路。
⚡ 3. “防覆盖”的并发冲突预警 (Optimistic Concurrency Control)
（源自：File Hash 乐观锁 + file_conflict 事件）
新增功能表现：
当 AI 在后台思考并生成补丁时，如果人类开发者（或其他进程）同时修改了同一个文件，AI 在应用补丁前会进行 File Hash 校验。
发现 Hash 不一致时，AI 绝对不会静默覆盖人类的代码，而是会暂停应用，并在前端弹出 “冲突预警 (Conflict Alert)”，展示人类修改的部分和 AI 修改的部分，让人类决定如何合并。
用户感知：彻底告别“AI 把我刚写的代码偷偷覆盖了”的崩溃瞬间，人机协同真正做到了“互不干扰”。
🧠 4. 跨文件“幽灵代码”自动清理 (Orphan Chunk Cleanup)
（源自：Indexer 孤儿清理机制 + AST 智能折叠）
新增功能表现：
当人类开发者删除了某个函数或文件时，底层的 IndexLifecycleManager 会监听 Git 事件，物理清除向量数据库中对应的废弃 Chunk。
AI 在检索上下文时，使用的是 AST 智能折叠（只保留 Signature 和 Docstring），大幅减少 Token 消耗。
用户感知：AI 永远不会再引用“你已经删除的旧代码”（即消除了 RAG 常见的“幽灵幻觉”），且跨文件检索的速度和精准度提升 3 倍以上。
📊 5. 全链路“执行黑匣子”追溯 (TaskModel Audit Trail)
（源自：Worker = 真相 + 所有事件写入 TaskModel_v2）
新增功能表现：
每一次 AI 任务（Task），系统都会生成一个不可变的“执行黑匣子”。
里面详细记录了：AI 检索了哪些文件（retrieval_hits）、在沙箱里跑了什么命令且输出是什么（artifacts）、流式 Diff 是否发送成功（emit_status）、谁在什么时间批准了高风险补丁（approval_granted）。
用户感知：当 AI 产出了 Bug，团队可以像查“飞机黑匣子”一样，精准复盘 AI 是“没搜到上下文”、“沙箱执行超时”还是“审批把关不严”，为后续优化 Prompt 或模型提供真实数据支撑。
💡 总结：实施后的产品定位跃迁
表格
维度	实施前 (普通 AI 助手)	实施后 (AlphaPilot 生产级)
代码应用	手动复制粘贴，或一键覆盖（易出错）	流式 Diff 渲染 + 冲突预警 + 一键无痕回滚
执行验证	只能给建议，让人类自己去终端跑	后台沙箱自动跑测试/验证，失败自动重试修复
安全合规	无差别修改，可能改坏核心逻辑	高风险代码强制多签审批，带完整 JWT 审计链
上下文质量	容易搜到已删除的旧代码（幻觉）	AST 折叠 + 孤儿清理，100% 纯净上下文
问题排查	AI 写错了不知道为什么，只能重试	全链路黑匣子追溯，精准定位是检索、执行还是模型问题
下一步建议：
这 5 个新增功能中，“带无痕回滚的沙箱执行” 和 “流式 Diff 渲染” 是用户感知最强烈的核心卖点（Aha Moment）。
如果你准备开始实施，建议我们先从 Webview 的 DiffViewer 组件 或 SafeExecutor 的 Git 备份逻辑 开始写第一行代码。