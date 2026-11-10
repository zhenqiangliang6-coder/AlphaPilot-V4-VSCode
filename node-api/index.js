// node-api/index.js
// ---------------------------------------------------------
// AlphaPilot OS v3.0 Node API Server
// 整合了 HTTP 服务、WebSocket 通信以及 FileOps Handler
// ---------------------------------------------------------

require("dotenv").config();
const path = require('path');
require("dotenv").config({ path: path.resolve(__dirname, '../python_worker/.env') });
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const os = require('os');
const crypto = require('crypto');
const { v4: uuidv4 } = require("uuid");
const { Redis } = require("@upstash/redis");
const {
    PROTOCOL_VERSION,
    TaskProtocolError,
    TaskContextValidationError,
    normalizeTaskSubmission,
    buildOrExtractTaskContext,
    computeContextHash,
} = require('./taskProtocol');

const {
    ProjectStrategyResolver,
    ProjectStrategyAuthorizer,
    ConfirmationRequiredError,
    AuthorizationDeniedError,
} = require('./projectStrategy');

// =========================
// 1. Import FileOps Handler
// =========================
const { FileOpsHandler } = require('./fileOpsHandler');

// =========================
// ⭐ 2. Import Memory Service (v3.1 新增)
// =========================
const memoryService = require('./services/memoryService');

console.log('✅ Memory Service 已加载');

// =========================
// ⭐ Phase 2.4: Import Confirmation Manager (P0-4)
// =========================
const { ConfirmationManager } = require('./confirmationManager');
const confirmationManager = new ConfirmationManager();

const pendingSubmissions = new Map();

console.log('✅ Confirmation Manager 已加载');

// ⭐ Phase 2.4: Import Traffic Monitor
// =========================
const { TrafficMonitor } = require('./trafficMonitor');
const trafficMonitor = new TrafficMonitor();

console.log('✅ Traffic Monitor 已加载');

// =========================
// 2. 启动 Express & Socket.io 服务器
// =========================
const app = express();
const server = http.createServer(app);

app.use(cors({ origin: '*', methods: ['GET', 'POST', 'PUT', 'DELETE'] }));
app.use(express.json({ limit: '10mb' }));

// =========================
// 3. 初始化双云 Redis（v2.8 架构）
// =========================

// Upstash Redis（国际模型：Qwen/OpenAI/Claude/Gemini）
const redisUpstash = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL,
  token: process.env.UPSTASH_REDIS_REST_TOKEN,
});

const REDIS_TYPE = (process.env.REDIS_TYPE || 'auto').toLowerCase();
const localRedisModels = new Set(
    (process.env.LOCAL_REDIS_MODELS || '')
        .split(',')
        .map((model) => model.trim().toLowerCase())
        .filter(Boolean)
);
let redisLocal = null;

// 阿里云 Tair Redis（国内模型：DeepSeek/Doubao）
// ⚠️ 注意：Node.js 的 @upstash/redis 只支持 Upstash，需要使用 ioredis 连接阿里云 Tair
let redisTair = null;

try {
    const IORedis = require('ioredis');

    // ⭐ 始终创建本地 Redis 作为后备（Upstash 限流时自动降级用）
    redisLocal = new IORedis({
        host: process.env.REDIS_HOST || '127.0.0.1',
        port: parseInt(process.env.REDIS_PORT || '6379'),
        password: process.env.REDIS_PASSWORD || undefined,
        maxRetriesPerRequest: 3,
        lazyConnect: true,
    });
    if (REDIS_TYPE === 'local' || localRedisModels.size > 0) {
        console.log('🐳 本地 Docker Redis 已配置（主用）');
    } else {
        console.log('🐳 本地 Docker Redis 已就绪（降级后备）');
    }
    
    const tairHost = process.env.TAIR_HOST;
    const tairPort = parseInt(process.env.TAIR_PORT || '6379');
    const tairPassword = process.env.TAIR_PASSWORD;
    const tairTLS = process.env.TAIR_TLS === 'true';
    
    if (tairHost && tairPassword) {
        redisTair = new IORedis({
            host: tairHost,
            port: tairPort,
            password: tairPassword,
            tls: tairTLS ? {} : undefined,  // 如果启用 TLS
            maxRetriesPerRequest: 3,
            lazyConnect: true,  // 延迟连接，按需使用
        });
        
        console.log('✅ 阿里云 Tair Redis 已配置（国内模型）');
    } else {
        console.log('⚠️  阿里云 Tair Redis 未配置，国内模型将 fallback 到 Upstash');
    }
} catch (err) {
    console.log('⚠️  加载 ioredis 失败，阿里云 Tair 不可用:', err.message);
    console.log('💡 请运行: npm install ioredis');
}

// ⭐ 自动降级包装器：Upstash 限流时自动切换到本地 Redis
// 确保 Node API 与 Python Worker 使用同一个 Redis 实例
function createAutoFallbackRedis(upstashClient, getFallbackClient) {
    let degraded = false;
    let fallbackClient = null;

    return new Proxy(upstashClient, {
        get(target, prop, receiver) {
            // 内部属性直接访问
            if (typeof prop === 'symbol' || prop.startsWith('_')) {
                return Reflect.get(target, prop, receiver);
            }

            const originalValue = Reflect.get(target, prop, receiver);

            // 非函数属性直接返回
            if (typeof originalValue !== 'function') {
                return originalValue;
            }

            // 包装函数调用，捕获限流错误后降级
            return function (...args) {
                if (degraded && fallbackClient) {
                    return fallbackClient[prop](...args);
                }

                try {
                    const result = originalValue.apply(target, args);
                    // 处理 Promise（@upstash/redis 返回 Promise）
                    if (result && typeof result.then === 'function') {
                        return result.catch((err) => {
                            const msg = (err.message || String(err)).toLowerCase();
                            if (msg.includes('max requests limit') || msg.includes('rate limit')) {
                                if (!degraded) {
                                    console.log(`\n⚠️  Upstash Redis 限流，Node API 自动降级到本地 Redis (localhost:6379)`);
                                    console.log(`   原因: ${err.message}`);
                                    fallbackClient = getFallbackClient();
                                    degraded = true;
                                }
                                return fallbackClient[prop](...args);
                            }
                            throw err;
                        });
                    }
                    return result;
                } catch (err) {
                    const msg = (err.message || String(err)).toLowerCase();
                    if (msg.includes('max requests limit') || msg.includes('rate limit')) {
                        if (!degraded) {
                            console.log(`\n⚠️  Upstash Redis 限流，Node API 自动降级到本地 Redis (localhost:6379)`);
                            console.log(`   原因: ${err.message}`);
                            fallbackClient = getFallbackClient();
                            degraded = true;
                        }
                        return fallbackClient[prop](...args);
                    }
                    throw err;
                }
            };
        }
    });
}

