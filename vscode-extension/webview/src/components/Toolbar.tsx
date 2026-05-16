// src/components/Toolbar.tsx
import React from 'react';
import { useChatStore } from '../store/chatStore';
import { clearChat, cancelTask } from '../utils/vscode';

interface ToolbarProps {
  showStepPanel: boolean;
  setShowStepPanel: (show: boolean) => void;
}

export const Toolbar: React.FC<ToolbarProps> = ({ showStepPanel, setShowStepPanel }) => {
  const { currentTaskId, isStreaming, messages } = useChatStore();

  return (
    <div className="border-b border-vscode-border p-3 bg-gradient-to-r from-vscode-bg to-vscode-list-hover/50 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">🚀</span>
          <span className="text-sm font-semibold text-vscode-fg">AlphaPilot Chat</span>
        </div>
        {isStreaming && (
          <span className="text-xs px-3 py-1 bg-blue-500/20 text-blue-400 rounded-full animate-pulse flex items-center gap-2">
            <span className="w-2 h-2 bg-blue-400 rounded-full"></span>
            AI 思考中...
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {/* ⭐ v3.2 新增：步骤面板切换按钮 */}
        <button
          onClick={() => setShowStepPanel(!showStepPanel)}
          disabled={messages.length === 0}
          title="显示/隐藏步骤面板"
          className={`px-3 py-1.5 text-xs rounded-lg transition-all flex items-center gap-2 ${
            showStepPanel 
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/50' 
              : 'hover:bg-vscode-list-hover text-vscode-fg-muted hover:text-vscode-fg'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          <span>📊</span>
          <span>步骤</span>
        </button>

        {/* 清空对话 */}
        <button
          onClick={clearChat}
          disabled={messages.length === 0 || isStreaming}
          title="清空对话"
          className="px-3 py-1.5 text-xs hover:bg-vscode-list-hover rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
        >
          <span>🗑️</span>
          <span>清空</span>
        </button>

        {/* 停止任务 */}
        {currentTaskId && isStreaming && (
          <button
            onClick={() => cancelTask(currentTaskId)}
            title="停止任务"
            className="px-3 py-1.5 text-xs hover:bg-red-500/20 text-red-400 rounded-lg transition-all flex items-center gap-2"
          >
            <span>⏹️</span>
            <span>停止</span>
          </button>
        )}
      </div>
    </div>
  );
};
