// src/utils/vscode.ts
import type { WebviewApi } from 'vscode-webview';

/**
 * VSCode Webview API 封装
 */
class VSCodeAPI {
  private vscode: WebviewApi<unknown>;

  constructor() {
    this.vscode = acquireVsCodeApi();
  }

  /**
   * 发送消息到 Extension
   */
  postMessage(message: any): void {
    console.log('📤 Webview → Extension:', message);
    this.vscode.postMessage(message);
  }

  /**
   * 设置状态
   */
  setState(state: any): void {
    this.vscode.setState(state);
  }

  /**
   * 获取状态
   */
  getState(): any {
    return this.vscode.getState();
  }
}

export const vscodeAPI = new VSCodeAPI();

/**
 * 消息类型定义
 */
export interface WebviewMessage {
  type: string;
  payload?: any;
}

/**
 * 便捷方法: 提交任务
 */
export function submitTask(prompt: string, model: string): void {
  vscodeAPI.postMessage({
    type: 'submit_task',
    payload: {
      prompt,
      model
    }
  });
}

/**
 * 便捷方法: 取消任务
 */
export function cancelTask(taskId: string): void {
  vscodeAPI.postMessage({
    type: 'cancel_task',
    payload: { taskId }
  });
}

/**
 * 便捷方法: 清空对话
 */
export function clearChat(): void {
  vscodeAPI.postMessage({
    type: 'clear_chat'
  });
}
