// src/extension.ts
// AlphaPilot 扩展入口 - 基于世界级架构重构
// 严格遵循 ARCHITECTURE_MANIFESTO.md 核心信条

import * as vscode from 'vscode';
import { spawn } from 'child_process';
import { ReactPanel } from './panels/reactPanel';
import { taskService } from './services/taskService';
import { websocketService } from './services/websocketService';
import { streamingService } from './services/streamingService';
import { diffService } from './services/diffService';
import { applyWorkspaceDeleteOps } from './services/workspaceDelete';
import { imageSanitizer } from './services/ImageSanitizer';
import {
  buildSummaryHookPrompt,
  evaluateStopHook,
  isAllowedTestCommand,
  MAX_REPAIR_ROUNDS,
  TEST_COMMAND_TIMEOUT_MS,
  TestRunEvidence,
} from './services/taskLifecycle';
import { AlphaPilotCompletionProvider } from './providers/inlineCompletionProvider';
import { dispatcher } from './core/dispatcher';
import { eventBus, EventType } from './core/eventBus';
import { resolveTaskStatus } from './taskModel';

const NODE_API_BASE_URL = 'http://localhost:3000';
const WS_URL = 'ws://localhost:3000';
const executionOutput = vscode.window.createOutputChannel('AlphaPilot Execution');
const lifecycleSummaryTaskIds = new Set<string>();
const MAX_TEST_OUTPUT_BYTES = 2 * 1024 * 1024;
const FILEOPS_APPLY_TIMEOUT_MS = 15 * 60 * 1000;

interface PendingTestRun {
  result: any;
  command: string;
  workspace: vscode.Uri;
  repairRounds: number;
  priorChangedFiles: string[];
  appliedFiles: string[];
  proposedWritePaths: string[];
  timeout: ReturnType<typeof setTimeout>;
}

interface TestWorkflowContext {
  result: any;
  command: string;
  workspace: vscode.Uri;
  repairRounds: number;
  priorChangedFiles: string[];
  appliedFiles: string[];
}

interface PendingTestAuthorization extends TestWorkflowContext {
  kind: 'test' | 'repair';
  evidence?: TestRunEvidence;
}

const pendingTestRuns = new Map<string, PendingTestRun>();
const pendingTestAuthorizations = new Map<string, PendingTestAuthorization>();
let extensionUriForPanels: vscode.Uri | undefined;

function runApprovedTestCommand(
  command: string,
  workspaceRoot: vscode.Uri,
  repairRounds: number,
): Promise<TestRunEvidence> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, {
      cwd: workspaceRoot.fsPath,
      shell: true,
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    let capturedBytes = 0;
    let outputLimitExceeded = false;
    let settled = false;
    let changedAfterTest = false;
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(workspaceRoot, '**/*'),
    );
    const recordSourceChange = (uri: vscode.Uri) => {
      const relative = vscode.workspace.asRelativePath(uri, false);
      if (
        /\.(py|js|jsx|ts|tsx|java|go|rs|cs|cpp|c|h|hpp)$/i.test(relative)
        && !/(^|[\\/])(?:\.git|node_modules|\.venv|venv|__pycache__|dist|build)([\\/]|$)/i.test(relative)
      ) {
        changedAfterTest = true;
      }
    };
    const watchers = [
      watcher.onDidCreate(recordSourceChange),
      watcher.onDidChange(recordSourceChange),
      watcher.onDidDelete(recordSourceChange),
    ];
    const cleanup = () => {
      clearTimeout(timeout);
      watchers.forEach((disposable) => disposable.dispose());
      watcher.dispose();
    };
    const finish = (evidence: TestRunEvidence) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(evidence);
    };
    const timeout = setTimeout(() => {
      child.kill();
      finish({
        command,
        exitCode: null,
        stdout,
        stderr,
        timedOut: true,
        repairRounds,
        changedAfterTest,
      });
    }, TEST_COMMAND_TIMEOUT_MS);

    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    const appendOutput = (target: 'stdout' | 'stderr', chunk: string) => {
      if (outputLimitExceeded) return;
      capturedBytes += Buffer.byteLength(chunk, 'utf8');
      if (target === 'stdout') stdout += chunk;
      else stderr += chunk;
      if (capturedBytes > MAX_TEST_OUTPUT_BYTES) {
        outputLimitExceeded = true;
        stderr += '\nAlphaPilot stopped capturing because test output exceeded 2 MiB.';
        child.kill();
      }
    };
    child.stdout.on('data', (chunk: string) => appendOutput('stdout', chunk));
    child.stderr.on('data', (chunk: string) => appendOutput('stderr', chunk));
    child.once('error', (error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(error);
    });
    child.once('close', (code) => finish({
      command,
      exitCode: code,
      stdout,
      stderr,
      timedOut: false,
      repairRounds,
      changedAfterTest,
    }));
  });
}

