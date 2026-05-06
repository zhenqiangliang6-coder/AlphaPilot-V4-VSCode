// src/App.tsx
import React, { useEffect } from 'react';
import { useChatStore } from './store/chatStore';
import { Toolbar } from './components/Toolbar';
import { ModelSelector } from './components/ModelSelector';
import { MessageList } from './components/MessageList';
import { ChatInput } from './components/ChatInput';
import { vscodeAPI } from './utils/vscode';

function App() {
  const { 
    addMessage, 
    updateMessage, 
    setCurrentTaskId, 
    setStreaming, 
    addStep, 
    updateStep,
    setCurrentPhase  // ⭐ 新增
  } = useChatStore();

  // 监听来自 Extension 的消息
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const message = event.data;
      console.log('📥 Extension → Webview:', message);

      switch (message.type) {
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
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  const handleTaskStarted = (payload: any) => {
    setCurrentTaskId(payload.task_id);
    setStreaming(true);
    
    // 添加用户消息
    addMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: payload.prompt,
      timestamp: Date.now()
    });

    // 添加 AI 占位消息（支持分离的通道）
    addMessage({
      id: payload.task_id,
      role: 'assistant',
      content: '',
      reasoningContent: '',  // ⭐ 思考过程
      contentChannel: '',    // ⭐ 最终产出
      timestamp: Date.now(),
      taskId: payload.task_id,
      steps: []
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

  return (
    <div className="flex flex-col h-screen bg-vscode-bg text-vscode-fg">
      <Toolbar />
      <ModelSelector />
      <MessageList />
      <ChatInput />
    </div>
  );
}

export default App;