// ⭐ 用自动降级包装器包裹 Upstash 客户端
const redisUpstashSafe = createAutoFallbackRedis(redisUpstash, () => {
    if (!redisLocal) {
        throw new Error('本地 Redis 不可用，无法降级。请确保 Docker Redis 已启动 (localhost:6379)');
    }
    return redisLocal;
});

// 智能路由函数：根据模型选择 Redis 实例
function getRedisClient(model, taskType) {
    const modelPrefix = (taskType || model).split('_')[0].split('-')[0].toLowerCase();

    if (REDIS_TYPE === 'local' || (REDIS_TYPE === 'auto' && localRedisModels.has(modelPrefix))) {
        if (!redisLocal) {
            throw new Error('本地 Redis 未配置；请检查 REDIS_HOST 和 REDIS_PORT');
        }
        return redisLocal;
    }

    if (REDIS_TYPE === 'upstash') return redisUpstashSafe;
    if (REDIS_TYPE === 'tair') return redisTair || redisUpstashSafe;
    
    // 国内模型列表
    const domesticModels = ['deepseek', 'doubao', 'maas'];
    
    if (domesticModels.includes(modelPrefix) && redisTair) {
        return redisTair;
    }
    
    // ⭐ auto 模式下优先本地 Redis（如果可用），不依赖 Upstash
    if (REDIS_TYPE === 'auto' && redisLocal) {
        return redisLocal;
    }
    // 默认使用 Upstash（包括 Qwen）—— 带自动降级保护
    return redisUpstashSafe;
}

// 为了向后兼容，保留 redis 变量（指向带降级保护的 Upstash）
const redis = redisUpstashSafe;

// =========================
// 4. 初始化 FileOps Handler
// =========================
let workspaceRoot = process.env.WORKSPACE_ROOT || null;  // ⭐ 允许初始为 null
const fileOpsHandler = new FileOpsHandler(workspaceRoot);  // ⭐ 允许初始为 null

if (!workspaceRoot) {
    console.log('   ⚠️  WORKSPACE_ROOT 未配置，等待 VSCode 扩展设置工作区...');
}

// ⭐ 智能工作区检测：若仍为空，尝试从任务中自动学习
function autoSetWorkspaceIfNeeded(workspacePath) {
    if (!workspaceRoot && workspacePath) {
        workspaceRoot = workspacePath;
        fileOpsHandler.setWorkspace(workspacePath);
        console.log(`   🔍 自动检测工作区: ${workspacePath}`);
    }
}

// =========================
// ⭐ R6: Import Authorization Verifier (最小安全契约 v1.0)
// =========================
const { AuthorizationVerifier } = require('./authorizationVerifier');
const authorizationVerifier = new AuthorizationVerifier({
    primaryRedis: redisUpstashSafe,
    localRedis: redisLocal,
    tairRedis: redisTair,
});

console.log('✅ Authorization Verifier (R6) 已加载');

// =========================
// 5. WebSocket 连接管理
// =========================
const taskSubscriptions = new Map(); // { task_id => Set<socket_id> }
const completedTasks = new Set();    // P1：已终态的任务 ID，用于拒绝迟到的产物事件
const streamContentCache = new Map(); // P2：缓存流式内容用于完整性校验 { task_id => accumulated_text }
const io = new Server(server, { cors: { origin: "*", methods: ["GET", "POST"] } });

io.on('connection', (socket) => {
    console.log('[Node API] Webview 已连接:', socket.id);
    
    socket.on("subscribe_task", (taskId) => {
        console.log(`📻 客户端订阅任务结果：${taskId}`);
        if (!taskSubscriptions.has(taskId)) {
            taskSubscriptions.set(taskId, new Set());
        }
        taskSubscriptions.get(taskId).add(socket.id);
        socket.emit("subscribed", { task_id: taskId });
    });

    socket.on("unsubscribe_task", (taskId) => {
        console.log(`📴 客户端取消订阅任务结果：${taskId}`);
        if (taskSubscriptions.has(taskId)) {
            taskSubscriptions.get(taskId).delete(socket.id);
            if (taskSubscriptions.get(taskId).size === 0) {
                taskSubscriptions.delete(taskId);
            }
        }
    });

    socket.on('disconnect', () => {
        console.log('[Node API] Webview 断开连接:', socket.id);
        for (const [taskId, sockets] of taskSubscriptions.entries()) {
            sockets.delete(socket.id);
            if (sockets.size === 0) {
                taskSubscriptions.delete(taskId);
            }
        }
    });
});

