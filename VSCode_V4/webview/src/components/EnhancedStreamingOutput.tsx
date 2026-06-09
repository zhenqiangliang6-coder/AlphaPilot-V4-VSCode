// src/components/EnhancedStreamingOutput.tsx
import React, { useState, useEffect, useRef } from 'react';

interface EnhancedStreamingOutputProps {
  content: string;
  isStreaming: boolean;
  channel?: 'reasoning' | 'content';
  speed?: number; // 打字速度 (ms)
}

export const EnhancedStreamingOutput: React.FC<EnhancedStreamingOutputProps> = ({ 
  content, 
  isStreaming, 
  channel = 'content',
  speed = 15 
}) => {
  const [displayedContent, setDisplayedContent] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);

  // 打字机效果
  useEffect(() => {
    if (content.length > displayedContent.length && isStreaming) {
      const timeout = setTimeout(() => {
        setDisplayedContent(content.substring(0, currentIndex + 1));
        setCurrentIndex(currentIndex + 1);
      }, speed);

      return () => clearTimeout(timeout);
    } else if (!isStreaming && content.length > displayedContent.length) {
      // 流式结束后，快速显示剩余内容
      setDisplayedContent(content);
      setCurrentIndex(content.length);
    }
  }, [content, displayedContent, currentIndex, isStreaming, speed]);

  // 重置状态当内容变化时
  useEffect(() => {
    setDisplayedContent('');
    setCurrentIndex(0);
  }, [content]);

  // 自动滚动到底部
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [displayedContent]);

  if (!content && !isStreaming) {
    return null;
  }

  const isReasoning = channel === 'reasoning';

  return (
    <div 
      ref={contentRef}
      className={`enhanced-streaming-output max-h-96 overflow-y-auto scrollbar-thin ${
        isReasoning ? 'text-purple-300' : 'text-vscode-fg'
      }`}
    >
      {/* 加载动画 */}
      {isStreaming && displayedContent.length === 0 && (
        <div className="flex items-center gap-2 mb-3 text-xs">
          <div className="flex gap-1">
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
          </div>
          <span className={isReasoning ? 'text-purple-400' : 'text-blue-400'}>
            {isReasoning ? '💭 AI 正在思考...' : '✨ AI 正在生成...'}
          </span>
        </div>
      )}
      
      {/* 内容展示 */}
      <div className="whitespace-pre-wrap text-sm leading-relaxed">
        {displayedContent}
        {isStreaming && displayedContent.length < content.length && (
          <span className="inline-block w-2 h-4 bg-blue-400 ml-1 animate-pulse">▌</span>
        )}
      </div>
    </div>
  );
};
