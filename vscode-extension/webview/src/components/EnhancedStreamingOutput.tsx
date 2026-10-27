// src/components/EnhancedStreamingOutput.tsx
// v3.6 P0: 流式输出智能渲染 - 区分文本/代码块/Mermaid，消除冗余打字机延迟

import React, { useEffect, useRef, useMemo } from 'react';

interface EnhancedStreamingOutputProps {
  content: string;
  isStreaming: boolean;
  channel?: 'reasoning' | 'content';
  speed?: number;
}

interface ContentSegment {
  type: 'text' | 'code_block';
  content: string;
  language: string;
  isComplete: boolean;   // 代码块是否已闭合 ```
}

function parseContentSegments(text: string): ContentSegment[] {
  const segments: ContentSegment[] = [];
  const regex = /```(\w*)\n([\s\S]*?)(```|$)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        type: 'text',
        content: text.substring(lastIndex, match.index),
        language: '',
        isComplete: true,
      });
    }

    const language = (match[1] || '').toLowerCase();
    const code = match[2] || '';
    const isComplete = match[3] === '```';

    segments.push({
      type: 'code_block',
      content: code,
      language,
      isComplete,
    });

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    segments.push({
      type: 'text',
      content: text.substring(lastIndex),
      language: '',
      isComplete: true,
    });
  }

  return segments;
}

const BLOCK_ICONS: Record<string, string> = {
  mermaid: '',
  python: '',
  javascript: '',
  typescript: '',
  json: '',
  bash: '',
  sh: '',
  sql: '',
  yaml: '',
  html: '',
  css: '',
  default: '',
};

const BLOCK_LABELS: Record<string, string> = {
  mermaid: '架构图',
  python: 'Python',
  javascript: 'JavaScript',
  typescript: 'TypeScript',
  json: 'JSON',
  bash: 'Shell',
  sh: 'Shell',
  sql: 'SQL',
  yaml: 'YAML',
  html: 'HTML',
  css: 'CSS',
  default: '代码块',
};

export const EnhancedStreamingOutput: React.FC<EnhancedStreamingOutputProps> = ({
  content,
  isStreaming,
  channel = 'content',
  speed = 5,   // ⭐ 提速：从15ms降到5ms（后端已逐token流式，无需再缓冲）
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const isReasoning = channel === 'reasoning';

  const segments = useMemo(() => parseContentSegments(content), [content]);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [content]);

  if (!content && !isStreaming) {
    return null;
  }

  return (
    <div
      ref={containerRef}
      className={`enhanced-streaming-output max-h-[500px] overflow-y-auto scrollbar-thin ${
        isReasoning ? 'text-purple-300' : 'text-vscode-fg'
      }`}
    >
      {/* 加载动画 */}
      {isStreaming && content.length === 0 && (
        <div className="flex items-center gap-2 mb-3 text-xs">
          <div className="flex gap-1">
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
          </div>
          <span className={isReasoning ? 'text-purple-400' : 'text-blue-400'}>
            {isReasoning ? '  AI 正在思考...' : '  AI 正在生成...'}
          </span>
        </div>
      )}

      {/* 内容展示 */}
      <div className="text-sm leading-relaxed">
        {segments.map((seg, i) => {
          if (seg.type === 'text') {
            return (
              <div key={i} className="whitespace-pre-wrap">
                {seg.content}
              </div>
            );
          }

          // 代码块
          if (seg.type === 'code_block') {
            const isMermaid = seg.language === 'mermaid';
            const icon = BLOCK_ICONS[seg.language] || BLOCK_ICONS.default;
            const label = BLOCK_LABELS[seg.language] || BLOCK_LABELS.default;

            if (isStreaming && !seg.isComplete) {
              return (
                <div
                  key={i}
                  className="my-3 rounded-lg border border-blue-500/20 bg-[#1e1e1e] overflow-hidden"
                >
                  <div className="flex items-center justify-between px-3 py-1.5 bg-blue-500/10 border-b border-blue-500/20">
                    <div className="flex items-center gap-2 text-xs text-blue-400">
                      <span>{icon}</span>
                      <span className="font-semibold">
                        {isMermaid ? '架构图' : label}
                      </span>
                    </div>
                    <span className="text-xs text-blue-400/70 animate-pulse">生成中...</span>
                  </div>
                  <pre className="p-3 text-xs text-gray-300 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto font-mono leading-relaxed">
                    {seg.content}
                  </pre>
                </div>
              );
            }

            if (isStreaming && seg.isComplete) {
              return (
                <div
                  key={i}
                  className="my-3 rounded-lg border border-green-500/20 bg-[#1e1e1e] overflow-hidden"
                >
                  <div className="flex items-center justify-between px-3 py-1.5 bg-green-500/10 border-b border-green-500/20">
                    <div className="flex items-center gap-2 text-xs text-green-400">
                      <span>{icon}</span>
                      <span className="font-semibold">
                        {isMermaid ? '架构图' : label}
                      </span>
                    </div>
                    <span className="text-xs text-green-400/70">{isMermaid ? ' ✓ 结构图完成' : ' ✓ 代码块完成'}</span>
                  </div>
                  <pre className="p-3 text-xs text-gray-300 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto font-mono leading-relaxed">
                    {seg.content}
                  </pre>
                </div>
              );
            }

            // ⭐ 非流式状态 → 折叠卡片（MarkdownRenderer 会渲染真实图表）
            return (
              <div
                key={i}
                className="my-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3"
              >
                <details>
                  <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400 flex items-center gap-2">
                    <span>{icon}</span>
                    <span>
                      {isMermaid ? ' 架构图源码' : `   ${label} 源码`}
                    </span>
                  </summary>
                  <pre className="mt-2 text-xs text-gray-400 whitespace-pre-wrap overflow-x-auto bg-gray-900/50 p-2 rounded max-h-48 overflow-y-auto">
                    {seg.content}
                  </pre>
                </details>
              </div>
            );
          }

          return null;
        })}

        {/* 流式光标 */}
        {isStreaming && content.length > 0 && (
          <span className="inline-block w-2 h-4 bg-blue-400 ml-0.5 animate-pulse"></span>
        )}
      </div>
    </div>
  );
};