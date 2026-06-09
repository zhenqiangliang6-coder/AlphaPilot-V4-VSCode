/**
 * ⭐ Webview 层 - 只负责 UI 渲染
 * 
 * 规则：
 * 1. 只接收 { type: "append", content: string } | { type: "done" } | { type: "error", message: string }
 * 2. 完全不解析 TaskModel（version, meta, worker_id等都不处理）
 * 3. 只做 DOM 操作和文本渲染
 * 4. 禁止任何业务逻辑、JSON 拼接、协议解析
 */

const vscode = acquireVsCodeApi();

// 告知扩展：前端脚本已加载
try {
    vscode.postMessage({ type: "webview_ready" });
    console.log("✅ Webview 已加载");
} catch (e) {
    console.warn("❌ 无法发送 ready 信号：", e);
}

const statusEl = document.getElementById("status");
const outputEl = document.getElementById("output");
const btnCopy = document.getElementById("btnCopy") || {};
const btnClear = document.getElementById("btnClear") || {};
const btnStop = document.getElementById("btnStop") || {};  // ⭐ 新增：停止按钮
const promptInput = document.getElementById("promptInput") || {};
const submitBtn = document.getElementById("submitBtn") || {};

// UI 状态
const uiState = {
    charCount: 0,
    isStreaming: false,
    taskId: null  // ⭐ 新增：当前任务 ID
};


// 监听来自 Extension 的消息（简化协议）
window.addEventListener("message", (event) => {
    const message = event.data;
    console.log("📨 Webview 收到消息:", message.type);

    switch (message.type) {
        // 开始流式输出
        case "append":
            handleAppend(message);
            break;

        // 流式完成
        case "done":
            handleDone();
            break;

        // 错误
        case "error":
            handleError(message);
            break;

        // ⭐ 新增：设置任务 ID
        case "setTaskId":
            handleSetTaskId(message);
            break;

        // ⭐ 新增：任务正在停止
        case "task_stopping":
            handleTaskStopping(message);
            break;

        // ⭐ 新增：任务已取消
        case "task_cancelled":
            handleTaskCancelled(message);
            break;

        // ⭐ 新增：停止失败
        case "stop_failed":
            handleStopFailed(message);
            break;

        default:
            console.warn("❌ 未知消息类型:", message.type);
    }
});

/**
 * 追加内容
 * 输入：{ type: "append", content: string }
 */
function handleAppend(message) {
    const { content } = message;
    if (!content) return;

    // 第一次追加时，切换为流式状态
    if (!uiState.isStreaming) {
        uiState.isStreaming = true;
        statusEl.textContent = "🔄 流式输出中...";
        outputEl.textContent = "";
        uiState.charCount = 0;
    }

    // 追加文本
    outputEl.textContent += content;
    uiState.charCount += content.length;

    // 自动滚动
    const parent = outputEl.parentElement;
    parent.scrollTop = parent.scrollHeight;

    console.log(`📝 已追加 ${content.length} 字（共 ${uiState.charCount} 字）`);
}

/**
 * 流式输出完成
 * 输入：{ type: "done" }
 */
function handleDone() {
    uiState.isStreaming = false;
    statusEl.textContent = `✨ 完成 | ${uiState.charCount} 字`;
    console.log("✅ 流式输出已完成");
}

/**
 * ⭐ 设置任务 ID
 * 输入：{ type: "setTaskId", taskId: string }
 */
function handleSetTaskId(message) {
    const { taskId } = message;
    uiState.taskId = taskId;
    console.log("📝 设置任务 ID:", taskId);
    
    // 显示停止按钮（如果有）
    if (btnStop && typeof btnStop.style !== 'undefined') {
        btnStop.style.display = 'inline-block';
        btnStop.disabled = false;
        btnStop.textContent = '⏹️ 停止任务';
    }
}

/**
 * ⭐ 任务正在停止
 * 输入：{ type: "task_stopping", taskId: string, status: string }
 */
