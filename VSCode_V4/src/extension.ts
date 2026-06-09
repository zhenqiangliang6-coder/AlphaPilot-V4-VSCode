// src/extension.ts
// AlphaPilot 扩展入口 - 基于世界级架构重构
// 严格遵循 ARCHITECTURE_MANIFESTO.md 核心信条

import * as vscode from 'vscode';
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

  // ⭐ 设置工作区路径（关键：让 Node API 知道文件应该写到哪里）
  setupWorkspace(context);

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
      // ⭐ v3.0 迁移：主面板已切换为 ReactPanel
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
        // ⭐ v3.0: 使用 ReactPanel 显示任务进度
        const panel = ReactPanel.show(context.extensionUri);

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
        { label: 'AlphaPilot (gemma LLM) - 离线运行', value: 'local_generate' },
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
  // ⭐ 监听工作区文件夹变化（实时响应工作区切换）
  const workspaceWatcher = vscode.workspace.onDidChangeWorkspaceFolders(async (event) => {
    console.log('📁 工作区文件夹发生变化');
    
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders && workspaceFolders.length > 0) {
      const workspacePath = workspaceFolders[0].uri.fsPath;
      
      try {
        const axios = require('axios');
        await axios.post(`${NODE_API_BASE_URL}/workspace/set`, {
          path: workspacePath
        });
        
        console.log(`[AlphaPilot] 🔄 Workspace 已自动更新为: ${workspacePath}`);
        vscode.window.showInformationMessage(`✅ 工作区已更新: ${workspacePath}`);
      } catch (error: any) {
        console.error('[AlphaPilot] ❌ 更新工作区失败:', error.message);
      }
    } else {
      console.warn('[AlphaPilot] ⚠️ 所有工作区已关闭');
    }
  });
  
  context.subscriptions.push(workspaceWatcher);
  
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
 * 设置工作区路径（关键：让 Node API 知道文件应该写到哪里）
 */
async function setupWorkspace(context: vscode.ExtensionContext): Promise<void> {
  try {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    
    if (workspaceFolders && workspaceFolders.length > 0) {
      const workspacePath = workspaceFolders[0].uri.fsPath;
      
      // 调用 Node API 设置工作区路径
      const axios = require('axios');
      await axios.post(`${NODE_API_BASE_URL}/workspace/set`, {
        path: workspacePath
      });
      
      console.log(`[AlphaPilot] ✅ Workspace 已设置为: ${workspacePath}`);
    } else {
      console.warn('[AlphaPilot] ⚠️ 未检测到工作区，FileOps 将写入临时目录');
    }
  } catch (error: any) {
    console.error('[AlphaPilot] ❌ 设置工作区失败:', error.message);
  }
}

/**
 * 连接 WebSocket 并监听事件
 */
async function connectWebSocket() {
  try {
    await websocketService.connect(WS_URL);
    console.log('✅ WebSocket 已连接');

    // ⭐ 监听 task_result 事件，自动执行 FileOps
    websocketService.on('task_result', async (result: any) => {
      console.log('\n📡 收到任务完成通知');
      
      // 检查是否有 FileOps 需要执行
      if (result.context?.final_file_ops && result.context.final_file_ops.length > 0) {
        console.log(`📋 检测到 ${result.context.final_file_ops.length} 个 FileOps，准备执行...`);
        
        try {
          const axios = require('axios');
          const response = await axios.post(`${NODE_API_BASE_URL}/fileops/execute`, {
            file_ops: result.context.final_file_ops
          });
          
          if (response.data.success) {
            console.log(`✅ FileOps 执行成功，生成 ${response.data.files?.length || 0} 个文件`);
            
            // 显示通知
            vscode.window.showInformationMessage(
              `✅ 已生成 ${response.data.files?.length || 0} 个文件`
            );
          } else {
            console.error('❌ FileOps 执行失败:', response.data.error);
            vscode.window.showErrorMessage(`FileOps 执行失败: ${response.data.error}`);
          }
        } catch (error: any) {
          console.error('❌ 执行 FileOps 时出错:', error.message);
          vscode.window.showErrorMessage(`执行 FileOps 失败: ${error.message}`);
        }
      }
    });

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