// =========================
// 6. 路由：任务提交（推送到 Upstash Redis）
// =========================
app.post('/task/submit', async (req, res) => {
    try {
        console.log("\n📥 收到前端提交任务：");
        console.log(JSON.stringify(req.body, null, 2));

        const submission = normalizeTaskSubmission(req.body, uuidv4);
        let { type, payload, source, meta } = submission;
        const task_id = uuidv4();
        const conversation_id = resolveConversationId(req.body, meta, payload.workspace_path);

        const collaborationMode = payload.collaboration_mode || "automatic";
        const supportedCollaborationModes = new Set([
            "automatic", "architect", "teacher", "pair_programmer", "engineer",
            "reviewer", "file_manager", "creative", "navigator"
        ]);
        if (!supportedCollaborationModes.has(collaborationMode)) {
            return res.status(400).json({ error: "不支持的协作模式", collaboration_mode: collaborationMode });
        }

// ⭐ 提取模型配置（支持自动推断）
        let model = meta.model;
        
        // 如果未指定模型，根据任务类型自动推断
        if (!model) {
            const MODEL_TYPE_MAP = {
                "qwen_generate": "qwen-turbo",
                "gemini_generate": process.env.GEMINI_MODEL || "gemini-3.5-flash",  // ⭐ Gemini 原生接口（经代理）
                "deepseek_generate": "deepseek-chat",
                "doubao_generate": "doubao-pro",
                "local_generate": "local-gemma4b",  // ⭐ Local LLM 模型
                "maas_generate": process.env.TENCENT_MAAS_MODEL || "hy4-preview",
                "modelscope_generate": process.env.MODELSCOPE_MODEL || "Qwen/Qwen3.8-Flash-Next",
                "openai_generate": "gpt-4o-mini",
                "claude_generate": "claude-3-5-sonnet"
            };
            model = MODEL_TYPE_MAP[type] || "qwen-turbo";
        }

        const stream = meta.stream || false;

        let finalPayload = {};

        // ⭐ 统一处理所有生成类任务
        if (type === "task.generate" || type.endsWith("_generate")) {
            const { prompt } = payload;
            const hasImages = payload.images && Array.isArray(payload.images) && payload.images.length > 0;
            if ((!prompt || typeof prompt !== "string") && !hasImages) {
                return res.status(400).json({ error: "生成任务需要 prompt 字符串或图片" });
            }
            finalPayload = {
                prompt,
                collaboration_mode: collaborationMode,
                ...(payload.images && Array.isArray(payload.images)
                    ? { images: payload.images }
                    : {}),
                ...(payload.context && typeof payload.context === 'object'
                    ? { context: payload.context }
                    : {}),
                ...(typeof payload.workspace_path === 'string'
                    ? { workspace_path: payload.workspace_path }
                    : {}),
                model: model
            };
        } else {
            finalPayload = payload;
        }

        // ⭐ v3.x: Webview 未传 workspace_path 时，注入 Node 已绑定的工作区根目录
        if (!finalPayload.workspace_path && workspaceRoot) {
            finalPayload.workspace_path = workspaceRoot;
        }

        // ⭐ 智能工作区检测：首次任务自动学习工作区路径
        autoSetWorkspaceIfNeeded(finalPayload.workspace_path || payload.workspace_path);

        // ⭐ Phase 2.2: ProjectStrategy — Resolver (建议) + Authorizer (授权)
        let taskContext = null;
        try {
            const promptText = finalPayload.prompt || '';
            const wsRoot = finalPayload.workspace_path || workspaceRoot;
            const workspaceRoots = wsRoot ? [path.resolve(wsRoot)] : [];

            const resolver = new ProjectStrategyResolver();
            const authorizer = new ProjectStrategyAuthorizer();

            const proposal = resolver.resolve(promptText, workspaceRoots);
            console.log(`   🎯 [Strategy] Resolver: mode=${proposal.mode} target=${proposal.targetPath} confidence=${proposal.confidence}`);

            if (workspaceRoots.length > 0) {
                const authorizedRoots = [workspaceRoots[0]];
                const result = authorizer.authorize(proposal, authorizedRoots);
                taskContext = {
                    context_id: task_id,
                    conversation_id: conversation_id || undefined,
                    workspace_roots: workspaceRoots,
                    authorized_roots: authorizedRoots,
                    allowed_paths: result.allowedPaths,
                    target_project_path: result.proposal.targetPath,
                    project_mode: result.proposal.mode,
                    created_at: new Date().toISOString(),
                    schema_version: '1.0',
                    context_hash: result.contextHash,
                    compatibility_policy: 'strict',
                };
                console.log(`   🔒 [Strategy] Authorizer: context_hash=${result.contextHash.slice(0, 16)}...`);
            } else {
                console.warn(`   ⚠️ [Strategy] No workspace roots; skipping Authorizer, using compat context`);
            }
        } catch (authErr) {
            if (authErr instanceof ConfirmationRequiredError) {
                console.warn(`   🔔 [Strategy] Confirmation required: ${authErr.message}`);

                const scope = authErr.scope instanceof Object && authErr.scope.toDict
                    ? authErr.scope.toDict()
                    : authErr.scope;

                const pendingContextHash = computeContextHash({
                    workspace_roots: (finalPayload.workspace_path ? [path.resolve(finalPayload.workspace_path)] : []),
                    authorized_roots: (finalPayload.workspace_path ? [path.resolve(finalPayload.workspace_path)] : []),
                    allowed_paths: { read: [], write: [], execute: [] },
                    target_project_path: finalPayload.workspace_path || '',
                    project_mode: scope.project_mode || scope.projectMode || '',
                    schema_version: '1.0',
                });

                const confirmation = confirmationManager.createConfirmation(task_id, scope, pendingContextHash);

                pendingSubmissions.set(task_id, {
                    finalPayload,
                    type,
                    model,
                    stream,
                    source,
                    meta,
                    submission,
                    collaborationMode,
                    conversation_id,
                });

                console.log(`   📋 [Confirmation] Created: ${confirmation.confirmationId}`);
                return res.json({
                    status: 'confirmation_required',
                    task_id,
                    confirmation: confirmation.toWebviewPayload(),
                });
            } else if (authErr instanceof AuthorizationDeniedError) {
                console.warn(`   🚫 [Strategy] Authorization denied: ${authErr.message}`);
            } else {
                console.warn(`   ⚠️ [Strategy] Strategy failed (will use compat context): ${authErr.message}`);
            }
        }

        if (!taskContext) {
            try {
                taskContext = buildOrExtractTaskContext(finalPayload);
                if (conversation_id) {
                    taskContext.conversation_id = conversation_id;
                }
                console.warn(`   🔄 [Strategy] Built compat_readonly task_context (write/execute denied)`);
            } catch (compatErr) {
                console.warn(`   ⚠️ [Strategy] Compat context build failed: ${compatErr.message}`);
            }
        }

        if (taskContext) {
            finalPayload.task_context = taskContext;
            finalPayload.workspace_path = taskContext.target_project_path;

            // ⭐ Phase 2.4: 流量监控 — 记录协议类型
            if (taskContext.compatibility_policy === 'strict') {
                trafficMonitor.recordNewProtocol();
            } else {
                trafficMonitor.recordCompatProtocol();
            }
            console.log(`   📊 [Traffic] Protocol: ${taskContext.compatibility_policy === 'strict' ? 'new (strict)' : 'compat (old)'} | Ratio: ${trafficMonitor.getReport().compat_ratio}`);
        }

        // ⭐ v3.1 新增：记录任务到 Memory Service
        let userId = meta.user_id || 'default-user';
        let projectId = meta.project_id || null;
        let prompt = finalPayload.prompt || JSON.stringify(finalPayload);
        
        let context = null;  // ⭐ v3.5 新增：上下文记忆
        
        try {
            // 创建或获取用户
            const user = await memoryService.getOrCreateUser(userId, `User-${userId}`, {});
            
            // 如果有项目 ID，创建或获取项目
            let project = null;
            if (projectId) {
                project = await memoryService.getOrCreateProject(user.id, `Project-${projectId}`, '', {});
            }
            
            // 创建任务记录
            await memoryService.createTask(task_id, user.id, project?.id || null, prompt, model, source);
            
            console.log(`   🧠 [Memory] 任务已记录: ${task_id}`);
            
            // ⭐ v3.5 新增：加载 Worker 上下文记忆
            if (project) {
                context = await memoryService.loadContextForWorker(task_id);
                console.log(`   🧠 [Memory] 上下文已加载:`);
                console.log(`      - 项目名称: ${context.project_context?.name || 'N/A'}`);
                console.log(`      - 项目记忆数: ${context.memory_context?.project_memories?.length || 0}`);
                console.log(`      - 用户偏好数: ${context.memory_context?.user_preferences?.length || 0}`);
            } else {
                console.log(`   ⚠️ [Memory] 无项目关联，跳过上下文加载`);
            }
        } catch (memoryError) {
            // ⭐ 降级策略：记忆系统失败不影响任务提交
            console.error(`   ⚠️ [Memory] 记录任务失败（不影响主流程）:`, memoryError.message);
        }

        // ⭐ 构建 TaskModel v2 格式
        const task = {
            protocol_version: PROTOCOL_VERSION,
            trace_id: submission.trace_id,
            task_id,
            type,
            payload: finalPayload,
            source,
            model,
            stream,
            timestamp: Date.now(),
            status: "pending",
            context: context || undefined  // ⭐ v3.5 新增：注入上下文记忆
        };

        console.log("\n📤 推入 Redis 队列（v2 标准格式 + 模型无关）");
        console.log(JSON.stringify(task, null, 2));

        // ⭐ 根据任务类型路由到专属队列（而非 model 字段）
        const queueName = getWorkerQueue(type);
        console.log(`🎯 路由到队列: ${queueName} (任务类型: ${type})`);

        // ⭐ v2.8 双云架构：根据模型选择 Redis 实例
        const targetRedis = getRedisClient(model, type);
        const redisType = targetRedis === redisLocal ? '本地 Docker Redis' : targetRedis === redisTair ? '阿里云 Tair' : 'Upstash';
        console.log(`💾 使用 Redis: ${redisType}`);

        const result = await targetRedis.lpush(queueName, JSON.stringify(task));
        console.log("Redis LPUSH 返回值：", result);
        console.log(`✅ 任务已成功推入 Redis 队列，当前队列长度：${result}`);

        const response = { 
            status: "submitted", 
            task_id,
            protocol_version: PROTOCOL_VERSION,
            trace_id: submission.trace_id,
            model,
            stream,
            message: "任务已提交到队列" 
        };

        console.log("\n📨 返回给插件：");
        console.log(JSON.stringify(response, null, 2));
        console.log("\n----------------------------------------\n");

        res.json(response);

    } catch (err) {
        console.error("❌ 提交任务接口发生错误：", err);
        if (err instanceof TaskProtocolError) {
            return res.status(400).json({ error: "Invalid task protocol", message: err.message });
        }
        res.status(500).json({ error: "Internal Server Error", message: err.message });
    }
});

