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
                "local_generate": "local-gemma4b"  // ⭐ Local LLM 模型
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

        // ⭐ 构建 TaskModel v2 格式
        const task = {
            task_id,
            type,
            payload: finalPayload,
            source,
            model,
            stream,
            timestamp: Date.now(),
            status: "pending"
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
// 8. 路由：设置工作区路径（VSCode 扩展调用）
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
// 9. 路由：FileOps 执行（VSCode 扩展调用）
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
// 9. 工具函数：过滤内部元数据
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
// 9. 工具函数：根据任务类型获取队列名称（✅ 符合架构信条）
// =========================
function getWorkerQueueByType(taskType) {
    const TYPE_QUEUE_MAP = {
        "qwen_generate": "task_queue:qwen",
        "deepseek_generate": "task_queue:deepseek",
        "doubao_generate": "task_queue:doubao",
        "local_generate": "task_queue:local",  // ⭐ Local LLM Worker
        "openai_generate": "task_queue:openai",
        "claude_generate": "task_queue:claude",
        "gemini_generate": "task_queue:gemini",
    };

    return TYPE_QUEUE_MAP[taskType] || "task_queue";
}

// =========================
// 10. 工具函数：根据模型名称获取队列名称（保留用于向后兼容）
// =========================
function getWorkerQueue(modelOrType) {
    const WORKER_QUEUE_MAP = {
        "qwen": "task_queue:qwen",
        "deepseek": "task_queue:deepseek",
        "doubao": "task_queue:doubao",
        "local": "task_queue:local",  // ⭐ Local LLM Worker
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
// 10. 启动服务
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