function isPathExplicitlyInRequest(request: string, relativePath: string): boolean {
  const normalizedRequest = request.replace(/\\/g, '/');
  const normalizedPath = relativePath.replace(/\\/g, '/').replace(/^\/+/, '');
  if (!normalizedPath) return false;
  const escapedPath = normalizedPath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pathBoundary = '[^A-Za-z0-9_./\\\\-]';
  return new RegExp(`(?:^|${pathBoundary})${escapedPath}(?=$|${pathBoundary})`, 'i')
    .test(normalizedRequest);
}

async function runAuthorizedTestWorkflow(
  result: any,
  command: string,
  workspace: vscode.Uri,
  repairRounds: number,
  priorChangedFiles: string[],
  appliedFiles: string[],
): Promise<void> {
  if (!isAllowedTestCommand(command)) {
    const message = `测试命令不在允许范围内；未运行任何命令：${command}`;
    executionOutput.appendLine(`[${result.task_id}] ${message}`);
    vscode.window.showWarningMessage(message);
    return;
  }
  if (!Number.isInteger(repairRounds) || repairRounds < 0 || repairRounds > MAX_REPAIR_ROUNDS) {
    vscode.window.showErrorMessage('修复轮次状态无效或已超限，停止自动执行；请人工介入。');
    return;
  }

  const pending: PendingTestAuthorization = {
    kind: 'test',
    result,
    command,
    workspace,
    repairRounds,
    priorChangedFiles,
    appliedFiles,
  };
  pendingTestAuthorizations.set(result.task_id, pending);
  postTestAuthorizationMessage('test_authorization_required', {
    taskId: result.task_id,
    mode: 'run',
    command,
    workspace: workspace.fsPath,
    repairRounds,
  });
  executionOutput.appendLine(`[${result.task_id}] 已在 AlphaPilot 面板请求运行测试授权：${command}`);
}

function postTestAuthorizationMessage(type: string, payload: any): void {
  if (!extensionUriForPanels) {
    throw new Error('AlphaPilot 面板尚未初始化，无法显示测试授权卡片。');
  }
  ReactPanel.postToCurrentPanel(extensionUriForPanels, { type, payload });
}

function showReactPanel(extensionUri: vscode.Uri): ReactPanel {
  const panel = ReactPanel.show(extensionUri);
  for (const [taskId, pending] of pendingTestAuthorizations) {
    if (pending.kind === 'test') {
      ReactPanel.postToCurrentPanel(extensionUri, {
        type: 'test_authorization_required',
        payload: {
          taskId,
          mode: 'run',
          command: pending.command,
          workspace: pending.workspace.fsPath,
          repairRounds: pending.repairRounds,
        },
      });
    } else {
      ReactPanel.postToCurrentPanel(extensionUri, {
        type: 'test_repair_required',
        payload: {
          taskId,
          mode: 'repair',
          command: pending.command,
          workspace: pending.workspace.fsPath,
          repairRounds: pending.repairRounds,
          failureSummary: `${pending.evidence?.stdout || ''}\n${pending.evidence?.stderr || ''}`
            .trim()
            .slice(-6000),
        },
      });
    }
  }
  return panel;
}