// =========================
// 7. 路由：任务完成通知（Worker → Node API → WebSocket）
// =========================
app.post('/task/notify/:task_id', async (req, res) => {
    try {
        const { task_id } = req.params;
        const result = req.body;

        console.log(`\n📡 收到任务完成通知：${task_id}`);
        
        // ⭐ v3.1.1 过滤内部元数据（如果结果中包含 file_ops）
        if (result.context?.final_file_ops) {
            const originalCount = result.context.final_file_ops.length;
            result.context.final_file_ops = filterInternalOps(result.context.final_file_ops);
            const filteredCount = result.context.final_file_ops.length;
            
            if (originalCount !== filteredCount) {
                console.log(`   📋 FileOps 过滤: ${originalCount} → ${filteredCount} (移除 ${originalCount - filteredCount} 个内部元数据)`);
            }
        }
        
        console.log(JSON.stringify(result, null, 2));

        // ⭐ v3.1 新增：更新任务状态到 Memory Service
        try {
            const { resolveStatus } = require('./taskStateContract');
            const resolved = resolveStatus(result);

            if (!resolved.valid) {
                console.error(`   ⛔ [Contract] 任务 ${task_id} 结果契约无效`);
                resolved.violations.forEach(v => console.error(`      - ${v.field}: ${v.message}`));
            } else {
                if (resolved.warnings.length > 0) {
                    console.warn(`   ⚠️ [Contract WARNING] 任务 ${task_id}:`);
                    resolved.warnings.forEach(w => console.warn(`      - ${w.field}: ${w.message}`));
                }
                const status = resolved.status;
                const summary = result.summary || result.result_summary || '';
                await memoryService.updateTaskStatus(task_id, status, summary);
                console.log(`   🧠 [Memory] 任务状态已更新: ${status}`);
            }
            
            // ⭐ 记录步骤执行结果（如果有）
            if (result.steps && Array.isArray(result.steps)) {
                for (const step of result.steps) {
                    try {
                        await memoryService.createTaskStep(
                            task_id,
                            step.step_type || step.type,
                            step.input || {}
                        );
                        
                        // 如果步骤有输出，更新步骤状态
                        if (step.output) {
                            const dbStep = await memoryService.getTaskSteps(task_id);
                            const lastStep = dbStep[dbStep.length - 1];
                            if (lastStep) {
                                await memoryService.updateTaskStep(
                                    lastStep.id,
                                    step.status || 'unknown',
                                    step.output
                                );
                            }
                        }
                    } catch (stepError) {
                        console.error(`   ⚠️ [Memory] 记录步骤失败:`, stepError.message);
                    }
                }
            }
            
            // ⭐ 记录 FileOps（如果有）
            if (result.context?.final_file_ops && Array.isArray(result.context.final_file_ops)) {
                for (const fileOp of result.context.final_file_ops) {
                    try {
                        await memoryService.recordFileOp(
                            task_id,
                            null, // step_id 暂时为空，后续可以关联
                            fileOp.op,
                            fileOp.path,
                            fileOp.role || 'main',
                            fileOp.reason || '',
                            fileOp.from_step || ''
                        );
                    } catch (fileOpError) {
                        console.error(`   ⚠️ [Memory] 记录 FileOp 失败:`, fileOpError.message);
                    }
                }
            }
        } catch (memoryError) {
            // ⭐ 降级策略：记忆系统失败不影响通知流程
            console.error(`   ⚠️ [Memory] 更新任务状态失败（不影响主流程）:`, memoryError.message);
        }

        // ⭐ v3.4: 执行 FileOps 写入磁盘（不依赖 VSCode 扩展）
        if (result.context?.final_file_ops && Array.isArray(result.context.final_file_ops)) {
            const writeOps = result.context.final_file_ops.filter(
                op => op.op !== 'delete' && op.op !== 'meta' && op.op !== 'depends'
            );
            if (writeOps.length > 0 && fileOpsHandler.isWorkspaceConfigured()) {
                console.log(`   💾 正在写入 ${writeOps.length} 个文件到工作区: ${fileOpsHandler.workspaceRoot}`);
                try {
                    const fileResult = await fileOpsHandler.handleRequest(writeOps, task_id);
                    if (fileResult.success) {
                        console.log(`   ✅ FileOps 写入成功: ${fileResult.files?.length || writeOps.length} 个文件`);
                        if (fileResult.files) {
                            fileResult.files.forEach(f => console.log(`      📄 ${f.path}`));
                        }
                    } else {
                        console.error(`   ❌ FileOps 写入失败:`, fileResult.errors || fileResult.error);
                    }
                } catch (fileWriteError) {
                    console.error(`   ❌ FileOps 写入异常:`, fileWriteError.message);
                }
            } else if (writeOps.length > 0 && !fileOpsHandler.isWorkspaceConfigured()) {
                console.log(`   ⚠️ 工作区未配置，跳过 FileOps 写入（${writeOps.length} 个文件等待 VSCode 扩展处理）`);
            }
        }

        // ⭐ 通过 WebSocket 推送给订阅的前端
        if (taskSubscriptions.has(task_id)) {
            const subscribers = taskSubscriptions.get(task_id);
            
            console.log(`\n📡 向 ${subscribers.size} 个订阅者推送任务结果：${task_id}`);
            
            subscribers.forEach((socketId) => {
                const socket = io.sockets.sockets.get(socketId);
                if (socket) {
                    socket.emit("task_result", result);
                    console.log(`   ✅ 已推送给客户端: ${socketId}`);
                }
            });
        } else {
            console.log(`⚠️ 没有客户端订阅任务结果：${task_id}`);
        }

        res.json({ status: "notified" });

    } catch (err) {
        console.error("❌ 推送通知发生错误：", err);
        res.status(500).json({ error: "Internal Server Error" });
    }
});

