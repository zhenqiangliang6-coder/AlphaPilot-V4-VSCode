// src/panels/taskHistoryPanel.ts
import * as vscode from 'vscode';
import { TaskHistoryManager } from '../taskHistory';

// ----------------------------
// 中文注释：任务历史面板（TaskHistoryPanel）
// ----------------------------
// 说明：这个面板负责把 `TaskHistoryManager` 中保存的历史数据显示在 Webview 中，
// 并处理面板内的交互（删除、查看详情、清空等）。
//
// 技术要点（菜鸟友好）：
// - 面板通过 postMessage 与 Webview 交换数据（发送 `historyData`）
// - 面板内的按钮会向扩展发送消息，扩展再调用 historyManager 做对应操作
// - 只改注释不会影响功能，注释仅作学习和维护用途

export class TaskHistoryPanel {
    private static currentPanel: TaskHistoryPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private disposables: vscode.Disposable[] = [];
    private isReady: boolean = false;
    private historyManager: TaskHistoryManager;

    public static show(extensionUri: vscode.Uri, historyManager: TaskHistoryManager) {
        if (TaskHistoryPanel.currentPanel) {
            TaskHistoryPanel.currentPanel.panel.reveal(vscode.ViewColumn.Beside);
            TaskHistoryPanel.currentPanel.refreshContent();
            return TaskHistoryPanel.currentPanel;
        }

        const panel = vscode.window.createWebviewPanel(
            'alphaPilotTaskHistory',
            'AlphaPilot 任务历史',
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [
                    vscode.Uri.joinPath(extensionUri, 'src', 'webviews')
                ]
            }
        );

        TaskHistoryPanel.currentPanel = new TaskHistoryPanel(panel, extensionUri, historyManager);
        return TaskHistoryPanel.currentPanel;
    }

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, historyManager: TaskHistoryManager) {
        this.panel = panel;
        this.historyManager = historyManager;

        this.panel.webview.html = this.getHtmlForWebview(this.panel.webview, extensionUri);

        this.panel.webview.onDidReceiveMessage(
            (message) => {
                this.handleMessage(message);
            },
            null,
            this.disposables
        );

        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
    }

    private handleMessage(message: any) {
        switch (message.type) {
            case 'ready':
                this.isReady = true;
                this.refreshContent();
                break;
            case 'viewTask':
                // 触发查看任务的事件
                this.panel.webview.postMessage({
                    type: 'taskDetail',
                    taskId: message.taskId
                });
                break;
            case 'deleteTask':
                this.historyManager.deleteTask(message.taskId);
                this.refreshContent();
                vscode.window.showInformationMessage('已删除任务记录');
                break;
            case 'clearHistory':
                vscode.window
                    .showWarningMessage('确实要清空所有任务历史吗？', '确认', '取消')
                    .then(choice => {
                        if (choice === '确认') {
                            this.historyManager.clearHistory();
                            this.refreshContent();
                        }
                    });
                break;
            case 'copyTaskId':
                vscode.env.clipboard.writeText(message.taskId);
                vscode.window.showInformationMessage('已复制任务 ID');
                break;
        }
    }

    public refreshContent(): void {
        const summary = this.historyManager.getHistorySummary();
        const msg = { type: 'historyData', payload: summary };
        if (this.isReady) {
            this.panel.webview.postMessage(msg);
        }
    }

    public dispose() {
        TaskHistoryPanel.currentPanel = undefined;
        this.panel.dispose();
        while (this.disposables.length) {
            const d = this.disposables.pop();
            if (d) d.dispose();
        }
    }

    private getHtmlForWebview(webview: vscode.Webview, extensionUri: vscode.Uri): string {
        const scriptUri = webview.asWebviewUri(
            vscode.Uri.joinPath(extensionUri, 'src', 'webviews', 'taskHistory.js')
        );
        const styleUri = webview.asWebviewUri(
            vscode.Uri.joinPath(extensionUri, 'src', 'webviews', 'taskHistory.css')
        );

        return /* html */ `
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8" />
                <title>AlphaPilot 任务历史</title>
                <link rel="stylesheet" href="${styleUri}">
            </head>
            <body>
                <div id="root">
                    <div class="header">
                        <div class="title">AlphaPilot · 任务历史</div>
                        <div class="controls">
                            <button id="btnRefresh" class="icon-btn" title="刷新">⟳</button>
                            <button id="btnClear" class="icon-btn danger" title="清空历史">🗑️</button>
                        </div>
                    </div>

                    <div class="search-box">
                        <input type="text" id="searchInput" placeholder="搜索任务..." />
                    </div>

                    <div class="content">
                        <div id="historyList" class="history-list"></div>
                        <div id="emptyState" class="empty-state" style="display: none;">
                            <div class="empty-icon">📋</div>
                            <div class="empty-text">暂无任务历史</div>
                        </div>
                    </div>
                </div>

                <script src="${scriptUri}"></script>
            </body>
            </html>
        `;
    }
}
