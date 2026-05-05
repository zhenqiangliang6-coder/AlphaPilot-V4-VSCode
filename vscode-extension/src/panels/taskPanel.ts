// src/panels/taskPanel.ts
// 主任务面板 - 统一管理 AI 结果和任务树

import * as vscode from 'vscode';
import { websocketService } from '../services/websocketService';
import { streamingService } from '../services/streamingService';
import { taskService } from '../services/taskService';

export class TaskPanel {
  private static currentPanel: TaskPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private isReady = false;
  private pendingMessages: any[] = [];
  private currentTaskId: string | null = null;
  private isStreaming = false;

  public static show(extensionUri: vscode.Uri): TaskPanel {
    if (TaskPanel.currentPanel) {
      TaskPanel.currentPanel.panel.reveal(vscode.ViewColumn.Beside);
      return TaskPanel.currentPanel;
    }

    const panel = vscode.window.createWebviewPanel(
      'alphapilotTask',
      'AlphaPilot · 智能体任务执行',
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, 'src', 'webviews')
        ]
      }
    );

    TaskPanel.currentPanel = new TaskPanel(panel, extensionUri);
    return TaskPanel.currentPanel;
  }

  private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
    this.panel = panel;
    this.panel.webview.html = this.getHtmlForWebview(extensionUri);

    // 监听 Webview 消息
    this.panel.webview.onDidReceiveMessage(
      (message) => {
        switch (message.type) {
          case 'webview_ready':
            this.isReady = true;
            console.log('✅ Webview 已就绪');
            // 发送缓存的消息
            while (this.pendingMessages.length > 0) {
              this.panel.webview.postMessage(this.pendingMessages.shift());
            }
            break;

          case 'submit_task':
            // ⭐ 处理从 Webview 提交的任务
            this.handleSubmitTask(message.prompt, message.model);
            break;

          case 'pause_stream':
            if (this.currentTaskId) {
              streamingService.pauseStream(this.currentTaskId);
            }
            break;

          case 'resume_stream':
            if (this.currentTaskId) {
              streamingService.resumeStream(this.currentTaskId);
            }
            break;

          case 'stop_task':
            if (this.currentTaskId) {
              taskService.cancelTask(this.currentTaskId);
            }
            break;

          case 'retry_step':
            // TODO: 实现步骤重试逻辑
            console.log('🔄 重试步骤:', message.stepId);
            break;

          case 'skip_step':
            // TODO: 实现步骤跳过逻辑
            console.log('⏭️ 跳过步骤:', message.stepId);
            break;

          case 'model_changed':
            // 模型切换
            console.log('🔄 模型已切换为:', message.model);
            break;
        }
      },
      null,
      this.disposables
    );

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
  }

  public dispose() {
    TaskPanel.currentPanel = undefined;
    this.panel.dispose();
    while (this.disposables.length) {
      this.disposables.pop()?.dispose();
    }
  }

  /**
   * 设置当前任务 ID
   */
  public setTaskId(taskId: string): void {
    this.currentTaskId = taskId;
    this.postMessage({ type: 'set_task_id', taskId });
    
    // 订阅 WebSocket 事件
    websocketService.subscribeTask(taskId);
  }

  /**
   * 处理 WebSocket 事件
   */
  public handleEvent(event: any): void {
    console.log('📨 面板收到事件:', event);

    // 根据事件类型分发到 Webview
    switch (event.event || Object.keys(event)[0]) {
      case 'stream_start':
      case 'streamStart':
        this.startStreaming();
        break;

      case 'stream_chunk':
      case 'streamChunk':
        const chunk = event.chunk || (Object.keys(event)[0] && event[Object.keys(event)[0]].chunk);
        if (chunk) {
          this.appendContent(chunk);
        }
        break;

      case 'stream_end':
      case 'streamEnd':
        this.endStreaming();
        break;

      case 'step_started':
      case 'stepStarted':
        const stepStarted = event.step_type || event.stepStarted;
        this.postMessage({ 
          type: 'step_started', 
          stepType: stepStarted,
          stepId: event.step_id 
        });
        break;

      case 'step_finished':
      case 'stepFinished':
        this.postMessage({ 
          type: 'step_finished',
          stepId: event.step_id,
          output: event.output 
        });
        break;

      case 'task_started':
      case 'taskStarted':
        this.postMessage({ type: 'task_started' });
        break;

      case 'task_completed':
      case 'taskCompleted':
        this.postMessage({ 
          type: 'task_completed',
          result: event.result 
        });
        break;

      case 'task_failed':
      case 'taskFailed':
        this.postMessage({ 
          type: 'task_failed',
          error: event.error 
        });
        break;

      case 'task_cancelled':
      case 'taskCancelled':
        this.postMessage({ 
          type: 'task_cancelled',
          reason: event.reason 
        });
        break;
    }
  }

  private startStreaming(): void {
    this.isStreaming = true;
    this.postMessage({ type: 'stream_start' });
  }

  private appendContent(content: string): void {
    this.postMessage({ type: 'append', content });
  }

  private endStreaming(): void {
    this.isStreaming = false;
    this.postMessage({ type: 'stream_end' });
  }

  /**
   * ⭐ 处理从 Webview 提交的任务
   */
  private async handleSubmitTask(prompt: string, model: string): Promise<void> {
    try {
      console.log(`📤 提交任务: ${prompt.substring(0, 50)}... (模型: ${model})`);
      
      // 调用 TaskService 提交任务
      const taskId = await taskService.submitTask(prompt, model);
      
      // 保存当前任务 ID
      this.currentTaskId = taskId;
      
      // 通知 Extension 保存任务 ID (确保 extension.ts 中注册了此命令)
      vscode.commands.executeCommand('alphapilot.saveTaskId', taskId);
      
      console.log(`✅ 任务已提交: ${taskId}`);
    } catch (error: any) {
      console.error('❌ 提交任务失败:', error);
      this.postMessage({
        type: 'task_failed',
        error: error.message
      });
    }
  }

  private postMessage(message: any): void {
    if (this.isReady) {
      this.panel.webview.postMessage(message);
    } else {
      this.pendingMessages.push(message);
    }
  }

  /**
   * 生成 Webview HTML
   */
  private getHtmlForWebview(extensionUri: vscode.Uri): string {
    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AlphaPilot - AI 编程助手</title>
  <style>
    :root {
      --primary-color: #007acc;
      --success-color: #4caf50;
      --warning-color: #ff9800;
      --error-color: #f44336;
      --bg-color: var(--vscode-editor-background);
      --text-color: var(--vscode-editor-foreground);
      --border-color: var(--vscode-panel-border);
      --hover-bg: var(--vscode-list-hoverBackground);
    }

    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background-color: var(--bg-color);
      color: var(--text-color);
      height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* 顶部工具栏 */
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      border-bottom: 1px solid var(--border-color);
      background-color: var(--vscode-titleBar-activeBackground);
    }

    .toolbar-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .logo {
      font-size: 18px;
      font-weight: 600;
      color: var(--primary-color);
    }

    .model-selector {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .model-selector label {
      font-size: 13px;
      opacity: 0.8;
    }

    .model-selector select {
      padding: 6px 12px;
      border: 1px solid var(--border-color);
      border-radius: 4px;
      background-color: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      font-size: 13px;
      cursor: pointer;
      outline: none;
    }

    .model-selector select:hover {
      border-color: var(--primary-color);
    }

    .toolbar-right {
      display: flex;
      gap: 8px;
    }

    .btn {
      padding: 6px 12px;
      border: 1px solid var(--border-color);
      border-radius: 4px;
      background-color: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
    }

    .btn:hover {
      opacity: 0.9;
      transform: translateY(-1px);
    }

    .btn:active {
      transform: translateY(0);
    }

    .btn-secondary {
      background-color: transparent;
      border-color: var(--border-color);
    }

    /* 主内容区 */
    .main-container {
      flex: 1;
      display: flex;
      overflow: hidden;
    }

    /* 左侧步骤树 */
    .sidebar {
      width: 280px;
      border-right: 1px solid var(--border-color);
      overflow-y: auto;
      padding: 12px;
    }

    .sidebar-title {
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 12px;
      opacity: 0.8;
    }

    .step-tree {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .step-item {
      padding: 10px;
      border-radius: 6px;
      background-color: var(--vscode-editor-inactiveSelectionBackground);
      border-left: 3px solid transparent;
      transition: all 0.2s;
    }

    .step-item.active {
      border-left-color: var(--primary-color);
      background-color: var(--vscode-list-activeSelectionBackground);
    }

    .step-item.completed {
      border-left-color: var(--success-color);
    }

    .step-item.error {
      border-left-color: var(--error-color);
    }

    .step-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }

    .step-icon {
      font-size: 16px;
    }

    .step-name {
      font-size: 13px;
      font-weight: 500;
      flex: 1;
    }

    .step-status {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 12px;
      background-color: var(--primary-color);
      color: white;
    }

    .progress-bar {
      height: 4px;
      background-color: var(--vscode-progressBar-background);
      border-radius: 2px;
      overflow: hidden;
    }

    .progress-fill {
      height: 100%;
      background-color: var(--primary-color);
      transition: width 0.3s ease;
    }

    /* 右侧聊天区 */
    .chat-area {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .messages-container {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .message {
      max-width: 85%;
      animation: fadeIn 0.3s ease;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .message.user {
      align-self: flex-end;
    }

    .message.ai {
      align-self: flex-start;
    }

    .message-bubble {
      padding: 12px 16px;
      border-radius: 12px;
      line-height: 1.6;
      font-size: 14px;
    }

    .message.user .message-bubble {
      background-color: var(--primary-color);
      color: white;
      border-bottom-right-radius: 4px;
    }

    .message.ai .message-bubble {
      background-color: var(--vscode-editor-inactiveSelectionBackground);
      border-bottom-left-radius: 4px;
    }

    .message-time {
      font-size: 11px;
      opacity: 0.6;
      margin-top: 4px;
      text-align: right;
    }

    /* 输入框区域 */
    .input-area {
      border-top: 1px solid var(--border-color);
      padding: 16px;
      background-color: var(--vscode-editor-background);
    }

    .input-wrapper {
      display: flex;
      gap: 8px;
      align-items: flex-end;
    }

    .input-field {
      flex: 1;
      padding: 10px 14px;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      background-color: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      font-size: 14px;
      resize: none;
      outline: none;
      min-height: 44px;
      max-height: 120px;
      font-family: inherit;
    }

    .input-field:focus {
      border-color: var(--primary-color);
    }

    .send-btn {
      padding: 10px 20px;
      background-color: var(--primary-color);
      color: white;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      transition: all 0.2s;
    }

    .send-btn:hover {
      opacity: 0.9;
      transform: translateY(-1px);
    }

    .send-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    /* 状态栏 */
    .status-bar {
      padding: 8px 16px;
      border-top: 1px solid var(--border-color);
      font-size: 12px;
      opacity: 0.8;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .typing-indicator {
      display: inline-flex;
      gap: 4px;
      align-items: center;
    }

    .typing-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: var(--primary-color);
      animation: typing 1.4s infinite;
    }

    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }

    @keyframes typing {
      0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
      30% { opacity: 1; transform: scale(1); }
    }

    /* 代码块样式 */
    pre {
      background-color: var(--vscode-textCodeBlock-background);
      padding: 12px;
      border-radius: 6px;
      overflow-x: auto;
      margin: 8px 0;
    }

    code {
      font-family: 'Consolas', 'Monaco', monospace;
      font-size: 13px;
    }
  </style>
</head>
<body>
  <!-- 顶部工具栏 -->
  <div class="toolbar">
    <div class="toolbar-left">
      <div class="logo">🚀 AlphaPilot</div>
      <div class="model-selector">
        <label for="modelSelect">模型:</label>
        <select id="modelSelect">
          <option value="qwen_generate">通义千问 (Qwen)</option>
          <option value="deepseek_generate">深度求索 (DeepSeek)</option>
          <option value="doubao_generate">豆包 (Doubao)</option>
        </select>
      </div>
    </div>
    <div class="toolbar-right">
      <button class="btn btn-secondary" id="btnClear" title="清空对话">🗑️ 清空</button>
      <button class="btn btn-secondary" id="btnPause" title="暂停输出">⏸️ 暂停</button>
      <button class="btn btn-secondary" id="btnResume" title="继续输出" style="display:none;">▶️ 继续</button>
      <button class="btn" id="btnStop" title="停止任务">⏹️ 停止</button>
    </div>
  </div>

  <!-- 主内容区 -->
  <div class="main-container">
    <!-- 左侧步骤树 -->
    <div class="sidebar">
      <div class="sidebar-title">执行步骤</div>
      <div class="step-tree" id="stepTree">
        <!-- 步骤将动态渲染 -->
      </div>
    </div>

    <!-- 右侧聊天区 -->
    <div class="chat-area">
      <div class="messages-container" id="messagesContainer">
        <!-- 消息将动态渲染 -->
      </div>

      <!-- 输入框 -->
      <div class="input-area">
        <div class="input-wrapper">
          <textarea 
            class="input-field" 
            id="inputField" 
            placeholder="输入你的问题... (Shift+Enter 换行)"
            rows="1"
          ></textarea>
          <button class="send-btn" id="sendBtn">发送 ➤</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 状态栏 -->
  <div class="status-bar">
    <span id="statusText">准备就绪</span>
    <span id="charCount"></span>
  </div>

  <script>
    const vscode = acquireVsCodeApi();
    let currentTaskId = null;
    let charCount = 0;
    let isPaused = false;
    let selectedModel = 'qwen_generate';

    // VS Code API 就绪
    window.onload = () => {
      vscode.postMessage({ type: 'webview_ready' });
      
      // 加载保存的模型选择
      const savedModel = localStorage.getItem('selected_model');
      if (savedModel) {
        document.getElementById('modelSelect').value = savedModel;
        selectedModel = savedModel;
      }
    };

    // 监听来自 Extension 的消息
    window.addEventListener('message', (event) => {
      const msg = event.data;
      console.log('📨 Webview 收到消息:', msg.type);

      switch (msg.type) {
        case 'set_task_id':
          currentTaskId = msg.taskId;
          break;

        case 'stream_start':
          addAIMessage('🔄 AI 正在思考中...', true);
          updateStatus('流式输出中...');
          break;

        case 'append':
          appendToLastMessage(msg.content);
          charCount += msg.content.length;
          updateCharCount();
          break;

        case 'stream_end':
          updateStatus('✨ 完成');
          break;

        case 'step_started':
          renderStepStarted(msg.stepType, msg.stepId);
          break;

        case 'step_finished':
          renderStepFinished(msg.stepId, msg.output);
          break;

        case 'task_started':
          updateStatus('🚀 任务已开始');
          break;

        case 'task_completed':
          updateStatus('🎉 任务已完成');
          break;

        case 'task_failed':
          updateStatus('❌ 任务失败：' + msg.error);
          addAIMessage('❌ 任务执行失败: ' + msg.error);
          break;

        case 'task_cancelled':
          updateStatus('⏹️ 任务已取消');
          break;
      }
    });

    // 模型选择变化
    document.getElementById('modelSelect').addEventListener('change', (e) => {
      selectedModel = e.target.value;
      localStorage.setItem('selected_model', selectedModel);
      vscode.postMessage({ 
        type: 'model_changed', 
        model: selectedModel 
      });
    });

    // 发送消息
    document.getElementById('sendBtn').addEventListener('click', sendMessage);
    document.getElementById('inputField').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    function sendMessage() {
      const input = document.getElementById('inputField');
      const message = input.value.trim();
      
      if (!message) return;

      // 添加用户消息
      addUserMessage(message);
      
      // 清空输入框
      input.value = '';
      input.style.height = 'auto';

      // 提交任务到后端
      vscode.postMessage({
        type: 'submit_task',
        prompt: message,
        model: selectedModel
      });
    }

    function addUserMessage(text) {
      const container = document.getElementById('messagesContainer');
      const messageDiv = document.createElement('div');
      messageDiv.className = 'message user';
      messageDiv.innerHTML = \`
        <div class="message-bubble">\${escapeHtml(text)}</div>
        <div class="message-time">\${new Date().toLocaleTimeString()}</div>
      \`;
      container.appendChild(messageDiv);
      scrollToBottom();
    }

    function addAIMessage(text, isStreaming = false) {
      const container = document.getElementById('messagesContainer');
      const messageDiv = document.createElement('div');
      messageDiv.className = 'message ai';
      messageDiv.id = isStreaming ? 'streaming-message' : null;
      messageDiv.innerHTML = \`
        <div class="message-bubble">\${formatMarkdown(text)}</div>
        \${!isStreaming ? '<div class="message-time">' + new Date().toLocaleTimeString() + '</div>' : ''}
      \`;
      container.appendChild(messageDiv);
      scrollToBottom();
    }

    function appendToLastMessage(content) {
      let streamingMsg = document.getElementById('streaming-message');
      if (!streamingMsg) {
        addAIMessage('', true);
        streamingMsg = document.getElementById('streaming-message');
      }
      
      const bubble = streamingMsg.querySelector('.message-bubble');
      bubble.innerHTML += escapeHtml(content);
      scrollToBottom();
    }

    // 按钮事件
    document.getElementById('btnPause').addEventListener('click', () => {
      isPaused = true;
      vscode.postMessage({ type: 'pause_stream' });
      document.getElementById('btnPause').style.display = 'none';
      document.getElementById('btnResume').style.display = 'inline-block';
      updateStatus('⏸️ 已暂停');
    });

    document.getElementById('btnResume').addEventListener('click', () => {
      isPaused = false;
      vscode.postMessage({ type: 'resume_stream' });
      document.getElementById('btnResume').style.display = 'none';
      document.getElementById('btnPause').style.display = 'inline-block';
      updateStatus('▶️ 继续输出中...');
    });

    document.getElementById('btnStop').addEventListener('click', () => {
      if (currentTaskId) {
        vscode.postMessage({ type: 'stop_task' });
        updateStatus('⏸️ 正在停止...');
      }
    });

    document.getElementById('btnClear').addEventListener('click', () => {
      document.getElementById('messagesContainer').innerHTML = '';
      document.getElementById('stepTree').innerHTML = '';
      charCount = 0;
      updateCharCount();
      updateStatus('已清空');
    });

    // 自动调整输入框高度
    document.getElementById('inputField').addEventListener('input', function() {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    function updateStatus(text) {
      document.getElementById('statusText').textContent = text;
    }

    function updateCharCount() {
      document.getElementById('charCount').textContent = \`\${charCount} 字\`;
    }

    function scrollToBottom() {
      const container = document.getElementById('messagesContainer');
      container.scrollTop = container.scrollHeight;
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    function formatMarkdown(text) {
      // 简单的 Markdown 格式化
      return text
        .replace(/\`\`\`([\\w]*)\\n([\\s\\S]*?)\`\`\`/g, '<pre><code>$2</code></pre>')
        .replace(/\`([^\\']+)\`/g, '<code>$1</code>')
        .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
        .replace(/\\*(.+?)\\*/g, '<em>$1</em>')
        .replace(/\\n/g, '<br>');
    }

    function renderStepStarted(stepType, stepId) {
      const stepTree = document.getElementById('stepTree');
      const stepItem = document.createElement('div');
      stepItem.className = 'step-item active';
      stepItem.id = 'step-' + stepId;
      stepItem.innerHTML = \`
        <div class="step-header">
          <span class="step-icon">▶️</span>
          <span class="step-name">\${getStepName(stepType)}</span>
          <span class="step-status">运行中</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" style="width: 30%"></div>
        </div>
      \`;
      stepTree.appendChild(stepItem);
      stepTree.parentElement.scrollTop = stepTree.scrollHeight;
    }

    function renderStepFinished(stepId, output) {
      const stepItem = document.getElementById('step-' + stepId);
      if (stepItem) {
        stepItem.classList.remove('active');
        stepItem.classList.add('completed');
        stepItem.querySelector('.step-icon').textContent = '✓';
        stepItem.querySelector('.step-status').textContent = '完成';
        stepItem.querySelector('.step-status').style.backgroundColor = '#4caf50';
        stepItem.querySelector('.progress-fill').style.width = '100%';
      }
    }

    function getStepName(stepType) {
      const names = {
        'analyze': '分析需求',
        'plan': '制定计划',
        'write': '编写代码',
        'refine': '优化代码',
        'test': '测试验证',
        'fix': '修复错误',
        'profile': '性能分析',
        'doc': '生成文档'
      };
      return names[stepType] || stepType;
    }
  </script>
</body>
</html>`;
  }

}
