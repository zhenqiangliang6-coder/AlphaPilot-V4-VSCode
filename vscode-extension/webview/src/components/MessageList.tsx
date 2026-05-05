// src/components/MessageList.tsx
import React, { useEffect, useRef } from 'react';
import { useChatStore } from '../store/chatStore';
import { StepTree } from './StepTree';

export const MessageList: React.FC = () => {
  const { messages } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <div className="text-center">
          <div className="text-4xl mb-2">🚀</div>
          <div>开始与 AlphaPilot 对话</div>
          <div className="text-sm mt-2">输入任务描述,AI 将帮你完成</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div
            className={`max-w-[80%] rounded-lg px-4 py-2 ${
              message.role === 'user'
                ? 'bg-vscode-button-bg text-vscode-button-fg'
                : 'bg-vscode-list-hover text-vscode-fg'
            }`}
          >
            {/* 用户消息 */}
            {message.role === 'user' && (
              <div className="whitespace-pre-wrap">{message.content}</div>
            )}

            {/* AI 消息 */}
            {message.role === 'assistant' && (
              <div className="space-y-3">
                {/* 步骤树 */}
                {message.steps && message.steps.length > 0 && (
                  <StepTree steps={message.steps} />
                )}

                {/* 文本内容 */}
                {message.content && (
                  <div className="prose prose-invert max-w-none">
                    <pre className="whitespace-pre-wrap text-sm">
                      {message.content}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* 时间戳 */}
            <div className="text-xs opacity-50 mt-2">
              {new Date(message.timestamp).toLocaleTimeString()}
            </div>
          </div>
        </div>
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
};
