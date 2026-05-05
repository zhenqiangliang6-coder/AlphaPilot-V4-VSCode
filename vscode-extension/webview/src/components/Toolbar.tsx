// src/components/Toolbar.tsx
import React from 'react';
import { useChatStore } from '../store/chatStore';
import { clearChat, cancelTask } from '../utils/vscode';

export const Toolbar: React.FC = () => {
  const { currentTaskId, isStreaming, messages } = useChatStore();

  return (
    <div className="border-b border-vscode-border p-2 bg-vscode-bg flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-vscode-fg">AlphaPilot Chat</span>
        {isStreaming && (
          <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded animate-pulse">
            AI 思考中...
          </span>
        )}
      </div>

      <div className="flex items-center gap-1">
        {/* 清空对话 */}
        <button
          onClick={clearChat}
          disabled={messages.length === 0 || isStreaming}
          title="清空对话"
          className="px-2 py-1 text-xs hover:bg-vscode-list-hover rounded disabled:opacity-50 disabled:cursor-not-allowed"
        >
          🗑️ 清空
        </button>

        {/* 停止任务 */}
        {currentTaskId && isStreaming && (
          <button
            onClick={() => cancelTask(currentTaskId)}
            title="停止任务"
            className="px-2 py-1 text-xs hover:bg-red-500/20 text-red-400 rounded"
          >
            ⏹️ 停止
          </button>
        )}
      </div>
    </div>
  );
};
