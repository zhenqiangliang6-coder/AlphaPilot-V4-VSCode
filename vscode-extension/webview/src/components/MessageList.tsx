// src/components/MessageList.tsx
import React, { useEffect, useRef } from 'react';
import { useChatStore } from '../store/chatStore';
import { StepTree } from './StepTree';
import { StreamingOutput } from './StreamingOutput';
import { MarkdownRenderer } from './MarkdownRenderer';
import { IntentBadge } from './IntentBadge';      // ⭐ v2.6 新增
import { PersonaIcon } from './PersonaIcon';      // ⭐ v2.6 新增

export const MessageList: React.FC = () => {
  const { messages, isStreaming, currentPhase } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <div className="text-center space-y-3">
          <div className="text-6xl animate-bounce">🚀</div>
          <div className="text-lg font-semibold">开始与 AlphaPilot 对话</div>
          <div className="text-sm text-gray-400">输入任务描述，AI 将帮你完成</div>
          <div className="text-xs text-gray-500 mt-4 space-y-1">
            <div>✨ 支持代码生成、问题解答、任务规划</div>
            <div>⚡ 实时流式输出，可视化执行步骤</div>
            <div>🎨 Markdown渲染，代码高亮显示</div>
            <div>💭 思考过程与最终产出分离展示</div>
            <div>🧠 智能意图识别，自动切换人格</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in`}
        >
          <div
            className={`max-w-[85%] rounded-lg px-4 py-3 shadow-md ${
              message.role === 'user'
                ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white'
                : 'bg-vscode-list-hover border border-vscode-border'
            }`}
          >
            {/* 用户消息 */}
            {message.role === 'user' && (
              <div className="whitespace-pre-wrap">{message.content}</div>
            )}

            {/* AI 消息 */}
            {message.role === 'assistant' && (
              <div className="space-y-4">
                {/* ⭐ v2.6 新增：意图和人格标签 */}
                {(message.intent || message.persona) && (
                  <div className="flex items-center gap-2 mb-2">
                    <PersonaIcon persona={message.persona} />
                    <IntentBadge intent={message.intent} />
                  </div>
                )}

                {/* 步骤树 */}
                {message.steps && message.steps.length > 0 && (
                  <StepTree steps={message.steps} />
                )}

                {/* ⭐ 思考过程（channel = reasoning）*/}
                {message.reasoningContent && (
                  <div className="mt-3 p-3 bg-purple-500/10 border-l-4 border-purple-500 rounded">
                    <div className="text-xs text-purple-400 mb-2 flex items-center gap-2">
                      <span>💭</span>
                      <span>AI 思考过程</span>
                      {isStreaming && <span className="animate-pulse">●</span>}
                    </div>
                    <StreamingOutput 
                      content={message.reasoningContent} 
                      isStreaming={isStreaming} 
                    />
                  </div>
                )}

                {/* ⭐ 最终产出（channel = content）*/}
                {(message.contentChannel || message.content) && (
                  <div className="mt-3">
                    {isStreaming ? (
                      <StreamingOutput 
                        content={message.contentChannel || message.content} 
                        isStreaming={isStreaming} 
                      />
                    ) : (
                      <MarkdownRenderer content={message.contentChannel || message.content} />
                    )}
                  </div>
                )}
              </div>
            )}

            {/* 时间戳和阶段标签 */}
            <div className="text-xs opacity-50 mt-2 text-right flex items-center justify-end gap-2">
              {currentPhase && isStreaming && (
                <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs">
                  {currentPhase}
                </span>
              )}
              <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
            </div>
          </div>
        </div>
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
};
