// src/extension.ts
// AlphaPilot 扩展入口 - 基于世界级架构重构
// 严格遵循 ARCHITECTURE_MANIFESTO.md 核心信条

import * as vscode from 'vscode';
import { TaskPanel } from './panels/taskPanel';
import { ReactPanel } from './panels/reactPanel';
import { taskService } from './services/taskService';
import { websocketService } from './services/websocketService';
import { streamingService } from './services/streamingService';
import { diffService } from './services/diffService';
import { AlphaPilotCompletionProvider } from './providers/inlineCompletionProvider';
import { dispatcher } from './core/dispatcher';
import { eventBus, EventType } from './core/eventBus';

const NODE_API_BASE_URL = 'http://localhost:3000';
const WS_URL = 'ws://localhost:3000';

export function activate(context: vscode.ExtensionContext) {
  console.log('🚀 AlphaPilot 扩展已激活 (v2.2 - React Webview 版)');

  // ============================================================
  // ⭐ 初始化核心层
  // ============================================================
  dispatcher.initialize();
  console.log('✅ Core Layer 已初始化 (Protocol + Dispatcher + EventBus)');

  // 初始化服务
  taskService.initialize(context);

  // 连接 WebSocket
  connectWebSocket();

  // ============================================================
  // ⭐ 注册智能代码补全提供者 (对标 GitHub Copilot)
  // ============================================================
  const completionProvider = new AlphaPilotCompletionProvider();
  const completionDisposable = vscode.languages.registerInlineCompletionItemProvider(
    [
      { scheme: 'file', language: 'python' },
      { scheme: 'file', language: 'javascript' },
      { scheme: 'file', language: 'typescript' },
      { scheme: 'file', language: 'java' },
      { scheme: 'file', language: 'cpp' },
      { scheme: 'file', language: 'c' },
      { scheme: 'file', language: 'go' },
      { scheme: 'file', language: 'rust' },
    ],
    completionProvider
  );
  context.subscriptions.push(completionDisposable);
  console.log('✅ 智能代码补全已启用');

  // ============================================================
  // 注册命令
  // ============================================================
  
  // ⭐ 新命令: 打开 React 面板
  const openReactPanelCommand = vscode.commands.registerCommand(
    'alphapilot.openReactPanel',
    () => {
      const panel = ReactPanel.show(context.extensionUri);
      
      // 如果有当前任务 ID，告诉面板
      const currentTaskId = context.workspaceState.get<string>('current_task_id');
      if (currentTaskId) {
        panel.setTaskId(currentTaskId);
      }
      
      // 触发事件
      eventBus.emit(EventType.PANEL_OPENED, undefined);
    }
  );

  const openPanelCommand = vscode.commands.registerCommand(
    'alphapilot.openPanel',
    () => {
      const panel = TaskPanel.show(context.extensionUri);
      
      // 如果有当前任务 ID，告诉面板
      const currentTaskId = context.workspaceState.get<string>('current_task_id');
      if (currentTaskId) {
        panel.setTaskId(currentTaskId);
      }
      
      // 触发事件
      eventBus.emit(EventType.PANEL_OPENED, undefined);
    }
  );

  const submitTaskCommand = vscode.commands.registerCommand(
    'alphapilot.submitTask',
    async () => {
      // 获取用户输入
      const prompt = await vscode.window.showInputBox({
        prompt: '请输入任务描述',
        placeHolder: '例如：帮我写一个 Python 函数，计算斐波那契数列',
        ignoreFocusOut: true
      });

      if (!prompt) {
        return;
      }

      try {
        // 显示面板
        const panel = TaskPanel.show(context.extensionUri);

        // 使用新的 Dispatcher 提交任务
        const selectedModel = context.workspaceState.get<string>('selected_model', 'qwen_generate');
        await dispatcher.submitTask(prompt, selectedModel);
        
        vscode.window.showInformationMessage(`✅ 任务已提交`);

      } catch (error: any) {
        vscode.window.showErrorMessage(`❌ 提交任务失败：${error.message}`);
      }
    }
  );

  const stopTaskCommand = vscode.commands.registerCommand(
    'alphapilot.stopTask',
    async () => {
      const taskId = context.workspaceState.get<string>('current_task_id');
      
      if (!taskId) {
        vscode.window.showWarningMessage('⚠️ 当前没有正在执行的任务');
        return;
      }

      try {
        await dispatcher.cancelTask(taskId);
        vscode.window.showInformationMessage(`⏹️ 已请求停止任务`);
      } catch (error: any) {
        vscode.window.showErrorMessage(`❌ 停止任务失败：${error.message}`);
      }
    }
  );

  // ⭐ 新增：选择模型命令
  const selectModelCommand = vscode.commands.registerCommand(
    'alphapilot.selectModel',
    async () => {
      const models = [
        { label: '通义千问 (Qwen) - 快速响应', value: 'qwen_generate' },
        { label: '深度求索 (DeepSeek) - 平衡性能', value: 'deepseek_generate' },
        { label: '豆包 (Doubao) - 多模态支持', value: 'doubao_generate' },
      ];

      const selected = await vscode.window.showQuickPick(models, {
        placeHolder: '选择 AI 模型',
        ignoreFocusOut: true
      });

      if (selected) {
        context.workspaceState.update('selected_model', selected.value);
        eventBus.emit(EventType.MODEL_CHANGED, { model: selected.value });
        vscode.window.showInformationMessage(`✅ 已切换到: ${selected.label}`);
      }
    }
  );

  // ⭐ 新增：保存任务 ID 命令
  const saveTaskIdCommand = vscode.commands.registerCommand(
    'alphapilot.saveTaskId',
    (taskId: string, prompt?: string) => {
      console.log(`💾 保存任务 ID: ${taskId}`);
      context.workspaceState.update('current_task_id', taskId);
      eventBus.emit(EventType.TASK_SUBMITTED, { 
        taskId,
        prompt: prompt || 'Unknown task'
      });
    }
  );

  context.subscriptions.push(
    openReactPanelCommand,  // ⭐ 新增
    openPanelCommand,
    submitTaskCommand,
    stopTaskCommand,
    selectModelCommand,
    saveTaskIdCommand  // ⭐ 新增
  );

  // ============================================================
  // ⭐ 订阅全局事件 (用于日志和监控)
  // ============================================================
  setupEventSubscriptions(context);
}

