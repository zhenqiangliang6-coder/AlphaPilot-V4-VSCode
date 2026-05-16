// src/components/ChatBubble.tsx
import React from 'react';
import { PersonaIcon } from './PersonaIcon';
import { IntentBadge } from './IntentBadge';
import { StepTree } from './StepTree';
import { EnhancedStreamingOutput } from './EnhancedStreamingOutput';
import { MarkdownRenderer } from './MarkdownRenderer';
import { Step } from '../store/chatStore';

interface ChatBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  reasoningContent?: string;
  contentChannel?: string;
  timestamp: number;
  taskId?: string;
  steps?: Step[];
  intent?: string;
  persona?: string;
  isStreaming?: boolean;
  currentPhase?: string | null;
}

// 人格对应的头像和标签
const personaConfig: Record<string, { icon: string; label: string; color: string }> = {
  engineer: { icon: '🤖', label: '工程师', color: 'blue' },
  creator: { icon: '🎨', label: '创作者', color: 'purple' },
  conversational: { icon: '💬', label: '对话者', color: 'green' },
  analyst: { icon: '🔬', label: '分析师', color: 'yellow' },
  architect: { icon: '️', label: '架构师', color: 'orange' }
};

export const ChatBubble: React.FC<ChatBubbleProps> = ({
  role,
  content,
  reasoningContent,
  contentChannel,
  timestamp,
  taskId,
  steps,
  intent,
  persona,
  isStreaming = false,
  currentPhase
}) => {
  const isUser = role === 'user';
  const personaInfo = persona ? personaConfig[persona] : null;

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in gap-3`}>
      {/* AI 头像 */}
      {!isUser && (
        <div className="flex-shrink-0 mt-2">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-lg shadow-lg">
            {personaInfo?.icon || '🚀'}
          </div>
        </div>
      )}

      {/* 消息气泡 */}
      <div className={`max-w-[80%] ${isUser ? 'order-first' : ''}`}>
        <div
          className={`rounded-2xl px-5 py-4 shadow-lg ${
            isUser
              ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-tr-sm'
              : 'bg-vscode-list-hover border border-vscode-border rounded-tl-sm'
          }`}
        >
          {/* 人格标签 (仅 AI 消息) */}
          {!isUser && (persona || intent) && (
            <div className="flex items-center gap-2 mb-3 pb-3 border-b border-vscode-border/50">
              {personaInfo && (
                <span className="px-2 py-1 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-full text-xs font-medium">
                  {personaInfo.icon} {personaInfo.label}
                </span>
              )}
              {intent && <IntentBadge intent={intent} />}
            </div>
          )}

          {/* 步骤树 */}
          {steps && steps.length > 0 && (
            <div className="mb-4">
              <StepTree steps={steps} />
            </div>
          )}

          {/* 思考过程 */}
          {reasoningContent && (
            <div className="mb-4 p-4 bg-purple-500/10 border-l-4 border-purple-500 rounded-lg">
              <div className="text-xs text-purple-400 mb-2 flex items-center gap-2">
                <span>💭</span>
                <span className="font-semibold">AI 思考过程</span>
                {isStreaming && (
                  <span className="px-2 py-0.5 bg-purple-500/20 rounded text-xs animate-pulse">
                    思考中
                  </span>
                )}
              </div>
              <EnhancedStreamingOutput 
                content={reasoningContent} 
                isStreaming={isStreaming}
                channel="reasoning"
              />
            </div>
          )}

          {/* 最终产出 */}
          {(contentChannel || content) && (
            <div>
              {isStreaming ? (
                <EnhancedStreamingOutput 
                  content={contentChannel || content} 
                  isStreaming={isStreaming}
                  channel="content"
                />
              ) : (
                <MarkdownRenderer content={contentChannel || content} />
              )}
            </div>
          )}

          {/* 时间戳和阶段 */}
          <div className="mt-3 pt-3 border-t border-vscode-border/30 flex items-center justify-between">
            <div className="flex items-center gap-2">
              {currentPhase && isStreaming && (
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  currentPhase === 'analyze' ? 'bg-blue-500/20 text-blue-400' :
                  currentPhase === 'plan' ? 'bg-yellow-500/20 text-yellow-400' :
                  currentPhase === 'write' ? 'bg-green-500/20 text-green-400' :
                  currentPhase === 'refine' ? 'bg-purple-500/20 text-purple-400' :
                  currentPhase === 'test' ? 'bg-cyan-500/20 text-cyan-400' :
                  'bg-gray-500/20 text-gray-400'
                }`}>
                  {currentPhase === 'analyze' && '🔍 '}
                  {currentPhase === 'plan' && ' '}
                  {currentPhase === 'write' && '✍️ '}
                  {currentPhase === 'refine' && '⚡ '}
                  {currentPhase === 'test' && '✅ '}
                  {currentPhase}
                </span>
              )}
            </div>
            <span className="text-xs opacity-50">
              {new Date(timestamp).toLocaleTimeString()}
            </span>
          </div>
        </div>
      </div>

      {/* 用户头像 */}
      {isUser && (
        <div className="flex-shrink-0 mt-2">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-green-500 to-blue-600 flex items-center justify-center text-lg shadow-lg">
            👤
          </div>
        </div>
      )}
    </div>
  );
};
