// src/components/ChatBubble.tsx
import React, { useMemo } from 'react';
import { PersonaIcon } from './PersonaIcon';
import { IntentBadge } from './IntentBadge';
import { StepTree } from './StepTree';
import { EnhancedStreamingOutput } from './EnhancedStreamingOutput';
import { MarkdownRenderer } from './MarkdownRenderer';
import { MermaidBlock } from './MermaidBlock';
import { Step, Artifact } from '../store/chatStore';

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
  artifacts?: Artifact[];
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
  artifacts,
  isStreaming = false,
  currentPhase
}) => {
  const isUser = role === 'user';
  const personaInfo = persona ? personaConfig[persona] : null;

  // P1：去重 — 从 MarkdownRenderer 的输入中剥离 mermaid_diagram 产物已覆盖的代码块
  const strippedContent = useMemo(() => {
    if (!artifacts || artifacts.length === 0 || isStreaming) {
      return contentChannel || content;
    }
    const hasMermaidArtifact = artifacts.some(a => a.artifact_type === 'mermaid_diagram');
    if (!hasMermaidArtifact) {
      return contentChannel || content;
    }
    // 剥离 ```mermaid...``` 代码块，避免与 artifact 卡片双重渲染
    return (contentChannel || content).replace(/```mermaid\s*\n[\s\S]*?```/g, '');
  }, [contentChannel, content, artifacts, isStreaming]);

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
                <div>
                  {/* P1：artifact 卡片（mermaid_diagram 用 MermaidBlock 渲染） */}
                  {artifacts && artifacts.length > 0 && !isStreaming && (
                    <div className="space-y-3 mb-4">
                      {artifacts.map((artifact) => {
                        if (artifact.artifact_type === 'mermaid_diagram') {
                          return (
                            <MermaidBlock
                              key={artifact.artifact_id}
                              code={artifact.content}
                              label={artifact.label}
                            />
                          );
                        }
                        // 其他 artifact 类型 P2 实现，当前降级为折叠源码
                        return (
                          <details key={artifact.artifact_id} className="my-2 bg-vscode-bg/50 rounded-lg p-3 border border-gray-500/20">
                            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300">
                              📦 {artifact.label || artifact.artifact_id} ({artifact.artifact_type})
                            </summary>
                            <pre className="mt-2 text-xs text-gray-400 overflow-x-auto max-h-32">
                              {artifact.content}
                            </pre>
                          </details>
                        );
                      })}
                    </div>
                  )}
                  {/* MarkdownRenderer：使用剥离 mermaid 块后的内容 */}
                  <MarkdownRenderer content={strippedContent} />
                </div>
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