function handleTaskStopping(message) {
    const { taskId, status } = message;
    console.log(`⏸️ 任务正在停止：${taskId} (${status})`);
    
    if (btnStop && typeof btnStop.style !== 'undefined') {
        btnStop.disabled = true;
        btnStop.textContent = '⏸️ 正在停止...';
    }
    
    statusEl.textContent = "⏸️ 正在停止任务...";
}

/**
 * ⭐ 任务已取消
 * 输入：{ type: "task_cancelled", taskId: string, reason: string }
 */
function handleTaskCancelled(message) {
    const { taskId, reason } = message;
    console.log(`✅ 任务已取消：${taskId} - ${reason}`);
    
    uiState.isStreaming = false;
    statusEl.textContent = `⏹️ 任务已取消`;
    outputEl.textContent = "任务已被用户主动取消\n\n" + (outputEl.textContent || "");
    
    if (btnStop && typeof btnStop.style !== 'undefined') {
        btnStop.style.display = 'none';
    }
}

/**
 * ⭐ 停止失败
 * 输入：{ type: "stop_failed", taskId: string, error: string }
 */
function handleStopFailed(message) {
    const { taskId, error } = message;
    console.error(`❌ 停止任务失败：${taskId} - ${error}`);
    
    if (btnStop && typeof btnStop.style !== 'undefined') {
        btnStop.disabled = false;
        btnStop.textContent = '⏹️ 停止任务';
    }
    
    statusEl.textContent = `❌ 停止失败：${error}`;
}

/**
 * 错误处理
 * 输入：{ type: "error", message: string }
 */
function handleError(message) {
    uiState.isStreaming = false;
    const errMsg = message.message || "未知错误";
    statusEl.textContent = `❌ 错误`;
    outputEl.textContent = `任务失败：${errMsg}`;
    console.error("❌ 任务错误:", errMsg);
    
    // 隐藏停止按钮
    if (btnStop && typeof btnStop.style !== 'undefined') {
        btnStop.style.display = 'none';
    }
}

/**
 * 清空输出
 */
function clearOutput() {
    statusEl.textContent = "已清空";
    outputEl.textContent = "";
    uiState.isStreaming = false;
    uiState.charCount = 0;
}

// 按钮事件
if (btnCopy && btnCopy.addEventListener) {
    btnCopy.addEventListener("click", () => {
        const text = outputEl.textContent || "";
        navigator.clipboard.writeText(text).then(() => {
            vscode.postMessage({ type: "notify", message: "已复制到剪贴板" });
            console.log("📋 已复制到剪贴板");
        });
    });
}

if (btnClear && btnClear.addEventListener) {
    btnClear.addEventListener("click", () => {
        clearOutput();
        console.log("🧹 已清空输出");
    });
}

// ⭐ 新增：停止按钮事件
if (btnStop && btnStop.addEventListener) {
    btnStop.addEventListener("click", () => {
        if (uiState.taskId) {
            console.log(`🛑 用户点击停止任务：${uiState.taskId}`);
            vscode.postMessage({ 
                type: "stop_task", 
                taskId: uiState.taskId 
            });
            
            // 禁用按钮防止重复点击
            btnStop.disabled = true;
            btnStop.textContent = '⏸️ 正在停止...';
        } else {
            vscode.postMessage({ 
                type: "notify", 
                message: "当前没有正在执行的任务" 
            });
        }
    });
    
    // 初始隐藏
    if (btnStop && typeof btnStop.style !== 'undefined') {
        btnStop.style.display = 'none';
    }
}

// 面板内提交 prompt 的逻辑：发送给 extension
if (submitBtn && submitBtn.addEventListener) {
    submitBtn.addEventListener("click", () => {
        const prompt = (promptInput && promptInput.value) ? promptInput.value : "";
        if (typeof prompt === 'string' && prompt.trim()) {
            vscode.postMessage({ type: "submit_prompt", prompt: prompt.trim() });
            // 清空输入框，保持焦点
            if (promptInput && typeof promptInput.value !== 'undefined') {
                promptInput.value = "";
                promptInput.focus();
            }
        }
    });
}

if (promptInput && promptInput.addEventListener) {
    promptInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            if (submitBtn && submitBtn.click) submitBtn.click();
            e.preventDefault();
        }
    });
}
