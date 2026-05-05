/**
 * AIResultPanel - Webview 面板（动态 HTML 版本）
 * 
 * 这是完整版本，包含：
 * - 动态 HTML（任务树 UI）
 * - WebSocket 连接 Node API
 * - 自动订阅 task_id
 * - 接收 steps / events / result
 * - 兼容旧版 append/done/error
 */

import * as vscode from "vscode";

export class AIResultPanel {
    private static currentPanel: AIResultPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private disposables: vscode.Disposable[] = [];
    private isReady = false;
    private pendingMessages: any[] = [];

    // ⭐ 当前任务 ID（用于订阅 Node API）
    private currentTaskId: string | null = null;

    public static show(extensionUri: vscode.Uri) {
        if (AIResultPanel.currentPanel) {
            AIResultPanel.currentPanel.panel.reveal(vscode.ViewColumn.Beside);
            return AIResultPanel.currentPanel;
        }

        const panel = vscode.window.createWebviewPanel(
            "alphaPilotCodeCompletion",
            "AlphaPilot 智能体任务树",
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true
            }
        );

        AIResultPanel.currentPanel = new AIResultPanel(panel, extensionUri);
        return AIResultPanel.currentPanel;
    }

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
        this.panel = panel;

        // ⭐ 使用动态 HTML（任务树 UI）
        this.panel.webview.html = this.getHtmlForWebview();

        // ⭐ 监听 Webview 消息
        this.panel.webview.onDidReceiveMessage(
            (msg) => {
                if (msg.type === "webview_ready") {
                    this.isReady = true;

                    // 把之前缓存的消息全部发给 Webview
                    while (this.pendingMessages.length) {
                        this.panel.webview.postMessage(this.pendingMessages.shift());
                    }
                }

                // Webview 请求提交 prompt
                if (msg.type === "submit_prompt") {
                    vscode.commands.executeCommand(
                        "alphaMinimalExtension.submitPrompt",
                        msg.prompt
                    );
                }

                // Webview 请求订阅 task_id
                if (msg.type === "subscribe_task") {
                    this.currentTaskId = msg.task_id;
                }
            },
            null,
            this.disposables
        );

        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
    }

    public dispose() {
        AIResultPanel.currentPanel = undefined;
        this.panel.dispose();
        while (this.disposables.length) {
            this.disposables.pop()?.dispose();
        }
    }

    private postMessage(message: any) {
        if (this.isReady) {
            this.panel.webview.postMessage(message);
        } else {
            this.pendingMessages.push(message);
        }
    }

    // ⭐ Extension → Webview：告诉 Webview 当前任务 ID
    public sendTaskId(taskId: string) {
        this.currentTaskId = taskId;
        this.postMessage({ type: "task_id", task_id: taskId });
    }

    // 兼容旧版 append/done/error
    public sendAppend(content: string) {
        this.postMessage({ type: "append", content });
    }

    public sendDone() {
        this.postMessage({ type: "done" });
    }

    public sendError(message: string) {
        this.postMessage({ type: "error", message });
    }

    /**
     * ⭐ 动态 HTML（任务树 UI）
     */
    private getHtmlForWebview(): string {
        return /* html */ `
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <title>智能体任务树</title>

  <style>
    body {
      font-family: Consolas, monospace;
      background: #1e1e1e;
      color: #ddd;
      margin: 0;
      padding: 0;
    }

    h2 {
      margin: 16px;
      color: #4fc3f7;
    }

    .section {
      margin: 16px;
      padding: 12px;
      background: #252526;
      border-radius: 6px;
      border: 1px solid #333;
    }

    #stream-output {
      white-space: pre-wrap;
      font-size: 14px;
      line-height: 1.5;
      padding: 8px;
      background: #111;
      border-radius: 4px;
      min-height: 80px;
    }

    .step {
      margin-bottom: 12px;
      padding: 10px;
      border-left: 3px solid #4fc3f7;
      background: #1b1b1b;
      border-radius: 4px;
    }

    .step-title {
      font-weight: bold;
      color: #4fc3f7;
      cursor: pointer;
    }

    .step-content {
      margin-top: 6px;
      padding-left: 12px;
      display: none;
    }

    .event {
      padding: 6px;
      border-bottom: 1px solid #333;
    }

    .event-type {
      color: #81c784;
      font-weight: bold;
    }

    .event-time {
      color: #aaa;
      font-size: 12px;
    }

    #final-result {
      white-space: pre-wrap;
      background: #111;
      padding: 10px;
      border-radius: 4px;
      min-height: 60px;
    }
  </style>
</head>

<body>

  <h2>🧠 智能体任务树（TaskModel v2）</h2>

  <div class="section">
    <h3>🔴 流式输出（兼容旧 UI）</h3>
    <div id="stream-output"></div>
  </div>

  <div class="section">
    <h3>🌳 任务步骤（steps）</h3>
    <div id="steps-container"></div>
  </div>

  <div class="section">
    <h3>📡 事件流（events）</h3>
    <div id="events-container"></div>
  </div>

  <div class="section">
    <h3>📦 最终结果（result）</h3>
    <div id="final-result"></div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();

    let currentTaskId = null;

    // ⭐ Webview 初始化
    window.onload = () => {
      vscode.postMessage({ type: "webview_ready" });
    };

    /* ============================================================
       WebSocket 连接 Node API
       ============================================================ */
    const socket = new WebSocket("ws://localhost:3000");

    socket.onopen = () => {
      console.log("WebSocket 已连接");

      // ⭐ 如果 Extension 已经传来 task_id，则立即订阅
      if (currentTaskId) {
        socket.send(JSON.stringify({
          event: "subscribe_task",
          task_id: currentTaskId
        }));
      }
    };

    /* ============================================================
       接收 Extension 传来的 task_id
       ============================================================ */
    window.addEventListener("message", (event) => {
      const msg = event.data;

      if (msg.type === "task_id") {
        currentTaskId = msg.task_id;

        // ⭐ 订阅任务
        socket.send(JSON.stringify({
          event: "subscribe_task",
          task_id: currentTaskId
        }));
      }
    });

    /* ============================================================
       流式输出（兼容旧 UI）
       ============================================================ */
    socket.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);

        // ✅ 修复：socket.io 的 emit 格式是 { eventName: payload }
        // 所以需要检查对象的 key 来确定事件类型
        const eventKeys = Object.keys(data);
        
        if (eventKeys.includes("stream_start")) {
          const payload = data.stream_start;
          document.getElementById("stream-output").innerText = "";
          console.log("✅ 收到 stream_start:", payload);
        }

        if (eventKeys.includes("stream_chunk")) {
          const payload = data.stream_chunk;
          document.getElementById("stream-output").innerText += payload.chunk || "";
          console.log("✅ 收到 stream_chunk:", payload);
        }

        if (eventKeys.includes("stream_error")) {
          const payload = data.stream_error;
          document.getElementById("stream-output").innerText += "\n[ERROR] " + (payload.message || "未知错误");
          console.log("✅ 收到 stream_error:", payload);
        }

        if (eventKeys.includes("stream_end")) {
          const payload = data.stream_end;
          console.log("✅ 收到 stream_end:", payload);
        }

      } catch (e) {
        console.error("❌ 处理 WebSocket 消息时出错:", e, event.data);
      }
    });

    /* ============================================================
       接收最终任务结果（TaskModel v2）
       ============================================================ */
    socket.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);

      if (msg.event !== "task_result") return;

      const task = msg.data;

      renderSteps(task.steps || []);
      renderEvents(task.events || []);
      renderFinalResult(task.result);
    });

    /* ============================================================
       渲染任务树（steps）
       ============================================================ */
    function renderSteps(steps) {
      const container = document.getElementById("steps-container");
      container.innerHTML = "";

      steps.forEach((step) => {
        const div = document.createElement("div");
        div.className = "step";

        // 使用textContent避免HTML解析问题
        const titleDiv = document.createElement("div");
        titleDiv.className = "step-title";
        titleDiv.textContent = "📌 " + step.id + "（" + step.type + "） - 状态：" + step.status;
        
        const contentDiv = document.createElement("div");
        contentDiv.className = "step-content";
        contentDiv.innerHTML = "<pre>" + JSON.stringify(step, null, 2) + "</pre>";

        div.appendChild(titleDiv);
        div.appendChild(contentDiv);

        titleDiv.onclick = () => {
          contentDiv.style.display = contentDiv.style.display === "none" ? "block" : "none";
        };

        container.appendChild(div);
      });
    }

    /* ============================================================
       渲染事件流（events）
       ============================================================ */
    function renderEvents(events) {
      const container = document.getElementById("events-container");
      container.innerHTML = "";

      events.forEach((ev) => {
        const div = document.createElement("div");
        div.className = "event";

        const typeDiv = document.createElement("div");
        typeDiv.className = "event-type";
        typeDiv.textContent = "🔹 " + ev.type;
        
        const timeDiv = document.createElement("div");
        timeDiv.className = "event-time";
        timeDiv.textContent = new Date(ev.timestamp).toLocaleTimeString();
        
        const dataPre = document.createElement("pre");
        dataPre.textContent = JSON.stringify(ev.data, null, 2);

        div.appendChild(typeDiv);
        div.appendChild(timeDiv);
        div.appendChild(dataPre);

        container.appendChild(div);
      });
    }

    /* ============================================================
       渲染最终结果（result）
       ============================================================ */
    function renderFinalResult(result) {
      document.getElementById("final-result").innerText =
        JSON.stringify(result, null, 2);
    }
  </script>

</body>
</html>
        `;
    }
}
