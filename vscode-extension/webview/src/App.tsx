// src/App.tsx
import React, { useEffect, useState, useRef } from 'react';
import { useChatStore } from './store/chatStore';
import { Toolbar } from './components/Toolbar';
import { ModelSelector } from './components/ModelSelector';
import { MessageList } from './components/MessageList';
import { ChatInput } from './components/ChatInput';
import { FileOpsList } from './components/FileOpsList';
import { StepPanel } from './components/StepPanel';  // ⭐ v3.2 新增
import { TaskHistoryPanel } from './components/TaskHistoryPanel';  // ⭐ v3.5+ 新增
import { FileVersionPanel } from './components/FileVersionPanel';  // ⭐ v3.5+ 新增
import { ProjectMemoryPanel } from './components/ProjectMemoryPanel';  // ⭐ v3.5+ 新增
import { ConfirmationCard } from './components/ConfirmationCard';  // ⭐ Phase 2.4 P0-4
import {
  TestAuthorizationRequest,
} from './components/TestAuthorizationCard';
import { TestAuthorizationBar } from './components/TestAuthorizationBar';
import { FileOpsConfirmCard } from './components/FileOpsConfirmCard';
import { vscodeAPI } from './utils/vscode';

function App() {
  const { 
    addMessage, 
    updateMessage, 
    setCurrentTaskId, 
    setStreaming, 
    addStep, 
    updateStep,
    setCurrentPhase,
    addArtifact,  // P1
    pendingConfirmation,  // Phase 2.4 P0-4
    setPendingConfirmation,
    clearPendingConfirmation,
  } = useChatStore();

  // ⭐ v2.7 新增：FileOps 状态管理
  const [showFileOps, setShowFileOps] = useState(false);
  const [showFileOpsPanel, setShowFileOpsPanel] = useState(false);
  const [currentFileOps, setCurrentFileOps] = useState<any[]>([]);
  const [currentTaskIdForFileOps, setCurrentTaskIdForFileOps] = useState<string | null>(null);
  const [testAuthorizations, setTestAuthorizations] = useState<TestAuthorizationRequest[]>([]);

  // P2: conversationId 多轮对话连续性
  const [conversationId] = useState<string>(() => {
    const saved = (vscodeAPI.getState() as any)?.conversationId;
    if (saved) return saved;
    const id = `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    vscodeAPI.setState({ ...(vscodeAPI.getState() as any || {}), conversationId: id });
    return id;
  });

  // ⭐ v3.2 新增：StepPanel 侧边栏状态
  const [showStepPanel, setShowStepPanel] = useState(false);

  // ⭐ v3.5+ 新增：任务历史、文件版本、项目记忆面板状态
  const [showTaskHistory, setShowTaskHistory] = useState(false);
  const [showFileVersion, setShowFileVersion] = useState(false);
  const [showProjectMemory, setShowProjectMemory] = useState(false);
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null);
  const [selectedFilePath, setSelectedFilePath] = useState<string>('');
  const [selectedProjectId, setSelectedProjectId] = useState<number>(1);  // 默认项目 ID
  const [selectedProjectName, setSelectedProjectName] = useState<string>('Default Project');

  const processedTaskIds = useRef<Set<string>>(new Set());

  // 监听来自 Extension 的消息
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const message = event.data;
      console.log('📥 Extension → Webview:', message);

      switch (message.type) {
        case 'test_authorization_required':
          setTestAuthorizations((current) => [
            ...current.filter((request) => request.taskId !== message.payload?.taskId),
            { ...message.payload, mode: 'run', status: 'pending' },
          ]);
          break;

        case 'test_repair_required':
          setTestAuthorizations((current) => [
            ...current.filter((request) => request.taskId !== message.payload?.taskId),
            { ...message.payload, mode: 'repair', status: 'pending' },
          ]);
          break;

        case 'test_authorization_status':
          setTestAuthorizations((current) => current.map((request) => (
            request.taskId === message.payload?.taskId
              ? { ...request, ...message.payload }
              : request
          )));
          break;

        case 'task_started':
          handleTaskStarted(message.payload);
          break;
        
        case 'task_completed':
          handleTaskCompleted(message.payload);
          break;
        
        case 'task_failed':
          handleTaskFailed(message.payload);
          break;
        
        case 'step_started':
          handleStepStarted(message.payload);
          break;
        
        case 'step_finished':
          handleStepFinished(message.payload);
          break;
        
        case 'stream_chunk':
          console.log('📥 Webview 收到 stream_chunk:', {
            task_id: message.payload?.task_id,
            phase: message.payload?.phase,
            channel: message.payload?.channel,
            chunk_length: message.payload?.chunk?.length
          });
          handleStreamChunk(message.payload);
          break;
        
        case 'stream_end':
          setStreaming(false);
          setCurrentPhase(null);  // ⭐ 重置阶段
          break;
        
        // ⭐ v2.7 新增：监听 file_ops 消息
        case 'file_ops':
          console.log('📁 Webview 收到 file_ops:', message.payload);
          handleFileOps(message.payload);
          break;
        
        // P1：监听产物事件
        case 'artifact_created':
          console.log('[P1] Webview 收到 artifact_created:', message.payload.artifact_id);
          handleArtifactCreated(message.payload);
          break;

        // Phase 2.4 P0-4: 确认请求
        case 'confirmation_required':
          console.log('🔔 [P0-4] Webview 收到 confirmation_required:', message.payload);
          handleConfirmationRequired(message.payload);
          break;

        case 'confirmation_resolved':
          console.log('✅ [P0-4] Webview 收到 confirmation_resolved:', message.payload);
          handleConfirmationResolved(message.payload);
          break;
      }
    };

    window.addEventListener('message', handleMessage);
    vscodeAPI.postMessage({ type: 'webview_ready' });
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  const handleTestAuthorizationDecision = (
    taskId: string,
    action: 'run' | 'skip' | 'repair' | 'stop',
  ) => {
    const request = testAuthorizations.find((item) => item.taskId === taskId);
    if (!request || request.status !== 'pending') return;

    setTestAuthorizations((current) => current.map((item) => (
      item.taskId === taskId
        ? {
          ...item,
          status: action === 'run' ? 'running' : action === 'repair' ? 'submitting' : 'skipped',
        }
        : item
    )));
    vscodeAPI.postMessage({
      type: 'test_authorization_decision',
      payload: {
        taskId,
        action,
      },
    });
  };

  const handleTaskStarted = (payload: any) => {
    // P3: 校验 payload 完整性
    if (!payload || !payload.task_id) {
      console.warn('[P3] task_started payload 缺少 task_id，跳过');
      return;
    }

    // === 去重守卫：同一 task_id 只处理一次，防止 HTTP+WebSocket 双重推送 ===
    if (processedTaskIds.current.has(payload.task_id)) {
      console.log('⚠️ 跳过重复的 task_started:', payload.task_id);
      return;
    }
    processedTaskIds.current.add(payload.task_id);

    setCurrentTaskId(payload.task_id);
    setStreaming(true);
    
    // ⭐ v2.6 新增：提取意图和人格信息
    const meta = payload.context?.meta || {};
    const intent = meta.intent;
    const persona = meta.persona;
    
    console.log('🧠 Intent Router 决策:', { intent, persona });
    
    // 用户消息已在 ChatInput.handleSubmit 中添加，此处只添加 AI 占位消息

    // 添加 AI 占位消息（支持分离的通道 + 意图/人格元数据）
    addMessage({
      id: payload.task_id,
      role: 'assistant',
      content: '',
      reasoningContent: '',  // ⭐ 思考过程
      contentChannel: '',    // ⭐ 最终产出
      timestamp: Date.now(),
      taskId: payload.task_id,
      steps: [],
      intent: intent,        // ⭐ v2.6 新增
      persona: persona       // ⭐ v2.6 新增
    });
  };

  const handleTaskCompleted = (payload: any) => {
    setCurrentTaskId(null);
    setStreaming(false);
    setCurrentPhase(null);
    
    // ⭐ 关键修复: 不要覆盖流式输出的内容!
    // 如果已经有 contentChannel (流式输出),就保留它
    // 只有在没有流式内容时,才使用 payload.result
    
    updateMessage(payload.task_id, (prev: any) => {
      // 检查是否已有流式内容
      const hasStreamingContent = prev.contentChannel || prev.content;
      
      if (hasStreamingContent) {
        // 已有流式内容,不覆盖,只标记任务完成
        console.log('✅ 保留流式输出内容,长度:', hasStreamingContent.length);
        return prev;
      }
      
      // 没有流式内容,使用 payload.result
      const content = typeof payload.result === 'string' 
        ? payload.result 
        : (payload.result?.text || '任务完成');
      
      console.log('✅ 使用 payload.result,内容:', content.substring(0, 50));
      return {
        ...prev,
        content: content
      };
    });
  };

  const handleTaskFailed = (payload: any) => {
    setCurrentTaskId(null);
    setStreaming(false);
    setCurrentPhase(null);
    
    updateMessage(payload.task_id, {
      content: `❌ 任务失败: ${payload.error.message}`
    });
  };

  const handleStepStarted = (payload: any) => {
    // ⭐ 更新当前阶段
    setCurrentPhase(payload.phase || payload.step_type);
    
    addStep(payload.task_id, {
      id: payload.step_id,
      type: payload.step_type,
      phase: payload.phase,  // ⭐ 保存阶段信息
      status: 'running',
      startedAt: Date.now()
    });
  };

  const handleStepFinished = (payload: any) => {
    updateStep(payload.task_id, payload.step_id, {
      status: 'completed',
      output: payload.output,
      completedAt: Date.now()
    });
  };

  const handleStreamChunk = (payload: any) => {
    const { task_id, chunk, phase, channel } = payload;
    
    console.log('🔄 handleStreamChunk - phase:', phase, 'channel:', channel);
    
    updateMessage(task_id, (prev: any) => {
      // ⭐ 根据 channel 分离内容
      if (channel === 'reasoning') {
        // 思考过程
        const newReasoning = (prev.reasoningContent || '') + chunk;
        console.log('✅ reasoning 更新 - 长度:', newReasoning.length);
        return {
          ...prev,
          reasoningContent: newReasoning
        };
      } else {
        // 最终产出（默认 channel = content）
        const newContent = (prev.contentChannel || prev.content || '') + chunk;
        console.log('✅ content 更新 - 长度:', newContent.length);
        return {
          ...prev,
          content: newContent,      // 向后兼容：也更新content
          contentChannel: newContent
        };
      }
    });
  };

  // ⭐ v2.7 新增：处理 file_ops 消息
  const handleFileOps = (payload: any) => {
    const { taskId, fileOps } = payload;
    
    console.log('📁 收到 FileOps:', { taskId, count: fileOps.length });
    
    setCurrentTaskIdForFileOps(taskId);
    setCurrentFileOps(fileOps);
    // ⭐ v3.5: 不再自动弹窗，改为面板按钮触发
    setShowFileOpsPanel(true);
  };

  // P1：处理 artifact_created 消息
  const handleArtifactCreated = (payload: any) => {
    const artifact = {
      artifact_id: payload.artifact_id,
      artifact_type: payload.artifact_type,
      format: payload.format,
      content: payload.content,
      label: payload.label,
      sequence: payload.sequence || 0,
      created_at: payload.created_at || Date.now(),
    };
    addArtifact(payload.task_id, artifact);
  };

  // Phase 2.4 P0-4: 收到确认请求
  const handleConfirmationRequired = (payload: any) => {
    if (!payload || !payload.confirmation_id) {
      console.warn('[P0-4] confirmation_required payload 缺少 confirmation_id');
      return;
    }
    setPendingConfirmation({
      confirmation_id: payload.confirmation_id,
      task_id: payload.task_id,
      target_path: payload.target_path,
      project_mode: payload.project_mode,
      allowed_paths: payload.allowed_paths,
      estimated_impact: payload.estimated_impact,
      expires_at: payload.expires_at,
      expires_in_seconds: payload.expires_in_seconds,
    });
  };

  // Phase 2.4 P0-4: 确认已解决（确认或拒绝后 Extension 发回结果）
  const handleConfirmationResolved = (payload: any) => {
    clearPendingConfirmation();
    if (payload.status === 'submitted') {
      console.log('[P0-4] Task submitted after confirmation:', payload.task_id);
    }
  };

  // ⭐ v2.7 新增：应用文件操作
  const handleApplyFileOps = () => {
    if (!currentTaskIdForFileOps || currentFileOps.length === 0) {
      console.warn('⚠️ 没有可应用的文件操作');
      return;
    }
    
    console.log('✅ 应用文件操作:', currentFileOps.length);
    
    // 发送消息给 Extension
    vscodeAPI.postMessage({
      type: 'apply_file_ops',
      taskId: currentTaskIdForFileOps,
      fileOps: currentFileOps
    });
    
    // 关闭 FileOps 面板
    setShowFileOps(false);
  };

  // ⭐ v2.7 新增：取消文件操作
  const handleCancelFileOps = () => {
    setShowFileOps(false);
    setCurrentFileOps([]);
    setCurrentTaskIdForFileOps(null);
  };

  return (
    <div className="flex flex-col h-screen bg-vscode-bg text-vscode-fg">
      <Toolbar 
        showStepPanel={showStepPanel} 
        setShowStepPanel={setShowStepPanel}
        showTaskHistory={showTaskHistory}
        setShowTaskHistory={setShowTaskHistory}
        showFileVersion={showFileVersion}
        setShowFileVersion={setShowFileVersion}
        showProjectMemory={showProjectMemory}
        setShowProjectMemory={setShowProjectMemory}
        showFileOpsPanel={showFileOpsPanel}
        setShowFileOpsPanel={setShowFileOpsPanel}
        pendingFileOpsCount={currentFileOps.length}
      />
      <ModelSelector />
      <MessageList />

      {/* Phase 2.4 P0-4: 确认卡片 — 内联嵌入聊天流 */}
      {pendingConfirmation && (
        <div className="px-4 pb-2">
          <ConfirmationCard
            confirmation={pendingConfirmation}
            onResolved={clearPendingConfirmation}
          />
        </div>
      )}

      <TestAuthorizationBar
        requests={testAuthorizations}
        onDecision={(taskId, action) => handleTestAuthorizationDecision(taskId, action)}
      />

      <ChatInput conversationId={conversationId} />

      {/* ⭐ v3.2 新增：StepPanel 侧边栏 */}
      {showStepPanel && (
        <div className="fixed right-0 top-12 h-full w-96 bg-vscode-panel border-l border-vscode-border shadow-2xl z-40 overflow-y-auto animate-slide-in-right">
          <div className="p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <span>📊</span>
                <span>任务步骤</span>
              </h3>
              <button
                onClick={() => setShowStepPanel(false)}
                className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-vscode-hover transition-colors"
              >
                ✕
              </button>
            </div>
            
            {/* 显示当前任务的所有步骤 */}
            {useChatStore.getState().messages
              .filter(msg => msg.taskId && msg.steps && msg.steps.length > 0)
              .map(msg => (
                <StepPanel
                  key={msg.taskId}
                  steps={msg.steps || []}
                  currentPhase={useChatStore.getState().currentPhase}
                  isStreaming={useChatStore.getState().isStreaming && msg.taskId === useChatStore.getState().currentTaskId}
                />
              ))}
          </div>
        </div>
      )}

      {/* ⭐ v3.5+ 新增：任务历史面板 */}
      {showTaskHistory && (
        <TaskHistoryPanel onClose={() => setShowTaskHistory(false)} />
      )}

      {/* ⭐ v3.5+ 新增：文件版本面板 */}
      {showFileVersion && selectedFileId && (
        <FileVersionPanel 
          fileId={selectedFileId}
          filePath={selectedFilePath}
          onClose={() => setShowFileVersion(false)}
        />
      )}

      {/* ⭐ v3.5+ 新增：项目记忆面板 */}
      {showProjectMemory && (
        <ProjectMemoryPanel 
          projectId={selectedProjectId}
          projectName={selectedProjectName}
          onClose={() => setShowProjectMemory(false)}
        />
      )}

      {/* P0: FileOps 确认卡片 — 内联嵌入聊天流（替代固定侧边栏） */}
      {showFileOpsPanel && currentFileOps.length > 0 && (
        <FileOpsConfirmCard
          fileOps={currentFileOps}
          taskId={currentTaskIdForFileOps}
          onApplyAll={() => {
            console.log('✅ 应用文件操作:', currentFileOps.length);
            vscodeAPI.postMessage({
              type: 'apply_file_ops',
              taskId: currentTaskIdForFileOps,
              fileOps: currentFileOps,
            });
            setShowFileOpsPanel(false);
            setCurrentFileOps([]);
            setCurrentTaskIdForFileOps(null);
          }}
          onRejectAll={() => {
            setShowFileOpsPanel(false);
            setCurrentFileOps([]);
            setCurrentTaskIdForFileOps(null);
          }}
        />
      )}

      <FileOpsList
        show={showFileOps}
        setShow={setShowFileOps}
        fileOps={currentFileOps}
        taskId={currentTaskIdForFileOps}
      />
    </div>
  );
}

export default App;