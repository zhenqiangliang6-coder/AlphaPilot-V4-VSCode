// src/panels/reactPanel.ts
// React Webview 面板 - 使用 Vite + React 构建的现代化 UI

import * as vscode from 'vscode';
import { getNonce } from '../utils/getNonce';
import { websocketService } from '../services/websocketService';
import { taskProtocolAdapter } from '../services/taskProtocolAdapter';
import { applyWorkspaceDeleteOps } from '../services/workspaceDelete';

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
        ],
        // ⭐ v3.0: 配置端口映射，允许 Webview 访问 Node API
        portMapping: [
          { webviewPort: 3000, extensionHostPort: 3000 }
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

    // Worker progress chunks are nested by the Node API; normalize once for the webview.
    const forwardStreamChunk = (data: any) => {
      const chunkData =
        data?.chunk && typeof data.chunk === 'object' ? data.chunk : data;
      const chunk =
        typeof chunkData?.content === 'string'
          ? chunkData.content
          : typeof chunkData?.chunk === 'string'
            ? chunkData.chunk
            : '';
      const taskId = data?.task_id || chunkData?.task_id;
      if (!taskId || !chunk) {
        console.warn('⚠️ 忽略格式无效的 stream_chunk:', data);
        return;
      }

      this.panel.webview.postMessage({
        type: 'stream_chunk',
        payload: {
          task_id: taskId,
          chunk,
          phase: chunkData.phase,
          channel: chunkData.channel
        }
      });
    };
    websocketService.on('task_stream_chunk', forwardStreamChunk);
    websocketService.on('stream_chunk', forwardStreamChunk);

    // ⭐ v2.7 新增：监听 file_ops 事件并转发给 Webview
    websocketService.on('file_ops', (data) => {
      console.log('📁 WebSocket: file_ops', data);
      
      // ⭐ 严格禁止修改/过滤 fileOps，原样转发
      // 这是架构信条 "Extension = 映射" 的核心要求
      this.panel.webview.postMessage({
        type: 'file_ops',
        payload: {
          taskId: data.taskId,
          fileOps: data.fileOps  // 原样推送，不做任何修改
        }
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
      
      // ⭐ v2.7 新增：处理 apply_file_ops 请求
      case 'apply_file_ops':
        this.handleApplyFileOps(message.payload);
        break;
    }
  }

  private async handleSubmitTask(payload: any): Promise<void> {
    try {
      const { prompt, model } = payload;
      const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      
      // 调用 Node API 提交任务
      const submission = taskProtocolAdapter.createSubmission(model, prompt, {
        workspace_path: workspacePath,
        source: 'react-webview'
      });
      const response = await fetch('http://localhost:3000/task/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(submission)
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
      }
      const data = taskProtocolAdapter.adaptSubmissionResponse(
        await response.json(),
        submission.trace_id
      );
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

  // ⭐ v2.7 新增：处理 apply_file_ops 请求,真正写盘
  private async handleApplyFileOps(payload: any): Promise<void> {
    const { taskId, fileOps } = payload;
    
    console.log('📁 应用文件操作:', { taskId, count: fileOps.length });
    
    try {
      // 获取工作区根目录
      const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
      if (!workspaceRoot) {
        vscode.window.showErrorMessage('❌ 未打开工作区文件夹');
        return;
      }

      const deletionOps = fileOps
        .filter((op: any) => op.action === 'delete' && typeof op.path === 'string')
        .map((op: any) => ({ op: 'delete' as const, path: op.path }));
      if (deletionOps.length > 0) {
        const deletion = await applyWorkspaceDeleteOps(deletionOps, workspaceRoot);
        if (deletion.rejected.length > 0) {
          throw new Error(deletion.rejected.join('\n'));
        }
        if (deletion.cancelled) {
          this.panel.webview.postMessage({
            type: 'file_ops_applied',
            success: false,
            error: '删除操作已取消',
            taskId,
          });
          return;
        }
      }
      
      let successCount = 0;
      let errorCount = 0;
      
      // 遍历所有文件操作
      for (const op of fileOps) {
        try {
          if (op.action === 'delete') continue;
          const uri = vscode.Uri.joinPath(workspaceRoot, op.path);
          
          if (op.action === 'create' && op.type === 'file') {
            // 创建文件
            await vscode.workspace.fs.writeFile(
              uri, 
              Buffer.from(op.content || '', 'utf8')
            );
            console.log(`✅ Created: ${op.path}`);
            successCount++;
          }
          
          if (op.action === 'modify' && op.type === 'file') {
            // 修改文件
            await vscode.workspace.fs.writeFile(
              uri, 
              Buffer.from(op.content || '', 'utf8')
            );
            console.log(`✅ Modified: ${op.path}`);
            successCount++;
          }
          
          if (op.action === 'create' && op.type === 'folder') {
            // 创建目录
            await vscode.workspace.fs.createDirectory(uri);
            console.log(`✅ Created directory: ${op.path}`);
            successCount++;
          }
          
        } catch (error) {
          console.error(`❌ Failed to apply operation: ${op.path}`, error);
          errorCount++;
        }
      }
      
      // 显示结果通知
      if (errorCount === 0) {
        vscode.window.showInformationMessage(
          `✅ 成功应用 ${successCount} 个文件操作`
        );
      } else {
        vscode.window.showWarningMessage(
          `⚠️ 部分操作失败: ${successCount} 成功, ${errorCount} 失败`
        );
      }
      
      // 通知 Webview 应用结果
      this.panel.webview.postMessage({
        type: 'file_ops_applied',
        success: errorCount === 0,
        successCount,
        errorCount,
        taskId
      });
      
    } catch (error: any) {
      console.error('❌ Failed to apply file ops:', error);
      vscode.window.showErrorMessage(
        `❌ 应用文件操作失败: ${error.message}`
      );
      
      // 通知 Webview 应用失败
      this.panel.webview.postMessage({
        type: 'file_ops_applied',
        success: false,
        error: error.message,
        taskId
      });
    }
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

    // ⭐ v3.0 最终修复：CSP 必须显式允许 localhost 和 ws 协议
    // 配合 portMapping 使用，确保 Webview 能穿透沙箱访问 Node API
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; 
    img-src vscode-resource: https: data:; 
    connect-src http://localhost:3000 ws://localhost:3000 ${this.panel.webview.cspSource}; 
    style-src ${this.panel.webview.cspSource} 'unsafe-inline'; 
    script-src 'nonce-${nonce}';">
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