/**
 * 设置全局事件订阅
 */
function setupEventSubscriptions(context: vscode.ExtensionContext): void {
  // 监听任务完成
  eventBus.on(EventType.TASK_COMPLETED, ({ taskId, result }) => {
    console.log(`🎉 任务完成: ${taskId}`);
  });

  // 监听错误
  eventBus.on(EventType.ERROR_OCCURRED, ({ message, stack }) => {
    console.error(`❌ 全局错误: ${message}`, stack);
    vscode.window.showErrorMessage(`AlphaPilot 错误: ${message}`);
  });

  // 监听模型切换
  eventBus.on(EventType.MODEL_CHANGED, ({ model }) => {
    console.log(`🔄 模型已切换: ${model}`);
  });
}

/**
 * 连接 WebSocket 并监听事件
 */
async function connectWebSocket() {
  try {
    await websocketService.connect(WS_URL);
    console.log('✅ WebSocket 已连接');

    // WebSocket 消息现在由 MessageDispatcher 统一处理
    // 这里只保留兼容性代码
    
  } catch (error: any) {
    console.error('❌ WebSocket 连接失败:', error);
    vscode.window.showWarningMessage(
      '⚠️ WebSocket 连接失败，请确保后端服务已启动 (http://localhost:3000)'
    );
  }
}

export function deactivate() {
  console.log('🛑 AlphaPilot 扩展已停用');
  
  // 清理资源
  dispatcher.dispose();
  eventBus.dispose();
  websocketService.disconnect();
}
