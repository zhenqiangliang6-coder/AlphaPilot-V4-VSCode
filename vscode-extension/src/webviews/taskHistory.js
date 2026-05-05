// src/webviews/taskHistory.js
const vscode = acquireVsCodeApi();

// 发送 ready 信号
try {
    vscode.postMessage({ type: 'ready' });
} catch (e) {
    console.warn('无法发送 ready 信号：', e);
}

const historyListEl = document.getElementById('historyList');
const emptyStateEl = document.getElementById('emptyState');
const searchInput = document.getElementById('searchInput');
const btnRefresh = document.getElementById('btnRefresh');
const btnClear = document.getElementById('btnClear');

let allTasks = [];

// 接收来自扩展的历史数据
window.addEventListener('message', (event) => {
    const message = event.data;
    console.log('📨 前端收到消息:', message);

    if (message.type === 'historyData') {
        handleHistoryData(message.payload);
    }
});

function handleHistoryData(tasks) {
    allTasks = tasks || [];
    renderHistoryList(allTasks);
}

function renderHistoryList(tasks) {
    historyListEl.innerHTML = '';

    if (tasks.length === 0) {
        historyListEl.style.display = 'none';
        emptyStateEl.style.display = 'flex';
        return;
    }

    historyListEl.style.display = 'block';
    emptyStateEl.style.display = 'none';

    tasks.forEach(task => {
        const item = createTaskItem(task);
        historyListEl.appendChild(item);
    });
}

function createTaskItem(task) {
    const item = document.createElement('div');
    item.className = `history-item status-${task.status}`;

    const statusIcon = getStatusIcon(task.status);
    const typeLabel = getTypeLabel(task.type);

    item.innerHTML = `
        <div class="item-header">
            <div class="item-meta">
                <span class="status-icon">${statusIcon}</span>
                <div class="item-info">
                    <div class="item-title">${escapeHtml(task.title)}</div>
                    <div class="item-type">${typeLabel}</div>
                </div>
            </div>
            <div class="item-time">${task.timeAgo}</div>
        </div>
        <div class="item-actions">
            <button class="action-btn" onclick="handleViewTask('${task.taskId}')">查看</button>
            <button class="action-btn secondary" onclick="handleCopyTaskId('${task.taskId}')">📋</button>
            <button class="action-btn danger-action" onclick="handleDeleteTask('${task.taskId}')">✕</button>
        </div>
    `;

    return item;
}

function getStatusIcon(status) {
    switch (status) {
        case 'done':
            return '✓';
        case 'pending':
            return '⏳';
        case 'error':
            return '✕';
        default:
            return '?';
    }
}

function getTypeLabel(type) {
    const labels = {
        'qwen_generate': '🤖 AI 生成',
        'add_numbers': '🧮 加法计算',
        'default': '📋 任务'
    };
    return labels[type] || labels['default'];
}

function handleViewTask(taskId) {
    vscode.postMessage({ type: 'viewTask', taskId });
}

function handleCopyTaskId(taskId) {
    vscode.postMessage({ type: 'copyTaskId', taskId });
}

function handleDeleteTask(taskId) {
    vscode.postMessage({ type: 'deleteTask', taskId });
}

// 搜索功能
searchInput.addEventListener('input', (e) => {
    const keyword = e.target.value.toLowerCase().trim();
    if (!keyword) {
        renderHistoryList(allTasks);
        return;
    }

    const filtered = allTasks.filter(task => 
        task.title.toLowerCase().includes(keyword) ||
        task.taskId.toLowerCase().includes(keyword) ||
        task.type.toLowerCase().includes(keyword)
    );

    renderHistoryList(filtered);
});

// 刷新按钮
btnRefresh.addEventListener('click', () => {
    vscode.postMessage({ type: 'ready' });
});

// 清空历史按钮
btnClear.addEventListener('click', () => {
    vscode.postMessage({ type: 'clearHistory' });
});

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}