// =========================
// 7.5. Phase 2.4: 用户确认端点 (P0-4)
// =========================

app.post('/task/confirm', async (req, res) => {
    try {
        const { confirmation_id, task_id } = req.body;

        if (!confirmation_id && !task_id) {
            return res.status(400).json({ error: 'confirmation_id or task_id is required' });
        }

        let confirmId = confirmation_id;
        if (!confirmId && task_id) {
            const record = confirmationManager.getByTaskId(task_id);
            if (!record) {
                return res.json({ status: 'confirmation_not_found', message: 'No pending confirmation for this task' });
            }
            confirmId = record.confirmationId;
        }

        const result = confirmationManager.confirm(confirmId);

        if (!result.success) {
            return res.json({
                status: 'confirmation_failed',
                reason: result.reason,
            });
        }

        const pending = pendingSubmissions.get(result.record.taskId);
        if (!pending) {
            return res.json({
                status: 'confirmed',
                confirmation_id: confirmId,
                message: 'Confirmed, but no pending submission found (may have expired)',
            });
        }

        const { finalPayload, type, model, stream, source, meta, submission, collaborationMode, conversation_id } = pending;

        const wsRoot = finalPayload.workspace_path || workspaceRoot;
        const workspaceRoots = wsRoot ? [path.resolve(wsRoot)] : [];
        const authorizedRoots = workspaceRoots.length > 0 ? [workspaceRoots[0]] : [];
        const allowedPaths = result.record.scope.allowed_paths
            || result.record.scope.allowedPaths
            || { read: authorizedRoots, write: authorizedRoots, execute: [] };

        const taskContext = {
            context_id: result.record.taskId,
            workspace_roots: workspaceRoots,
            authorized_roots: authorizedRoots,
            allowed_paths: allowedPaths,
            target_project_path: result.record.scope.target_project_path
                || result.record.scope.targetProjectPath
                || wsRoot,
            project_mode: result.record.scope.project_mode
                || result.record.scope.projectMode
                || 'modify_existing_project',
            created_at: new Date().toISOString(),
            schema_version: '1.0',
            conversation_id,
            context_hash: result.record.contextHash,
            compatibility_policy: 'strict',
            confirmation_id: confirmId,
        };

        finalPayload.task_context = taskContext;
        finalPayload.workspace_path = taskContext.target_project_path;

        // ⭐ v3.5 补充：确认路径加载记忆上下文（与非确认路径对齐）
        let prompt = finalPayload.prompt || JSON.stringify(finalPayload);
        let userId = meta?.user_id || 'default-user';
        let projectId = meta?.project_id || null;
        let context = null;
        try {
            const user = await memoryService.getOrCreateUser(userId, `User-${userId}`, {});
            let project = null;
            if (projectId) {
                project = await memoryService.getOrCreateProject(user.id, `Project-${projectId}`, '', {});
            }
            const actualTaskId = result.record.taskId;
            await memoryService.createTask(actualTaskId, user.id, project?.id || null, prompt, model, source);
            if (project) {
                context = await memoryService.loadContextForWorker(actualTaskId);
                console.log(`   🧠 [Memory/Confirm] 上下文已加载 (${context.memory_context?.project_memories?.length || 0} 条记忆)`);
            }
        } catch (memoryError) {
            console.error(`   ⚠️ [Memory/Confirm] 记忆加载失败（不影响主流程）:`, memoryError.message);
        }

        const task = {
            protocol_version: PROTOCOL_VERSION,
            trace_id: submission.trace_id,
            task_id: result.record.taskId,
            type,
            payload: finalPayload,
            source,
            model,
            stream,
            timestamp: Date.now(),
            status: 'pending',
            context: context || undefined  // ⭐ v3.5 新增
        };

        const queueName = getWorkerQueue(type);
        const targetRedis = getRedisClient(model, type);
        await targetRedis.lpush(queueName, JSON.stringify(task));

        pendingSubmissions.delete(result.record.taskId);

        console.log(`   ✅ [Confirmation] Task ${result.record.taskId} confirmed and pushed to queue`);
        return res.json({
            status: 'submitted',
            task_id: result.record.taskId,
            confirmation_id: confirmId,
            prompt: prompt,
            model: model,
            message: 'Task confirmed and submitted',
        });
    } catch (err) {
        console.error('❌ /task/confirm error:', err);
        res.status(500).json({ error: 'Internal Server Error', message: err.message });
    }
});

