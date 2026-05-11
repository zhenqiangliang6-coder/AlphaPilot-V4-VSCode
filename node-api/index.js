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
// 3. 初始化 Redis (Upstash)
// =========================
const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL,
  token: process.env.UPSTASH_REDIS_REST_TOKEN,
});

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
                "doubao_generate": "doubao-pro"
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

        // ⭐ 根据模型类型路由到专属队列
        const queueName = getWorkerQueue(model);
        console.log(`🎯 路由到队列: ${queueName} (模型: ${model})`);

        const result = await redis.lpush(queueName, JSON.stringify(task));
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
        
        console.log(`\n📋 FileOps 执行请求:`);
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
// 9. 工具函数：根据模型名称获取队列名称
// =========================
function getWorkerQueue(modelOrType) {
    const WORKER_QUEUE_MAP = {
        "qwen": "task_queue:qwen",
        "deepseek": "task_queue:deepseek",
        "doubao": "task_queue:doubao",
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