async function handleTestAuthorizationDecision(data: any): Promise<void> {
  const taskId = typeof data?.taskId === 'string' ? data.taskId : '';
  const action = data?.action;
  const pending = pendingTestAuthorizations.get(taskId);
  if (!pending) {
    executionOutput.appendLine(`[${taskId || 'unknown'}] 忽略过期或重复的测试授权响应。`);
    return;
  }

  if (pending.kind === 'test') {
    if (action !== 'run' && action !== 'skip') return;
    pendingTestAuthorizations.delete(taskId);
    if (action === 'skip') {
      executionOutput.appendLine(`[${taskId}] 用户在面板中选择跳过测试。`);
      postTestAuthorizationMessage('test_authorization_status', {
        taskId,
        status: 'skipped',
        message: '用户选择跳过；测试命令未执行。',
      });
      return;
    }

    postTestAuthorizationMessage('test_authorization_status', {
      taskId,
      status: 'running',
      message: '已授权，正在运行测试…',
    });
    await executeAuthorizedTestWorkflow(pending);
    return;
  }

  if (action !== 'repair' && action !== 'stop') return;
  pendingTestAuthorizations.delete(taskId);
  if (action === 'stop') {
    executionOutput.appendLine(`[${taskId}] 用户在面板中选择停止，不提交修复任务。`);
    postTestAuthorizationMessage('test_authorization_status', {
      taskId,
      status: 'skipped',
      message: '已停止；没有提交修复任务。',
    });
    return;
  }

  postTestAuthorizationMessage('test_authorization_status', {
    taskId,
    status: 'submitting',
    message: '正在提交修复任务…',
  });
  await submitRepairTask(pending);
}

