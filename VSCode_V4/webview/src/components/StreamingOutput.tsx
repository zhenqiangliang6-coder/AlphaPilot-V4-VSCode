// src/components/StreamingOutput.tsx
import React, { useState, useEffect } from 'react';

interface StreamingOutputProps {
  content: string;
  isStreaming: boolean;
}

export const StreamingOutput: React.FC<StreamingOutputProps> = ({ content, isStreaming }) => {
  const [displayedContent, setDisplayedContent] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);

  // 打字机效果
  useEffect(() => {
    if (content.length > displayedContent.length) {
      const timeout = setTimeout(() => {
        setDisplayedContent(content.substring(0, currentIndex + 1));
        setCurrentIndex(currentIndex + 1);
      }, 10); // 每10ms显示一个字符

      return () => clearTimeout(timeout);
    }
  }, [content, displayedContent, currentIndex]);

  // 重置状态当内容变化时
  useEffect(() => {
    setDisplayedContent('');
    setCurrentIndex(0);
  }, [content]);

  if (!content && !isStreaming) {
    return null;
  }

  return (
    <div className="streaming-output">
      {isStreaming && (
        <div className="flex items-center gap-2 mb-2 text-xs text-blue-400">
          <span className="animate-pulse">●</span>
          <span>AI 正在思考...</span>
        </div>
      )}
      
      <div className="whitespace-pre-wrap text-sm leading-relaxed">
        {displayedContent || (isStreaming ? '▌' : '')}
      </div>
    </div>
  );
};