app.post('/task/deny', (req, res) => {
    try {
        const { confirmation_id, task_id } = req.body;

        if (!confirmation_id && !task_id) {
            return res.status(400).json({ error: 'confirmation_id or task_id is required' });
        }

        let confirmId = confirmation_id;
        if (!confirmId && task_id) {
            const record = confirmationManager.getByTaskId(task_id);
            if (!record) {
                return res.json({ status: 'no_pending_confirmation', message: 'No pending confirmation found' });
            }
            confirmId = record.confirmationId;
        }

        const record = confirmationManager.getById(confirmId);
        const result = confirmationManager.deny(confirmId);

        if (record) {
            pendingSubmissions.delete(record.taskId);
        }

        console.log(`   ❌ [Confirmation] Denied: ${confirmId} (reason: ${result.reason})`);
        return res.json({
            status: 'denied',
            confirmation_id: confirmId,
            reason: result.reason,
        });
    } catch (err) {
        console.error('❌ /task/deny error:', err);
        res.status(500).json({ error: 'Internal Server Error', message: err.message });
    }
});

// =========================
// 7.5 Phase 2.4: Traffic Monitor 端点
// =========================
app.get('/admin/traffic', (req, res) => {
    try {
        const report = trafficMonitor.getReport();
        return res.json(report);
    } catch (err) {
        console.error('❌ /admin/traffic error:', err);
        res.status(500).json({ error: 'Internal Server Error', message: err.message });
    }
});

app.post('/admin/traffic/reset', (req, res) => {
    try {
        trafficMonitor.reset();
        return res.json({ status: 'reset', message: 'Traffic monitor reset' });
    } catch (err) {
        console.error('❌ /admin/traffic/reset error:', err);
        res.status(500).json({ error: 'Internal Server Error', message: err.message });
    }
});

// =========================
// 7.6. [REMOVED] Duplicate stream_chunk handler merged into section 8
// =========================

// =========================
// 7.6. 路由：Worker 流式错误输出 ⭐ v3.2 新增
// =========================
app.post('/task/stream_error/:task_id', (req, res) => {
    try {
        const { task_id } = req.params;
        const error = req.body;

        // ⭐ 推送错误给订阅者
        if (taskSubscriptions.has(task_id)) {
            const subscribers = taskSubscriptions.get(task_id);
            subscribers.forEach((socketId) => {
                const socket = io.sockets.sockets.get(socketId);
                if (socket) {
                    socket.emit("task_stream_error", { task_id, error });
                }
            });
        }

        // ⭐ 必须立即结束响应
        res.json({ status: "ok" });
    } catch (err) {
        console.error("❌ stream_error 处理失败:", err);
        res.status(500).json({ error: "Internal Server Error" });
    }
});

// =========================
// 8. 路由：流式输出（Worker → Node API → WebSocket）⭐ v3.5+ 新增
// =========================

app.post('/task/stream_start/:task_id', (req, res) => {
    const { task_id } = req.params;
    const { title, phase } = req.body;
    
    console.log(`\n🌊 [Stream] stream_start: ${task_id}`);
    if (title) console.log(`   标题: ${title}`);
    if (phase) console.log(`   阶段: ${phase}`);
    
    // 通过 WebSocket 广播给所有订阅者
    io.emit('stream_start', {
        task_id,
        title: title || 'AI 正在生成...',
        phase: phase || null,
        timestamp: Date.now()
    });
    
    res.json({ status: "ok" });
});

app.post('/task/stream_chunk/:task_id', (req, res) => {
    const { task_id } = req.params;
    const { content, phase, channel, message_type } = req.body;
    
    // P0：step_started 信封 — 步骤开始事件
    if (message_type === 'step_started') {
        const { step_id, step_type, phase } = req.body;
        io.emit('step_started', { task_id, step_id, step_type, phase });
        return res.json({ status: 'ok' });
    }

    // P0：step_finished 信封 — 步骤完成事件
    if (message_type === 'step_finished') {
        const { step_id, step_type } = req.body;
        io.emit('step_finished', { task_id, step_id, step_type });
        return res.json({ status: 'ok' });
    }

    // P1：类型化信封分支 — 产物事件走独立 WS 通道
    if (message_type === 'artifact_created') {
        const { artifact_id, artifact_type, format, sequence, created_at, label } = req.body;
        
        // 最小校验
        if (!artifact_id || !artifact_type || !format || content === undefined) {
            console.warn(`[P1] artifact_created 缺少必需字段: ${JSON.stringify(req.body)}`);
            return res.status(400).json({ error: 'artifact_created 缺少必需字段' });
        }
        
        // 终态检查：stream_end 已触发过的任务不再接受产物
        if (completedTasks.has(task_id)) {
            console.warn(`[P1] artifact_created 被拒绝: 任务 ${task_id} 已终态`);
            return res.status(409).json({ error: '任务已终态，拒绝产物事件' });
        }
        
        console.log(`[P1] artifact_created: ${artifact_id} (${artifact_type}/${format}) for task ${task_id}`);
        
        io.emit('artifact_created', {
            task_id,
            artifact_id,
            artifact_type,
            format,
            content,
            label: label || null,
            sequence: sequence || 0,
            created_at: created_at || Date.now(),
        });
        
        return res.json({ status: "ok" });
    }
    
    // 常规文本增量（现有行为不变）
    // P2：累积 content 通道的文本用于完整性校验
    if (content && channel === 'content') {
      const prev = streamContentCache.get(task_id) || '';
      streamContentCache.set(task_id, prev + content);
    }
    io.emit('stream_chunk', {
        task_id,
        chunk: content || '',
        phase: phase || null,
        channel: channel || 'content',
        timestamp: Date.now()
    });
    
    res.json({ status: "ok" });
});

