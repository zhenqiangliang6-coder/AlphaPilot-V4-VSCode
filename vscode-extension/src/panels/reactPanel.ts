// src/panels/reactPanel.ts
// React Webview 面板 - 使用 Vite + React 构建的现代化 UI

import * as vscode from 'vscode';
import * as path from 'path';
import * as crypto from 'crypto';
import { getNonce } from '../utils/getNonce';
import { websocketService } from '../services/websocketService';

export class ReactPanel {
  private static currentPanel: ReactPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private currentTaskId: string | null = null;
  private imageSessions: Map<string, string> = new Map();
  private webviewReady = false;
  private pendingWebviewMessages: any[] = [];

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

  public static postToCurrentPanel(extensionUri: vscode.Uri, message: any): void {
    ReactPanel.show(extensionUri).postToWebview(message);
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

    // P1：监听产物事件
    websocketService.on('artifact_created', (data) => {
      console.log('[P1] Extension 收到 artifact_created:', data.artifact_id);
      this.panel.webview.postMessage({
        type: 'artifact_created',
        payload: data
      });
    });

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
      this.cleanupTempImages(data.task_id);
    });

    // 兼容新版本的 task_result_v3
    websocketService.on('task_result_v3', (data) => {
      console.log('📥 WebSocket: task_result_v3 (compat)', data);
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
      this.cleanupTempImages(data.task_id);
    });

    // 兼容旧版本的 task_completed 事件
    websocketService.on('task_completed', (data) => {
      console.log('📥 WebSocket: task_completed (legacy)', data);
      this.panel.webview.postMessage({
        type: 'task_completed',
        payload: data
      });
      this.currentTaskId = null;
      this.cleanupTempImages(data.task_id);
    });

    // 兼容旧版本的 task_failed 事件
    websocketService.on('task_failed', (data) => {
      console.log('📥 WebSocket: task_failed (legacy)', data);
      this.panel.webview.postMessage({
        type: 'task_failed',
        payload: data
      });
      this.currentTaskId = null;
      this.cleanupTempImages(data.task_id);
    });
  }

  private handleMessage(message: any): void {
    console.log('📥 Webview → Extension:', message);

    switch (message.type) {
      case 'webview_ready':
        this.webviewReady = true;
        this.pendingWebviewMessages.splice(0).forEach((pending) => {
          void this.panel.webview.postMessage(pending);
        });
        break;

      case 'test_authorization_decision':
        websocketService.triggerLocal('test_authorization_decision', message.payload);
        break;

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

      // Phase 2.4 P0-4: 用户确认
      case 'confirm_task':
        this.handleConfirmTask(message.payload);
        break;

      case 'deny_task':
        this.handleDenyTask(message.payload);
        break;
    }

  }

  private postToWebview(message: any): void {
    if (!this.webviewReady) {
      this.pendingWebviewMessages.push(message);
      return;
    }
    void this.panel.webview.postMessage(message);
  }

  private async handleSubmitTask(payload: any): Promise<void> {
    let imageSessionId: string | null = null;
    try {
      const { prompt, model, images: webviewImages, conversationId } = payload;

      let imageRefs: { path: string; name: string }[] = [];

      if (webviewImages && webviewImages.length > 0) {
        imageSessionId = crypto.randomUUID();
        const wsRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
        if (wsRoot) {
          const sessionDir = vscode.Uri.joinPath(wsRoot, '.alphapilot', 'temp', imageSessionId);
          await vscode.workspace.fs.createDirectory(sessionDir);

          for (const img of webviewImages) {
            const base64Data = (img.base64 as string).replace(/^data:image\/\w+;base64,/, '');
            const buf = Buffer.from(base64Data, 'base64');
            const imgPath = `.alphapilot/temp/${imageSessionId}/${img.id}.jpg`;
            const imgUri = vscode.Uri.joinPath(wsRoot, imgPath);
            await vscode.workspace.fs.writeFile(imgUri, buf);
            imageRefs.push({ path: imgPath, name: img.name });
          }
        }
      }

      const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

      const response = await fetch('http://localhost:3000/task/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          type: model,
          payload: {
            prompt,
            images: imageRefs.length > 0 ? imageRefs : undefined,
            ...(workspacePath ? { workspace_path: workspacePath } : {}),
          },
          source: 'react-webview'
        })
      });

      const data = await response.json();
      console.log('📨 服务器响应:', data.status);

      if (data.status === 'confirmation_required') {
        console.log('🔔 任务需要用户确认:', data.confirmation);
        if (imageSessionId) {
          this.imageSessions.set(data.task_id, imageSessionId);
        }
        this.panel.webview.postMessage({
          type: 'confirmation_required',
          payload: data.confirmation,
        });
        return;
      }

      const taskId = data.task_id;

      console.log('✅ 任务提交成功:', taskId, imageRefs.length ? `(含 ${imageRefs.length} 张图片)` : '');

      if (imageSessionId) {
        this.imageSessions.set(taskId, imageSessionId);
      }

      this.panel.webview.postMessage({
        type: 'task_started',
        payload: {
          task_id: taskId,
          prompt: prompt,
          model: model
        }
      });

      websocketService.subscribeTask(taskId);
      this.currentTaskId = taskId;

    } catch (error: any) {
      console.error('❌ 提交任务失败:', error);
      if (imageSessionId) {
        await this.cleanupTempImages(imageSessionId);
      }
      this.panel.webview.postMessage({
        type: 'task_failed',
        payload: {
          error: { message: error.message }
        }
      });
    }
  }

  private async cleanupTempImages(sessionIdOrTaskId: string): Promise<void> {
    try {
      const sessionId = this.imageSessions.get(sessionIdOrTaskId) || sessionIdOrTaskId;
      const wsRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
      if (!wsRoot) { return; }
      const sessionDir = vscode.Uri.joinPath(wsRoot, '.alphapilot', 'temp', sessionId);
      await vscode.workspace.fs.delete(sessionDir, { recursive: true, useTrash: false });
      this.imageSessions.delete(sessionIdOrTaskId);
      console.log('🧹 Temp images cleaned:', sessionId);
    } catch {
      // Directory may not exist — safe to ignore
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
  // ⭐ R6 安全契约：写盘前调用 /auth/approve 完成审批
  private async handleApplyFileOps(payload: any): Promise<void> {
    const { taskId, fileOps } = payload;
    
    console.log('📁 应用文件操作:', { taskId, count: fileOps.length });

    try {
      // ⭐ R6：写盘前先调用 /auth/approve 完成授权审批
      const approveResp = await fetch('http://localhost:3000/auth/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId }),
      });
      if (!approveResp.ok) {
        throw new Error(`授权审批 HTTP ${approveResp.status}`);
      }
      const approveData = await approveResp.json();
      if (approveData.success !== true) {
        throw new Error(`授权审批失败: ${String(approveData.error || '未获准')}`);
      }
      console.log(`   🔓 [R6] 审批通过: task_id=${taskId}, approved_count=${approveData.approved_count}`);

      // 获取工作区根目录
      const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
      if (!workspaceRoot) {
        throw new Error('未打开工作区文件夹');
      }
      
      let successCount = 0;
      let errorCount = 0;
      
      // 遍历所有文件操作
      for (const op of fileOps) {
        try {
          const uri = vscode.Uri.joinPath(workspaceRoot, op.path);

          // ⭐ v3.4: 兼容 Worker 格式 (op.op / op.file_type) 和旧格式 (op.action / op.type)
          const action = op.op || op.action;
          const type = op.file_type || op.type || 'file';

          if (action === 'create' && type === 'file') {
            // 创建文件
            await vscode.workspace.fs.writeFile(
              uri,
              Buffer.from(op.content || '', 'utf8')
            );
            console.log(`✅ Created: ${op.path}`);
            successCount++;
          } else if (action === 'modify' && type === 'file') {
            // 修改文件
            await vscode.workspace.fs.writeFile(
              uri,
              Buffer.from(op.content || '', 'utf8')
            );
            console.log(`✅ Modified: ${op.path}`);
            successCount++;
          } else if (action === 'create' && type === 'folder') {
            // 创建目录
            await vscode.workspace.fs.createDirectory(uri);
            console.log(`✅ Created directory: ${op.path}`);
            successCount++;
          } else if (action === 'delete') {
            // 删除文件/目录
            await vscode.workspace.fs.delete(uri, { recursive: true });
            console.log(`✅ Deleted: ${op.path}`);
            successCount++;
          } else {
            // ⭐ 其他操作类型的文件写入（test, doc, rewrite 等）
            await vscode.workspace.fs.writeFile(
              uri,
              Buffer.from(op.content || '', 'utf8')
            );
            console.log(`✅ Written (${action}): ${op.path}`);
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
      websocketService.triggerLocal('file_ops_applied', {
        taskId,
        success: errorCount === 0,
        successCount,
        errorCount,
      });
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
      websocketService.triggerLocal('file_ops_applied', {
        taskId,
        success: false,
        error: error.message,
      });
      this.panel.webview.postMessage({
        type: 'file_ops_applied',
        success: false,
        error: error.message,
        taskId
      });
    }
  }

  // Phase 2.4 P0-4: 用户确认
  private async handleConfirmTask(payload: { confirmation_id: string; task_id: string }): Promise<void> {
    try {
      console.log('✅ 用户确认任务:', payload);
      const response = await fetch('http://localhost:3000/task/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confirmation_id: payload.confirmation_id,
          task_id: payload.task_id,
        }),
      });
      const data = await response.json();
      console.log('📨 confirm 响应:', data);

      if (data.status === 'submitted') {
        websocketService.subscribeTask(payload.task_id);
        this.currentTaskId = payload.task_id;

        // ⭐ 确认路径补充：发送 task_started，让前端显示 AI 占位 + 开启流式监听
        this.panel.webview.postMessage({
          type: 'task_started',
          payload: {
            task_id: payload.task_id,
            prompt: data.prompt || '',
            model: data.model || '',
          },
        });
      }

      this.panel.webview.postMessage({
        type: 'confirmation_resolved',
        payload: { status: data.status, task_id: payload.task_id },
      });
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      console.error('❌ 确认任务失败:', msg);
      this.panel.webview.postMessage({
        type: 'confirmation_resolved',
        payload: { status: 'error', task_id: payload.task_id, error: msg },
      });
    }
  }

  private async handleDenyTask(payload: { confirmation_id: string; task_id: string }): Promise<void> {
    try {
      console.log('❌ 用户拒绝任务:', payload);
      const response = await fetch('http://localhost:3000/task/deny', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confirmation_id: payload.confirmation_id,
          task_id: payload.task_id,
        }),
      });
      const data = await response.json();
      console.log('📨 deny 响应:', data);

      this.panel.webview.postMessage({
        type: 'confirmation_resolved',
        payload: { status: 'denied', task_id: payload.task_id },
      });
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      console.error('❌ 拒绝任务失败:', msg);
      this.panel.webview.postMessage({
        type: 'confirmation_resolved',
        payload: { status: 'error', task_id: payload.task_id, error: msg },
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
    script-src 'nonce-${nonce}' ${this.panel.webview.cspSource};">
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
    
    // 清理所有图片临时目录
    for (const sessionId of this.imageSessions.values()) {
      this.cleanupTempImages(sessionId);
    }
    
    while (this.disposables.length) {
      const disposable = this.disposables.pop();
      if (disposable) {
        disposable.dispose();
      }
    }
  }
}