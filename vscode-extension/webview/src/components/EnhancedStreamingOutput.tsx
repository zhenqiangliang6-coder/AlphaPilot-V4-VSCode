// src/components/EnhancedStreamingOutput.tsx
// v4.0 Tech 重构 — rAF 打字机引擎 + 增量 Markdown 渲染 + 流式光标 + shimmer 思考态
// 渲染策略：
//   - 已稳定文本段  → memo 隔离的 MarkdownRenderer（chunk 到达时不重渲）
//   - 已闭合代码块  → memo 隔离的 Prism 高亮（只渲一次）
//   - 尾部活动文本段 → 纯文本 + terminal 风格流式光标
//   - 生成中代码块   → 流光呼吸卡片 + 纯文本预览
// 滚动策略：仅当用户位于底部附近时自动跟随，向上翻阅历史不被打断

import React, { useEffect, useMemo, useRef } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { MarkdownRenderer } from './MarkdownRenderer';
import { useTypewriter } from '../hooks/useTypewriter';
import { parseContentSegments } from './streamSegments';

interface EnhancedStreamingOutputProps {
  content: string;
  isStreaming: boolean;
  channel?: 'reasoning' | 'content';
  speed?: number; // 每字符毫秒（兼容旧参数），默认 5ms → 200 cps
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

/** 稳定文本段 — memo 隔离：chunk 到达 / 打字机推进时，已稳定段落零重渲 */
const StableText = React.memo(function StableText({ content }: { content: string }) {
  return (
    <div className="markdown-renderer text-sm leading-relaxed">
      <MarkdownRenderer content={content} />
    </div>
  );
});

/** 已闭合代码块 — Prism 高亮一次，内容不再变化 */
const ClosedCode = React.memo(function ClosedCode({
  code,
  language,
}: {
  code: string;
  language: string;
}) {
  const isMermaid = language === 'mermaid';
  const label = BLOCK_LABELS[language] || BLOCK_LABELS.default;
  return (
    <div className="my-3 rounded-lg border border-emerald-400/15 bg-[#161b26] overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-emerald-400/[0.06] border-b border-emerald-400/15">
        <span className="text-[11px] font-medium text-emerald-300/90 tracking-wide">
          {BLOCK_ICONS[language] || BLOCK_ICONS.default} {isMermaid ? '架构图' : label}
        </span>
        <span className="text-[10px] text-emerald-400/60">✓ 完成</span>
      </div>
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={isMermaid ? 'text' : language || 'text'}
        PreTag="div"
        customStyle={{ margin: 0, fontSize: '12px', lineHeight: '1.6', background: 'transparent' }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
});

export const EnhancedStreamingOutput: React.FC<EnhancedStreamingOutputProps> = ({
  content,
  isStreaming,
  channel = 'content',
  speed = 5,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const isReasoning = channel === 'reasoning';

  // ⚡ rAF 打字机引擎：时间步进、智能追赶、收尾快速补齐
  const shown = useTypewriter(content, isStreaming, {
    cps: Math.min(2000, Math.round(1000 / Math.max(speed, 1))),
  });

  const segments = useMemo(() => parseContentSegments(shown), [shown]);

  // 智能自动滚动：仅当用户位于底部附近（<80px）时跟随，向上翻阅不打扰
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) {
      el.scrollTop = el.scrollHeight;
    }
  }, [shown, segments.length]);

  if (!content && !isStreaming) {
    return null;
  }

  const lastIdx = segments.length - 1;

  return (
    <div
      ref={containerRef}
      className={`enhanced-streaming-output max-h-[500px] overflow-y-auto scrollbar-thin ${
        isReasoning ? 'text-purple-300/90' : 'text-vscode-fg'
      }`}
    >
      {/* 思考/生成中 shimmer 态 */}
      {isStreaming && shown.length === 0 && (
        <div className="mb-3">
          <div className="flex items-center gap-2 mb-2.5 text-xs">
            <span className="w-1.5 h-1.5 rounded-full bg-gradient-to-r from-cyan-400 to-indigo-400 ap-dot" />
            <span className={isReasoning ? 'text-purple-400/80' : 'text-indigo-400/80'}>
              {isReasoning ? 'AI 正在思考' : 'AI 正在生成'}
            </span>
          </div>
          <div className="space-y-2">
            <div className="h-3 ap-shimmer" style={{ width: '86%' }} />
            <div className="h-3 ap-shimmer" style={{ width: '94%' }} />
            <div className="h-3 ap-shimmer" style={{ width: '58%' }} />
          </div>
        </div>
      )}

      <div className="text-sm leading-relaxed">
        {segments.map((seg, i) => {
          const isTail = isStreaming && i === lastIdx;

          if (seg.type === 'text') {
            if (isTail) {
              // 尾部活动段：纯文本（低成本），光标统一在末尾
              return (
                <div key={i} className="whitespace-pre-wrap">
                  {seg.content}
                </div>
              );
            }
            return <StableText key={i} content={seg.content} />;
          }

          // 代码块
          if (seg.isComplete) {
            return (
              <ClosedCode key={i} code={seg.content} language={seg.language} />
            );
          }

          // 生成中代码块：流光呼吸卡片
          const isMermaid = seg.language === 'mermaid';
          return (
            <div
              key={i}
              className="my-3 rounded-lg border border-indigo-400/25 bg-[#161b26] overflow-hidden ap-breathe"
            >
              <div className="flex items-center justify-between px-3 py-1.5 bg-indigo-400/[0.06] border-b border-indigo-400/20">
                <span className="text-[11px] font-medium text-indigo-300/90 tracking-wide">
                  {BLOCK_ICONS[seg.language] || BLOCK_ICONS.default}{' '}
                  {isMermaid ? '架构图' : BLOCK_LABELS[seg.language] || BLOCK_LABELS.default}
                </span>
                <span className="text-[10px] text-indigo-300/70">生成中…</span>
              </div>
              <pre className="p-3 text-xs text-gray-300/90 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto font-mono leading-relaxed">
                {seg.content}
              </pre>
              <div className="h-0.5 ap-shimmer" />
            </div>
          );
        })}

        {/* terminal 风格流式光标 */}
        {isStreaming && shown.length > 0 && <span className="ap-cursor" />}
      </div>
    </div>
  );
};
