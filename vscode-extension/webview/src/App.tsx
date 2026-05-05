// src/App.tsx
import React, { useEffect } from 'react';
import { useChatStore } from './store/chatStore';
import { Toolbar } from './components/Toolbar';
import { ModelSelector } from './components/ModelSelector';
import { MessageList } from './components/MessageList';
import { ChatInput } from './components/ChatInput';
import { vscodeAPI } from './utils/vscode';

function App() {
  const { addMessage, updateMessage, setCurrentTaskId, setStreaming, addStep, updateStep } = useChatStore();

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
          console.log('📥 Webview 收到 stream_chunk:', JSON.stringify(message.payload, null, 2));
          handleStreamChunk(message.payload);
          break;
        
        case 'stream_end':
          setStreaming(false);
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

    // 添加 AI 占位消息
    addMessage({
      id: payload.task_id,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      taskId: payload.task_id,
      steps: []
    });
  };

  const handleTaskCompleted = (payload: any) => {
    setCurrentTaskId(null);
    setStreaming(false);
    
    // ⭐ 修复: result 可能是字符串(代码)或对象(有 text 字段)
    const content = typeof payload.result === 'string' 
      ? payload.result 
      : (payload.result?.text || '任务完成');
    
    updateMessage(payload.task_id, {
      content: content
    });
  };

  const handleTaskFailed = (payload: any) => {
    setCurrentTaskId(null);
    setStreaming(false);
    
    updateMessage(payload.task_id, {
      content: `❌ 任务失败: ${payload.error.message}`
    });
  };

  const handleStepStarted = (payload: any) => {
    addStep(payload.task_id, {
      id: payload.step_id,
      type: payload.step_type,
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
    console.log('🔄 handleStreamChunk 被调用 - task_id:', payload.task_id, 'chunk:', payload.chunk?.substring(0, 50));
    
    updateMessage(payload.task_id, (prev: any) => {
      const newContent = (prev.content || '') + payload.chunk;
      console.log('✅ 消息内容更新 - 长度:', newContent.length, '内容预览:', newContent.substring(0, 100));
      return {
        ...prev,
        content: newContent
      };
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
