// src/panels/reactPanel.ts
// React Webview 面板 - 使用 Vite + React 构建的现代化 UI

import * as vscode from 'vscode';
import { getNonce } from '../utils/getNonce';
import { websocketService } from '../services/websocketService';

export class ReactPanel {
  private static currentPanel: ReactPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private currentTaskId: string | null = null;

  public static show(extensionUri: vscode.Uri): ReactPanel {
    if (ReactPanel.currentPanel) {
      ReactPanel.currentPanel.panel.reveal(vscode.ViewColumn.Beside);
      return ReactPanel.currentPanel;
    }

    const panel = vscode.window.createWebviewPanel(
      'alphapilotReact',
      'AlphaPilot Chat (React)',
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, 'webview-dist')
        ]
      }
    );

    ReactPanel.currentPanel = new ReactPanel(panel, extensionUri);
    return ReactPanel.currentPanel;
  }

  private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
    this.panel = panel;
    this.panel.webview.html = this.getHtmlForWebview(extensionUri);

    // 监听 Webview 消息
    this.panel.webview.onDidReceiveMessage(
      (message) => this.handleMessage(message),
      null,
      this.disposables
    );

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    // ⭐ 新增：订阅 WebSocket 事件并转发给 Webview
    this.setupWebSocketListeners();
  }

  /**
   * 设置 WebSocket 事件监听器
   */
  private setupWebSocketListeners(): void {
    // 任务已开始
    websocketService.on('task_started', (data) => {
      console.log('📥 WebSocket: task_started', data);
      this.currentTaskId = data.task_id;
      this.panel.webview.postMessage({
        type: 'task_started',
        payload: data
      });
    });

    // 步骤已开始
    websocketService.on('step_started', (data) => {
      console.log('📥 WebSocket: step_started', data);
      this.panel.webview.postMessage({
        type: 'step_started',
        payload: data
      });
    });

    // 步骤已完成
    websocketService.on('step_finished', (data) => {
      console.log('📥 WebSocket: step_finished', data);
      this.panel.webview.postMessage({
        type: 'step_finished',
        payload: data
      });
    });

    // 流式数据块
    websocketService.on('stream_chunk', (data) => {
      console.log('📥 WebSocket: stream_chunk 收到数据:', JSON.stringify(data, null, 2));
      
      // 检查数据格式
      if (!data || !data.task_id) {
        console.error(' stream_chunk 数据格式错误:', data);
        return;
      }
      
      console.log('📤 转发到 Webview - task_id:', data.task_id, 'chunk:', data.chunk?.substring(0, 50));
      
      this.panel.webview.postMessage({
        type: 'stream_chunk',
        payload: data
      });
    });

    // 任务已完成 (兼容 task_result 和 task_completed)
    websocketService.on('task_result', (data) => {
      console.log('📥 WebSocket: task_result', data);
      
      // 根据任务状态判断是成功还是失败
      if (data.status === 'error') {
        this.panel.webview.postMessage({
          type: 'task_failed',
          payload: {
            task_id: data.task_id,
            error: data.error || { message: 'Unknown error' }
          }
        });
      } else {
        this.panel.webview.postMessage({
          type: 'task_completed',
          payload: {
            task_id: data.task_id,
            result: data.result || data
          }
        });
      }
      
      this.currentTaskId = null;
    });

    // 兼容旧版本的 task_completed 事件
    websocketService.on('task_completed', (data) => {
      console.log('📥 WebSocket: task_completed (legacy)', data);
      this.panel.webview.postMessage({
        type: 'task_completed',
        payload: data
      });
      this.currentTaskId = null;
    });

    // 兼容旧版本的 task_failed 事件
    websocketService.on('task_failed', (data) => {
      console.log('📥 WebSocket: task_failed (legacy)', data);
      this.panel.webview.postMessage({
        type: 'task_failed',
        payload: data
      });
      this.currentTaskId = null;
    });
  }

  private handleMessage(message: any): void {
    console.log('📥 Webview → Extension:', message);

    switch (message.type) {
      case 'submit_task':
        this.handleSubmitTask(message.payload);
        break;

      case 'cancel_task':
        this.handleCancelTask(message.payload);
        break;

      case 'clear_chat':
        this.handleClearChat();
        break;
    }
  }

  private async handleSubmitTask(payload: any): Promise<void> {
    try {
      const { prompt, model } = payload;
      
      // 调用 Node API 提交任务
      const response = await fetch('http://localhost:3000/task/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: model,
          payload: { prompt },
          source: 'react-webview'
        })
      });

      const data = await response.json();
      const taskId = data.task_id;

      console.log('✅ 任务提交成功:', taskId);

      //  关键修复：立即向 Webview 发送 task_started 消息
      this.panel.webview.postMessage({
        type: 'task_started',
        payload: {
          task_id: taskId,
          prompt: prompt,
          model: model
        }
      });

      // 订阅任务更新
      websocketService.subscribeTask(taskId);
      this.currentTaskId = taskId;
      
    } catch (error: any) {
      console.error('❌ 提交任务失败:', error);
      this.panel.webview.postMessage({
        type: 'task_failed',
        payload: {
          error: { message: error.message }
        }
      });
    }
  }

  private handleCancelTask(payload: any): void {
    // TODO: 调用 Node API 取消任务
    console.log('⏹️ 取消任务:', payload.taskId);
  }

  private handleClearChat(): void {
    console.log('🗑️ 清空聊天');
    // Webview 会自行清空状态
  }

  public setTaskId(taskId: string): void {
    // 设置当前任务 ID
    console.log('📋 设置任务 ID:', taskId);
  }

  private getHtmlForWebview(extensionUri: vscode.Uri): string {
    const scriptUri = this.panel.webview.asWebviewUri(
      vscode.Uri.joinPath(extensionUri, 'webview-dist', 'assets', 'index.js')
    );

    const styleUri = this.panel.webview.asWebviewUri(
      vscode.Uri.joinPath(extensionUri, 'webview-dist', 'assets', 'index.css')
    );

    const nonce = getNonce();

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${this.panel.webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>AlphaPilot Chat</title>
  <link href="${styleUri}" rel="stylesheet">
</head>
<body>
  <div id="root"></div>
  <script type="module" nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }

  public dispose(): void {
    ReactPanel.currentPanel = undefined;
    this.panel.dispose();
    
    // 取消 WebSocket 订阅
    if (this.currentTaskId) {
      websocketService.unsubscribeTask(this.currentTaskId);
    }
    
    while (this.disposables.length) {
      const disposable = this.disposables.pop();
      if (disposable) {
        disposable.dispose();
      }
    }
  }
}