app.post('/task/stream_error/:task_id', (req, res) => {
    const { task_id } = req.params;
    const { message } = req.body;
    
    console.log(`\n❌ [Stream] stream_error: ${task_id} - ${message}`);
    
    // 通过 WebSocket 广播给所有订阅者
    io.emit('stream_error', {
        task_id,
        message: message || '未知错误',
        timestamp: Date.now()
    });
    
    res.json({ status: "ok" });
});

app.post('/task/stream_end/:task_id', (req, res) => {
    const { task_id } = req.params;
    
    console.log(`\n✅ [Stream] stream_end: ${task_id}`);
    
    // P2：标记任务终态，防止迟到的产物事件
    completedTasks.add(task_id);

    // P2：流式完整性校验 — 检查是否有未闭合的 Mermaid/Markdown 块
    const cached = streamContentCache.get(task_id);
    if (cached && typeof cached === 'string') {
        const backtickGroups = (cached.match(/```/g) || []).length;
        if (backtickGroups % 2 !== 0) {
            console.warn(`⚠️ [P2] stream_end 检测到未闭合代码块: task ${task_id}, content 长度 ${cached.length}`);
            io.emit('stream_chunk', {
                task_id,
                chunk: '\n```',
                phase: null,
                channel: 'content',
                timestamp: Date.now(),
            });
        }
        // P2：清理缓存，防止内存泄漏
        streamContentCache.delete(task_id);
    }
    
    // 通过 WebSocket 广播给所有订阅者
    io.emit('stream_end', {
        task_id,
        timestamp: Date.now()
    });
    
    res.json({ status: "ok" });
});

// =========================
// 9. 路由：任务历史查询（v3.5+ 新增）⭐
// =========================

