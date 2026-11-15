// src/components/StreamingOutput.tsx
// v4.0 修复版 — 修复旧版「content 变化即重置打字机」的闪回 bug
// 旧版问题：
//   1) 监听 content 的 effect 在流式场景每次 chunk 到达都重置进度 → 视觉上不断从头重打
//   2) 逐字符 setTimeout(10ms) 产生 O(n) 个定时器，长文本卡顿
// 新版：useTypewriter rAF 引擎（时间步进 + 智能追赶 + 收尾快速补齐）

import React from 'react';
import { useTypewriter } from '../hooks/useTypewriter';

interface StreamingOutputProps {
  content: string;
  isStreaming: boolean;
}

export const StreamingOutput: React.FC<StreamingOutputProps> = ({ content, isStreaming }) => {
  const shown = useTypewriter(content, isStreaming, { cps: 100 });

  if (!content && !isStreaming) {
    return null;
  }

  return (
    <div className="streaming-output">
      {isStreaming && shown.length === 0 && (
        <div className="flex items-center gap-2 mb-2 text-xs text-blue-400">
          <span className="animate-pulse">●</span>
          <span>AI 正在思考...</span>
        </div>
      )}

      <div className="whitespace-pre-wrap text-sm leading-relaxed">
        {shown}
        {isStreaming && <span className="ap-cursor" />}
      </div>
    </div>
  );
};
