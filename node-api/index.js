// index.js
require("dotenv").config();
const express = require("express");
const { createServer } = require("http");
const { Server } = require("socket.io");
const { v4: uuidv4 } = require("uuid");
const { Redis } = require("@upstash/redis");

// 引入你升级后的 TaskModel v2
const {
  createTaskSubmit,
  createTaskResultSuccess,
  createTaskResultError,
  createDLQItem,
  validateTaskResult
} = require("./taskModel");

const app = express();
const httpServer = createServer(app);
const io = new Server(httpServer, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"],
  },
});

// ⭐ 关键修复：增加 body-parser 限制到 10MB
// 原因：智能体生成的 reasoning + content 可能非常大（复杂分析、代码生成、测试用例等）
// 这是世界级编程助手（Cursor/Claude Code）都必须做的配置
app.use(express.json({ limit: "10mb" }));
app.use(express.urlencoded({ limit: "10mb", extended: true }));

const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL,
  token: process.env.UPSTASH_REDIS_REST_TOKEN,
});

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

// ============================================================
// ⭐ 新增：支持的模型列表（与Python端保持一致）
// ============================================================
const SUPPORTED_MODELS = {
  qwen: ["qwen-turbo", "qwen-plus", "qwen-max", "qwen2.5"],
  deepseek: ["deepseek-chat", "deepseek-coder"],
  doubao: ["doubao-pro", "doubao-lite"],
  gpt: ["gpt-4", "gpt-4o", "gpt-5"],
  claude: ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
  gemini: ["gemini-pro", "gemini-ultra"]
};

// ============================================================
// v2 新增：事件流缓存（task_id => events[]）
// ============================================================
const taskEvents = new Map();

// ============================================================
// WebSocket 连接管理
// ============================================================
const taskSubscriptions = new Map(); // { task_id => Set<socket_id> }

io.on("connection", (socket) => {
  console.log(`\n🔌 WebSocket 客户端已连接：${socket.id}`);

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

  socket.on("disconnect", () => {
    console.log(`🔌 WebSocket 客户端已断开连接：${socket.id}`);
    
    for (const [taskId, sockets] of taskSubscriptions.entries()) {
      sockets.delete(socket.id);
      if (sockets.size === 0) {
        taskSubscriptions.delete(taskId);
      }
    }
  });
});

// ============================================================
// 推送任务结果（完整 v2 格式）
// ============================================================
async function broadcastTaskResult(taskId, result) {
  if (taskSubscriptions.has(taskId)) {
    const subscribers = taskSubscriptions.get(taskId);
    
    console.log(`\n📡 向 ${subscribers.size} 个订阅者推送任务结果：${taskId}`);
    console.log("📦 推送完整的标准格式数据：");
    console.log(pretty(result));
    
    subscribers.forEach((socketId) => {
      const socket = io.sockets.sockets.get(socketId);
      if (socket) {
        socket.emit("task_result", result);
      }
    });
  }
}

app.set("broadcastTaskResult", broadcastTaskResult);

// ============================================================
// 【任务提交】支持 TaskModel v2 + 模型无关协议
// ============================================================
app.post("/task/submit", async (req, res) => {
  try {
    console.log("\n📥 收到前端提交任务：");
    console.log(pretty(req.body));

    const { type, payload, source = "vscode-plugin", meta = {} } = req.body;
    const task_id = uuidv4();

    // ⭐ 验证任务类型（支持模型无关的 task.generate）
    if (!type) return res.status(400).json({ error: "任务类型 type 不能为空" });
    
    // 允许的类型：task.generate（推荐）或向后兼容的旧类型
    const allowedTypes = ["task.generate", "qwen_generate", "deepseek_generate", "doubao_generate"];
    if (!allowedTypes.includes(type)) {
      return res.status(400).json({ 
        error: `不支持的任务类型: ${type}`,
        supported: allowedTypes
      });
    }

    if (!payload || typeof payload !== "object") {
      return res.status(400).json({ error: "payload 必须是对象" });
    }

    // ⭐ 提取模型配置（从 meta 字段）
    const model = meta.model || "qwen-turbo";  // 默认模型
    const stream = meta.stream || false;  // 默认非流式

    // 验证模型名称
    const modelVendor = model.split("-")[0];
    if (!SUPPORTED_MODELS[modelVendor]) {
      console.warn(`⚠️ 未知模型厂商: ${modelVendor}，使用默认队列`);
    }

    let finalPayload = {};

    // ⭐ 统一处理所有生成类任务
    if (type === "task.generate" || type.endsWith("_generate")) {
      const { prompt } = payload;
      if (!prompt || typeof prompt !== "string") {
        return res.status(400).json({ error: "生成任务需要 prompt 字符串" });
      }
      finalPayload = { prompt };
    } else {
      // 其他任务类型（向后兼容）
      finalPayload = payload;
    }

    // ⭐ 使用 v2 TaskModel，传入模型和流式配置
    const task = createTaskSubmit(task_id, type, finalPayload, source, model, stream);

    console.log("\n📤 推入 Redis 队列（v2 标准格式 + 模型无关）");
    console.log(pretty(task));

    // ⭐ 根据模型类型路由到专属队列（符合多智能体架构）
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
    console.log(pretty(response));
    console.log("\n----------------------------------------\n");

    res.json(response);

  } catch (err) {
    console.error("❌ 提交任务接口发生错误：", err);
    res.status(500).json({ error: "Internal Server Error", message: err.message });
  }
});

