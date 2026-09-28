// node-api/index.js
// ---------------------------------------------------------
// AlphaPilot OS v3.0 Node API Server
// 整合了 HTTP 服务、WebSocket 通信以及 FileOps Handler
// ---------------------------------------------------------

require("dotenv").config();
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const os = require('os');
const { v4: uuidv4 } = require("uuid");
const { Redis } = require("@upstash/redis");

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

// 阿里云 Tair Redis（国内模型：DeepSeek/Doubao）
// ⚠️ 注意：Node.js 的 @upstash/redis 只支持 Upstash，需要使用 ioredis 连接阿里云 Tair
let redisTair = null;

try {
    const IORedis = require('ioredis');
    
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

// 智能路由函数：根据模型选择 Redis 实例
function getRedisClient(model) {
    // 提取模型前缀
    const modelPrefix = model.split('_')[0].split('-')[0];
    
    // 国内模型列表
    const domesticModels = ['deepseek', 'doubao'];
    
    if (domesticModels.includes(modelPrefix) && redisTair) {
        return redisTair;
    }
    
    // 默认使用 Upstash（包括 Qwen）
    return redisUpstash;
}

// 为了向后兼容，保留 redis 变量（指向 Upstash）
const redis = redisUpstash;

// =========================
// 4. 初始化 FileOps Handler
// =========================
const workspaceRoot = process.env.WORKSPACE_ROOT;  // ⭐ 不再 fallback 到 os.tmpdir()
const fileOpsHandler = new FileOpsHandler(workspaceRoot || null);  // ⭐ 允许初始为 null

if (!workspaceRoot) {
    console.log('   ⚠️  WORKSPACE_ROOT 未配置，等待 VSCode 扩展设置工作区...');
}

// =========================
// 5. WebSocket 连接管理
// =========================
const taskSubscriptions = new Map(); // { task_id => Set<socket_id> }
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

        const { type, payload, source = "vscode-plugin", meta = {} } = req.body;
        const task_id = uuidv4();

        if (!type) return res.status(400).json({ error: "任务类型 type 不能为空" });
        if (!payload || typeof payload !== "object") {
            return res.status(400).json({ error: "payload 必须是对象" });
        }

        // ⭐ 提取模型配置（支持自动推断）
        let model = meta.model;
        
        // 如果未指定模型，根据任务类型自动推断
        if (!model) {
            const MODEL_TYPE_MAP = {
                "qwen_generate": "qwen-turbo",
                "deepseek_generate": "deepseek-chat",
                "doubao_generate": "doubao-pro",
                "local_generate": "local-gemma4b",  // ⭐ Local LLM 模型
                "maas_generate": "maas-hy4-preview"  // ⭐ 腾讯 MaaS (TokenHub)
            };
            model = MODEL_TYPE_MAP[type] || "qwen-turbo";
        }

        const stream = meta.stream || false;

        let finalPayload = {};

        // ⭐ 统一处理所有生成类任务
        if (type === "task.generate" || type.endsWith("_generate")) {
            const { prompt } = payload;
            if (!prompt || typeof prompt !== "string") {
                return res.status(400).json({ error: "生成任务需要 prompt 字符串" });
            }
            finalPayload = { prompt };
        } else {
            finalPayload = payload;
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
        const queueName = getWorkerQueueByType(type);
        console.log(`🎯 路由到队列: ${queueName} (任务类型: ${type})`);

        // ⭐ v2.8 双云架构：根据模型选择 Redis 实例
        const targetRedis = getRedisClient(model);
        const redisType = targetRedis === redisTair ? '阿里云 Tair' : 'Upstash';
        console.log(`💾 使用 Redis: ${redisType}`);

        const result = await targetRedis.lpush(queueName, JSON.stringify(task));
        console.log("Redis LPUSH 返回值：", result);
        console.log(`✅ 任务已成功推入 Redis 队列，当前队列长度：${result}`);

        const response = { 
            status: "submitted", 
            task_id,
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
            const status = result.status || 'done';
            const summary = result.summary || result.result_summary || '';
            
            await memoryService.updateTaskStatus(task_id, status, summary);
            
            console.log(`   🧠 [Memory] 任务状态已更新: ${status}`);
            
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
                                    step.status || 'done',
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
// 7.5. 路由：Worker 流式输出（步骤中间内容）⭐ v3.2 新增
// =========================
app.post('/task/stream_chunk/:task_id', (req, res) => {
    try {
        const { task_id } = req.params;
        const chunk = req.body;

        // ⭐ 推送给订阅者（实时步骤输出）
        if (taskSubscriptions.has(task_id)) {
            const subscribers = taskSubscriptions.get(task_id);
            subscribers.forEach((socketId) => {
                const socket = io.sockets.sockets.get(socketId);
                if (socket) {
                    socket.emit("task_stream_chunk", { task_id, chunk });
                }
            });
        }

        // ⭐ 必须立即结束响应，否则 Worker 会卡住并重试
        res.json({ status: "ok" });
    } catch (err) {
        console.error("❌ stream_chunk 处理失败:", err);
        res.status(500).json({ error: "Internal Server Error" });
    }
});

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
    const { content, phase, channel } = req.body;
    
    // 通过 WebSocket 广播给所有订阅者
    io.emit('stream_chunk', {
        task_id,
        chunk: content || '',
        phase: phase || null,
        channel: channel || 'content',  // reasoning / content
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

    fileOpsHandler.setWorkspace(path);
    console.log(`📁 工作区已更新为: ${path}`);

    res.json({ status: "ok", workspace: path });
});

// =========================
// 13. 路由：FileOps 执行（VSCode 扩展调用）
// =========================
app.post('/fileops/execute', async (req, res) => {
    const { file_ops } = req.body;
    
    try {
        // ⭐ v3.1.1 过滤内部元数据
        const filteredOps = filterInternalOps(file_ops);
        
        console.log(`\n FileOps 执行请求:`);
        console.log(`   原始: ${file_ops?.length || 0} 个操作`);
        console.log(`   过滤后: ${filteredOps.length} 个操作`);
        console.log(`   工作区: ${fileOpsHandler.workspaceRoot}`);
        
        const result = await fileOpsHandler.handleRequest(filteredOps);
        
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
// 15. 工具函数：根据任务类型获取队列名称（✅ 符合架构信条）
// =========================
function getWorkerQueueByType(taskType) {
    const TYPE_QUEUE_MAP = {
        "qwen_generate": "task_queue:qwen",
        "deepseek_generate": "task_queue:deepseek",
        "doubao_generate": "task_queue:doubao",
        "local_generate": "task_queue:local",  // ⭐ Local LLM Worker
        "maas_generate": "task_queue:maas",  // ⭐ 腾讯 MaaS (TokenHub)
        "openai_generate": "task_queue:openai",
        "claude_generate": "task_queue:claude",
        "gemini_generate": "task_queue:gemini",
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
        "local": "task_queue:local",  // ⭐ Local LLM Worker
        "maas": "task_queue:maas",  // ⭐ 腾讯 MaaS (TokenHub)
        "gpt": "task_queue:openai",
        "claude": "task_queue:claude",
        "gemini": "task_queue:gemini",
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
