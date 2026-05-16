// src/components/MessageList.tsx
import React, { useEffect, useRef } from 'react';
import { useChatStore } from '../store/chatStore';
import { ChatBubble } from './ChatBubble';  // ⭐ v3.2 新增：拟人化气泡对话框

export const MessageList: React.FC = () => {
  const { messages, isStreaming, currentPhase } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <div className="text-center space-y-4">
          <div className="text-7xl animate-bounce">🚀</div>
          <div className="text-xl font-semibold">开始与 AlphaPilot 对话</div>
          <div className="text-sm text-gray-400">输入任务描述，AI 将帮你完成</div>
          <div className="text-xs text-gray-500 mt-6 space-y-2 bg-vscode-list-hover/50 p-4 rounded-lg">
            <div>✨ 支持代码生成、问题解答、任务规划</div>
            <div> 实时流式输出，可视化执行步骤</div>
            <div>🎨 Markdown渲染，代码高亮显示</div>
            <div>💭 思考过程与最终产出分离展示</div>
            <div>🧠 智能意图识别，自动切换人格</div>
            <div>📁 文件操作预览，安全可控</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      {messages.map((message) => (
        <ChatBubble
          key={message.id}
          role={message.role}
          content={message.content}
          reasoningContent={message.reasoningContent}
          contentChannel={message.contentChannel}
          timestamp={message.timestamp}
          taskId={message.taskId}
          steps={message.steps}
          intent={message.intent}
          persona={message.persona}
          isStreaming={!!(isStreaming && message.taskId)}
          currentPhase={currentPhase}
        />
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
};