app.get('/tasks/history', async (req, res) => {
    try {
        const { user_id, project_id, limit = 20, offset = 0 } = req.query;
        
        console.log(`\n📋 [History] 查询任务历史`);
        console.log(`   用户: ${user_id || '全部'}`);
        console.log(`   项目: ${project_id || '全部'}`);
        console.log(`   限制: ${limit}, 偏移: ${offset}`);
        
        // 构建查询条件
        const where = {};
        if (user_id) where.user_id = parseInt(user_id);
        if (project_id) where.project_id = parseInt(project_id);
        
        const tasks = await memoryService.prisma.task.findMany({
            where,
            orderBy: { created_at: 'desc' },
            take: parseInt(limit),
            skip: parseInt(offset),
            include: {
                user: { select: { id: true, name: true } },
                project: { select: { id: true, name: true } },
                steps: {
                    orderBy: { created_at: 'asc' },
                    select: {
                        id: true,
                        step_type: true,
                        status: true,
                        output: true,
                        created_at: true,
                        finished_at: true
                    }
                }
            }
        });
        
        const total = await memoryService.prisma.task.count({ where });
        
        console.log(`   ✅ 找到 ${tasks.length} 个任务 (总计: ${total})`);
        
        res.json({
            success: true,
            data: tasks,
            pagination: {
                total,
                limit: parseInt(limit),
                offset: parseInt(offset),
                hasMore: (parseInt(offset) + parseInt(limit)) < total
            }
        });
    } catch (error) {
        console.error('❌ 查询任务历史失败:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// =========================
// 10. 路由：文件版本查询（v3.5+ 新增）⭐
// =========================

app.get('/files/:fileId/versions', async (req, res) => {
    try {
        const { fileId } = req.params;
        const { limit = 10 } = req.query;
        
        console.log(`\n📄 [Versions] 查询文件版本: ${fileId}`);
        
        const versions = await memoryService.prisma.fileVersion.findMany({
            where: { file_id: parseInt(fileId) },
            orderBy: { created_at: 'desc' },  // ⭐ 修改为 created_at
            take: parseInt(limit),
            include: {
                task: {
                    select: {
                        id: true,
                        prompt: true,
                        created_at: true
                    }
                }
            }
        });
        
        console.log(`   ✅ 找到 ${versions.length} 个版本`);
        
        res.json({
            success: true,
            data: versions
        });
    } catch (error) {
        console.error('❌ 查询文件版本失败:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// =========================
// 11. 路由：项目记忆查询（v3.5+ 新增）⭐
// =========================

app.get('/projects/:projectId/memories', async (req, res) => {
    try {
        const { projectId } = req.params;
        const { type, limit = 20 } = req.query;
        
        console.log(`\n🧠 [Memories] 查询项目记忆: ${projectId}`);
        
        const where = { project_id: parseInt(projectId) };
        if (type) where.memory_type = type;
        
        const memories = await memoryService.prisma.memory.findMany({  // ⭐ 修改为 memory
            where,
            orderBy: { importance: 'desc' },
            take: parseInt(limit)
        });
        
        console.log(`   ✅ 找到 ${memories.length} 条记忆`);
        
        res.json({
            success: true,
            data: memories
        });
    } catch (error) {
        console.error('❌ 查询项目记忆失败:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// =========================
// 12. 路由：工作区路径设置（VSCode 扩展调用）
// =========================
app.post('/workspace/set', (req, res) => {
    const { path } = req.body;
    
    if (!path) {
        return res.status(400).json({ error: "path 不能为空" });
    }

    workspaceRoot = path;
    fileOpsHandler.setWorkspace(path);
    console.log(`📁 工作区已更新为: ${path}`);

    res.json({ status: "ok", workspace: path });
});

// =========================
// 13. 路由：FileOps 执行（VSCode 扩展调用）
// =========================
app.post('/fileops/execute', async (req, res) => {
    const { file_ops, task_id } = req.body;

    try {
        console.log(`\n📁 FileOps 执行请求:`);
        console.log(`   task_id: ${task_id || '(未提供)'}`);
        console.log(`   原始: ${file_ops?.length || 0} 个操作`);
        console.log(`   工作区: ${fileOpsHandler.workspaceRoot}`);

        // ⭐ R6 安全契约：执行端独立授权验证
        const nonMetaOps = (file_ops || []).filter(
            (op) => op.op && !["meta", "depends"].includes(op.op)
        );
        if (nonMetaOps.length > 0) {
            const authResult = await authorizationVerifier.verifyExecutionAuthorization(
                task_id,
                nonMetaOps
            );

            if (!authResult.authorized) {
                console.warn(
                    `   🚫 [AuthVerifier] 授权验证失败: ${authResult.reason}`
                );
                return res.status(403).json({
                    success: false,
                    error: "执行授权验证失败",
                    reason: authResult.reason,
                    auth_source: authResult.authSource || null,
                });
            }
        }

        // ⭐ v3.1.1 过滤内部元数据
        const filteredOps = filterInternalOps(file_ops);

        console.log(`   过滤后: ${filteredOps.length} 个操作`);

        const result = await fileOpsHandler.handleRequest(filteredOps, task_id || null);

        console.log(`   ✅ FileOps 执行完成: ${result.success ? '成功' : '失败'}`);
        if (result.files) {
            console.log(`   📄 生成文件: ${result.files.length} 个`);
            result.files.forEach(f => console.log(`      - ${f.path}`));
        }

        res.json(result);
    } catch (error) {
        console.error(`   ❌ FileOps 执行失败:`, error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// =========================
// 13b. 治理：失败回滚与审计（G1/G2/G4 生产层）
// =========================
app.post('/governance/rollback/:task_id', (req, res) => {
    const { task_id } = req.params;
    if (!fileOpsHandler.isWorkspaceConfigured()) {
        return res.status(400).json({ success: false, error: '工作区未配置' });
    }
    try {
        const result = fileOpsHandler.rollback(task_id);
        res.json(result);
    } catch (error) {
        console.error(`   ❌ 回滚失败:`, error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.get('/governance/snapshot/:task_id', (req, res) => {
    const { task_id } = req.params;
    if (!fileOpsHandler.isWorkspaceConfigured()) {
        return res.status(400).json({ success: false, error: '工作区未配置' });
    }
    try {
        const snapshot = fileOpsHandler.getSnapshot(task_id);
        if (!snapshot) {
            return res.status(404).json({ success: false, error: `快照不存在: ${task_id}` });
        }
        res.json({ success: true, snapshot });
    } catch (error) {
        console.error(`   ❌ 读取快照失败:`, error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// =========================
// R6 安全契约：用户审批端点
// VSCode Extension 用户确认后调用，将授权状态从 awaiting_host_policy 更新为 approved
// =========================
app.post('/auth/approve', async (req, res) => {
    const { task_id } = req.body;

    try {
        console.log(`\n🔓 授权审批请求:`);
        console.log(`   task_id: ${task_id || '(未提供)'}`);

        const result = await authorizationVerifier.approveAuthorization(task_id);

        if (result.success) {
            console.log(`   ✅ 授权审批完成: ${result.approvedCount || 0} 项`);
            res.json({
                success: true,
                task_id,
                approved_count: result.approvedCount || 0,
                reason: result.reason || null,
            });
        } else {
            console.warn(`   ❌ 授权审批失败: ${result.reason}`);
            res.status(400).json({
                success: false,
                task_id,
                error: result.reason,
            });
        }
    } catch (error) {
        console.error(`   ❌ 授权审批异常:`, error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// =========================
// 14. 工具函数：过滤内部元数据
// =========================
/**
 * 过滤掉内部元数据操作（v3.1.1）
 * - 移除 _internal: true 的操作
 * - 保留所有用户可见的文件操作
 */
function filterInternalOps(fileOps) {
    if (!Array.isArray(fileOps)) {
        return [];
    }
    
    return fileOps.filter(op => !op._internal);
}

// =========================
// 14.5 工具函数：会话 ID 解析（conversation_id 归属后端，多轮连续性兜底）
// =========================
function resolveConversationId(body, meta, workspacePath) {
    // 1) 前端显式续接（恢复历史会话）→ 沿用
    if (typeof body.conversation_id === 'string' && body.conversation_id.trim()) {
        return body.conversation_id.trim();
    }
    // 2) 后端自动生成稳定会话 ID（同 user + 同 project 共享，跨 project 隔离）
    const userId = (meta && meta.user_id) || 'default-user';
    const projectId = (meta && meta.project_id) || workspacePath || 'default-project';
    const raw = `${userId}\x00${projectId}`;
    return 'conv-' + crypto.createHash('sha256').update(raw).digest('hex').slice(0, 16);
}

// =========================
// 15. 工具函数：根据任务类型获取队列名称（✅ 符合架构信条）
// =========================
function getWorkerQueueByType(taskType) {
    const TYPE_QUEUE_MAP = {
        "qwen_generate": "task_queue:qwen",
        "deepseek_generate": "task_queue:deepseek",
        "doubao_generate": "task_queue:doubao",
        "maas_generate": "task_queue:maas",
        "modelscope_generate": "task_queue:modelscope",
        "local_generate": "task_queue:local",
        "openai_generate": "task_queue:openai",
        "claude_generate": "task_queue:claude",
        "gemini_generate": "task_queue:gemini",
        "node_generate": "node_worker",
        "java_generate": "java_worker",
        "ts_generate": "ts_worker",
    };

    return TYPE_QUEUE_MAP[taskType] || "task_queue";
}

// =========================
// 16. 工具函数：根据模型名称获取队列名称（保留用于向后兼容）
// =========================
function getWorkerQueue(modelOrType) {
    const WORKER_QUEUE_MAP = {
        "qwen": "task_queue:qwen",
        "deepseek": "task_queue:deepseek",
        "doubao": "task_queue:doubao",
        "maas": "task_queue:maas",
        "modelscope": "task_queue:modelscope",
        "local": "task_queue:local",
        "gpt": "task_queue:openai",
        "claude": "task_queue:claude",
        "gemini": "task_queue:gemini",
        "node": "node_worker",
        "java": "java_worker",
        "ts": "ts_worker",
    };

    let modelPrefix;
    if (modelOrType.startsWith("task.")) {
        modelPrefix = "qwen";  // 默认
    } else {
        modelPrefix = modelOrType.split("_")[0].split("-")[0];
    }
    
    return WORKER_QUEUE_MAP[modelPrefix] || "task_queue";
}

// =========================
// 17. 启动服务
// =========================
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`\n🚀 AlphaPilot Node API v3.2 已启动 on port ${PORT}`);
    console.log(`   · WebSocket 服务: ✅ 已开启`);
    console.log(`   · Redis: ${process.env.UPSTASH_REDIS_REST_URL ? '✅ Upstash' : '❌ 未配置'}`);
    
    if (fileOpsHandler.isWorkspaceConfigured()) {
        console.log(`   · FileOps Handler: ✅ 已就绪 (Workspace: ${workspaceRoot})`);
    } else {
        console.log(`   · FileOps Handler: ⏳ 等待 VSCode 扩展设置工作区...`);
        console.log(`      提示: VSCode 扩展应在启动时调用 POST /workspace/set`);
    }
    
    console.log('');
});