async function executeAuthorizedTestWorkflow(pending: TestWorkflowContext): Promise<void> {
  const {
    result,
    command,
    workspace,
    repairRounds,
    priorChangedFiles,
    appliedFiles,
  } = pending;
  executionOutput.appendLine(`[${result.task_id}] 用户已在面板中授权测试命令：${command}`);
  executionOutput.show(true);
  executionOutput.appendLine(`工作目录：${workspace.fsPath}`);

  let evidence: TestRunEvidence;
  try {
    evidence = await runApprovedTestCommand(command, workspace, repairRounds);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    executionOutput.appendLine(`[${result.task_id}] 测试命令启动失败：${message}`);
    postTestAuthorizationMessage('test_authorization_status', {
      taskId: result.task_id,
      status: 'failed',
      message: `测试命令启动失败：${message}`,
    });
    return;
  }

  executionOutput.appendLine(`测试退出码：${String(evidence.exitCode)}`);
  if (evidence.stdout) executionOutput.appendLine(`stdout:\n${evidence.stdout}`);
  if (evidence.stderr) executionOutput.appendLine(`stderr:\n${evidence.stderr}`);
  const stopDecision = evaluateStopHook(evidence);
  if (!stopDecision.complete) {
    executionOutput.appendLine(`停止钩子未通过：${stopDecision.reasons.join('；')}`);

    if (
      evidence.exitCode !== 0
      && !evidence.timedOut
      && repairRounds < MAX_REPAIR_ROUNDS
    ) {
      const repairContext: PendingTestAuthorization = {
        kind: 'repair',
        result,
        command,
        workspace,
        repairRounds,
        priorChangedFiles,
        appliedFiles,
        evidence,
      };
      pendingTestAuthorizations.set(result.task_id, repairContext);
      postTestAuthorizationMessage('test_repair_required', {
        taskId: result.task_id,
        mode: 'repair',
        command,
        workspace: workspace.fsPath,
        repairRounds,
        failureSummary: `${evidence.stdout}\n${evidence.stderr}`.trim().slice(-6000)
          || stopDecision.reasons.join('\n'),
      });
      executionOutput.appendLine(`[${result.task_id}] 已在 AlphaPilot 面板中请求是否提交修复任务。`);
    } else {
      const message = repairRounds >= MAX_REPAIR_ROUNDS
        ? `达到最大修复轮次；停止修复。${stopDecision.reasons.join('；')}`
        : stopDecision.reasons.join('；');
      postTestAuthorizationMessage('test_authorization_status', {
        taskId: result.task_id,
        status: 'failed',
        message,
      });
    }
    return;
  }

  postTestAuthorizationMessage('test_authorization_status', {
    taskId: result.task_id,
    status: 'completed',
    message: `测试通过：${command}`,
  });

  const summaryPrompt = buildSummaryHookPrompt({
    goal: result.context?.meta?.task_goal || result.context?.meta?.user_request || '',
    changedFiles: [...new Set([...priorChangedFiles, ...appliedFiles])],
    evidence: {
      ...evidence,
      stdout: evidence.stdout.slice(0, 4000),
      stderr: evidence.stderr.slice(0, 4000),
    },
    remainingIssues: (result.context?.meta?.deferred_steps || [])
      .filter((step: unknown) => step !== 'test'),
  });
  try {
    const summaryTaskId = await taskService.submitTask(
      `请生成以下证据的结项报告：\n\n${summaryPrompt}`,
      'qwen_generate',
      {
        context: { lifecycle_summary: true },
        workspace_path: workspace.fsPath,
      },
    );
    lifecycleSummaryTaskIds.add(summaryTaskId);
    websocketService.subscribeTask(summaryTaskId);
    executionOutput.appendLine(`[${result.task_id}] 停止钩子通过；已启动独立总结钩子 ${summaryTaskId}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    executionOutput.appendLine(`[${result.task_id}] 测试通过，但结项总结任务提交失败：${message}`);
    vscode.window.showErrorMessage(`测试通过，但结项总结生成失败：${message}`);
  }
}

async function submitRepairTask(pending: PendingTestAuthorization): Promise<void> {
  const {
    result,
    command,
    workspace,
    repairRounds,
    priorChangedFiles,
    appliedFiles,
    evidence,
  } = pending;
  if (!evidence) {
    throw new Error('缺少测试失败证据，拒绝提交修复任务。');
  }
  const failedOutput = `${evidence.stdout}\n${evidence.stderr}`.slice(0, 12000);
  const taskGoal = result.context?.meta?.task_goal || result.context?.meta?.user_request || '';
  const repairPrompt = [
    '请实现必要的最小代码修改以修复以下测试错误。先读取并定位涉及的源文件，只修改与失败直接相关的内容。',
    `原始任务：${taskGoal}`,
    `失败测试命令：${command}`,
    `退出码：${String(evidence.exitCode)}`,
    '测试输出：',
    failedOutput,
    '修复后仅提出文件变更；不要运行测试。测试命令会再次请求用户授权。',
  ].join('\n\n');
  try {
    const repairTaskId = await taskService.submitTask(repairPrompt, 'qwen_generate', {
      context: {
        task_goal: taskGoal,
        repair_rounds: repairRounds + 1,
        authorized_test_command: command,
        auto_repair_on_test_failure: false,
        prior_changed_files: [...new Set([...priorChangedFiles, ...appliedFiles])],
      },
      workspace_path: workspace.fsPath,
    });
    websocketService.subscribeTask(repairTaskId);
    executionOutput.appendLine(`[${result.task_id}] 已提交第 ${repairRounds + 1} 轮修复任务：${repairTaskId}`);
    postTestAuthorizationMessage('test_authorization_status', {
      taskId: result.task_id,
      status: 'submitted',
      message: `修复任务已提交（${repairTaskId}）；文件变更仍需你在面板中应用。`,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    executionOutput.appendLine(`[${result.task_id}] 修复任务提交失败：${message}`);
    postTestAuthorizationMessage('test_authorization_status', {
      taskId: result.task_id,
      status: 'failed',
      message: `修复任务提交失败：${message}`,
    });
  }
}

export function activate(context: vscode.ExtensionContext) {
  console.log('🚀 AlphaPilot 扩展已激活 (v2.2 - React Webview 版)');
  extensionUriForPanels = context.extensionUri;
  context.subscriptions.push(executionOutput);
  context.subscriptions.push({
    dispose: websocketService.on('test_authorization_decision', (data) => {
      void handleTestAuthorizationDecision(data).catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        const taskId = typeof data?.taskId === 'string' ? data.taskId : 'unknown';
        executionOutput.appendLine(`[${taskId}] 处理面板授权决定失败：${message}`);
        vscode.window.showErrorMessage(`AlphaPilot 授权操作失败：${message}`);
        try {
          postTestAuthorizationMessage('test_authorization_status', {
            taskId,
            status: 'failed',
            message: `授权操作失败：${message}`,
          });
        } catch (panelError) {
          const panelMessage = panelError instanceof Error ? panelError.message : String(panelError);
          executionOutput.appendLine(`[${taskId}] 无法更新授权卡片：${panelMessage}`);
        }
      });
    }),
  });

  // ============================================================
  // ⭐ 初始化核心层
  // ============================================================
  dispatcher.initialize();
  console.log('✅ Core Layer 已初始化 (Protocol + Dispatcher + EventBus)');

  // ⭐ v4.3: 预热 ImageSanitizer Worker Thread (延迟 2s，避免卡 IDE 启动)
  imageSanitizer.warmup();

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
      const panel = showReactPanel(context.extensionUri);
      
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
      const panel = showReactPanel(context.extensionUri);
      
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
        const panel = showReactPanel(context.extensionUri);

        // 使用新的 Dispatcher 提交任务
        const selectedModel = context.workspaceState.get<string>('selected_model', 'qwen_generate');
        const taskId = await dispatcher.submitTask(prompt, selectedModel);
        await context.workspaceState.update('current_task_id', taskId);
        
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
        { label: 'Gemini (谷歌) - 长上下文·需代理', value: 'gemini_generate' },
        { label: '深度求索 (DeepSeek) - 平衡性能', value: 'deepseek_generate' },
        { label: '豆包 (Doubao) - 多模态支持', value: 'doubao_generate' },
        { label: '腾讯混元 (MaaS) - 本地 Redis 测试', value: 'maas_generate' },
        { label: 'ModelScope - 本地 Redis 测试', value: 'modelscope_generate' },
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
async function setupWorkspace(context?: vscode.ExtensionContext): Promise<void> {
  try {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    
    if (!workspaceFolders || workspaceFolders.length === 0) {
      console.warn('[AlphaPilot] ⚠️ 未检测到工作区，FileOps 将写入临时目录');
      return;
    }

    const workspacePath = workspaceFolders[0].uri.fsPath;
    const axios = require('axios');
    const maxRetries = 15;
    const retryDelayMs = 2000;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        await axios.post(`${NODE_API_BASE_URL}/workspace/set`, { path: workspacePath }, { timeout: 3000 });
        console.log(`[AlphaPilot] ✅ Workspace 已设置为: ${workspacePath} (尝试 ${attempt}/${maxRetries})`);
        return;
      } catch (err: any) {
        const isConnectionError = err.code === 'ECONNREFUSED' || err.code === 'ECONNRESET' || err.code === 'ETIMEDOUT';
        if (!isConnectionError || attempt === maxRetries) {
          console.error(`[AlphaPilot] ❌ 设置工作区失败 (尝试 ${attempt}/${maxRetries}):`, err.message);
          if (attempt === maxRetries) return;
        }
        console.log(`[AlphaPilot] ⏳ Node API 未就绪，${retryDelayMs / 1000}s 后重试 (${attempt}/${maxRetries})...`);
        await new Promise(resolve => setTimeout(resolve, retryDelayMs));
      }
    }
  } catch (error: any) {
    console.error('[AlphaPilot] ❌ 设置工作区失败:', error.message);
  }
}

/**
 * 连接 WebSocket 并监听事件
 */
async function connectWebSocket() {
  websocketService.on('connected', async () => {
    await setupWorkspace();
    console.log('[AlphaPilot] 📁 (重连) 已同步工作区路径到 Node API');
  });

  try {
    await websocketService.connect(WS_URL);
    console.log('✅ WebSocket 已连接');

    await setupWorkspace();
    console.log('[AlphaPilot] 📁 已同步工作区路径到 Node API');

    websocketService.on('file_ops_applied', async (data: any) => {
      const taskId = typeof data?.taskId === 'string' ? data.taskId : '';
      const pending = pendingTestRuns.get(taskId);
      if (!pending) return;

      clearTimeout(pending.timeout);
      pendingTestRuns.delete(taskId);
      if (data.success !== true) {
        const message = '文件变更未全部成功应用，已跳过测试，不能报告验证通过。';
        executionOutput.appendLine(`[${taskId}] ${message}`);
        vscode.window.showErrorMessage(message);
        return;
      }

      await runAuthorizedTestWorkflow(
        pending.result,
        pending.command,
        pending.workspace,
        pending.repairRounds,
        pending.priorChangedFiles,
        [...pending.appliedFiles, ...pending.proposedWritePaths],
      );
    });

    // ⭐ 监听 task_result 事件，自动执行 FileOps
    websocketService.on('task_result', async (result: any) => {
      console.log('\n📡 收到任务完成通知');

      if (lifecycleSummaryTaskIds.has(result.task_id)) {
        lifecycleSummaryTaskIds.delete(result.task_id);
        const report = typeof result.result === 'string' ? result.result : '总结任务未返回报告。';
        executionOutput.appendLine(`\n[${result.task_id}] 结项报告\n${report}`);
        executionOutput.show(true);
        vscode.window.showInformationMessage('AlphaPilot 已生成结项报告，请查看执行输出。');
        return;
      }

      const authorizationRequests = result.context?.meta?.authorization_requests || [];
      const repairRounds = result.context?.meta?.repair_rounds ?? 0;
      const inheritedTestCommand = result.context?.meta?.authorized_test_command;
      const testAuthorizationPending = authorizationRequests.some((request: any) => request.type === 'test')
        || (
          Number.isInteger(repairRounds)
          && repairRounds > 0
          && typeof inheritedTestCommand === 'string'
        );
      const deletionAuthorizationPending = authorizationRequests.some((request: any) => request.type === 'delete');
      const resolved = resolveTaskStatus(result);
      if (!resolved.valid) {
        console.warn(`[AlphaPilot] 任务结果契约无效 (task_state=${result.task_state}, status=${result.status})，拒绝应用 FileOps`);
        return;
      }
      const resolvedStatus = resolved.status;
      if (
        resolvedStatus !== 'done'
        && !(resolvedStatus === 'awaiting_authorization' && (testAuthorizationPending || deletionAuthorizationPending))
      ) {
        console.warn(`[AlphaPilot] 任务状态为 ${resolvedStatus} (task_state=${result.task_state})，不应用部分 FileOps`);
        return;
      }
      const appliedFiles: string[] = [];
      let proposedWritePaths: string[] = [];
      const priorChangedFiles = Array.isArray(result.context?.meta?.prior_changed_files)
        ? result.context.meta.prior_changed_files.filter((filePath: unknown): filePath is string => (
          typeof filePath === 'string' && filePath.length > 0
        ))
        : [];
      
      // 检查是否有 FileOps 需要执行
      const collaborationMode = result.context?.meta?.collaboration_mode;
      const isFileManager = collaborationMode === 'file_manager';
      const mayWriteFiles = collaborationMode === 'pair_programmer'
        || collaborationMode === 'engineer'
        || isFileManager
        || (collaborationMode === 'architect' && result.context?.meta?.file_changes_allowed === true);

      if (!mayWriteFiles && result.context?.final_file_ops?.length > 0) {
        console.warn(`[AlphaPilot] 已按 ${collaborationMode} 模式拦截文件修改`);
      } else if (result.context?.final_file_ops && result.context.final_file_ops.length > 0) {
        const fileOps = result.context.final_file_ops;
        const workspace = vscode.workspace.workspaceFolders?.[0]?.uri;
        if (!workspace) {
          vscode.window.showErrorMessage('无法执行 FileOps：当前未打开工作区。');
          return;
        }

        const deleteOps = fileOps.filter((op: any) => op.op === 'delete');
        const writeOps = fileOps.filter((op: any) => op.op !== 'delete');

        if (deleteOps.length > 0) {
          const originalRequest = String(result.context?.meta?.user_request || '');
          const unrequestedPaths = deleteOps
            .map((op: any) => String(op.path || ''))
            .filter((targetPath: string) => !isPathExplicitlyInRequest(originalRequest, targetPath));
          if (result.context?.meta?.intent !== 'delete_files' || unrequestedPaths.length > 0) {
            const reason = result.context?.meta?.intent !== 'delete_files'
              ? '当前请求不是明确的删除任务'
              : `以下路径未在用户请求中逐字指定：${unrequestedPaths.join('、')}`;
            vscode.window.showErrorMessage(`删除请求已拒绝：${reason}`);
            executionOutput.appendLine(`[${result.task_id}] 删除请求已拒绝：${reason}`);
            return;
          }
        }

        if (isFileManager && writeOps.length > 0) {
          vscode.window.showErrorMessage('安全文件管理任务只允许提出删除候选项；已拒绝其他文件操作。');
          return;
        }
        if (
          collaborationMode === 'architect'
          && writeOps.some((op: any) => {
            const relative = String(op.path || '').replace(/\\/g, '/').replace(/^\/+/, '');
            const filename = relative.split('/').pop()?.toLowerCase() || '';
            return !relative.startsWith('docs/')
              || !/architecture|架构/.test(filename)
              || !/\.(md|mmd|puml)$/.test(filename);
          })
        ) {
          vscode.window.showErrorMessage('架构师模式仅允许写入 docs/ 下的架构文档；其他操作已拒绝。');
          return;
        }

        if (deleteOps.length > 0) {
          try {
            const deletion = await applyWorkspaceDeleteOps(deleteOps, workspace);
            if (deletion.rejected.length > 0) {
              const details = deletion.rejected.join('\n');
              executionOutput.appendLine(`[${result.task_id}] 删除请求已拒绝：\n${details}`);
              vscode.window.showErrorMessage(`删除请求已拒绝：\n${details}`);
              return;
            }
            if (deletion.cancelled) {
              executionOutput.appendLine(`[${result.task_id}] 用户取消删除操作`);
              return;
            }
            if (deletion.deleted.length > 0) {
              appliedFiles.push(...deletion.deleted.map((filePath) => `${filePath}（已移入回收站）`));
              executionOutput.appendLine(
                `[${result.task_id}] 已移入回收站：${deletion.deleted.join('、')}`
              );
              vscode.window.showInformationMessage(
                `已移入回收站：${deletion.deleted.join('、')}`
              );
            }
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            executionOutput.appendLine(`[${result.task_id}] 删除失败：${message}`);
            vscode.window.showErrorMessage(`删除失败：${message}`);
            return;
          }
        }

        if (writeOps.length > 0) {
          proposedWritePaths = writeOps
            .map((op: any) => op.path)
            .filter((filePath: unknown): filePath is string => (
              typeof filePath === 'string' && filePath.length > 0
            ));
          executionOutput.appendLine(
            `[${result.task_id}] 收到 ${writeOps.length} 个写入 FileOps，转发至对话面板内嵌确认`
          );

          console.log(`📋 [${result.task_id}] 转发 ${writeOps.length} 个写入 FileOps 到对话面板内嵌确认`);
          executionOutput.appendLine(`[${result.task_id}] FileOps 已转发至对话面板，请在面板内确认`);
          executionOutput.show(true);

          websocketService.triggerLocal('file_ops', {
            taskId: result.task_id,
            fileOps: writeOps
          });
        }
      }

      if (testAuthorizationPending) {
        const workspace = vscode.workspace.workspaceFolders?.[0]?.uri;
        const command = result.context?.meta?.proposed_test_command;
        if (!workspace || typeof command !== 'string' || !isAllowedTestCommand(command)) {
          const message = !workspace
            ? '测试需要一个打开的工作区。'
            : `模型没有提供安全、可识别的测试命令；未运行任何命令。提议命令：${String(command || '（无）')}`;
          executionOutput.appendLine(`[${result.task_id}] ${message}`);
          vscode.window.showWarningMessage(message);
          return;
        }

        const hasUnappliedWrites = (result.context?.final_file_ops || [])
          .some((op: any) => op.op !== 'delete');
        if (
          repairRounds > 0
          && typeof inheritedTestCommand === 'string'
          && appliedFiles.length === 0
          && proposedWritePaths.length === 0
        ) {
          const message = '修复任务没有产生可应用的文件变更，停止重测并请求人工检查。';
          executionOutput.appendLine(`[${result.task_id}] ${message}`);
          vscode.window.showWarningMessage(message);
          return;
        }
        if (hasUnappliedWrites && proposedWritePaths.length === 0) {
          const message = '存在未获准或未转发的文件变更，已跳过测试，避免验证旧代码或报告虚假通过。';
          executionOutput.appendLine(`[${result.task_id}] ${message}`);
          vscode.window.showWarningMessage(message);
          return;
        }
        if (proposedWritePaths.length > 0) {
          const existing = pendingTestRuns.get(result.task_id);
          if (existing) clearTimeout(existing.timeout);
          const pending: PendingTestRun = {
            result,
            command,
            workspace,
            repairRounds,
            priorChangedFiles,
            appliedFiles,
            proposedWritePaths,
            timeout: setTimeout(() => {
              pendingTestRuns.delete(result.task_id);
              executionOutput.appendLine(
                `[${result.task_id}] 等待文件变更确认超时；未运行测试。`
              );
            }, FILEOPS_APPLY_TIMEOUT_MS),
          };
          pendingTestRuns.set(result.task_id, pending);
          executionOutput.appendLine(
            `[${result.task_id}] 等待用户应用 ${proposedWritePaths.length} 个文件变更后再运行测试。`
          );
          vscode.window.showInformationMessage(
            '请先在 AlphaPilot 面板应用文件变更；应用成功后将继续运行已授权的测试命令。'
          );
          return;
        }

        await runAuthorizedTestWorkflow(
          result,
          command,
          workspace,
          repairRounds,
          priorChangedFiles,
          appliedFiles,
        );
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
  for (const pending of pendingTestRuns.values()) {
    clearTimeout(pending.timeout);
  }
  pendingTestRuns.clear();
  imageSanitizer.dispose();
  dispatcher.dispose();
  eventBus.dispose();
  websocketService.disconnect();
}