// ============================================================
// ⭐ 改进：根据模型名称获取队列名称（模型无关）
// ============================================================
function getWorkerQueue(modelOrType) {
  // Worker 与队列的映射关系
  const WORKER_QUEUE_MAP = {
    "qwen": "task_queue:qwen",
    "deepseek": "task_queue:deepseek",
    "doubao": "task_queue:doubao",
    "gpt": "task_queue:openai",  // GPT系列使用OpenAI Worker
    "claude": "task_queue:claude",
    "gemini": "task_queue:gemini",
  };

  // 提取模型前缀 (qwen/deepseek/doubao/gpt/claude/gemini)
  let modelPrefix;
  
  if (modelOrType.startsWith("task.")) {
    // 如果是 task.generate，需要从其他地方推断（暂时使用默认）
    modelPrefix = "qwen";  // 默认
  } else {
    modelPrefix = modelOrType.split("_")[0].split("-")[0];
  }
  
  // 查找映射，如果没有则使用默认队列（向后兼容）
  return WORKER_QUEUE_MAP[modelPrefix] || "task_queue";
}

// ============================================================
// 【任务完成通知】Worker → Node API → WebSocket
// 合并 v2 的 events
// ============================================================
app.post("/task/notify/:task_id", async (req, res) => {
  try {
    const { task_id } = req.params;
    const result = req.body;

    console.log(`\n📡 收到任务完成通知：${task_id}`);
    console.log(pretty(result));

    // v2：合并事件流
    if (taskEvents.has(task_id)) {
      result.events = taskEvents.get(task_id);
      taskEvents.delete(task_id);
    }

    const broadcastFn = req.app.get("broadcastTaskResult");
    if (broadcastFn) {
      await broadcastFn(task_id, result);
    }

    res.json({ status: "notified" });

  } catch (err) {
    console.error("❌ 推送通知发生错误：", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

// ============================================================
// 【流式输出】升级为 v2 事件流
// ============================================================

// 流开始
app.post("/task/stream_start/:task_id", async (req, res) => {
  try {
    const { task_id } = req.params;
    const { title, phase } = req.body;

    console.log(`\n🔴 流式开始：${task_id} - ${title} (phase: ${phase})`);

    // v2：记录事件
    if (!taskEvents.has(task_id)) taskEvents.set(task_id, []);
    taskEvents.get(task_id).push({
      timestamp: Date.now(),
      type: "stream_start",
      data: { title, phase }
    });

    // 推送给前端
    if (taskSubscriptions.has(task_id)) {
      const subscribers = taskSubscriptions.get(task_id);
      subscribers.forEach((socketId) => {
        const socket = io.sockets.sockets.get(socketId);
        if (socket) {
          socket.emit("stream_start", { task_id, title, phase });
        }
      });
    }

    res.json({ status: "stream_started" });

  } catch (err) {
    console.error("❌ stream_start 错误：", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

// 流内容块（⭐ 增强：支持 phase 和 channel）
app.post("/task/stream_chunk/:task_id", async (req, res) => {
  try {
    const { task_id } = req.params;
    const { content, phase, channel } = req.body;

    // v2：记录 token 事件（包含 phase 和 channel）
    if (!taskEvents.has(task_id)) taskEvents.set(task_id, []);
    taskEvents.get(task_id).push({
      timestamp: Date.now(),
      type: "token",
      data: { 
        text: content,
        phase: phase || "unknown",
        channel: channel || "content"
      }
    });

    // 推送给前端（携带 phase 和 channel）
    if (taskSubscriptions.has(task_id)) {
      const subscribers = taskSubscriptions.get(task_id);
      subscribers.forEach((socketId) => {
        const socket = io.sockets.sockets.get(socketId);
        if (socket) {
          socket.emit("stream_chunk", { 
            task_id, 
            chunk: content,
            phase: phase || "unknown",
            channel: channel || "content"
          });
        }
      });
    }

    res.json({ status: "chunk_sent" });

  } catch (err) {
    console.error("❌ stream_chunk 错误：", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

// 流结束
app.post("/task/stream_end/:task_id", async (req, res) => {
  try {
    const { task_id } = req.params;
    const { phase } = req.body;

    console.log(`\n🟢 流式结束：${task_id} (phase: ${phase})`);

    // v2：记录事件
    if (!taskEvents.has(task_id)) taskEvents.set(task_id, []);
    taskEvents.get(task_id).push({
      timestamp: Date.now(),
      type: "stream_end",
      data: { phase }
    });

    // 推送给前端
    if (taskSubscriptions.has(task_id)) {
      const subscribers = taskSubscriptions.get(task_id);
      subscribers.forEach((socketId) => {
        const socket = io.sockets.sockets.get(socketId);
        if (socket) {
          socket.emit("stream_end", { task_id, phase });
        }
      });
    }

    res.json({ status: "stream_ended" });

  } catch (err) {
    console.error("❌ stream_end 错误：", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

// 流错误
app.post("/task/stream_error/:task_id", async (req, res) => {
  try {
    const { task_id } = req.params;
    const { message, phase } = req.body;

    console.log(`\n⚠️ 流式错误：${task_id} - ${message} (phase: ${phase})`);

    // v2：记录事件
    if (!taskEvents.has(task_id)) taskEvents.set(task_id, []);
    taskEvents.get(task_id).push({
      timestamp: Date.now(),
      type: "error",
      data: { message, phase }
    });

    // 推送给前端
    if (taskSubscriptions.has(task_id)) {
      const subscribers = taskSubscriptions.get(task_id);
      subscribers.forEach((socketId) => {
        const socket = io.sockets.sockets.get(socketId);
        if (socket) {
          socket.emit("stream_error", { task_id, message, phase });
        }
      });
    }

    res.json({ status: "stream_error_sent" });

  } catch (err) {
    console.error("❌ stream_error 错误：", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

// ============================================================
// ⭐ 新增：【停止任务】接口 - 生产级取消能力
// ============================================================
app.post("/task/stop/:task_id", async (req, res) => {
  try {
    const { task_id } = req.params;

    console.log(`\n🛑 收到停止任务请求：${task_id}`);

    // 1. 写入 Redis：让 Worker v2 看到停止标记
    await redis.set(`stop:${task_id}`, "1");

    console.log(`✅ 已设置停止标记：stop:${task_id}`);

    // 2. 推送取消事件给订阅的前端
    if (taskSubscriptions.has(task_id)) {
      const subscribers = taskSubscriptions.get(task_id);
      subscribers.forEach((socketId) => {
        const socket = io.sockets.sockets.get(socketId);
        if (socket) {
          socket.emit("task_cancelled", { 
            task_id,
            reason: "用户主动取消",
            timestamp: Date.now()
          });
        }
      });
      console.log(`📡 已向 ${subscribers.size} 个订阅者推送取消事件`);
    }

    res.json({ 
      status: "stopping", 
      task_id,
      message: "已发送停止请求，任务将在下一步执行前停止"
    });

  } catch (err) {
    console.error("❌ 停止任务失败：", err);
    res.status(500).json({ 
      error: "Failed to stop task",
      message: err.message 
    });
  }
});

// ============================================================
// 启动服务
// ============================================================
// ============================================================
// DLQ 管理 APIs
// ============================================================
app.get("/dlq/items", async (req, res) => {
  try {
    console.log("\n🔍 查询 DLQ 队列...\n");
    
    const dlqItems = await redis.lrange("dlq", 0, -1);
    
    if (dlqItems.length === 0) {
      console.log("✅ DLQ 队列为空");
      return res.json({ items: [] });
    }
    
    const parsedItems = dlqItems.map(item => 
      typeof item === 'string' ? JSON.parse(item) : item
    );
    
    console.log(`📦 DLQ 中共有 ${dlqItems.length} 个失败任务`);
    
    res.json({ items: parsedItems });
    
  } catch (err) {
    console.error("❌ 查询 DLQ 失败：", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

app.get("/dlq/item/:task_id", async (req, res) => {
  try {
    const { task_id } = req.params;
    
    console.log(`\n🔍 查询 DLQ 中的任务：${task_id}\n`);
    
    const dlqItems = await redis.lrange("dlq", 0, -1);
    
    for (const item of dlqItems) {
      const parsed = typeof item === 'string' ? JSON.parse(item) : item;
      if (parsed.task_id === task_id) {
        console.log(`✅ 找到任务：${task_id}`);
        return res.json(parsed);
      }
    }
    
    console.log(`⚠️ 未找到任务：${task_id}`);
    res.status(404).json({ error: "Not Found" });
    
  } catch (err) {
    console.error("❌ 查询失败：", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

app.delete("/dlq/item/:task_id", async (req, res) => {
  try {
    const { task_id } = req.params;
    
    console.log(`\n🗑️ 从 DLQ 中移除任务：${task_id}\n`);
    
    const dlqItems = await redis.lrange("dlq", 0, -1);
    const filtered = dlqItems.filter(item => {
      const parsed = typeof item === 'string' ? JSON.parse(item) : item;
      return parsed.task_id !== task_id;
    });
    
    await redis.del("dlq");
    if (filtered.length > 0) {
      for (const item of filtered) {
        const itemStr = typeof item === 'string' ? item : JSON.stringify(item);
        await redis.lpush("dlq", itemStr);
      }
    }
    
    console.log(`✅ 已从 DLQ 移除任务：${task_id}`);
    res.json({ status: "removed" });
    
  } catch (err) {
    console.error("❌ 删除失败：", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

// ============================================================
// 启动服务
// ============================================================
const PORT = 3000;
httpServer.listen(PORT, () => {
  console.log(`Node API 已启动：http://localhost:${PORT}`);
  console.log(`WebSocket 服务已启动：ws://localhost:${PORT}\n`);
});
